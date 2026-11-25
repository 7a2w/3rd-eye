/* Tiny JSON field readers for the short command messages from the phone. */
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include "te_app.h"

static const char *find_value(const char *js, const char *key)
{
    char pat[32];
    snprintf(pat, sizeof pat, "\"%s\"", key);
    const char *p = strstr(js, pat);
    if (!p) return NULL;
    p += strlen(pat);
    while (*p == ' ' || *p == ':') p++;
    return p;
}

bool json_str(const char *js, const char *key, char *out, size_t max)
{
    const char *p = find_value(js, key);
    if (!p || *p != '"') return false;
    p++;
    size_t n = 0;
    while (*p && *p != '"' && n + 1 < max) out[n++] = *p++;
    out[n] = 0;
    return true;
}

bool json_int(const char *js, const char *key, long *out)
{
    const char *p = find_value(js, key);
    if (!p) return false;
    if (!strncmp(p, "true", 4)) { *out = 1; return true; }
    if (!strncmp(p, "false", 5)) { *out = 0; return true; }
    char *end;
    long v = strtol(p, &end, 10);
    if (end == p) return false;
    *out = v;
    return true;
}
