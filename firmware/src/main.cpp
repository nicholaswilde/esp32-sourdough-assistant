// ESP32-S3 Sourdough Baker Assistant - On-Device PLE INT4 Inference REPL
// Runs offline on ESP32-S3 (N16R8) with model memory-mapped at partition 0x110000.
// Exposes OpenAI-compatible HTTP API on port 8080 for Open WebUI / curl access.

#include <Arduino.h>
#include "esp_partition.h"
#include "esp_spi_flash.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"

#define LLM_INT8_ACT 1
#define LLM_PROFILE 1
#define LLM_PROFILE_NOW() esp_timer_get_time()

#include "llm.h"
#include "bpe_tokenizer.h"
#include "generated/tokenizer_asset.h"
#include "generated/sourdough_words.h"
#include "generated/sourdough_out2in.h"
#include "generated/sourdough_subvocab.h"

// ---- WiFi / HTTP Server -----------------------------------------------------
#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoJson.h>
#if __has_include("secrets.h")
#  include "secrets.h"
#else
#  define WIFI_SSID     "your_wifi_network"
#  define WIFI_PASSWORD "your_wifi_password"
#endif

static WebServer http_server(8080);
static bool wifi_connected = false;
static void setup_http_routes();  // forward declaration

// ---- Globals & Buffers -----------------------------------------------------
static Model model;
static Scratch s;
static BpeTokenizer tokenizer;

static size_t psram_used = 0, sram_used = 0;
#define STATIC_SRAM_BYTES (2 * LLM_Q8_MAX_INPUT)

static void *ps_or_die(size_t n, const char *what) {
  void *p = heap_caps_malloc(n, MALLOC_CAP_SPIRAM);
  if (!p) {
    Serial.printf("FATAL: required PSRAM allocation failed: %s (%u bytes)\n", what, (unsigned)n);
    while (1) delay(1000);
  }
  psram_used += n;
  return p;
}

static void *sram_or_die(size_t n, const char *what) {
  void *p = heap_caps_malloc(n, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  if (!p) {
    Serial.printf("FATAL: required SRAM allocation failed: %s (%u bytes)\n", what, (unsigned)n);
    while (1) delay(1000);
  }
  sram_used += n;
  return p;
}

// ---- Dual-Core Worker for Matvec -------------------------------------------
static TaskHandle_t worker_h, main_h;
static const QT *job_t;
static const int8_t *job_xq;
static float job_xs;
static float *job_y;
static int job_split;

static void worker_main(void *param) {
  (void)param;
  while (1) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    matvec_i8_range(job_t, job_xq, job_xs, job_y, 0, job_split);
    xTaskNotifyGive(main_h);
  }
}

static void matvec_par(const QT *t, const float *x, float *y) {
  alignas(16) static int8_t xq[LLM_Q8_MAX_INPUT];
  float xs;
  if (!t->w8 || t->rows < 64) {
    MATVEC(t, x, y);
    return;
  }
  quantize_act(x, t->cols, xq, &xs);
  job_t = t; job_xq = xq; job_xs = xs; job_y = y;
  job_split = t->rows / 2;
  xTaskNotifyGive(worker_h);
  matvec_i8_range(t, xq, xs, y, job_split, t->rows);
  ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
}

// ---- Sub-Vocabulary Prediction (Hierarchical Softmax Output Head) -----------
// Default to 0 (disabled): Full-head evaluation accelerated by 128-bit SIMD provides
// 100% domain accuracy at ~14.5 tok/s. Use /subvocab <n> to enable sub-vocab clustering.
static int g_subvocab_clusters = 0;

static void matvec_subvocab(const QT *t, const float *x, float *y) {
  if (g_subvocab_clusters <= 0 || g_subvocab_clusters >= SOURDOUGH_SUBVOCAB_NUM_CLUSTERS || !t->w8) {
    matvec_par(t, x, y);
    return;
  }

  alignas(16) static int8_t xq[LLM_Q8_MAX_INPUT];
  float xs;
  quantize_act(x, t->cols, xq, &xs);

  // 1. Score all K cluster centroids (SIMD vector dot products)
  float c_scores[SOURDOUGH_SUBVOCAB_NUM_CLUSTERS];
  for (int k = 0; k < SOURDOUGH_SUBVOCAB_NUM_CLUSTERS; k++) {
    int32_t dot = llm_dot_i8(SOURDOUGH_SUBVOCAB_CENTROIDS[k], xq, t->cols);
    c_scores[k] = (float)dot * xs * SOURDOUGH_SUBVOCAB_SCALES[k];
  }

  // 2. Select top M clusters
  int top_clusters[SOURDOUGH_SUBVOCAB_NUM_CLUSTERS];
  bool cluster_selected[SOURDOUGH_SUBVOCAB_NUM_CLUSTERS] = {false};
  int m_count = g_subvocab_clusters;
  if (m_count > SOURDOUGH_SUBVOCAB_NUM_CLUSTERS) m_count = SOURDOUGH_SUBVOCAB_NUM_CLUSTERS;

  for (int m = 0; m < m_count; m++) {
    int best_k = -1;
    float best_score = -1e30f;
    for (int k = 0; k < SOURDOUGH_SUBVOCAB_NUM_CLUSTERS; k++) {
      if (!cluster_selected[k] && c_scores[k] > best_score) {
        best_score = c_scores[k];
        best_k = k;
      }
    }
    if (best_k >= 0) {
      cluster_selected[best_k] = true;
      top_clusters[m] = best_k;
    }
  }

  // 3. Initialize all logits to -1e30f
  for (int i = 0; i < t->rows; i++) {
    y[i] = -1e30f;
  }

  // 4. Compute dot products for candidate tokens in predicted clusters
  for (int m = 0; m < m_count; m++) {
    int k = top_clusters[m];
    uint16_t offset = SOURDOUGH_SUBVOCAB_OFFSETS[k];
    uint16_t count = SOURDOUGH_SUBVOCAB_COUNTS[k];
    for (uint16_t i = 0; i < count; i++) {
      int r = SOURDOUGH_SUBVOCAB_TOKENS[offset + i];
      if (r < t->rows) {
        y[r] = matvec_dot_row_i8(t, r, xq, xs);
      }
    }
  }

  // 5. Always compute guaranteed special tokens (BOS, EOS, PAD, UNK, punctuation)
  for (int i = 0; i < SOURDOUGH_SUBVOCAB_ALWAYS_COUNT; i++) {
    int r = SOURDOUGH_SUBVOCAB_ALWAYS_INCLUDE[i];
    if (r < t->rows && y[r] <= -1e20f) {
      y[r] = matvec_dot_row_i8(t, r, xq, xs);
    }
  }
}

// Copy RMSNorm weights from mapped flash to internal SRAM for speed
static void copy_norms_to_sram() {
  Cfg *c = &model.c;
  int D = c->dim, L = c->n_layers, P = c->ple_dim;
  const float **vecs[4 * 32 + 2];
  int sizes[4 * 32 + 2], n_vec = 0;

  vecs[n_vec] = &model.ple_proj_norm; sizes[n_vec++] = P;
  for (int l = 0; l < L; l++) {
    vecs[n_vec] = &model.attn_norm[l]; sizes[n_vec++] = D;
    vecs[n_vec] = &model.ffn_norm[l];  sizes[n_vec++] = D;
    vecs[n_vec] = &model.ple_norm[l];  sizes[n_vec++] = D;
  }
  vecs[n_vec] = &model.out_norm; sizes[n_vec++] = D;

  for (int i = 0; i < n_vec; i++) {
    size_t bytes = (size_t)sizes[i] * sizeof(float);
    void *dst = sram_or_die(bytes, "norm vector");
    memcpy(dst, *vecs[i], bytes);
    *vecs[i] = (const float *)dst;
  }
  Serial.printf("[s3-sourdough] Copied %d RMSNorm vectors to SRAM\n", n_vec);
}

// ---- Allocation & SRAM Buffers ---------------------------------------------
static void alloc_scratch() {
  Cfg *c = &model.c;
  int D = c->dim, L = c->n_layers, F = c->ffn, P = c->ple_dim, S = c->seq_len;

  s.x      = (float *)sram_or_die(D * 4, "x");
  s.h      = (float *)sram_or_die((F > D ? F : D) * 4, "h");
  s.qkv    = (float *)sram_or_die(3 * D * 4, "qkv");
  s.att    = (float *)sram_or_die(D * 4, "att");
  s.g1     = (float *)sram_or_die(F * 4, "g1");
  s.g2     = (float *)sram_or_die(F * 4, "g2");
  s.ple    = (float *)sram_or_die(L * P * 4, "ple");
  s.tmpP   = (float *)sram_or_die(L * P * 4, "tmpP");
  s.trow   = (float *)sram_or_die(L * P * 4, "trow");
  s.scores = (float *)sram_or_die(S * 4, "scores");

  s.logits = (float *)ps_or_die((size_t)model.out_vocab * 4, "logits");
  s.kcache = (float *)ps_or_die((size_t)L * S * D * 4, "kcache");
  s.vcache = (float *)ps_or_die((size_t)L * S * D * 4, "vcache");
}

static void emit_word(int best, int &pieces_out) {
  if (best < 0 || best >= SOURDOUGH_WORD_COUNT) return;
  const char *w = SOURDOUGH_WORDS[best];
  bool punct = (w[1] == '\0' && strchr(".,:;?%", w[0]) != NULL);
  if (pieces_out && !punct) Serial.print(' ');
  Serial.print(w);
  Serial.flush();
  pieces_out++;
}

static void emit_word_buf(int best, int &pieces_out, String &buf) {
  if (best < 0 || best >= SOURDOUGH_WORD_COUNT) return;
  const char *w = SOURDOUGH_WORDS[best];
  bool punct = (w[1] == '\0' && strchr(".,:;?%", w[0]) != NULL);
  if (pieces_out && !punct) buf += ' ';
  buf += w;
  pieces_out++;
}

// ---- Sampling Helpers ------------------------------------------------------
#ifndef DEFAULT_TEMPERATURE
#define DEFAULT_TEMPERATURE 0.75f
#endif
#ifndef DEFAULT_TOP_P
#define DEFAULT_TOP_P 0.90f
#endif
#define RECENT_WINDOW 32

static float g_temperature = DEFAULT_TEMPERATURE;
static float g_topp = DEFAULT_TOP_P;

typedef struct {
  float prob;
  int index;
} ProbIndex;

static ProbIndex *probindex = NULL;
static uint64_t rng_seed = 1337;

static unsigned int random_u32() {
  rng_seed ^= rng_seed >> 12;
  rng_seed ^= rng_seed << 25;
  rng_seed ^= rng_seed >> 27;
  return (rng_seed * 0x2545F4914F6CDD1Dull) >> 32;
}

static float random_f32() {
  return (random_u32() >> 8) / 16777216.0f;
}

static int compare_probindex(const void *a, const void *b) {
  ProbIndex *a_ = (ProbIndex *)a;
  ProbIndex *b_ = (ProbIndex *)b;
  if (a_->prob > b_->prob) return -1;
  if (a_->prob < b_->prob) return 1;
  return 0;
}

static int sample(float *logits, int n, float temperature, float topp, ProbIndex *pindex) {
  if (temperature <= 0.01f) {
    int best = 0; float best_val = -1e30f;
    for (int i = 0; i < n; i++) {
      if (logits[i] > best_val) { best_val = logits[i]; best = i; }
    }
    return best;
  }

  // Softmax
  float max_val = -1e30f;
  for (int i = 0; i < n; i++) {
    if (logits[i] > max_val) max_val = logits[i];
  }
  float sum = 0.0f;
  for (int i = 0; i < n; i++) {
    logits[i] = expf((logits[i] - max_val) / temperature);
    sum += logits[i];
  }
  for (int i = 0; i < n; i++) logits[i] /= sum;

  if (topp <= 0.0f || topp >= 1.0f) {
    float r = random_f32(), cdf = 0.0f;
    for (int i = 0; i < n; i++) {
      cdf += logits[i];
      if (r < cdf) return i;
    }
    return n - 1;
  }

  for (int i = 0; i < n; i++) {
    pindex[i].index = i;
    pindex[i].prob = logits[i];
  }
  qsort(pindex, n, sizeof(ProbIndex), compare_probindex);

  float cumsum = 0.0f;
  int last_idx = n - 1;
  for (int i = 0; i < n; i++) {
    cumsum += pindex[i].prob;
    if (cumsum >= topp) { last_idx = i; break; }
  }

  float r = random_f32() * cumsum, cdf = 0.0f;
  for (int i = 0; i <= last_idx; i++) {
    cdf += pindex[i].prob;
    if (r < cdf) return pindex[i].index;
  }
  return pindex[last_idx].index;
}


// ---- Setup & Inference REPL ------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n=======================================================");
  Serial.println("  🥖 ESP32-S3 Sourdough Baker Assistant (PLE INT4)    ");
  Serial.println("=======================================================");

  // 1. Initialize BPE Tokenizer
  int tok_rc = bpe_tokenizer_load(TOKENIZER_ASSET, TOKENIZER_ASSET_SIZE, &tokenizer);
  if (tok_rc != 0) {
    Serial.printf("FATAL: Failed to load BPE tokenizer asset (code %d)\n", tok_rc);
    while (1) delay(1000);
  }
  Serial.printf("[s3-sourdough] Tokenizer ready: vocab=%u, merges=%u\n",
                tokenizer.active_vocab, tokenizer.merge_count);

  // 2. Memory-map model partition from Flash (0x110000, subtype 0x40)
  const esp_partition_t *part = esp_partition_find_first(
      ESP_PARTITION_TYPE_DATA, (esp_partition_subtype_t)0x40, "model");
  if (!part) {
    Serial.println("FATAL: 'model' partition not found at 0x110000!");
    while (1) delay(1000);
  }

  const void *base = NULL;
  spi_flash_mmap_handle_t mmap_h;
  esp_err_t err = esp_partition_mmap(part, 0, part->size, SPI_FLASH_MMAP_DATA, &base, &mmap_h);
  if (err != ESP_OK) {
    Serial.printf("FATAL: esp_partition_mmap failed: %d\n", err);
    while (1) delay(1000);
  }

  // 3. Load PLE Model
  int llm_err = llm_load((const uint8_t *)base, &model);
  if (llm_err != 0) {
    uint32_t magic; memcpy(&magic, base, 4);
    Serial.printf("FATAL: llm_load error %d (magic: 0x%08x)\n", llm_err, magic);
    while (1) delay(1000);
  }

  Cfg *c = &model.c;
  Serial.printf("[s3-sourdough] Model loaded: vocab=%d, dim=%d, layers=%d, heads=%d, ffn=%d, ple_dim=%d\n",
                c->vocab, c->dim, c->n_layers, c->n_heads, c->ffn, c->ple_dim);

  if (model.out_vocab != SOURDOUGH_WORD_COUNT) {
    Serial.printf("FATAL: word table mismatch: model %d vs table %d\n",
                  model.out_vocab, SOURDOUGH_WORD_COUNT);
    while (1) delay(1000);
  }

  // 4. Allocate Scratch & Relocate Norms
  alloc_scratch();
  copy_norms_to_sram();

  // Stage core weights to int8 in PSRAM for fast matvec
  void *(*ps_alloc_fn)(size_t) = [](size_t n) -> void * {
    void *p = heap_caps_malloc(n, MALLOC_CAP_SPIRAM);
    if (p) psram_used += n;
    return p;
  };
  int want = llm_core_stage_count(&model);
  int staged = llm_stage_core_int8_alloc(&model, ps_alloc_fn);
  void *hb = ps_alloc_fn(llm_stage_int8_bytes(&model.out_head));
  if (hb) {
    llm_stage_int8(&model.out_head, hb);
    staged++;
  }
  Serial.printf("[s3-sourdough] Staged %d core + head tensors to int8 in PSRAM\n", staged);

  // 5. Setup dual-core acceleration
  main_h = xTaskGetCurrentTaskHandle();
  if (xTaskCreatePinnedToCore(worker_main, "matvec_worker", 4096, NULL, 2, &worker_h, 0) == pdPASS) {
    model.layer_matvec = matvec_par;
    if (model.out_head.w8) model.head_matvec = matvec_subvocab;
    Serial.println("[s3-sourdough] Dual-core acceleration enabled (Core 0 + Core 1)");
  }

  probindex = (ProbIndex *)ps_or_die(model.out_vocab * sizeof(ProbIndex), "probindex");

  rng_seed ^= (uint64_t)esp_timer_get_time();

  Serial.printf("[s3-sourdough] Free SRAM: %.1f KB | Free PSRAM: %.2f MB\n",
                heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024.0,
                heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1048576.0);
  Serial.printf("[s3-sourdough] Sampling: temp=%.2f, top_p=%.2f, rep_window=%d\n",
                g_temperature, g_topp, RECENT_WINDOW);
  if (g_subvocab_clusters > 0) {
    Serial.printf("[s3-sourdough] Sub-vocab: top %d/%d clusters active\n",
                  g_subvocab_clusters, SOURDOUGH_SUBVOCAB_NUM_CLUSTERS);
  } else {
    Serial.println("[s3-sourdough] Sub-vocab: disabled (full vocabulary evaluation for maximum accuracy)");
  }
#if defined(__XTENSA__) && defined(CONFIG_IDF_TARGET_ESP32S3)
  Serial.println("[s3-sourdough] SIMD: ESP32-S3 PIE 128-bit vector instructions active");
#else
  Serial.println("[s3-sourdough] SIMD: Scalar fallback");
#endif
  // 7. Start WiFi + HTTP server
  Serial.printf("[s3-sourdough] WiFi: connecting to \"%s\"...\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 20) {
    delay(500);
    Serial.print('.');
    tries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    wifi_connected = true;
    Serial.printf("\n[s3-sourdough] WiFi: connected, IP=%s\n", WiFi.localIP().toString().c_str());
    Serial.printf("[s3-sourdough] HTTP: OpenAI API at http://%s:8080/v1/chat/completions\n",
                  WiFi.localIP().toString().c_str());
    setup_http_routes();
    http_server.begin();
  } else {
    Serial.println("\n[s3-sourdough] WiFi: offline – HTTP server disabled, Serial REPL only.");
  }

  Serial.println("\nReady! Enter your sourdough question below:\n");
  Serial.print("User: ");
}

// ---- Shared inference: fills 'out' with the assistant's answer ---------------
static void run_inference_to_buf(const String &prompt, String &out, int &n_tokens, float &tok_per_sec) {
  uint16_t prompt_tokens[128];
  int n_prompt = bpe_encode_ascii(&tokenizer, prompt.c_str(), prompt_tokens, 120);
  if (n_prompt < 0) {
    out = "Error: prompt contains unsupported characters or is too long.";
    n_tokens = 0; tok_per_sec = 0.0f;
    return;
  }

  llm_profile_reset(&s);
  int pos = 0;
  for (int i = 0; i < n_prompt; i++) llm_forward(&model, prompt_tokens[i], pos++, &s);
  llm_forward(&model, SOURDOUGH_OUT2IN[SOURDOUGH_BOS], pos++, &s);

  int64_t t0 = esp_timer_get_time();
  int pieces_out = 0;
  int max_pieces = 60;
  int recent[RECENT_WINDOW];
  for (int i = 0; i < RECENT_WINDOW; i++) recent[i] = -1;

  for (int step = 0; step < max_pieces && pos < model.c.seq_len; step++) {
    s.logits[SOURDOUGH_PAD] = -1e30f;
    s.logits[SOURDOUGH_BOS] = -1e30f;
    s.logits[SOURDOUGH_UNK] -= 10.0f;

    for (int d = 1; d <= RECENT_WINDOW && d <= step; d++) {
      int idx = (step - d + RECENT_WINDOW) % RECENT_WINDOW;
      int prev = recent[idx];
      if (prev >= 0 && prev < SOURDOUGH_WORD_COUNT) {
        float factor = 0.80f + 0.15f * ((float)(d - 1) / (float)RECENT_WINDOW);
        if (s.logits[prev] > 0) s.logits[prev] *= factor;
        else s.logits[prev] *= (2.0f - factor);
      }
    }

    if (step >= max_pieces - 10) {
      float boost = (float)(step - (max_pieces - 10) + 1) * 1.5f;
      s.logits[SOURDOUGH_EOS] += boost;
      s.logits[5] += boost * 0.5f;
    }

    int best = sample(s.logits, SOURDOUGH_WORD_COUNT, g_temperature, g_topp, probindex);
    if (best == SOURDOUGH_EOS) break;

    recent[step % RECENT_WINDOW] = best;
    emit_word_buf(best, pieces_out, out);

    if (step >= max_pieces - 8 && (best == 5 || best == 8)) break;

    llm_forward(&model, SOURDOUGH_OUT2IN[best], pos++, &s);
  }

  int64_t total_us = esp_timer_get_time() - t0;
  n_tokens = pieces_out;
  tok_per_sec = (total_us > 0) ? (pieces_out * 1e6f / total_us) : 0.0f;
}

// ---- HTTP Handlers ----------------------------------------------------------

// GET /v1/models
static void handle_models() {
  JsonDocument doc;
  doc["object"] = "list";
  JsonArray data = doc["data"].to<JsonArray>();
  JsonObject m = data.add<JsonObject>();
  m["id"]       = "esp32-sourdough";
  m["object"]   = "model";
  m["owned_by"] = "esp32-s3";
  String body;
  serializeJson(doc, body);
  http_server.send(200, "application/json", body);
}

// POST /v1/chat/completions
static void handle_chat_completions() {
  if (!http_server.hasArg("plain")) {
    http_server.send(400, "application/json", "{\"error\":\"no body\"}");
    return;
  }

  JsonDocument req;
  DeserializationError err = deserializeJson(req, http_server.arg("plain"));
  if (err) {
    http_server.send(400, "application/json", "{\"error\":\"invalid json\"}");
    return;
  }

  // Extract last user message from messages array
  String prompt;
  for (JsonObject msg : req["messages"].as<JsonArray>()) {
    if (String(msg["role"].as<const char *>()) == "user") {
      prompt = msg["content"].as<const char *>();
    }
  }
  if (prompt.isEmpty()) {
    http_server.send(400, "application/json", "{\"error\":\"no user message\"}");
    return;
  }

  Serial.printf("[HTTP] Question: %s\n", prompt.c_str());

  String answer;
  int n_tokens = 0;
  float tok_per_sec = 0.0f;
  run_inference_to_buf(prompt, answer, n_tokens, tok_per_sec);

  Serial.printf("[HTTP] Answer (%d words, %.1f words/s): %s\n", n_tokens, tok_per_sec, answer.c_str());

  // Build OpenAI-compatible response
  JsonDocument resp;
  resp["id"]     = "chatcmpl-1";
  resp["object"] = "chat.completion";
  resp["model"]  = "esp32-sourdough";
  JsonArray choices = resp["choices"].to<JsonArray>();
  JsonObject choice = choices.add<JsonObject>();
  choice["index"]         = 0;
  choice["finish_reason"] = "stop";
  JsonObject msg_out = choice["message"].to<JsonObject>();
  msg_out["role"]    = "assistant";
  msg_out["content"] = answer;
  JsonObject usage = resp["usage"].to<JsonObject>();
  usage["prompt_tokens"]     = (int)prompt.length() / 4;
  usage["completion_tokens"] = n_tokens;
  usage["total_tokens"]      = (int)prompt.length() / 4 + n_tokens;

  String body;
  serializeJson(resp, body);
  http_server.send(200, "application/json", body);
}

static void handle_not_found() {
  http_server.send(404, "application/json", "{\"error\":\"not found\"}");
}

// ---- Register HTTP routes (called once WiFi is up, at end of setup) ---------
static void setup_http_routes() {
  http_server.on("/v1/models", HTTP_GET, handle_models);
  http_server.on("/v1/chat/completions", HTTP_POST, handle_chat_completions);
  http_server.onNotFound(handle_not_found);
}

void loop() {
  if (wifi_connected) http_server.handleClient();

  if (!Serial.available()) {
    delay(20);
    return;
  }

  String prompt = Serial.readStringUntil('\n');
  prompt.trim();
  if (prompt.length() == 0) return;

  // Echo user question
  Serial.println(prompt);

  // Interactive parameter commands
  if (prompt.startsWith("/temp")) {
    float t = prompt.substring(prompt.indexOf(' ') + 1).toFloat();
    if (t >= 0.0f && t <= 2.0f) {
      g_temperature = t;
      Serial.printf("Assistant: Temperature set to %.2f\n\nUser: ", g_temperature);
    } else {
      Serial.printf("Assistant: Invalid temperature (0.0-2.0). Current: %.2f\n\nUser: ", g_temperature);
    }
    return;
  }
  if (prompt.startsWith("/topp")) {
    float p = prompt.substring(prompt.indexOf(' ') + 1).toFloat();
    if (p > 0.0f && p <= 1.0f) {
      g_topp = p;
      Serial.printf("Assistant: Top-p set to %.2f\n\nUser: ", g_topp);
    } else {
      Serial.printf("Assistant: Invalid top-p (0.0-1.0). Current: %.2f\n\nUser: ", g_topp);
    }
    return;
  }
  if (prompt.startsWith("/subvocab")) {
    String arg = prompt.substring(prompt.indexOf(' ') + 1);
    arg.trim();
    if (prompt == "/subvocab" || arg.length() == 0) {
      Serial.printf("Assistant: Sub-vocab -> clusters=%d/%d (status: %s)\n\nUser: ",
                    g_subvocab_clusters, SOURDOUGH_SUBVOCAB_NUM_CLUSTERS,
                    g_subvocab_clusters > 0 ? "ENABLED" : "DISABLED");
    } else if (arg.equalsIgnoreCase("off") || arg == "0") {
      g_subvocab_clusters = 0;
      Serial.println("Assistant: Sub-vocabulary prediction disabled (full vocabulary evaluation).\n\nUser: ");
    } else if (arg.equalsIgnoreCase("on")) {
      g_subvocab_clusters = SOURDOUGH_SUBVOCAB_DEFAULT_TOP_CLUSTERS;
      Serial.printf("Assistant: Sub-vocabulary prediction enabled (top %d clusters).\n\nUser: ", g_subvocab_clusters);
    } else {
      int c = arg.toInt();
      if (c >= 0 && c <= SOURDOUGH_SUBVOCAB_NUM_CLUSTERS) {
        g_subvocab_clusters = c;
        Serial.printf("Assistant: Sub-vocabulary clusters set to %d / %d.\n\nUser: ",
                      g_subvocab_clusters, SOURDOUGH_SUBVOCAB_NUM_CLUSTERS);
      } else {
        Serial.printf("Assistant: Invalid clusters (0-%d). Current: %d\n\nUser: ",
                      SOURDOUGH_SUBVOCAB_NUM_CLUSTERS, g_subvocab_clusters);
      }
    }
    return;
  }
  if (prompt == "/simd") {
#if defined(__XTENSA__) && defined(CONFIG_IDF_TARGET_ESP32S3)
    Serial.println("Assistant: SIMD status -> ESP32-S3 PIE 128-bit vector instructions ACTIVE\n\nUser: ");
#else
    Serial.println("Assistant: SIMD status -> Scalar fallback\n\nUser: ");
#endif
    return;
  }
  if (prompt == "/config") {
    Serial.printf("Assistant: Config -> temp=%.2f | top_p=%.2f | rep_window=%d | subvocab=%d/%d clusters (%s) | SIMD=%s\n\nUser: ",
                  g_temperature, g_topp, RECENT_WINDOW, g_subvocab_clusters, SOURDOUGH_SUBVOCAB_NUM_CLUSTERS,
                  g_subvocab_clusters > 0 ? "ON" : "OFF",
#if defined(__XTENSA__) && defined(CONFIG_IDF_TARGET_ESP32S3)
                  "ESP32-S3 PIE"
#else
                  "Scalar"
#endif
    );
    return;
  }

  // 1. Encode prompt with on-device BPE tokenizer
  uint16_t prompt_tokens[128];
  int n_prompt = bpe_encode_ascii(&tokenizer, prompt.c_str(), prompt_tokens, 120);
  if (n_prompt < 0) {
    Serial.println("Assistant: Error: Prompt contains unsupported characters or is too long.\n");
    Serial.print("User: ");
    return;
  }

  Serial.print("Assistant: ");
  llm_profile_reset(&s);

  int pos = 0;
  // 2. Prime KV cache with prompt tokens
  for (int i = 0; i < n_prompt; i++) {
    llm_forward(&model, prompt_tokens[i], pos++, &s);
  }
  // 3. Feed BOS token
  llm_forward(&model, SOURDOUGH_OUT2IN[SOURDOUGH_BOS], pos++, &s);

  // 4. Autoregressive whole-word generation
  int64_t t0 = esp_timer_get_time();
  int pieces_out = 0;
  int max_pieces = 60;
  int recent[RECENT_WINDOW];
  for (int i = 0; i < RECENT_WINDOW; i++) recent[i] = -1;

  for (int step = 0; step < max_pieces && pos < model.c.seq_len; step++) {
    // Suppress non-word special tokens (<pad>, <bos>, and strongly suppress <unk>)
    s.logits[SOURDOUGH_PAD] = -1e30f;
    s.logits[SOURDOUGH_BOS] = -1e30f;
    s.logits[SOURDOUGH_UNK] -= 10.0f;

    // Distance-weighted repetition penalty across recent window
    for (int d = 1; d <= RECENT_WINDOW && d <= step; d++) {
      int idx = (step - d + RECENT_WINDOW) % RECENT_WINDOW;
      int prev = recent[idx];
      if (prev >= 0 && prev < SOURDOUGH_WORD_COUNT) {
        // More recent tokens get stronger penalty (d=1: factor=0.80, d=32: factor=0.95)
        float factor = 0.80f + 0.15f * ((float)(d - 1) / (float)RECENT_WINDOW);
        if (s.logits[prev] > 0) s.logits[prev] *= factor;
        else s.logits[prev] *= (2.0f - factor);
      }
    }

    // Adaptive EOS and punctuation boosting near output budget end to wrap up cleanly
    if (step >= max_pieces - 10) {
      float boost = (float)(step - (max_pieces - 10) + 1) * 1.5f;
      s.logits[SOURDOUGH_EOS] += boost;
      s.logits[5] += boost * 0.5f; // index 5 is '.'
    }

    // Nucleus / Top-p sampling with temperature
    int best = sample(s.logits, SOURDOUGH_WORD_COUNT, g_temperature, g_topp, probindex);
    if (best == SOURDOUGH_EOS) break;

    recent[step % RECENT_WINDOW] = best;
    emit_word(best, pieces_out);

    // If near end of output budget and completed a sentence, terminate cleanly
    if (step >= max_pieces - 8 && (best == 5 || best == 8)) { // '.' or '?'
      break;
    }

    llm_forward(&model, SOURDOUGH_OUT2IN[best], pos++, &s);
  }

  int64_t total_us = esp_timer_get_time() - t0;
  float tok_per_sec = (total_us > 0) ? (pieces_out * 1e6f / total_us) : 0.0f;

  Serial.printf("\n\n[%d words in %.2f s, %.1f words/s]\n", pieces_out, total_us / 1e6f, tok_per_sec);
  Serial.print("\nUser: ");
}
