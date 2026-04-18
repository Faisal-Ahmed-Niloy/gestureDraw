#include <WiFi.h>
#include <WebSocketsServer.h>
#include <TFT_eSPI.h>
#include <ArduinoJson.h>

// ================= WIFI =================
const char* ssid = "Faisal";
const char* password = "Faisal-123";

// ========================================

WebSocketsServer webSocket = WebSocketsServer(81);
TFT_eSPI tft = TFT_eSPI();

// -------- SCREEN CONFIG --------
#define SCREEN_W 320
#define SCREEN_H 240
#define HEADER_HEIGHT 28

#define DRAW_X 0
#define DRAW_Y HEADER_HEIGHT
#define DRAW_W SCREEN_W
#define DRAW_H (SCREEN_H - HEADER_HEIGHT)

// -------- COLORS --------
#define HEADER_COLOR 0x001F   // Deep Blue
#define BORDER_COLOR TFT_WHITE

// -------- STATUS FLAGS --------
bool wifiConnected = false;
bool wsClientConnected = false;

// ================= UI =================

void drawUI() {
  tft.fillScreen(TFT_BLACK);

  // HEADER
  tft.fillRect(0, 0, SCREEN_W, HEADER_HEIGHT, HEADER_COLOR);

  // TITLE (LEFT)
  tft.setTextFont(2);
  tft.setTextColor(TFT_WHITE, HEADER_COLOR);
  tft.setTextDatum(TL_DATUM);
  tft.drawString("Gesture Drawing", 5, 6);

  // DRAWING AREA BORDER
  tft.drawRect(DRAW_X, DRAW_Y, DRAW_W, DRAW_H, BORDER_COLOR);
}

// ================= STATUS =================

void updateStatus() {
  tft.setTextFont(2);
  tft.setTextColor(TFT_WHITE, HEADER_COLOR);
  tft.setTextDatum(TR_DATUM);

  // Clear right header area properly
  tft.fillRect(SCREEN_W/2, 0, SCREEN_W/2, HEADER_HEIGHT, HEADER_COLOR);

  String status = "";
  status += "WiFi:";
  status += (wifiConnected ? "OK " : "-- ");
  status += "WS:";
  status += (wsClientConnected ? "OK" : "--");

  // Draw text aligned to top-right corner
  tft.drawString(status, SCREEN_W - 5, 4);
}


// ================= DRAWING =================

void drawFromJSON(String payload) {
  StaticJsonDocument<8192> doc;

  if (deserializeJson(doc, payload)) {
    Serial.println("JSON Error");
    return;
  }

  const char* cmd = doc["cmd"];

  // -------- CLEAR SCREEN --------
  if (strcmp(cmd, "clear") == 0) {
    tft.fillRect(DRAW_X + 1, DRAW_Y + 1, DRAW_W - 2, DRAW_H - 2, TFT_BLACK);
    return;
  }

  // -------- DRAW LINES --------
  if (strcmp(cmd, "draw") == 0) {
    JsonArray pts = doc["points"];

    int prev_x = -1, prev_y = -1;

    for (JsonArray p : pts) {
      int x = p[0];
      int y = p[1];

      int sx = map(x, 0, 640, DRAW_X, DRAW_W);
      int sy = map(y, 0, 480, DRAW_Y, DRAW_Y + DRAW_H);

      if (sx < DRAW_X || sx > DRAW_W || sy < DRAW_Y || sy > DRAW_Y + DRAW_H)
        continue;

      if (prev_x != -1) {
        tft.drawLine(prev_x, prev_y, sx, sy, TFT_WHITE);
      }

      prev_x = sx;
      prev_y = sy;
    }
  }
}

// ================= WEBSOCKET =================

void webSocketEvent(uint8_t num, WStype_t type, uint8_t * payload, size_t length) {

  switch (type) {

    case WStype_CONNECTED:
      wsClientConnected = true;
      updateStatus();
      break;

    case WStype_DISCONNECTED:
      wsClientConnected = false;
      updateStatus();
      break;

    case WStype_TEXT:
      drawFromJSON(String((char*)payload));
      break;
  }
}

// ================= SETUP =================

void setup() {
  Serial.begin(115200);

  tft.init();
  tft.setRotation(1);

  drawUI();

  // -------- WIFI --------
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(400);
    Serial.print(".");
  }

  wifiConnected = true;

  Serial.println("\nWiFi Connected!");
  Serial.println(WiFi.localIP());

  updateStatus();

  // -------- WEBSOCKET --------
  webSocket.begin();
  webSocket.onEvent(webSocketEvent);
}

// ================= LOOP =================

void loop() {
  webSocket.loop();
}