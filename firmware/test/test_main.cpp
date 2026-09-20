#include <unity.h>
#include <stdbool.h>
#include <string.h>
#include "llm.h"
#include "bpe_tokenizer.h"
#include "generated/tokenizer_asset.h"
#include "generated/vocab.h"
#include "generated/sourdough_words.h"
#include "generated/sourdough_subvocab.h"

void test_bpe_encoder() {
    BpeTokenizer tok;
    int rc = bpe_tokenizer_load(TOKENIZER_ASSET, TOKENIZER_ASSET_SIZE, &tok);
    TEST_ASSERT_EQUAL_INT(0, rc);
    TEST_ASSERT_EQUAL_UINT32(4096, tok.active_vocab);
    TEST_ASSERT_EQUAL_UINT32(3839, tok.merge_count);

    uint16_t out[128];
    int n = bpe_encode_ascii(&tok, "Why is my bread gummy?", out, 128);
    TEST_ASSERT_EQUAL_INT(8, n);
    uint16_t expected[8] = {55, 72, 89, 346, 453, 394, 940, 31};
    for (int i = 0; i < 8; i++) {
        TEST_ASSERT_EQUAL_UINT16(expected[i], out[i]);
    }
}

void test_dot_product_i8() {
    alignas(16) int8_t a[32] = {
        1, 2, 3, 4, 5, 6, 7, 8, -1, -2, -3, -4, -5, -6, -7, -8,
        10, 10, 10, 10, -10, -10, -10, -10, 2, 2, 2, 2, -2, -2, -2, -2
    };
    alignas(16) int8_t b[32] = {
        8, 7, 6, 5, 4, 3, 2, 1, -8, -7, -6, -5, -4, -3, -2, -1,
        1, 1, 1, 1, 1, 1, 1, 1, -1, -1, -1, -1, -1, -1, -1, -1
    };

    // First 16 elements:
    // (1*8 + 2*7 + 3*6 + 4*5 + 5*4 + 6*3 + 7*2 + 8*1) * 2 = 120 * 2 = 240
    int32_t dot16 = llm_dot_i8(a, b, 16);
    TEST_ASSERT_EQUAL_INT32(240, dot16);

    // Full 32 elements:
    // next 8: (10*1)*4 + (-10*1)*4 = 0
    // next 8: (2*-1)*4 + (-2*-1)*4 = 0
    int32_t dot32 = llm_dot_i8(a, b, 32);
    TEST_ASSERT_EQUAL_INT32(240, dot32);

    // Tail testing (odd length: 19 elements)
    int32_t dot19 = llm_dot_i8(a, b, 19);
    TEST_ASSERT_EQUAL_INT32(240 + 30, dot19);

    // Single element
    int32_t dot1 = llm_dot_i8(a, b, 1);
    TEST_ASSERT_EQUAL_INT32(8, dot1);
}

void test_subvocab_clustering() {
    TEST_ASSERT_EQUAL_INT(16, SOURDOUGH_SUBVOCAB_NUM_CLUSTERS);
    TEST_ASSERT_EQUAL_INT(160, SOURDOUGH_SUBVOCAB_DIM);
    TEST_ASSERT_EQUAL_INT(SOURDOUGH_WORD_COUNT, SOURDOUGH_SUBVOCAB_OUT_VOCAB);
    TEST_ASSERT_EQUAL_INT(4, SOURDOUGH_SUBVOCAB_DEFAULT_TOP_CLUSTERS);

    // Verify all token counts sum to total vocabulary
    uint32_t total_count = 0;
    bool seen[SOURDOUGH_SUBVOCAB_OUT_VOCAB] = {false};
    for (int k = 0; k < SOURDOUGH_SUBVOCAB_NUM_CLUSTERS; k++) {
        uint16_t offset = SOURDOUGH_SUBVOCAB_OFFSETS[k];
        uint16_t count = SOURDOUGH_SUBVOCAB_COUNTS[k];
        TEST_ASSERT_EQUAL_UINT32(total_count, offset);
        total_count += count;
        TEST_ASSERT_TRUE(count > 0);

        for (uint16_t i = 0; i < count; i++) {
            uint16_t tok = SOURDOUGH_SUBVOCAB_TOKENS[offset + i];
            TEST_ASSERT_TRUE(tok < SOURDOUGH_SUBVOCAB_OUT_VOCAB);
            TEST_ASSERT_FALSE(seen[tok]);
            seen[tok] = true;
        }
    }
    TEST_ASSERT_EQUAL_UINT32(SOURDOUGH_SUBVOCAB_OUT_VOCAB, total_count);

    // Verify all 1882 tokens are partitioned exactly once
    for (int t = 0; t < SOURDOUGH_SUBVOCAB_OUT_VOCAB; t++) {
        TEST_ASSERT_TRUE(seen[t]);
    }

    // Verify special tokens guaranteed inclusion
    TEST_ASSERT_TRUE(SOURDOUGH_SUBVOCAB_ALWAYS_COUNT >= 4);
    TEST_ASSERT_EQUAL_UINT16(0, SOURDOUGH_SUBVOCAB_ALWAYS_INCLUDE[0]); // PAD
    TEST_ASSERT_EQUAL_UINT16(1, SOURDOUGH_SUBVOCAB_ALWAYS_INCLUDE[1]); // BOS
    TEST_ASSERT_EQUAL_UINT16(2, SOURDOUGH_SUBVOCAB_ALWAYS_INCLUDE[2]); // EOS
    TEST_ASSERT_EQUAL_UINT16(3, SOURDOUGH_SUBVOCAB_ALWAYS_INCLUDE[3]); // UNK
}

#include "wifi_manager.cpp"

void test_wifi_manager_initial_state() {
    WifiManager wifi("InitialSSID", "InitialPass");
    TEST_ASSERT_EQUAL(WIFI_STATE_DISCONNECTED, wifi.getState());
    TEST_ASSERT_EQUAL_STRING("0.0.0.0", wifi.getIPAddress().c_str());
    TEST_ASSERT_EQUAL(-100, wifi.getRSSI());
    TEST_ASSERT_EQUAL_STRING("InitialSSID", wifi.getSSID().c_str());

    String apSSID = wifi.getAPSSID();
    TEST_ASSERT_TRUE(apSSID.startsWith("sourdough-assistant-"));

    wifi.setCredentials("NewSSID", "NewPass");
    TEST_ASSERT_EQUAL_STRING("NewSSID", wifi.getSSID().c_str());
}

void test_wifi_portal_catppuccin_mocha_styling() {
    String html = WifiManager::generatePortalHTML(0, "<div class='net-item'>Test</div>", "CurrentSSID");

    // Catppuccin Mocha Color Palette tokens
    TEST_ASSERT_TRUE(html.indexOf("#1e1e2e") != -1); // Mocha Base
    TEST_ASSERT_TRUE(html.indexOf("#181825") != -1); // Mocha Mantle
    TEST_ASSERT_TRUE(html.indexOf("#11111b") != -1); // Mocha Crust
    TEST_ASSERT_TRUE(html.indexOf("#313244") != -1); // Mocha Surface0
    TEST_ASSERT_TRUE(html.indexOf("#45475a") != -1); // Mocha Surface1
    TEST_ASSERT_TRUE(html.indexOf("#cdd6f4") != -1); // Mocha Text
    TEST_ASSERT_TRUE(html.indexOf("#a6adc8") != -1); // Mocha Subtext0
    TEST_ASSERT_TRUE(html.indexOf("#cba6f7") != -1); // Mocha Mauve
    TEST_ASSERT_TRUE(html.indexOf("#f5c2e7") != -1); // Mocha Pink
    TEST_ASSERT_TRUE(html.indexOf("#89b4fa") != -1); // Mocha Blue
}

void test_wifi_portal_network_listing_and_form() {
    String netList = "<div class='net-item' onclick='selectSSID(\"BakerNet\")'>"
                     "<span>BakerNet</span>"
                     "<span style='color: #a6adc8; font-size: 12px;'>-45 dBm</span>"
                     "</div>";
    String html = WifiManager::generatePortalHTML(1, netList, "");

    // Network list rendered
    TEST_ASSERT_TRUE(html.indexOf("BakerNet") != -1);
    TEST_ASSERT_TRUE(html.indexOf("-45 dBm") != -1);
    TEST_ASSERT_TRUE(html.indexOf("class='net-list'") != -1);

    // Form inputs and actions
    TEST_ASSERT_TRUE(html.indexOf("action='/save'") != -1);
    TEST_ASSERT_TRUE(html.indexOf("id='ssid'") != -1);
    TEST_ASSERT_TRUE(html.indexOf("id='pass'") != -1);
    TEST_ASSERT_TRUE(html.indexOf("Save & Connect") != -1);

    // Client-side JavaScript helpers
    TEST_ASSERT_TRUE(html.indexOf("function selectSSID(ssid)") != -1);
    TEST_ASSERT_TRUE(html.indexOf("function togglePwd(id, el)") != -1);
}

void test_wifi_portal_saved_and_scanning_pages() {
    String savedHtml = WifiManager::generateSavedHTML("SourdoughBakery");
    TEST_ASSERT_TRUE(savedHtml.indexOf("Configuration Saved") != -1);
    TEST_ASSERT_TRUE(savedHtml.indexOf("SourdoughBakery") != -1);
    TEST_ASSERT_TRUE(savedHtml.indexOf("#a6e3a1") != -1); // Mocha Green

    String scanningHtml = WifiManager::generateScanningHTML();
    TEST_ASSERT_TRUE(scanningHtml.indexOf("Scanning for Wi-Fi...") != -1);
    TEST_ASSERT_TRUE(scanningHtml.indexOf("content='3;url=/'") != -1);
}

#include "landing_html.h"
#include "settings_html.h"
#include "ota_html.h"

void test_landing_html_catppuccin_mocha() {
    String html = landing_html;
    TEST_ASSERT_TRUE(html.indexOf("#1e1e2e") != -1); // Mocha Base
    TEST_ASSERT_TRUE(html.indexOf("#181825") != -1); // Mocha Mantle
    TEST_ASSERT_TRUE(html.indexOf("#313244") != -1); // Mocha Surface0
    TEST_ASSERT_TRUE(html.indexOf("#cdd6f4") != -1); // Mocha Text
    TEST_ASSERT_TRUE(html.indexOf("#cba6f7") != -1); // Mocha Mauve
    TEST_ASSERT_TRUE(html.indexOf("#f5c2e7") != -1); // Mocha Pink
    TEST_ASSERT_TRUE(html.indexOf("#89b4fa") != -1); // Mocha Blue
    TEST_ASSERT_TRUE(html.indexOf("#a6e3a1") != -1); // Mocha Green
    TEST_ASSERT_TRUE(html.indexOf("#f38ba8") != -1); // Mocha Red

    // Navigation and Chat hooks
    TEST_ASSERT_TRUE(html.indexOf("/settings") != -1);
    TEST_ASSERT_TRUE(html.indexOf("/update") != -1);
    TEST_ASSERT_TRUE(html.indexOf("/reset") != -1);
    TEST_ASSERT_TRUE(html.indexOf("/v1/chat/completions") != -1);
    TEST_ASSERT_TRUE(html.indexOf("chat-container") != -1);
}

void test_settings_html_catppuccin_mocha() {
    String html = settings_html;
    TEST_ASSERT_TRUE(html.indexOf("#1e1e2e") != -1); // Mocha Base
    TEST_ASSERT_TRUE(html.indexOf("#181825") != -1); // Mocha Mantle
    TEST_ASSERT_TRUE(html.indexOf("#313244") != -1); // Mocha Surface0
    TEST_ASSERT_TRUE(html.indexOf("#cdd6f4") != -1); // Mocha Text
    TEST_ASSERT_TRUE(html.indexOf("#cba6f7") != -1); // Mocha Mauve
    TEST_ASSERT_TRUE(html.indexOf("#f5c2e7") != -1); // Mocha Pink
    TEST_ASSERT_TRUE(html.indexOf("#89b4fa") != -1); // Mocha Blue

    // Sliders & inputs
    TEST_ASSERT_TRUE(html.indexOf("action=\"/settings/save\"") != -1);
    TEST_ASSERT_TRUE(html.indexOf("id=\"temp_slider\"") != -1);
    TEST_ASSERT_TRUE(html.indexOf("id=\"topp_slider\"") != -1);
    TEST_ASSERT_TRUE(html.indexOf("id=\"subvocab\"") != -1);
    TEST_ASSERT_TRUE(html.indexOf("info-table") != -1);
}

void test_ota_html_catppuccin_mocha() {
    String html = ota_html;
    TEST_ASSERT_TRUE(html.indexOf("#1e1e2e") != -1); // Mocha Base
    TEST_ASSERT_TRUE(html.indexOf("#181825") != -1); // Mocha Mantle
    TEST_ASSERT_TRUE(html.indexOf("#313244") != -1); // Mocha Surface0
    TEST_ASSERT_TRUE(html.indexOf("#a6e3a1") != -1); // Mocha Green (progress)
    TEST_ASSERT_TRUE(html.indexOf("/v1/update") != -1);
    TEST_ASSERT_TRUE(html.indexOf("dropZone") != -1);
}

int main(int argc, char **argv) {
    UNITY_BEGIN();
    RUN_TEST(test_bpe_encoder);
    RUN_TEST(test_dot_product_i8);
    RUN_TEST(test_subvocab_clustering);
    RUN_TEST(test_wifi_manager_initial_state);
    RUN_TEST(test_wifi_portal_catppuccin_mocha_styling);
    RUN_TEST(test_wifi_portal_network_listing_and_form);
    RUN_TEST(test_wifi_portal_saved_and_scanning_pages);
    RUN_TEST(test_landing_html_catppuccin_mocha);
    RUN_TEST(test_settings_html_catppuccin_mocha);
    RUN_TEST(test_ota_html_catppuccin_mocha);
    UNITY_END();
    return 0;
}


