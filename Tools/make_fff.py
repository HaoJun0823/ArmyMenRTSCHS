#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Army Men RTS —— .fff 字体解析 / 生成器
======================================

格式依据（IDA 反编译 amrts.exe `sub_4A26F0`，已 round-trip 字节级验证）
----------------------------------------------------------------------
  [4B]  magic: 'BORK' (0x4B524F42 小端) = 类型2 / 'FONT' = 类型1
  [+]   count: 类型1 = u8, 类型2 = u16        (sub_4A26F0 @0x4a277e)
  [+1]  metric: u8                            (@0x4a2794)
  [+3]  跳过 3 字节                           (@0x4a27c1 v11 = v7+3)
  条目表 count × 7B:
        [u16 code][u8 adv][u8 a][u8 b][u8 c][u8 d]   (@0x4a27d6..0x4a2821)
        类型1 时 code 写回为 u8 存入 u16 槽位；类型2 为原生 u16
  字形数据 count ×:
        [u8 w][u8 h][w*h 字节 8bit alpha]     (@0x4a2884)
        加载时校验 w,h <= 0x64，否则 "Font file is corrupt"

运行时限制（决定为何必须走 DLL hook，见 README）
------------------------------------------------
  1. 字形查找表按 u8 索引，仅 256 槽：v53[*(u8*)v24] / v67[2*v34+72]
     → u16 汉字码(0x4E00+) 会被截断冲突，无法直塞
  2. 字形 w/h <= 100
  3. 字形最终 blit 进 128x128 纹理页：sub_449370(v31,128,128,1,...)

用法
----
  python make_fff.py info    <in.fff>
  python make_fff.py verify  <in.fff>            # 解析后重建，应 IDENTICAL
  python make_fff.py dump    <in.fff> <out.json> # 导出为可编辑 JSON
  python make_fff.py build   <in.json> <out.fff> # 由 JSON 重建

Python 3.8+，无第三方依赖。
"""
import argparse
import json
import struct
import sys

MAGIC_T1 = b"FONT"   # type1: u8 count / u8 code
MAGIC_T2 = b"BORK"   # type2: u16 count / u16 code
MAX_DIM = 0x64       # 100，加载器硬上限


class Fff:
    def __init__(self):
        self.magic = MAGIC_T2
        self.metric = 0
        self.entries = []   # list of dict(code, adv, a, b, c, d)
        self.glyphs = []    # list of dict(w, h, data_b64)

    # ---- 解析 ----
    @staticmethod
    def parse(data):
        f = Fff()
        magic = data[:4]
        if magic not in (MAGIC_T1, MAGIC_T2):
            raise ValueError("不是 .fff (magic=%r)" % magic)
        f.magic = magic
        off = 4
        if magic == MAGIC_T2:
            (count,) = struct.unpack_from("<H", data, off); off += 2
        else:
            count = data[off]; off += 1
        f.metric = data[off]; off += 1
        # Engine reader (sub_4A26F0) advances v7 by 3 total from data+6, i.e.
        # entries begin at data+9. So only 2 bytes are skipped after metric.
        f.skip2 = data[off:off + 2]; off += 2
        for _ in range(count):
            code, adv, a, b, c, d = struct.unpack_from("<H5B", data, off)
            f.entries.append(dict(code=code, adv=adv, a=a, b=b, c=c, d=d))
            off += 7
        for _ in range(count):
            w, h = data[off], data[off + 1]; off += 2
            if w > MAX_DIM or h > MAX_DIM:
                raise ValueError("字形尺寸超限 w=%d h=%d (上限 %d)" % (w, h, MAX_DIM))
            bm = data[off:off + w * h]; off += w * h
            f.glyphs.append(dict(w=w, h=h, data_b64=bm.hex()))
        f.rest = data[off:]           # 理论上应为空
        return f

    # ---- 序列化 ----
    def build(self):
        out = bytearray()
        out += self.magic
        n = len(self.entries)
        if self.magic == MAGIC_T2:
            out += struct.pack("<H", n)
        else:
            out += bytes([n & 0xFF])
        out += bytes([self.metric & 0xFF])
        out += getattr(self, "skip2", b"\x00\x00")   # entries begin at data+9
        for e in self.entries:
            out += struct.pack("<H5B", e["code"] & 0xFFFF, e["adv"] & 0xFF,
                               e["a"] & 0xFF, e["b"] & 0xFF, e["c"] & 0xFF, e["d"] & 0xFF)
        for g in self.glyphs:
            w, h = g["w"], g["h"]
            if w > MAX_DIM or h > MAX_DIM:
                raise ValueError("字形尺寸超限 w=%d h=%d" % (w, h))
            out += bytes([w, h])
            out += bytes.fromhex(g["data_b64"])
        return bytes(out)

    def to_json(self):
        return {"magic": self.magic.decode("latin1"), "metric": self.metric,
                "skip2": getattr(self, "skip2", b"\x00\x00").hex(),
                "entries": self.entries, "glyphs": self.glyphs}

    @staticmethod
    def from_json(o):
        f = Fff()
        f.magic = o["magic"].encode("latin1")
        f.metric = o["metric"]
        f.skip2 = bytes.fromhex(o.get("skip2", "0000"))
        f.entries = o["entries"]
        f.glyphs = o["glyphs"]
        return f


def cmd_info(a):
    d = open(a.path, "rb").read()
    f = Fff.parse(d)
    codes = [e["code"] for e in f.entries]
    print("文件      : %s (%d B)" % (a.path, len(d)))
    print("magic     : %s (类型%s)" % (f.magic.decode(), "2/u16" if f.magic == MAGIC_T2 else "1/u8"))
    print("count     : %d" % len(f.entries))
    print("metric    : %d" % f.metric)
    print("code 范围 : %d..%d (0x%X..0x%X)  去重=%d" %
          (min(codes), max(codes), min(codes), max(codes), len(set(codes))))
    ws = [g["w"] for g in f.glyphs]; hs = [g["h"] for g in f.glyphs]
    print("字形尺寸  : w %d..%d  h %d..%d" % (min(ws), max(ws), min(hs), max(hs)))
    print("尾部残留  : %d B" % len(getattr(f, "rest", b"")))


def cmd_verify(a):
    d = open(a.path, "rb").read()
    f = Fff.parse(d)
    rb = f.build()
    print("原始 %d B / 重建 %d B" % (len(d), len(rb)))
    print("IDENTICAL : %s" % (rb == d))
    if rb != d:
        for k in range(min(len(rb), len(d))):
            if rb[k] != d[k]:
                print("首个差异 @%d: 重建=%02X 原始=%02X" % (k, rb[k], d[k])); break
        else:
            print("  前缀一致，长度差 %d" % (len(d) - len(rb)))
    return 0 if rb == d else 2


def cmd_dump(a):
    d = open(a.path, "rb").read()
    f = Fff.parse(d)
    json.dump(f.to_json(), open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("导出 %d 字形 -> %s" % (len(f.entries), a.out))


def cmd_build(a):
    o = json.load(open(a.json, encoding="utf-8"))
    f = Fff.from_json(o)
    b = f.build()
    open(a.out, "wb").write(b)
    print("生成 %s (%d B, %d 字形)" % (a.out, len(b), len(f.entries)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=".fff 字体解析/生成（IDA 验证格式）")
    s = ap.add_subparsers(dest="cmd", required=True)
    p = s.add_parser("info");   p.add_argument("path"); p.set_defaults(func=cmd_info)
    p = s.add_parser("verify"); p.add_argument("path"); p.set_defaults(func=cmd_verify)
    p = s.add_parser("dump");   p.add_argument("path"); p.add_argument("out"); p.set_defaults(func=cmd_dump)
    p = s.add_parser("build");  p.add_argument("json"); p.add_argument("out"); p.set_defaults(func=cmd_build)
    args = ap.parse_args()
    sys.exit(args.func(args) or 0)
