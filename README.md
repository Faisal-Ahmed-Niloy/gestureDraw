# ✋ Gesture Drawing System (ESP32 + Computer Vision)

Real-time gesture-controlled drawing system using Python (computer vision) and ESP32 with WebSocket communication. Hand movements captured via webcam are processed and sent over WiFi to an ESP32, which renders drawings on an ILI9341 TFT display.

---

## 🚀 Features

- Real-time hand tracking (OpenCV + MediaPipe)
- Gesture-based drawing control (start / stop / clear)
- WebSocket communication
- Live drawing on ESP32 TFT display
- Simple UI with WiFi + connection status

---

## 🧠 System Architecture

Camera → Python (Hand Tracking) → WebSocket → ESP32 → ILI9341 Display

---

## 🛠️ Requirements

### Hardware
- ESP32 DevKit V1
- ILI9341 TFT Display
- USB cable
- PC with webcam
- WiFi network (same for ESP32 and PC)

---

### Software

#### Python (PC Side)
Install dependencies:
```bash
pip install opencv-python mediapipe numpy websocket-client
ESP32 (PlatformIO)

Install libraries via platformio.ini:

lib_deps =
  bblanchon/ArduinoJson
  links2004/WebSockets
  bodmer/TFT_eSPI


⚙️ ESP32 Setup
Open project in VS Code (PlatformIO)
Set WiFi credentials in main.cpp:
const char* ssid = "YOUR_WIFI";
const char* password = "YOUR_PASSWORD";
Configure TFT pins in User_Setup.h (ILI9341)
Build and upload firmware
Open Serial Monitor to get ESP32 IP address


🐍 Python Setup

Run gesture tracking client:

python gesture_client.py
What it does:
Captures webcam frames
Detects hand landmarks
Extracts fingertip coordinates
Sends data to ESP32 via WebSocket


📡 WebSocket Format
Draw Data
{
  "cmd": "draw",
  "points": [[x1,y1],[x2,y2],[x3,y3]]
}
Clear Screen
{
  "cmd": "clear"
}


✋ Gesture Controls
Gesture	Action
Open hand	Start drawing
Finger movement	Draw path
Stop gesture	Pause drawing
Clear gesture	Reset screen


📺 ESP32 UI
Top-left: Gesture Drawing title
Top-right: WiFi + WebSocket status
Main area: Drawing canvas


📌 Notes
ESP32 and PC must be on the same network
Default WebSocket port: 81
Use ESP32 IP in Python script
Lower camera resolution improves performance