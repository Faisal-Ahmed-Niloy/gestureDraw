"""
GESTURE MAP
───────────────────────────────────────────────────────────
  ☝  Index only          →  DRAW
  ✌  Index + Middle (V)  →  SEND
  🖐  4-5 fingers open    →  CLEAR
  ✊  Anything else       →  IDLE


KEYBOARD SHORTCUTS (preview window)
───────────────────────────────────────────────────────────
  Q  =  Quit
  C  =  Force-send drawing to ESP32  (same as V-sign)
  X  =  Force-clear ESP32 + canvas
  S  =  Toggle per-message debug log
  U  =  Undo last stroke

"""

import cv2
import mediapipe as mp
import websocket
import json
import time
import threading
import numpy as np
from collections import deque
import queue


ESP32_IP          = "xx.xxx.xxx.xx"   # change this ESP32's IP
WS_PORT           = 81

COORD_W           = 640     # coordinate space the firmware maps from
COORD_H           = 480

CAMERA_INDEX      = 0
MIN_MOVE_PX       = 5       # dead-zone to suppress jitter

# ── webSoc tuning ───
RECONNECT_DELAY_S  = 2.0
INTER_MSG_DELAY_S  = 0.12
                         
CONNECT_TIMEOUT_S  = 6

MAX_PTS_PER_MSG   = 120


G_DRAW  = "DRAW"
G_SEND  = "SEND"
G_CLEAR = "CLEAR"
G_IDLE  = "IDLE"

G_COLOR = {
    G_DRAW:  (0,  230,  60),
    G_SEND:  (0,  200, 255),
    G_CLEAR: (0,   60, 230),
    G_IDLE:  (160, 160, 160),
}


class PersistentSender:
    """
    Maintains a single long-lived WebSocket connection to the ESP32.
    Messages are queued and dispatched by a background worker thread.
    Auto-reconnects on drop with exponential back-off.

    This avoids the connect→send→close→reconnect loop that caused the
    ESP32 display to flicker/blank with the links2004 WebSocket library.
    """

    def __init__(self, url: str):
        self._url      = url
        self._q        = queue.Queue()   # queue of (messages_list, debug_flag)
        self._ws       = None
        self._lock     = threading.Lock()
        self._busy     = False
        self.last_ok   = True
        self.connected = False
        self._stop     = False

        # Start background worker
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    # pub API
    def submit(self, messages: list, debug: bool = False):
        """Non-blocking: queue messages for delivery."""
        if self._busy:
            print("[SENDER] Still busy with previous job — skipped.")
            return
        self._q.put((messages, debug))

    @property
    def busy(self) -> bool:
        return self._busy

    def stop(self):
        self._stop = True
        self._q.put(None)   # unblock worker

    # bg worker ──
    def _worker(self):
        while not self._stop:
            # Ensure connection is alive
            if not self._is_connected():
                self._reconnect()
                if not self._is_connected():
                    # failed to connect - drain queue to avoid stale jobs piling up
                    try:
                        self._q.get_nowait()
                        self._q.task_done()
                    except queue.Empty:
                        pass
                    time.sleep(RECONNECT_DELAY_S)
                    continue

            # wait for job
            try:
                job = self._q.get(timeout=1.0)
            except queue.Empty:
                continue

            if job is None:   # stop signal
                break

            messages, debug = job
            self._busy = True
            ok = self._send_all(messages, debug)
            self.last_ok = ok
            if ok:
                print(f"[SENDER] ✓ {len(messages)} message(s) sent.")
            else:
                print("[SENDER] ✗ Send failed — will reconnect.")
            self._busy = False
            self._q.task_done()

    def _is_connected(self) -> bool:
        with self._lock:
            if self._ws is None:
                return False
            try:
                # Ping to verify connection is still alive
                self._ws.ping()
                return True
            except Exception:
                self._ws = None
                self.connected = False
                return False

    def _reconnect(self):
        print(f"[SENDER] Connecting to {self._url} …")
        with self._lock:
            try:
                ws = websocket.create_connection(
                    self._url,
                    timeout              = CONNECT_TIMEOUT_S,
                    skip_utf8_validation = True,
                )
                self._ws       = ws
                self.connected = True
                print("[SENDER] Connected ✓")
                # ESP32 time to complete its WS handshake
                time.sleep(0.4)
            except Exception as e:
                self._ws       = None
                self.connected = False
                print(f"[SENDER] Connect failed: {e}")

    def _send_all(self, messages: list, debug: bool) -> bool:
        for i, msg in enumerate(messages):
            with self._lock:
                ws = self._ws
            if ws is None:
                return False
            try:
                raw = json.dumps(msg, separators=(",", ":"))
                ws.send(raw)
                if debug:
                    pts = len(msg.get("points", []))
                    print(f"[WS] msg {i+1}/{len(messages)} "
                          f"cmd={msg.get('cmd')} pts={pts}")
                # Inter-message breathing room so ESP32 can render
                if i < len(messages) - 1:
                    time.sleep(INTER_MSG_DELAY_S)
            except Exception as e:
                print(f"[SENDER] Send error on msg {i+1}: {e}")
                with self._lock:
                    self._ws       = None
                    self.connected = False
                return False
        return True



class GestureDetector:
    _TIPS = [4,  8,  12, 16, 20]
    _PIPS = [3,  6,  10, 14, 18]

    def __init__(self):
        mp_h = mp.solutions.hands
        self._hands = mp_h.Hands(
            static_image_mode        = False,
            max_num_hands            = 1,
            min_detection_confidence = 0.72,
            min_tracking_confidence  = 0.72,
        )
        self._mp_hands = mp_h
        md = mp.solutions.drawing_utils
        self._draw_pt = md.DrawingSpec(color=(0, 255, 120), thickness=2, circle_radius=3)
        self._draw_ln = md.DrawingSpec(color=(255, 100, 0),  thickness=2)
        self._mp_draw = md

    def process(self, bgr):
        rgb     = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        results = self._hands.process(rgb)
        gesture = G_IDLE
        tip_px  = None

        if results.multi_hand_landmarks:
            lm   = results.multi_hand_landmarks[0]
            h, w = bgr.shape[:2]
            self._mp_draw.draw_landmarks(
                bgr, lm, self._mp_hands.HAND_CONNECTIONS,
                self._draw_pt, self._draw_ln,
            )
            fu     = self._fingers_up(lm)
            tip_px = (int(lm.landmark[8].x * w), int(lm.landmark[8].y * h))
            gesture = self._classify(fu)

        return gesture, tip_px, bgr

    def _fingers_up(self, lm):
        up = []
        for i, (tip, pip) in enumerate(zip(self._TIPS, self._PIPS)):
            if i == 0:
                wx = lm.landmark[0].x
                up.append(abs(lm.landmark[tip].x - wx) > abs(lm.landmark[pip].x - wx))
            else:
                up.append(lm.landmark[tip].y < lm.landmark[pip].y)
        return up

    def _classify(self, fu):
        _, idx, mid, ring, pinky = fu
        total = sum(fu)
        if total >= 4:
            return G_CLEAR
        if idx and mid and not ring and not pinky:
            return G_SEND
        if idx and not mid and not ring and not pinky:
            return G_DRAW
        return G_IDLE

    def release(self):
        self._hands.close()


class StrokeBuffer:
    def __init__(self):
        self._strokes    = []
        self._current    = []
        self._last_pt    = None
        self._smooth_buf = deque(maxlen=6)

    def add_point(self, pt: tuple):
        self._smooth_buf.append(pt)
        sx = int(round(np.mean([p[0] for p in self._smooth_buf])))
        sy = int(round(np.mean([p[1] for p in self._smooth_buf])))
        smooth = (sx, sy)

        if self._last_pt is None:
            self._last_pt = smooth
            self._current.append(list(smooth))
            return None

        dx = smooth[0] - self._last_pt[0]
        dy = smooth[1] - self._last_pt[1]
        if dx * dx + dy * dy < MIN_MOVE_PX * MIN_MOVE_PX:
            return None

        prev = self._last_pt
        self._last_pt = smooth
        self._current.append(list(smooth))
        return (prev, smooth)

    def end_stroke(self):
        if len(self._current) >= 2:
            self._strokes.append(self._current)
        self._current  = []
        self._last_pt  = None
        self._smooth_buf.clear()

    def cancel_stroke(self):
        self._current  = []
        self._last_pt  = None
        self._smooth_buf.clear()

    def undo(self):
        if self._strokes:
            self._strokes.pop()

    def clear(self):
        self._strokes = []
        self._current = []
        self._last_pt = None
        self._smooth_buf.clear()

    def build_messages(self) -> list:
        """
        Chunk all strokes into draw messages that fit inside the ESP32
        StaticJsonDocument<16384>. MAX_PTS_PER_MSG is set conservatively
        so the firmware never hits a deserialise error.
        Consecutive chunks share one overlap point so lines stay continuous.
        """
        messages = []
        for stroke in self._strokes:
            pts = stroke
            i   = 0
            while i < len(pts):
                chunk = pts[i : i + MAX_PTS_PER_MSG]
                if len(chunk) >= 2:
                    messages.append({"cmd": "draw", "points": chunk})
                i += MAX_PTS_PER_MSG - 1   # 1-point overlap for continuity
        return messages

    @property
    def has_strokes(self) -> bool:
        return bool(self._strokes)

    @property
    def stroke_count(self) -> int:
        return len(self._strokes)

    @property
    def point_count(self) -> int:
        return sum(len(s) for s in self._strokes)




class DrawingApp:
    _FONT = cv2.FONT_HERSHEY_SIMPLEX

    def __init__(self, esp32_ip: str):
        url            = f"ws://{esp32_ip}:{WS_PORT}"
        self._sender   = PersistentSender(url)
        self._detector = GestureDetector()
        self._buffer   = StrokeBuffer()
        self._cap      = self._open_cam()
        self._debug    = False

        self._drawing        = False
        self._send_latch     = False
        self._clear_latch    = False
        self._clear_rearmed  = True

        self._canvas = np.zeros((COORD_H, COORD_W, 3), dtype=np.uint8)

        self._status_msg = "Ready — waiting for connection…"
        self._status_t   = time.time()
        self._status_ok  = True


    def _open_cam(self):
        cap = cv2.VideoCapture(CAMERA_INDEX)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  COORD_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, COORD_H)
        cap.set(cv2.CAP_PROP_FPS,          30)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera {CAMERA_INDEX}")
        return cap


    def _set_status(self, msg: str, ok: bool = True):
        self._status_msg = msg
        self._status_t   = time.time()
        self._status_ok  = ok
        print(f"[APP] {msg}")


    def _redraw_canvas(self):
        self._canvas[:] = 0
        for stroke in self._buffer._strokes:
            for i in range(1, len(stroke)):
                p1 = tuple(stroke[i - 1])
                p2 = tuple(stroke[i])
                cv2.line(self._canvas, p1, p2, (255, 255, 255), 2, cv2.LINE_AA)


    def _do_send(self):
        if not self._buffer.has_strokes:
            self._set_status("Nothing to send.", ok=False)
            return
        if self._sender.busy:
            self._set_status("Still sending — wait…", ok=False)
            return
        msgs = self._buffer.build_messages()
        self._set_status(
            f"Sending {self._buffer.stroke_count} stroke(s) / "
            f"{self._buffer.point_count} pts in {len(msgs)} msg(s)…"
        )
        self._sender.submit(msgs, self._debug)

    def _do_clear(self):
        self._buffer.clear()
        self._canvas[:] = 0
        self._sender.submit([{"cmd": "clear"}], self._debug)
        self._set_status("Cleared.")


    def _handle(self, gesture: str, tip_px):
        if gesture == G_DRAW:
            self._send_latch    = False
            self._clear_rearmed = True
            self._clear_latch   = False

            if tip_px:
                result = self._buffer.add_point(tip_px)
                if result:
                    cv2.line(self._canvas, result[0], result[1],
                             (255, 255, 255), 2, cv2.LINE_AA)
            self._drawing = True
            return

        if self._drawing:
            self._buffer.end_stroke()
            self._drawing = False

        if gesture == G_SEND:
            if not self._send_latch:
                self._do_send()
                self._send_latch = True
            return
        self._send_latch = False

        if gesture == G_CLEAR:
            if self._clear_rearmed and not self._clear_latch:
                self._do_clear()
                self._clear_latch   = True
                self._clear_rearmed = False
            return

        self._buffer.cancel_stroke()


    def _draw_hud(self, frame, gesture, tip_px):
        h, w = frame.shape[:2]
        gc   = G_COLOR[gesture]

        cv2.putText(frame, f"Gesture: {gesture}",
                    (10, 30), self._FONT, 0.75, gc, 2, cv2.LINE_AA)

        cv2.putText(frame,
                    f"Strokes: {self._buffer.stroke_count}  "
                    f"Pts: {self._buffer.point_count}",
                    (10, 56), self._FONT, 0.52, (200, 200, 200), 1, cv2.LINE_AA)

        if not self._sender.connected:
            s_col, s_txt = (0, 80, 230),  "DISCONNECTED"
        elif self._sender.busy:
            s_col, s_txt = (0, 200, 255), "SENDING…"
        elif not self._sender.last_ok:
            s_col, s_txt = (0, 80, 230),  "SEND FAILED"
        else:
            s_col, s_txt = (0, 200, 80),  "Connected"
        cv2.putText(frame, f"WS: {s_txt}",
                    (10, 78), self._FONT, 0.52, s_col, 1, cv2.LINE_AA)

        arm_col = (0, 200, 80) if self._clear_rearmed else (0, 140, 220)
        arm_txt = "CLEAR: ready" if self._clear_rearmed else "CLEAR: draw first"
        cv2.putText(frame, arm_txt,
                    (10, 100), self._FONT, 0.45, arm_col, 1, cv2.LINE_AA)

        if time.time() - self._status_t < 3.0:
            b_col = (0, 210, 80) if self._status_ok else (0, 80, 220)
            cv2.putText(frame, self._status_msg,
                        (10, h - 36), self._FONT, 0.5, b_col, 1, cv2.LINE_AA)

        legends = [
            ("☝ DRAW",        G_COLOR[G_DRAW]),
            ("✌ SEND",        G_COLOR[G_SEND]),
            ("🖐 CLEAR",       G_COLOR[G_CLEAR]),
            ("Q/C/X/U/S keys", (160, 160, 160)),
        ]
        x = 6
        for txt, col in legends:
            cv2.putText(frame, txt, (x, h - 12),
                        self._FONT, 0.38, col, 1, cv2.LINE_AA)
            x += w // len(legends)

        if self._debug:
            cv2.putText(frame, "[DBG]", (w - 70, 28),
                        self._FONT, 0.5, (0, 200, 255), 1, cv2.LINE_AA)

        if tip_px:
            cv2.circle(frame, tip_px, 14, gc, 2, cv2.LINE_AA)
            cv2.circle(frame, tip_px,  4, gc, -1, cv2.LINE_AA)


    def run(self):
        print("\n[APP] Ready.")
        print("  ☝ Index  = draw on PC canvas")
        print("  ✌ V-sign = send drawing to ESP32")
        print("  🖐 Palm   = clear everything")
        print("  Keys: Q=quit  C=send  X=clear  U=undo  S=debug\n")

        while True:
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.03)
                continue

            frame = cv2.flip(frame, 1)
            gesture, tip_px, frame = self._detector.process(frame)
            self._handle(gesture, tip_px)
            self._draw_hud(frame, gesture, tip_px)

            cv2.imshow("Gesture Camera", frame)
            cv2.imshow("PC Canvas  (ESP32 mirror)", self._canvas)

            key = cv2.waitKey(1) & 0xFF
            if   key == ord('q'):
                break
            elif key == ord('c'):
                self._do_send()
            elif key == ord('x'):
                self._do_clear()
                self._clear_rearmed = True
            elif key == ord('u'):
                self._buffer.undo()
                self._redraw_canvas()
                self._set_status("Undo.")
            elif key == ord('s'):
                self._debug = not self._debug
                print(f"[APP] Debug: {'ON' if self._debug else 'OFF'}")

        self._cleanup()

    def _cleanup(self):
        print("\n[APP] Shutting down…")
        self._sender.stop()
        self._cap.release()
        self._detector.release()
        cv2.destroyAllWindows()
        print("[APP] Bye.")


def _get_ip() -> str:
    if ESP32_IP.strip():
        return ESP32_IP.strip()
    print("Find the IP in Serial Monitor after 'WiFi Connected!'\n")
    ip = input("Enter ESP32 IP address: ").strip()
    if not ip:
        raise ValueError("No IP address entered.")
    return ip


if __name__ == "__main__":
    app = DrawingApp(_get_ip())
    app.run()