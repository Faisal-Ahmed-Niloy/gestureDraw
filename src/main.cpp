#include <WiFi.h>
#include <WebSocketsServer.h>
#include <TFT_eSPI.h>
#include <ArduinoJson.h>


const char* ssid     = "ssid";
const char* password = "pass";

WebSocketsServer webSocket = WebSocketsServer(81);
TFT_eSPI tft = TFT_eSPI();


#define SCREEN_W      320
#define SCREEN_H      240
#define HEADER_HEIGHT  28
#define DRAW_X          0
#define DRAW_Y    HEADER_HEIGHT
#define DRAW_W    SCREEN_W
#define DRAW_H    (SCREEN_H - HEADER_HEIGHT)

//must match Python COORD_W / COORD_H
#define SRC_W  640
#define SRC_H  480


#define HEADER_COLOR  0x001F   // deep blue
#define BORDER_COLOR  TFT_WHITE
#define DRAW_COLOR    TFT_WHITE


bool wifiConnected   = false;
bool wsClientConnected = false;

void drawUI(const String& ip = "") {
  tft.fillScreen(TFT_BLACK);

  // Header bar
  tft.fillRect(0, 0, SCREEN_W, HEADER_HEIGHT, HEADER_COLOR);

  tft.setTextFont(2);
  tft.setTextColor(TFT_WHITE, HEADER_COLOR);
  tft.setTextDatum(TL_DATUM);

  String title = "Gesture Draw";
  if (ip.length() > 0) {
    title += "|";
    title += ip;
  }
  tft.drawString(title, 5, 6);


  tft.drawRect(DRAW_X, DRAW_Y, DRAW_W, DRAW_H, BORDER_COLOR);
}


void updateStatus() {
  tft.setTextFont(1);
  tft.setTextColor(TFT_WHITE, HEADER_COLOR);
  tft.setTextDatum(TR_DATUM);

  tft.fillRect(224, 0, SCREEN_W - 224, HEADER_HEIGHT, HEADER_COLOR);

  String status = "WiFi:";
  status += (wifiConnected    ? "OK " : "-- ");
  status += "WS:";
  status += (wsClientConnected ? "OK"  : "--");

  tft.drawString(status, SCREEN_W - 5, 4);
}


void drawFromJSON(const String& payload) {
  DynamicJsonDocument doc(16384);

  DeserializationError err = deserializeJson(doc, payload);
  if (err) {
    Serial.print("[JSON] Parse error: ");
    Serial.println(err.c_str());
    Serial.print("[JSON] Payload length: ");
    Serial.println(payload.length());
    return;
  }

  const char* cmd = doc["cmd"];
  if (!cmd) {
    Serial.println("[JSON] Missing 'cmd' field");
    return;
  }


  if (strcmp(cmd, "clear") == 0) {
    // Wipe only the drawing area, leave the header intact
    tft.fillRect(DRAW_X + 1, DRAW_Y + 1, DRAW_W - 2, DRAW_H - 2, TFT_BLACK);
    Serial.println("[CMD] clear");
    return;
  }


  if (strcmp(cmd, "draw") == 0) {
    JsonArray pts = doc["points"];
    if (pts.isNull()) {
      Serial.println("[JSON] 'points' array missing");
      return;
    }

    int prev_sx = -1, prev_sy = -1;
    int drawn   = 0;

    for (JsonArray p : pts) {
      if (p.size() < 2) continue;

      int raw_x = p[0];
      int raw_y = p[1];

      // Map from Python coordinate space → display drawing area
      int sx = map(raw_x, 0, SRC_W, DRAW_X + 1, DRAW_X + DRAW_W - 1);
      int sy = map(raw_y, 0, SRC_H, DRAW_Y + 1, DRAW_Y + DRAW_H - 1);

      // Clamp to drawing area (skip points outside)
      if (sx < DRAW_X + 1 || sx > DRAW_X + DRAW_W - 2) continue;
      if (sy < DRAW_Y + 1 || sy > DRAW_Y + DRAW_H - 2) continue;

      if (prev_sx != -1) {
        tft.drawLine(prev_sx, prev_sy, sx, sy, DRAW_COLOR);
        drawn++;
      }

      prev_sx = sx;
      prev_sy = sy;
    }

    Serial.print("[CMD] draw — segments: ");
    Serial.println(drawn);
    return;
  }

  Serial.print("[JSON] Unknown cmd: ");
  Serial.println(cmd);
}


void webSocketEvent(uint8_t num, WStype_t type,
                    uint8_t* payload, size_t length) {
  switch (type) {

    case WStype_CONNECTED:
      wsClientConnected = true;
      updateStatus();
      Serial.print("[WS] Client connected, num=");
      Serial.println(num);
      break;

    case WStype_DISCONNECTED:
      wsClientConnected = false;
      updateStatus();
      Serial.print("[WS] Client disconnected, num=");
      Serial.println(num);
      break;

    case WStype_TEXT:
      drawFromJSON(String((char*)payload));
      break;

    case WStype_ERROR:
      Serial.print("[WS] Error, num=");
      Serial.println(num);
      break;

    default:
      break;
  }
}


void setup() {
  Serial.begin(115200);
  delay(200);

  tft.init();
  tft.setRotation(1);   
  drawUI();             

  Serial.print("Connecting to WiFi");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(400);
    Serial.print(".");
  }
  wifiConnected = true;
  Serial.println("\n[WiFi] Connected!");
  Serial.print("[WiFi] IP: ");
  Serial.println(WiFi.localIP());

  drawUI(WiFi.localIP().toString());
  updateStatus();

  
  webSocket.begin();
  webSocket.onEvent(webSocketEvent);
  Serial.println("[WS] Server started on port 81");
}

void loop() {
  webSocket.loop();
}