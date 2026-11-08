#include <Arduino.h>
#include <WiFi.h>

extern "C" {
  #include "esp_wifi.h"
  #include "esp_wifi_types.h"
  #include "esp_ping.h"
  #include "ping/ping_sock.h"
  #include "lwip/inet.h"
  #include "lwip/netdb.h"
  #include "lwip/sockets.h"
}

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

// ═══════════════════════════════════════════════════════════════
//  USER CONFIG — edit these, flash once, then control via Serial
// ═══════════════════════════════════════════════════════════════
#if __has_include("wifi_config.h")
#include "wifi_config.h"
#else
#include "wifi_config.example.h"
#endif

// Target packets per second (10-20 is ideal for localization)
// The ping task sends this many ICMP pings/sec to the router,
// each ping triggers a CSI report back from the AP.
static const uint32_t TARGET_PACKETS_PER_SEC = 10;

// How many CSI rows to collect per position before auto-stopping
static const uint32_t TARGET_ROWS_PER_CAPTURE = 1500;

// Filter to only capture CSI from the connected AP
static const bool FILTER_TO_CONNECTED_AP = true;
// ═══════════════════════════════════════════════════════════════


// ─── Internal state ───
static uint8_t g_connected_bssid[6] = {0};
static bool    g_have_bssid = false;
static ip_addr_t g_router_ip;

// Queue payload
static const int MAX_CSI_BYTES = 256;
typedef struct {
  uint32_t ts_ms;
  int8_t   rssi;
  uint8_t  chan;
  uint8_t  mac[6];
  uint16_t len;
  int8_t   data[MAX_CSI_BYTES];
} CsiFrame;

static QueueHandle_t g_csi_queue = nullptr;

// Session control
static volatile bool g_capture_active = false;
static uint32_t g_capture_start_ms    = 0;
static uint32_t g_rows_captured       = 0;
static uint32_t g_rows_target         = TARGET_ROWS_PER_CAPTURE;
static uint32_t g_total_csi_seen      = 0;

// Ping handle
static esp_ping_handle_t g_ping_handle = nullptr;
static volatile bool g_ping_running = false;

// Scenario metadata (set via serial commands)
static String g_scenario_id  = "S00";
static String g_position_id  = "P00";
static String g_description  = "";

// Serial input buffer
static String g_serial_buf = "";

// ─── Helpers ───

static void mac_to_str(const uint8_t mac[6], char* out, size_t out_sz) {
  snprintf(out, out_sz, "%02X:%02X:%02X:%02X:%02X:%02X",
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

// ─── Ping callbacks (we don't need the results, just triggering CSI) ───

static void ping_success_cb(esp_ping_handle_t hdl, void *args) {
  // intentionally empty — we only care about the CSI side-effect
}

static void ping_timeout_cb(esp_ping_handle_t hdl, void *args) {
  // intentionally empty
}

static void ping_end_cb(esp_ping_handle_t hdl, void *args) {
  // intentionally empty
}

// ─── Ping task: sends continuous ICMP pings to router ───

static void start_ping() {
  if (g_ping_running) return;

  esp_ping_config_t ping_config = ESP_PING_DEFAULT_CONFIG();
  ping_config.target_addr = g_router_ip;
  ping_config.count       = 0;  // infinite pings
  // Interval in ms between pings
  ping_config.interval_ms = 1000 / TARGET_PACKETS_PER_SEC;
  ping_config.timeout_ms  = 1000;
  ping_config.data_size   = 32;

  esp_ping_callbacks_t cbs = {};
  cbs.on_ping_success = ping_success_cb;
  cbs.on_ping_timeout = ping_timeout_cb;
  cbs.on_ping_end     = ping_end_cb;

  esp_err_t err = esp_ping_new_session(&ping_config, &cbs, &g_ping_handle);
  if (err != ESP_OK) {
    Serial.printf("[ERROR] Failed to create ping session: %s\n", esp_err_to_name(err));
    return;
  }

  err = esp_ping_start(g_ping_handle);
  if (err != ESP_OK) {
    Serial.printf("[ERROR] Failed to start ping: %s\n", esp_err_to_name(err));
    esp_ping_delete_session(g_ping_handle);
    g_ping_handle = nullptr;
    return;
  }

  g_ping_running = true;
  Serial.printf("[PING] Pinging router at %d pkt/s to generate CSI traffic\n",
                TARGET_PACKETS_PER_SEC);
}

static void stop_ping() {
  if (!g_ping_running || !g_ping_handle) return;
  esp_ping_stop(g_ping_handle);
  esp_ping_delete_session(g_ping_handle);
  g_ping_handle = nullptr;
  g_ping_running = false;
}

// ─── CSI callback: enqueue every frame while capture is active ───

static void IRAM_ATTR csi_rx_cb(void *ctx, wifi_csi_info_t *info) {
  (void)ctx;
  if (!info || !info->buf || info->len == 0) return;

  g_total_csi_seen++;

  if (FILTER_TO_CONNECTED_AP && g_have_bssid) {
    if (memcmp(info->mac, g_connected_bssid, 6) != 0) return;
  }

  if (!g_capture_active) return;
  if (!g_csi_queue) return;

  CsiFrame frame;
  frame.ts_ms = (uint32_t)millis();
  frame.rssi  = (int8_t)info->rx_ctrl.rssi;
  frame.chan   = (uint8_t)info->rx_ctrl.channel;
  memcpy(frame.mac, info->mac, 6);

  uint16_t L = (uint16_t)info->len;
  if (L > MAX_CSI_BYTES) L = MAX_CSI_BYTES;
  frame.len = L;
  memcpy(frame.data, info->buf, L);

  BaseType_t hpTaskWoken = pdFALSE;
  xQueueSendFromISR(g_csi_queue, &frame, &hpTaskWoken);
  if (hpTaskWoken) portYIELD_FROM_ISR();
}

// ─── WiFi + CSI init ───

static void setup_wifi_and_csi() {
  WiFi.mode(WIFI_MODE_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WIFI] Connecting to %s ", WIFI_SSID);

  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) {
    delay(200);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WIFI] Connected! IP: %s\n", WiFi.localIP().toString().c_str());

    // Get router IP for pinging
    ip_addr_set_zero(&g_router_ip);
    g_router_ip.type = IPADDR_TYPE_V4;
    g_router_ip.u_addr.ip4.addr = (uint32_t)WiFi.gatewayIP();
    Serial.printf("[WIFI] Router/gateway: %s\n", WiFi.gatewayIP().toString().c_str());

    // Get BSSID
    wifi_ap_record_t ap;
    if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) {
      memcpy(g_connected_bssid, ap.bssid, 6);
      g_have_bssid = true;
      char bssid_str[18];
      mac_to_str(g_connected_bssid, bssid_str, sizeof(bssid_str));
      Serial.printf("[WIFI] BSSID: %s  Channel: %d\n", bssid_str, ap.primary);
    }
  } else {
    Serial.println("[WARN] WiFi not connected! Pinging won't work.");
    Serial.println("[WARN] CSI will only capture from background traffic (very slow).");
  }

  // Enable promiscuous + CSI
  wifi_promiscuous_filter_t filt = {};
  filt.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT | WIFI_PROMIS_FILTER_MASK_DATA;
  esp_wifi_set_promiscuous_filter(&filt);

  wifi_csi_config_t csi_config = {};
  csi_config.lltf_en           = true;
  csi_config.htltf_en          = true;
  csi_config.stbc_htltf2_en    = true;
  csi_config.ltf_merge_en      = true;
  csi_config.channel_filter_en = true;
  csi_config.manu_scale        = true;
  csi_config.shift             = 0;

  ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_config));
  ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(csi_rx_cb, nullptr));
  ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
  ESP_ERROR_CHECK(esp_wifi_set_csi(true));

  Serial.println("[CSI] CSI capture engine ready.");
}

// ─── Capture session control ───

static void start_capture() {
  // Clear any stale frames in queue
  CsiFrame dummy;
  while (xQueueReceive(g_csi_queue, &dummy, 0) == pdTRUE) {}

  g_rows_captured    = 0;
  g_capture_start_ms = millis();
  g_capture_active   = true;

  // Start pinging to generate CSI traffic
  start_ping();

  // Print CSV header
  Serial.println("---CSV_START---");
  Serial.printf("# scenario=%s, position=%s, description=%s\n",
                g_scenario_id.c_str(), g_position_id.c_str(), g_description.c_str());
  Serial.printf("# target_rows=%u, target_rate=%u_pkt_per_sec\n",
                g_rows_target, TARGET_PACKETS_PER_SEC);
  Serial.println("ts_ms,rssi,chan,mac,csi_len,csi_raw");
}

static void stop_capture(const char* reason) {
  g_capture_active = false;
  stop_ping();

  uint32_t elapsed_ms = millis() - g_capture_start_ms;
  float elapsed_s = elapsed_ms / 1000.0f;
  float actual_rate = (elapsed_s > 0) ? (g_rows_captured / elapsed_s) : 0;

  Serial.println("---CSV_END---");
  Serial.printf("[DONE] %s | rows=%u, time=%.1fs, rate=%.1f pkt/s\n",
                reason, g_rows_captured, elapsed_s, actual_rate);
  Serial.printf("[DONE] Scenario=%s Position=%s\n",
                g_scenario_id.c_str(), g_position_id.c_str());
  Serial.println("[READY] Send 'start' for next capture or set new position.");
}

// ─── Serial command handler ───

static void print_help() {
  Serial.println();
  Serial.println("╔══════════════════════════════════════════════════════════╗");
  Serial.println("║         ESP32 CSI Data Collection Tool v2.0             ║");
  Serial.println("╠══════════════════════════════════════════════════════════╣");
  Serial.println("║ COMMANDS:                                               ║");
  Serial.println("║   scenario S07    — set scenario ID (e.g. S01-S26)      ║");
  Serial.println("║   position P03    — set position ID (e.g. P01-P13)      ║");
  Serial.println("║   desc 1wall_LOS  — set description text                ║");
  Serial.println("║   rows 1500       — set target rows (default 1500)      ║");
  Serial.println("║   start           — begin capture for current position   ║");
  Serial.println("║   stop            — manually stop capture early          ║");
  Serial.println("║   status          — show current settings + CSI stats    ║");
  Serial.println("║   help            — show this menu                       ║");
  Serial.println("╠══════════════════════════════════════════════════════════╣");
  Serial.println("║ WORKFLOW:                                                ║");
  Serial.println("║   1. Set scenario + position + desc                      ║");
  Serial.println("║   2. Person takes position, stands still 5s              ║");
  Serial.println("║   3. Send 'start' — capture runs until target rows       ║");
  Serial.println("║   4. Copy CSV from serial output                         ║");
  Serial.println("║   5. Change position, repeat from step 2                 ║");
  Serial.println("╚══════════════════════════════════════════════════════════╝");
  Serial.println();
}

static void print_status() {
  Serial.println();
  Serial.println("─── Current Status ───");
  Serial.printf("  Scenario:    %s\n", g_scenario_id.c_str());
  Serial.printf("  Position:    %s\n", g_position_id.c_str());
  Serial.printf("  Description: %s\n", g_description.length() > 0 ? g_description.c_str() : "(none)");
  Serial.printf("  Target rows: %u\n", g_rows_target);
  Serial.printf("  Target rate: %u pkt/s\n", TARGET_PACKETS_PER_SEC);
  Serial.printf("  Capturing:   %s\n", g_capture_active ? "YES" : "no");
  if (g_capture_active) {
    float elapsed = (millis() - g_capture_start_ms) / 1000.0f;
    float pct = (g_rows_target > 0) ? (100.0f * g_rows_captured / g_rows_target) : 0;
    Serial.printf("  Progress:    %u / %u (%.0f%%) in %.1fs\n",
                  g_rows_captured, g_rows_target, pct, elapsed);
  }
  Serial.printf("  WiFi:        %s\n", WiFi.status() == WL_CONNECTED ? "connected" : "DISCONNECTED");
  Serial.printf("  Ping active: %s\n", g_ping_running ? "yes" : "no");
  Serial.printf("  Total CSI frames seen (all time): %u\n", g_total_csi_seen);
  Serial.println("──────────────────────");
  Serial.println();
}

static void handle_command(const String& cmd) {
  String c = cmd;
  c.trim();
  if (c.length() == 0) return;

  if (c == "help" || c == "h" || c == "?") {
    print_help();
  }
  else if (c == "status" || c == "s") {
    print_status();
  }
  else if (c == "start") {
    if (g_capture_active) {
      Serial.println("[WARN] Capture already running! Send 'stop' first.");
    } else {
      Serial.printf("[START] Capturing %s / %s ...\n",
                    g_scenario_id.c_str(), g_position_id.c_str());
      start_capture();
    }
  }
  else if (c == "stop") {
    if (g_capture_active) {
      stop_capture("Manual stop");
    } else {
      Serial.println("[INFO] No capture running.");
    }
  }
  else if (c.startsWith("scenario ") || c.startsWith("sc ")) {
    String val = c.substring(c.indexOf(' ') + 1);
    val.trim();
    g_scenario_id = val;
    Serial.printf("[SET] Scenario = %s\n", g_scenario_id.c_str());
  }
  else if (c.startsWith("position ") || c.startsWith("pos ")) {
    String val = c.substring(c.indexOf(' ') + 1);
    val.trim();
    g_position_id = val;
    Serial.printf("[SET] Position = %s\n", g_position_id.c_str());
  }
  else if (c.startsWith("desc ")) {
    String val = c.substring(5);
    val.trim();
    g_description = val;
    Serial.printf("[SET] Description = %s\n", g_description.c_str());
  }
  else if (c.startsWith("rows ")) {
    String val = c.substring(5);
    val.trim();
    uint32_t r = val.toInt();
    if (r > 0 && r <= 50000) {
      g_rows_target = r;
      Serial.printf("[SET] Target rows = %u\n", g_rows_target);
    } else {
      Serial.println("[ERROR] Rows must be 1-50000.");
    }
  }
  else if (c == "next" || c == "n") {
    // Quick shortcut: increment position number and start
    // Extract number from position ID like "P03"
    int num = 0;
    for (int i = 0; i < (int)g_position_id.length(); i++) {
      if (isDigit(g_position_id[i])) {
        num = g_position_id.substring(i).toInt();
        break;
      }
    }
    num++;
    char buf[16];
    snprintf(buf, sizeof(buf), "P%02d", num);
    g_position_id = String(buf);
    Serial.printf("[NEXT] Position = %s — send 'start' when person is ready\n",
                  g_position_id.c_str());
  }
  else {
    Serial.printf("[ERROR] Unknown command: '%s' — type 'help'\n", c.c_str());
  }
}

// ─── Arduino entry points ───

void setup() {
  Serial.begin(115200);
  delay(1000);

  g_csi_queue = xQueueCreate(128, sizeof(CsiFrame));
  if (!g_csi_queue) {
    Serial.println("[FATAL] Failed to create CSI queue!");
    while (true) delay(1000);
  }

  setup_wifi_and_csi();
  print_help();
  print_status();
}

void loop() {
  // ── Handle serial commands ──
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (g_serial_buf.length() > 0) {
        handle_command(g_serial_buf);
        g_serial_buf = "";
      }
    } else {
      g_serial_buf += c;
    }
  }

  // ── Drain CSI queue and output CSV rows ──
  if (g_capture_active) {
    CsiFrame frame;
    while (xQueueReceive(g_csi_queue, &frame, 0) == pdTRUE) {
      char macbuf[18];
      mac_to_str(frame.mac, macbuf, sizeof(macbuf));

      // Print CSV row: ts_ms,rssi,chan,mac,csi_len,csi_raw
      Serial.print(frame.ts_ms);    Serial.print(',');
      Serial.print((int)frame.rssi); Serial.print(',');
      Serial.print((int)frame.chan); Serial.print(',');
      Serial.print(macbuf);          Serial.print(',');
      Serial.print((int)frame.len);  Serial.print(',');

      for (uint16_t i = 0; i < frame.len; i++) {
        Serial.print((int)frame.data[i]);
        if (i + 1 < frame.len) Serial.print(' ');
      }
      Serial.println();

      g_rows_captured++;

      // Progress indicator every 100 rows
      if (g_rows_captured % 100 == 0) {
        float elapsed = (millis() - g_capture_start_ms) / 1000.0f;
        float pct = (g_rows_target > 0) ? (100.0f * g_rows_captured / g_rows_target) : 0;
        Serial.printf("# [PROGRESS] %u / %u (%.0f%%) — %.1fs elapsed\n",
                      g_rows_captured, g_rows_target, pct, elapsed);
      }

      // Auto-stop when target reached
      if (g_rows_captured >= g_rows_target) {
        stop_capture("Target reached");
        break;
      }
    }
  }

  delay(1);
}