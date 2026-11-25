#pragma once
#include <stddef.h>
#include <stdint.h>

/* IMA ADPCM, 4 bits per sample (4 times smaller than 16-bit PCM). */
typedef struct { int16_t pred; int8_t index; } adpcm_state_t;

/* Writes a 4-byte block header (predictor, index) then n/2 bytes. Returns bytes written. */
size_t adpcm_encode_block(adpcm_state_t *st, const int16_t *pcm, size_t n, uint8_t *out);
