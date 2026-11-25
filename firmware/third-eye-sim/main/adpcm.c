#include "adpcm.h"

static const int16_t step_table[89] = {
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66,
    73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408,
    449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
    2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630,
    9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767};
static const int8_t index_table[16] = {-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8};

static uint8_t encode_one(adpcm_state_t *st, int16_t s)
{
    int step = step_table[st->index];
    int diff = s - st->pred;
    uint8_t code = 0;
    if (diff < 0) { code = 8; diff = -diff; }
    int delta = step >> 3;
    if (diff >= step) { code |= 4; diff -= step; delta += step; }
    step >>= 1;
    if (diff >= step) { code |= 2; diff -= step; delta += step; }
    step >>= 1;
    if (diff >= step) { code |= 1; delta += step; }
    int p = st->pred + ((code & 8) ? -delta : delta);
    if (p > 32767) p = 32767;
    if (p < -32768) p = -32768;
    st->pred = p;
    int idx = st->index + index_table[code];
    st->index = idx < 0 ? 0 : (idx > 88 ? 88 : idx);
    return code;
}

size_t adpcm_encode_block(adpcm_state_t *st, const int16_t *pcm, size_t n, uint8_t *out)
{
    out[0] = st->pred & 0xff;
    out[1] = (uint16_t)st->pred >> 8;
    out[2] = st->index;
    out[3] = 0;
    size_t o = 4;
    for (size_t i = 0; i + 1 < n; i += 2) {
        uint8_t lo = encode_one(st, pcm[i]);
        uint8_t hi = encode_one(st, pcm[i + 1]);
        out[o++] = lo | (hi << 4);
    }
    return o;
}
