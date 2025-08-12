#include <WiFi.h>
#include "esp_camera.h"
#include "FS.h"
#include "SD_MMC.h"
#include <WebServer.h>

//-------------------------
// กำหนดขา ESP32-CAM AI-Thinker
//-------------------------
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

//-------------------------
// ข้อมูล Wi-Fi
//-------------------------
const char* ssid     = "Room74-2.4G";
const char* password = "Adam@1989";

// ตั้งเวลา timeout รอบการเชื่อมต่อ (มิลลิวินาที)
const unsigned long WIFI_TIMEOUT_MS = 10000;
// เพิ่มตัวนับชื่อไฟล์รูป
int photoNumber = 0;
//-------------------------
// HTTP server บนพอร์ต 80
//-------------------------
WebServer server(80);

//-------------------------
// Camera configuration
//-------------------------
camera_config_t camera_config = {
  .pin_pwdn       = PWDN_GPIO_NUM,
  .pin_reset      = RESET_GPIO_NUM,
  .pin_xclk       = XCLK_GPIO_NUM,
  .pin_sccb_sda   = SIOD_GPIO_NUM,
  .pin_sccb_scl   = SIOC_GPIO_NUM,
  .pin_d7         = Y9_GPIO_NUM,
  .pin_d6         = Y8_GPIO_NUM,
  .pin_d5         = Y7_GPIO_NUM,
  .pin_d4         = Y6_GPIO_NUM,
  .pin_d3         = Y5_GPIO_NUM,
  .pin_d2         = Y4_GPIO_NUM,
  .pin_d1         = Y3_GPIO_NUM,
  .pin_d0         = Y2_GPIO_NUM,
  .pin_vsync      = VSYNC_GPIO_NUM,
  .pin_href       = HREF_GPIO_NUM,
  .pin_pclk       = PCLK_GPIO_NUM,
  .xclk_freq_hz   = 20000000,
  .ledc_timer     = LEDC_TIMER_0,
  .ledc_channel   = LEDC_CHANNEL_0,
  .pixel_format   = PIXFORMAT_JPEG,
  .frame_size     = FRAMESIZE_VGA,
  .jpeg_quality   = 12,
  .fb_count       = 1
};

//-------------------------
// ฟังก์ชันจับภาพและส่งกลับ
//-------------------------
void handleCapture() {
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    server.send(500, "text/plain", "Capture failed");
    return;
  }

  // ส่ง HTTP headers ก่อน แล้วโฟลว์บัฟเฟอร์ภาพ
  server.sendHeader("Content-Type", "image/jpeg");
  server.sendHeader("Content-Length", String(fb->len));
  server.send(200);

  WiFiClient &client = server.client();
  client.write(fb->buf, fb->len);

  esp_camera_fb_return(fb);
}

//-------------------------
// เริ่มต้นกล้อง
//-------------------------
bool initCamera() {
  esp_err_t err = esp_camera_init(&camera_config);
  if (err != ESP_OK) {
    Serial.printf("Camera init error 0x%x\n", err);
    return false;
  }
  Serial.println("Camera initialized");
  return true;
}

// ฟังก์ชันช่วยเชื่อมต่อ WiFi พร้อมรายงานสถานะและ timeout
bool connectWiFi(unsigned long timeoutMs = WIFI_TIMEOUT_MS) {
  Serial.printf("Connecting to '%s'…\n", ssid);
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > timeoutMs) {
      Serial.printf(
        "\nTimeout after %lums, status=%d\n\n",
        timeoutMs,
        WiFi.status()
      );
      return false;
    }
    delay(200);
    Serial.print(".");
  }

  Serial.printf("\nConnected! IP: %s\n\n", WiFi.localIP().toString().c_str());
  return true;
}

//-------------------------
// mount SD_MMC
//-------------------------
bool initSD() {
  if (!SD_MMC.begin("/sdcard", true)) {
    Serial.println("SD_MMC mount failed");
    return false;
  }
  uint64_t size = SD_MMC.cardSize() / (1024 * 1024);
  Serial.printf("SD_MMC mounted, size: %lluMB\n", size);
  return true;
}

// ฟังก์ชันสแกนหา WiFi รอบๆ (เลือกใช้หรือไม่ก็ได้)
void scanNetworks() {
  Serial.println("\nScanning for WiFi networks...");
  int n = WiFi.scanNetworks();
  if (n == 0) {
    Serial.println("  No networks found");
  } else {
    for (int i = 0; i < n; i++) {
      Serial.printf(
        "  %2d: %s (%d dBm) [%s]\n",
        i + 1,
        WiFi.SSID(i).c_str(),
        WiFi.RSSI(i),
        (WiFi.encryptionType(i) == WIFI_AUTH_OPEN ? "Open" : "Encrypted")
      );
    }
  }
  WiFi.scanDelete();
  Serial.println();
}

// ฟังก์ชันถ่ายภาพและเซฟลง SD_MMC
void takePhoto() {
  camera_fb_t * fb = esp_camera_fb_get();  
  if (!fb) {
    Serial.println("Camera capture failed");
    return;
  }

  // สร้างชื่อไฟล์แบบ photo0.jpg, photo1.jpg, …
  String path = "/photo" + String(photoNumber++) + ".jpg";
  fs::FS &fs = SD_MMC;
  File file = fs.open(path.c_str(), FILE_WRITE);

  if (!file) {
    Serial.println("Failed to open file in writing mode");
  } else {
    file.write(fb->buf, fb->len);   // เขียนบัฟเฟอร์ภาพลงไฟล์
    Serial.printf("Saved file to: %s\n", path.c_str());
    file.close();
  }

  esp_camera_fb_return(fb);  // คืนบัฟเฟอร์กลับให้กล้อง
}

//-------------------------
// setup()
//-------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("___IMAGE COLLECTION SERVER___");

  if (!initCamera()) {
    Serial.println("Camera init failed → Halt");
    while (true) delay(1000);
  }
  delay(10);

 // สแกน WiFi รอบๆ (ไม่บังคับ ใช้ debug ช่วงแรก)
  scanNetworks();

  if (!connectWiFi()) {
    Serial.println("WiFi connect failed → Halt");
    while (true) delay(1000);
  }
  delay(10);

  if (!initSD()) {
    Serial.println("SD_MMC init failed → Halt");
    while (true) delay(1000);
  }
  delay(10);

  server.on("/capture", HTTP_GET, handleCapture);
  server.begin();
  Serial.println("HTTP server started");
}

//-------------------------
// loop()
//-------------------------
void loop() {
  server.handleClient();
  delay(1);
  
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "take") {
      Serial.println("Capturing image...");
      takePhoto();  // ฟังก์ชันถ่ายภาพแล้วเซฟลง SD
    }
  }
}
