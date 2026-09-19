#include <unity.h>
#include <stdbool.h>
#include <string.h>
#include "llm.h"
#include "bpe_tokenizer.h"
#include "generated/tokenizer_asset.h"
#include "generated/vocab.h"
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
    uint16_t expected[8] = {55, 72, 89, 343, 434, 394, 944, 31};
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
    TEST_ASSERT_EQUAL_INT(1882, SOURDOUGH_SUBVOCAB_OUT_VOCAB);
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

int main(int argc, char **argv) {
    UNITY_BEGIN();
    RUN_TEST(test_bpe_encoder);
    RUN_TEST(test_dot_product_i8);
    RUN_TEST(test_subvocab_clustering);
    UNITY_END();
    return 0;
}
