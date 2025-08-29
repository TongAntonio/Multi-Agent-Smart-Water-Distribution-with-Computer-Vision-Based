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

// Wi-Fi
const char* ssid     = "Room74-2.4G";
const char* password = "Adam@1989";

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


// สร้างหน้า HTML แสดงลิงก์ไฟล์
void handleFileList() {
  String html = "<!DOCTYPE html><html><head>"
                "<meta charset='UTF-8'><title>Gallery</title>"
                "</head><body><h1>SD-CAM Gallery</h1>";
  File root = SD_MMC.open("/");
  File file = root.openNextFile();
  while (file) {
    if (!file.isDirectory()) {
      String name = file.name();               // "/photo0.jpg"
      html += "<div><a href=\"";
      html += name;
      html += "\">";
      html += name.substring(1);               // "photo0.jpg"
      html += "</a></div>\n";
    }
    file = root.openNextFile();
  }
  html += "</body></html>";
  server.send(200, "text/html", html);
}

// ถ้า URL ไม่ตรง route ไหน ให้ตรวจว่าเป็นไฟล์บน SD หรือไม่
void handleNotFound(){
  String path = server.uri();              // เช่น "/photo0.jpg"
  if (SD_MMC.exists(path)) {
    File file = SD_MMC.open(path);
    server.streamFile(file, "image/jpeg");
    file.close();
  } else {
    server.send(404, "text/plain", "Not found");
  }
}

void setup(){
  Serial.begin(115200);
  delay(1000);

  // Init camera
  if (esp_camera_init(&camera_config) != ESP_OK) {
    Serial.println("Camera init failed");
    while(true) delay(1000);
  }

  // Init SD
  if (!SD_MMC.begin("/sdcard", true)) {
    Serial.println("SD_MMC init failed");
    while(true) delay(1000);
  }

  // Connect Wi-Fi
  WiFi.begin(ssid, password);
  Serial.print("Connecting WiFi");
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 10000) {
    Serial.print(".");
    delay(500);
  }
  Serial.println();
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  // Setup HTTP routes
  server.on("/", HTTP_GET, handleFileList);
  server.onNotFound(handleNotFound);

  server.begin();
  Serial.println("Web server started");
}

void loop(){
  server.handleClient();

  // ถ้าอยากให้พิมพ์ "take" ทาง Serial → ถ่าย + เซฟ SD
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    if (cmd.equalsIgnoreCase("take")) {
      camera_fb_t* fb = esp_camera_fb_get();
      if (fb) {
        String path = "/photo" + String(millis()) + ".jpg";
        File f = SD_MMC.open(path, FILE_WRITE);
        if (f) {
          f.write(fb->buf, fb->len);
          f.close();
          Serial.printf("Saved %s\n", path.c_str());
        }
        esp_camera_fb_return(fb);
      }
    }
  }
}
