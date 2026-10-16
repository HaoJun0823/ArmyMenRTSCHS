// chs_core.h -- CJK glyph core: GBK decode + TTF rasterize + cache
// Plan B: keep original English bitmap font untouched; render CJK via TTF at runtime.
// NOTE: kept ASCII-only on purpose (MSVC codepage 936 mangles non-ASCII bytes).
#pragma once
#include <windows.h>
#include <unordered_map>
#include <vector>

struct Glyph {
    int  w = 0, h = 0;
    int  advance = 0;   // horizontal step (px)
    int  bearingY = 0;  // pixels above baseline
    std::vector<BYTE> alpha; // w*h, 0..255
};

class ChsFont {
public:
    bool  Init(const wchar_t* fontPath, int px);
    void  Shutdown();
    const Glyph* Get(wchar_t ch);
    int   Height() const { return height_; }

private:
    bool  Rasterize(wchar_t ch, Glyph& out);

    HDC          hdc_ = nullptr;
    HFONT        hfont_ = nullptr;
    HBITMAP      hbmp_ = nullptr;
    BYTE*        bits_ = nullptr;
    int          dibW_ = 64, dibH_ = 64;
    int          height_ = 0;
    int          px_ = 0;
    std::unordered_map<wchar_t, Glyph> cache_;
};

// GBK -> Unicode. Returns bytes consumed: 2 for a decoded pair, 1 for ASCII,
// 0 when the bytes are NOT a valid GBK sequence.
//
// Returning 0 matters: the old code fell back to "treat the lead byte as a
// character", which pushed an 0x81..0xFE byte into the engine's u8 glyph
// lookup. The stock fonts map 0xC0..0xFF to the Cyrillic alphabet, so a failed
// decode rendered as a stray Cyrillic letter. Callers must skip such a byte
// without ever handing it to the engine.
inline int GBK_Decode(const BYTE* p, wchar_t& ch) {
    BYTE a = p[0];
    if (a < 0x80) { ch = (wchar_t)a; return 1; }
    if (p[1] == 0) { ch = 0; return 0; }        // lone lead byte at end of string
    ch = 0;
    int n = MultiByteToWideChar(936, 0, (LPCSTR)p, 2, &ch, 1);
    if (n <= 0 || ch == 0) { ch = 0; return 0; }
    return 2;
}

// True when the byte starts a GBK double-byte CJK sequence.
inline bool GBK_IsCjk(const BYTE* p) {
    return p[0] >= 0x81 && p[0] <= 0xFE && p[1] >= 0x40 && p[1] <= 0xFE && p[1] != 0x7F;
}
