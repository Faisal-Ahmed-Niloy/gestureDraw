import cv2
import mediapipe as mp
import websocket
import json
import time

# ================= CONFIG =================
ESP32_IP = "192.168.1.100"   # 🔴 CHANGE THIS
WS_URL = f"ws://{ESP32_IP}:81/"

MAX_POINTS = 500
SMOOTHING = 0.7
GESTURE_HOLD_TIME = 0.5  # seconds

# ==========================================

ws = websocket.WebSocket()
ws.connect(WS_URL)

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1)

cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

canvas = None
points = []
recording = False

prev_x, prev_y = -1, -1

# Gesture timers
start_time = 0
stop_time = 0
erase_time = 0


# ----------- GESTURE FUNCTIONS -----------

def is_start_gesture(hand):
    # Thumb up
    return hand.landmark[4].y < hand.landmark[3].y

def is_stop_gesture(hand):
    # Index down
    return hand.landmark[8].y > hand.landmark[6].y

def is_erase_gesture(hand):
    # Middle finger up
    return hand.landmark[12].y < hand.landmark[10].y


# ========================================

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape

    if canvas is None:
        canvas = frame.copy() * 0

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = hands.process(rgb)

    current_time = time.time()

    if result.multi_hand_landmarks:
        for hand_landmarks in result.multi_hand_landmarks:

            lm = hand_landmarks.landmark[8]
            x = int(lm.x * w)
            y = int(lm.y * h)

            # -------- SMOOTHING --------
            if prev_x != -1:
                x = int(SMOOTHING * prev_x + (1 - SMOOTHING) * x)
                y = int(SMOOTHING * prev_y + (1 - SMOOTHING) * y)

            # -------- START GESTURE --------
            if is_start_gesture(hand_landmarks):
                if start_time == 0:
                    start_time = current_time
                elif current_time - start_time > GESTURE_HOLD_TIME:
                    recording = True
                    points = []
                    prev_x, prev_y = -1, -1
            else:
                start_time = 0

            # -------- STOP GESTURE --------
            if is_stop_gesture(hand_landmarks):
                if stop_time == 0:
                    stop_time = current_time
                elif current_time - stop_time > GESTURE_HOLD_TIME:
                    recording = False

                    if len(points) > 0:
                        msg = {
                            "cmd": "draw",
                            "points": points
                        }
                        ws.send(json.dumps(msg))

            else:
                stop_time = 0

            # -------- ERASE GESTURE --------
            if is_erase_gesture(hand_landmarks):
                if erase_time == 0:
                    erase_time = current_time
                elif current_time - erase_time > GESTURE_HOLD_TIME:
                    canvas[:] = 0
                    ws.send(json.dumps({"cmd": "clear"}))
            else:
                erase_time = 0

            # -------- DRAWING --------
            if recording:
                points.append([x, y])

                # Downsample if too many points
                if len(points) > MAX_POINTS:
                    points = points[::2]

                if prev_x != -1:
                    cv2.line(canvas, (prev_x, prev_y), (x, y), (255, 255, 255), 3)

                prev_x, prev_y = x, y

            cv2.circle(frame, (x, y), 5, (0, 255, 0), -1)

    # -------- DISPLAY --------
    combined = cv2.addWeighted(frame, 0.7, canvas, 0.3, 0)
    cv2.imshow("Gesture Drawing (Hybrid)", combined)

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
ws.close()
cv2.destroyAllWindows()