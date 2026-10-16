// chs_core.cpp -- TTF rasterizer (GDI only, no third-party deps)
#include "pch.h"
#include "chs_core.h"

bool ChsFont::Init(const wchar_t* fontPath, int px) {
    px_ = px;
    height_ = px;

    AddFontResourceExW(fontPath, FR_PRIVATE, 0);

    // Family name for msyh.ttc. Fall back to simsun if caller passes a TTF.
    const wchar_t* family = L"Microsoft YaHei";

    hdc_ = CreateCompatibleDC(nullptr);
    if (!hdc_) return false;

    int h = -MulDiv(px, GetDeviceCaps(hdc_, LOGPIXELSY), 72); // negative => cell height
    hfont_ = CreateFontW(h, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
                         DEFAULT_CHARSET, OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS,
                         ANTIALIASED_QUALITY, FF_DONTCARE, family);
    if (!hfont_) { DeleteDC(hdc_); hdc_ = nullptr; return false; }
    SelectObject(hdc_, hfont_);
    SetTextColor(hdc_, RGB(255, 255, 255));
    SetBkColor(hdc_, RGB(0, 0, 0));
    SetBkMode(hdc_, OPAQUE);

    dibW_ = px * 3; dibH_ = px * 3;
    BITMAPINFO bi{};
    bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bi.bmiHeader.biWidth = dibW_;
    bi.bmiHeader.biHeight = -dibH_;   // top-down
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32;
    bi.bmiHeader.biCompression = BI_RGB;
    hbmp_ = CreateDIBSection(hdc_, &bi, DIB_RGB_COLORS, (void**)&bits_, nullptr, 0);
    if (!hbmp_ || !bits_) { Shutdown(); return false; }
    SelectObject(hdc_, hbmp_);
    return true;
}

void ChsFont::Shutdown() {
    if (hbmp_)  { DeleteObject(hbmp_);  hbmp_ = nullptr; }
    if (hfont_) { DeleteObject(hfont_); hfont_ = nullptr; }
    if (hdc_)   { DeleteDC(hdc_);       hdc_ = nullptr; }
    bits_ = nullptr;
}

bool ChsFont::Rasterize(wchar_t ch, Glyph& out) {
    if (!hdc_ || !bits_) return false;
    memset(bits_, 0, dibW_ * dibH_ * 4);

    wchar_t s[2] = { ch, 0 };
    RECT rc{ 0, 0, dibW_, dibH_ };
    int ret = DrawTextW(hdc_, s, 1, &rc, DT_SINGLELINE | DT_NOCLIP | DT_NOPREFIX);

    SIZE sz{};
    GetTextExtentPoint32W(hdc_, s, 1, &sz);

    if (ret <= 0) { // whitespace: advance only
        out.w = 0; out.h = 0; out.advance = sz.cx; out.bearingY = 0;
        out.alpha.clear();
        return true;
    }

    int minX = dibW_, minY = dibH_, maxX = -1, maxY = -1;
    for (int y = 0; y < dibH_; ++y) {
        const BYTE* row = bits_ + (y * dibW_ * 4);
        for (int x = 0; x < dibW_; ++x) {
            BYTE v = row[x * 4];          // R channel as luminance
            if (v > 8) {
                if (x < minX) minX = x;
                if (y < minY) minY = y;
                if (x > maxX) maxX = x;
                if (y > maxY) maxY = y;
            }
        }
    }
    if (maxX < 0) {
        out.w = 0; out.h = 0; out.advance = sz.cx; out.bearingY = 0;
        out.alpha.clear();
        return true;
    }

    out.w = maxX - minX + 1;
    out.h = maxY - minY + 1;
    out.bearingY = dibH_ - 1 - maxY;
    out.alpha.assign((size_t)out.w * out.h, 0);
    for (int y = 0; y < out.h; ++y) {
        const BYTE* src = bits_ + ((y + minY) * dibW_ * 4) + minX * 4;
        BYTE* dst = &out.alpha[(size_t)y * out.w];
        for (int x = 0; x < out.w; ++x) dst[x] = src[x * 4];
    }
    out.advance = sz.cx;
    return true;
}

const Glyph* ChsFont::Get(wchar_t ch) {
    auto it = cache_.find(ch);
    if (it != cache_.end()) return &it->second;
    Glyph g;
    if (!Rasterize(ch, g)) return nullptr;
    auto r = cache_.emplace(ch, std::move(g));
    return &r.first->second;
}
