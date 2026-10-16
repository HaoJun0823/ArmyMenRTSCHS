#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gen_fff.py -- TTF -> .fff 字体生成器（多字号组），供 Army Men RTS 汉化使用

为什么要多字号
--------------
游戏的 if_fonts.cfg 定义多套字体，各自 metric（行高）不同：
    font_arial_10.fff          metric=16   拉丁 cap 高 10   (System/Button/HUD)
    font_stencil_14.fff        metric=19   拉丁 cap 高 15   (Debriefing/主菜单)
    font_stencil_24.fff        metric=30   拉丁 cap 高 26   (Movie/Resource)
绘制时引擎把当前字体对象传给绘制函数。汉字必须用**对应字号**渲染，
否则会在 HUD 里过大、在主菜单里过小。本工具按 "metric:GDI尺寸" 组分别出页。

.fff 格式（引擎 sub_4A26F0 权威语义，已用原版 4 个字体往返验证）
--------------------------------------------------------------
  "BORK" | u16 count | u8 metric | 2 字节跳过      <- 条目表从 offset 9 开始
  count x 7B: u16 slot, u8 adv, u8 left, u8 top, u8 right, u8 bottom
  count x 字形: u8 w, u8 h, w*h 字节 8bit alpha
  约束: w,h <= 100

索引格式（供 DLL 读，避免解析 JSON）
-----------------------------------
  "CHSI" | u32 glyphCount | u16 groupCount | u8 prefixLen | prefix
  groupCount x 4B: u16 metric, u16 pageCount
  glyphCount x 12B: u32 unicode, u16 group, u16 page, u16 slot, u8 adv, u8 pad

页文件名: chs_g{group}_p{page}.fff

用法
----
  python gen_fff.py --ttf C:\\Windows\\Fonts\\msyh.ttc --chars-file chars.txt \
      --groups "16:13,19:18,30:31" --out chs.fff
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import struct
import sys

gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

gdi32.AddFontResourceExW.argtypes = [ctypes.c_wchar_p, wt.DWORD, wt.LPVOID]
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateFontW.argtypes = [
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD,
    wt.DWORD, ctypes.c_wchar_p]
gdi32.CreateFontW.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.c_void_p, wt.UINT,
                                   ctypes.c_void_p, wt.HANDLE, wt.DWORD]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.SetTextColor.argtypes = [wt.HDC, wt.DWORD]
gdi32.SetBkColor.argtypes = [wt.HDC, wt.DWORD]
gdi32.SetBkMode.argtypes = [wt.HDC, ctypes.c_int]
gdi32.TextOutW.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
gdi32.GetTextExtentPoint32W.argtypes = [wt.HDC, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
gdi32.SetTextAlign.argtypes = [wt.HDC, wt.UINT]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteObject.restype = wt.BOOL
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.DeleteDC.restype = wt.BOOL

FW_NORMAL = 400
DEFAULT_CHARSET = 1
OUT_TT_PRECIS = 4
CLIP_DEFAULT_PRECIS = 0
ANTIALIASED_QUALITY = 4
FF_DONTCARE = 0
BI_RGB = 0
OPAQUE = 2
TA_LEFT = 0
TA_BASELINE = 24
MAX_DIM = 100


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


class Rasterizer:
    """GDI 单字符栅格化 -> 8bit alpha"""

    def __init__(self, ttf_path, px, baseline_ref=None):
        self.px = px
        # baseline_ref = baseline row inside the game's row box, taken from the
        # matching stock font (metric 16 -> 13, 19 -> 18, 30 -> 29). Default
        # approximates it when not supplied.
        self.baseline_ref = baseline_ref if baseline_ref is not None else max(6, int(px * 0.72) + 3)
        self.baseline = int(px * 1.25) + 2
        self.cellW = px * 2 + 10
        self.cellH = self.baseline + int(px * 0.55) + 8

        self.font_res = gdi32.AddFontResourceExW(ctypes.c_wchar_p(ttf_path), 0x10, 0)
        self.hdc = gdi32.CreateCompatibleDC(None)
        if not self.hdc:
            raise OSError("CreateCompatibleDC failed")

        self.hfont = gdi32.CreateFontW(
            -px, 0, 0, 0, FW_NORMAL, False, False, False,
            DEFAULT_CHARSET, OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS,
            ANTIALIASED_QUALITY, FF_DONTCARE, ctypes.c_wchar_p("Microsoft YaHei"))
        if not self.hfont:
            raise OSError("CreateFontW failed")
        gdi32.SelectObject(self.hdc, self.hfont)

        bi = BITMAPINFO()
        bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.bmiHeader.biWidth = self.cellW
        bi.bmiHeader.biHeight = -self.cellH
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = 32
        bi.bmiHeader.biCompression = BI_RGB
        self.bits = ctypes.c_void_p()
        self.hbmp = gdi32.CreateDIBSection(self.hdc, ctypes.byref(bi), 0,
                                           ctypes.byref(self.bits), None, 0)
        if not self.hbmp:
            raise OSError("CreateDIBSection failed")
        gdi32.SelectObject(self.hdc, self.hbmp)
        gdi32.SetTextColor(self.hdc, 0x00FFFFFF)
        gdi32.SetBkColor(self.hdc, 0x00000000)
        gdi32.SetBkMode(self.hdc, OPAQUE)
        gdi32.SetTextAlign(self.hdc, TA_LEFT | TA_BASELINE)

        self.stride = self.cellW
        self.buf = ctypes.cast(self.bits, ctypes.POINTER(ctypes.c_ubyte))

    def close(self):
        if self.hbmp:
            gdi32.DeleteObject(self.hbmp)
        if self.hfont:
            gdi32.DeleteObject(self.hfont)
        if self.hdc:
            gdi32.DeleteDC(self.hdc)

    def render(self, ch):
        ctypes.memset(self.bits, 0, self.cellW * self.cellH * 4)
        wbuf = ctypes.create_unicode_buffer(ch, 1)
        if not gdi32.TextOutW(self.hdc, 0, self.baseline, wbuf, 1):
            return None
        size = wt.SIZE()
        gdi32.GetTextExtentPoint32W(self.hdc, wbuf, 1, ctypes.byref(size))
        adv = max(0, size.cx)

        minX, minY, maxX, maxY = self.cellW, self.cellH, -1, -1
        for y in range(self.cellH):
            base = y * self.stride * 4
            for x in range(self.cellW):
                if self.buf[base + x * 4] > 8:
                    if x < minX: minX = x
                    if y < minY: minY = y
                    if x > maxX: maxX = x
                    if y > maxY: maxY = y
        if maxX < 0:
            return (adv, 0, 0, 0, 0, 0, 0, b"")

        w = maxX - minX + 1
        h = maxY - minY + 1
        if w > MAX_DIM or h > MAX_DIM:
            return None
        alpha = bytearray(w * h)
        for y in range(h):
            src = (y + minY) * self.stride * 4 + minX * 4
            dst = y * w
            for x in range(w):
                alpha[dst + x] = self.buf[src + x * 4]

        # Entry metrics are BASELINE-RELATIVE, matching the stock fonts:
        #   l = 1 (left bearing), r = l + w
        #   b = baseline row  (stock: 13 / 18 / 29 for metric 16 / 19 / 30)
        #   t = b - h         (ink top above baseline)
        # Stock checks: stencil_14 'B' -> t=3 b=18 h=15; arial_10 'B' -> t=3 b=13 h=10.
        # The raw ink box inside our scratch cell must NOT be written here: doing so
        # put b beyond the row box (b=20 for metric=19) and pushed text down-left as
        # the advance accumulated.
        b_ref = self.baseline_ref
        l_out = 1
        r_out = min(100, l_out + w)
        t_out = max(0, min(100, b_ref - h))
        b_out = min(100, b_ref)
        return (adv, l_out, t_out, r_out, b_out, w, h, bytes(alpha))


def build_fff(entries, metric):
    """entries: list of (slot, adv, l, t, r, b, w, h, pix)"""
    out = bytearray()
    out += b"BORK"
    out += struct.pack("<H", len(entries))
    out.append(metric & 0xFF)
    out += b"\x00\x00"        # entries begin at offset 9
    for (slot, adv, l, t, r, b, w, h, _) in entries:
        out += struct.pack("<H5B", slot & 0xFFFF, min(adv, 255),
                           min(l, 100), min(t, 100), min(r, 100), min(b, 100))
    for (slot, adv, l, t, r, b, w, h, pix) in entries:
        out += bytes([w, h]) + pix
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description="TTF -> .fff 多字号生成器")
    ap.add_argument("--ttf", required=True)
    ap.add_argument("--chars", default=None)
    ap.add_argument("--chars-file", default=None)
    ap.add_argument("--groups", default="16:13,19:18,30:31",
                    help="metric:GDI尺寸 列表，如 16:13,19:18,30:31")
    ap.add_argument("--baselines", default="16:13,19:18,30:29",
                    help="metric:基线行 列表，取自同 metric 的原版字体（决定 t/b 字段）")
    ap.add_argument("--per-page", type=int, default=0,
                    help="每页字形上限；0=自动(按 128x128 纹理容量模拟打包)")
    ap.add_argument("--prefix", default="library\\language\\")
    ap.add_argument("--out", required=True, help="索引基名（页文件同目录）")
    args = ap.parse_args()

    chars = []
    if args.chars:
        chars.extend(args.chars)
    if args.chars_file:
        chars.extend(open(args.chars_file, encoding="utf-8").read())
    seen = set()
    uniq = [c for c in chars if not (c in seen or seen.add(c))]
    if not uniq:
        print("没有字符", file=sys.stderr)
        return 1

    groups = []
    for spec in args.groups.split(","):
        m, g = spec.split(":")
        groups.append((int(m), int(g)))

    baselines = {}
    for spec in args.baselines.split(","):
        m, b = spec.split(":")
        baselines[int(m)] = int(b)

    outdir = os.path.dirname(os.path.abspath(args.out)) or "."
    base = os.path.splitext(os.path.basename(args.out))[0]
    prefix = args.prefix.encode("ascii")

    def page_fits(entries, w_new, h_new):
        """Simulate the engine's 128x128 packing (sub_4A26F0):
             Source starts at 1; Source += w+1 per glyph; wrap when
             Source + w + 1 > 127; row height = tallest glyph in that row.
           Returns True if one more glyph still fits.
           entries are (slot, adv, l, t, r, b, w, h, pix)."""
        Source, y, rowH = 1, 0, 0
        for e in entries:
            w, h = e[6], e[7]
            if Source + w + 1 > 127:
                y += rowH
                Source = 1
                rowH = 0
            if y + h + 1 > 127:
                return False
            Source += w + 1
            rowH = max(rowH, h + 1)
        if Source + w_new + 1 > 127:
            y += rowH
            Source = 1
            rowH = 0
        if y + h_new + 1 > 127:
            return False
        return True

    # index[unicode] = list of (group, page, slot, adv)，每个字号组一项。
    # 之前只存单条导致后一组覆盖前一组（829 条全落到最后一组），故改为按组收集。
    index = {}
    group_pages = []    # per group: list of pages; page = list of entries

    for gi, (metric, gsize) in enumerate(groups):
        rz = Rasterizer(args.ttf, gsize, baselines.get(metric))
        pages = []
        cur = []
        slot = 0
        for c in uniq:
            r = rz.render(c)
            if r is None:
                continue
            adv, l, t, rt, bt, w, h, pix = r
            # Page capacity: a 128x128 texture holds only a limited number of
            # glyphs. Overfilling made glyphs overwrite each other -> solid blocks.
            over_cap = args.per_page and slot >= args.per_page
            no_room = (not over_cap) and cur and not page_fits(cur, w, h)
            if over_cap or no_room:
                pages.append(cur); cur = []; slot = 0
            slot += 1
            cur.append((slot, adv, l, t, rt, bt, w, h, pix))
            index.setdefault(ord(c), []).append((gi, len(pages), slot, adv))
        if cur:
            pages.append(cur)
        rz.close()
        group_pages.append((metric, pages))

    # 写页文件
    written = []
    for gi, (metric, pages) in enumerate(group_pages):
        for pi, page in enumerate(pages):
            data = build_fff(page, metric)
            fn = "chs_g%d_p%02d.fff" % (gi, pi)
            with open(os.path.join(outdir, fn), "wb") as f:
                f.write(data)
            written.append((gi, pi, fn, len(page), len(data), metric))

    # 写索引：每条 (unicode, group) 记录一条，DLL 按 rec.g 分发到各组。
    # 若只写一条（组无关），后一组会覆盖前一组，导致汉字全落到最后一组。
    all_recs = []
    for u in sorted(index):
        for (gi, pi, sl, adv) in index[u]:
            all_recs.append((u, gi, pi, sl, adv))

    idx_path = os.path.join(outdir, base + "_index.bin")
    with open(idx_path, "wb") as f:
        f.write(b"CHSI")
        f.write(struct.pack("<I", len(all_recs)))
        f.write(struct.pack("<H", len(groups)))
        f.write(struct.pack("<B", len(prefix)))
        f.write(prefix)
        for metric, pages in group_pages:
            f.write(struct.pack("<HH", metric, len(pages)))
        for (u, gi, pi, sl, adv) in all_recs:
            f.write(struct.pack("<IHHHB", u, gi, pi, sl, min(adv, 255)))
            f.write(b"\x00")

    print("组数=%d  唯一字形=%d  索引记录=%d" % (len(groups), len(index), len(all_recs)))
    for gi, (metric, pages) in enumerate(group_pages):
        tot = sum(len(p) for p in pages)
        print("  group %d: metric=%2d pages=%d glyphs=%d" % (gi, metric, len(pages), tot))
    print("索引: %s (%d B)" % (idx_path, os.path.getsize(idx_path)))
    print("页文件: %d 个" % len(written))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
