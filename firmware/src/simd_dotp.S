/* ESP32-S3 PIE SIMD int8 vector dot product
 * Computes signed 8-bit dot product using 128-bit vector instructions.
 * Requires 16-byte alignment for full SIMD acceleration.
 */

#if defined(__has_include)
#if __has_include("sdkconfig.h")
#include "sdkconfig.h"
#endif
#endif

#if defined(__XTENSA__) && defined(CONFIG_IDF_TARGET_ESP32S3)

.section .text
.global simd_dotp_i8
.type simd_dotp_i8, @function
.align 4

simd_dotp_i8:
    entry a1, 16
    extui a6, a4, 0, 4      // a6 = len % 16 (tail elements)
    srli a4, a4, 4          // a4 = len / 16 (16-byte blocks)
    movi.n a7, 0            // accumulator = 0
    beqz a4, .Ltail_start

    ee.zero.accx
    ee.vld.128.ip     q0, a2, 16
    loopnez a4, .Lsimd_loop
        ee.vld.128.ip     q1, a3, 16
        ee.vmulas.s8.accx.ld.ip q0, a2, 16, q0, q1
    .Lsimd_loop:

    rur.accx_0 a7
    addi a2, a2, -16

.Ltail_start:
    loopnez a6, .Ltail_loop
        l8ui a8, a2, 0
        l8ui a9, a3, 0
        sext a8, a8, 7
        sext a9, a9, 7
        mull a8, a8, a9
        add a7, a7, a8
        addi a2, a2, 1
        addi a3, a3, 1
    .Ltail_loop:

    mov.n a2, a7
    retw.n

#endif
