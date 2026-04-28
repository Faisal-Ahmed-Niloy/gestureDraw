import asyncio
import base64
import json
import threading
import time
import cv2
import numpy as np
import websockets

from display_server_2 import DrawingApp, ESP32_IP, _get_ip

BRIDGE_HOST      = "localhost"
BRIDGE_PORT      = 8765
FRAME_SEND_EVERY = 1        # send every N camera frames (1 = all frames)
JPEG_QUALITY     = 60       # 0-100 — lower = smaller payload, faster


_clients     : set  = set()
_clients_lock       = threading.Lock()
_loop        : asyncio.AbstractEventLoop | None = None   # set when server starts


def _broadcast(msg: dict):
    """Thread-safe broadcast to all connected browser clients."""
    if not _clients or _loop is None:
        return
    raw = json.dumps(msg)
    with _clients_lock:
        targets = list(_clients)

    async def _send_all():
        dead = []
        for ws in targets:
            try:
                await ws.send(raw)
            except Exception:
                dead.append(ws)
        if dead:
            with _clients_lock:
                for ws in dead:
                    _clients.discard(ws)

    asyncio.run_coroutine_threadsafe(_send_all(), _loop)


# websoc-server
async def _handler(websocket):
    print(f"[Bridge] Browser connected from {websocket.remote_address}")
    with _clients_lock:
        _clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        with _clients_lock:
            _clients.discard(websocket)
        print("[Bridge] Browser disconnected")


def _start_server_thread():
    """Run the asyncio WS server in its own thread."""
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    async def _serve():
        async with websockets.serve(_handler, BRIDGE_HOST, BRIDGE_PORT):
            print(f"[Bridge] WS server running on ws://{BRIDGE_HOST}:{BRIDGE_PORT}")
            await asyncio.Future()   # run forever

    _loop.run_until_complete(_serve())


#drawingapp with web bridge
class WebDrawingApp(DrawingApp):

    def __init__(self, esp32_ip: str):
        super().__init__(esp32_ip)
        self._frame_counter = 0

    
    def run(self):
        print("\n[WebApp] Running with Web UI bridge.")
        print(f"  Open index.html or file:///D:/IIOT-Professional-Project/HandGestureCar_OpenCV/index.html \n")

        while True:
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.03)
                continue

            frame = cv2.flip(frame, 1)
            gesture, tip_px, frame = self._detector.process(frame)
            self._handle(gesture, tip_px)
            self._draw_hud(frame, gesture, tip_px)

            
            self._frame_counter += 1
            if self._frame_counter % FRAME_SEND_EVERY == 0:
                self._send_frame(frame)

            
            self._send_status(gesture)

            #local OpenCV preview
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

        self._cleanup()

    
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
        
        for m in msgs:
            if m.get("cmd") == "draw":
                _broadcast({"type": "draw", "points": m["points"]})

        self._sender.submit(msgs, self._debug)

    
    def _do_clear(self):
        self._buffer.clear()
        self._canvas[:] = 0
        self._sender.submit([{"cmd": "clear"}], self._debug)
        self._set_status("Cleared.")
        _broadcast({"type": "clear"})

    
    def _send_frame(self, frame: np.ndarray):
        """JPEG-encode the annotated camera frame and broadcast it."""
        ok, buf = cv2.imencode(
            '.jpg', frame,
            [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
        )
        if not ok:
            return
        b64 = base64.b64encode(buf.tobytes()).decode('ascii')
        _broadcast({"type": "frame", "data": b64})

    def _send_status(self, gesture: str):
        """Broadcast current app state so the UI stays in sync."""
        _broadcast({
            "type":         "status",
            "gesture":      gesture,
            "sender_busy":  self._sender.busy,
            "sender_ok":    self._sender.last_ok,
            "ws_connected": self._sender.connected,
            "esp_ip":       _get_ip() if self._sender.connected else "",
            "strokes":      self._buffer.stroke_count,
            "pts":          self._buffer.point_count,
        })



if __name__ == "__main__":
    # 1 - start bridge WS server in bg
    srv_thread = threading.Thread(target=_start_server_thread, daemon=True)
    srv_thread.start()
    time.sleep(0.5) #binding time

    # 2- run the patched drawing app until pressed Q
    ip  = _get_ip()
    app = WebDrawingApp(ip)
    app.run()