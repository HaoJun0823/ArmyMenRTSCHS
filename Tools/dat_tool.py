#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Army Men RTS —— language .dat (DOCB) 解包 / 打包工具
====================================================

格式依据（重要，勿臆测）
------------------------
本工具的二进制规则来自 **IDA Pro 对 amrts.exe 的权威反编译**（函数 `sub_4E6180`，
由 `sub_4E6300` 加载 `library\\language\\<name>.dat` 后循环调用），并用
**字节级 round-trip 验证**：解析 english.dat 后重新序列化，与原始字节 100% 一致
（34334 字节，范围 [0x36, 0x8654)）。

注意：1 代源码（Army Men\\ArmyMen\\src）**不包含** DOCB 字符串表实现，
因此格式并非来自 1 代源码，而是来自本作 exe 的逆向 + 往返校验。

二进制布局
----------
文件 = [44 字节头] + [blob] + [12 字节尾]

头（44B）：
    'DOCB' | u32 version(=1) | u32 blockCount(=2) | 目录项...
    内含两个块声明名 "Stats 1.0" / "Database 1.0"（见 sub_4E6300）
    以及 u32 记录数、u32 字节数，用于分配索引表（8 字节/条，随后 qsort 二分查找）

blob（核心，偏移 0x36 起）：
    节点 = type:u8, nameLen:u8, name[nameLen] （nameLen 已含结尾 NUL）
           随后按 2 字节对齐填充：pad = ((nameLen + 1) & 0xFE) - nameLen
    type=6  容器：紧跟 u16 childCount，随后递归 childCount 个子节点
    type=4  叶子：紧跟 u16 vlen（= 值字节数 + 2）、u16 tag、value[vlen-2]
                  末尾填充 pad = (((vlen + 1) & 0xFE) + 2) - (2 + vlen)
    type 其他：游戏会报 "Bad type %d"（见 sub_4E6180）

tag 说明：叶子值的 u16 tag 含义未逆向（疑似值类型/格式标记），
    工具 **原样保留**，确保往返无损。

尾（12B）：另一块结构，工具原样保留。

游戏查值方式：路径每段算 CRC32（sub_4D9A30，多项式 0x04C11DB7）后
    在排序索引里二分查找 —— 因此 **节点名（键）绝不可翻译，只能翻译叶子值**。

用法
----
    python dat_tool.py info    english.dat
    python dat_tool.py unpack  english.dat  out.json
    python dat_tool.py pack    out.json     rebuilt.dat
    python dat_tool.py export  out.json     strings.tsv      # 导出待翻译
    python dat_tool.py apply   out.json     strings.tsv  translated.json  [--encoding gbk]
    python dat_tool.py verify  english.dat                   # 往返自检（应输出 IDENTICAL: True）

Python 3.8+，无第三方依赖。
"""

import argparse
import base64
import json
import os
import struct
import sys

MAGIC = b"DOCB"
HEADER_SIZE = 44
TAIL_SIZE = 12           # 尾部块结构，原样保留
DEFAULT_BLOB_START = 0x36
DEFAULT_ENCODING = "latin1"   # 原文件为 8-bit CP1252/latin1；翻译中文时用 gbk


# ---------------------------------------------------------------- 解析

class Dat:
    def __init__(self, raw):
        if raw[:4] != MAGIC:
            raise ValueError("不是 DOCB 文件（magic=%r）" % raw[:4])
        self.raw = raw
        self.header = raw[:HEADER_SIZE]
        self.tail = raw[len(raw) - TAIL_SIZE:] if len(raw) > HEADER_SIZE + TAIL_SIZE else b""
        self.blob_start = DEFAULT_BLOB_START
        # header(44) 与 blob(0x36) 之间存在固定间隙，必须原样保留，否则整体偏移错位
        self.pre = raw[HEADER_SIZE:self.blob_start]
        # blob = [blob_start, len(raw)-TAIL_SIZE)
        self.blob_end = len(raw) - TAIL_SIZE
        self.nodes = []          # list of (path:list[str], value|None, tag|None)
        self.parse_ok = False
        self.end = self.blob_start

    # ---- 解析 ----
    def parse(self, encoding=DEFAULT_ENCODING):
        N = self.blob_end
        dat = self.raw
        p = [self.blob_start]
        nodes = self.nodes

        def node(path):
            o = p[0]
            if o + 2 > N:
                return False
            t = dat[o]
            ln = dat[o + 1]
            ns = o + 2
            if ns + ln > N or ln == 0:
                return False
            name = dat[ns:ns + ln].decode(encoding, "replace")
            if not name.endswith("\x00"):
                return False
            key = name[:-1]
            p[0] = ns + ((ln + 1) & 0xFFFFFFFE)
            if t == 4:
                vp = p[0]
                if vp + 4 > N:
                    return False
                vlen = dat[vp] | (dat[vp + 1] << 8)
                tag = struct.unpack_from("<H", dat, vp + 2)[0]
                vlen -= 2
                vs = vp + 4
                if vlen < 0 or vs + vlen > N:
                    return False
                val = dat[vs:vs + vlen].decode(encoding, "replace")
                p[0] = vp + ((((vlen + 2) + 1) & 0xFFFFFFFE) + 2)
                nodes.append((path + [key], val, tag))
                return True
            elif t == 6:
                cp = p[0]
                if cp + 2 > N:
                    return False
                cc = dat[cp] | (dat[cp + 1] << 8)
                p[0] = cp + 2
                nodes.append((path + [key], None, None))
                for _ in range(cc):
                    if not node(path + [key]):
                        return False
                return True
            return False

        if not node([]):
            self.parse_ok = False
            return False
        # 顶层可能还有并列节点，继续读到 blob 结束
        while p[0] < N:
            if not node([]):
                break
        self.end = p[0]
        self.parse_ok = True
        return True

    # ---- 序列化（按树递归，严格匹配原序）----
    def serialize(self, encoding=DEFAULT_ENCODING, on_error="replace"):
        """on_error: 'replace'(不可编码字符->?) / 'strict'(抛异常) / 'ignore'(丢弃)"""
        # 建树：path -> (value, tag)；children[path] = 直接子节点列表（保持原顺序）
        order = []            # 前序节点顺序（与 self.nodes 一致）
        valmap = {}
        for (path, val, tag) in self.nodes:
            valmap[tuple(path)] = (val, tag)
        children = {}
        for (path, val, tag) in self.nodes:
            parent = tuple(path[:-1])
            children.setdefault(parent, []).append(tuple(path))
        roots = children.get((), [])

        buf = bytearray()
        stats = {"replaced": 0, "paths": []}

        def emit(path_tuple):
            name = path_tuple[-1] if path_tuple else ""
            val, tag = valmap.get(path_tuple, (None, None))
            t = 6 if val is None else 4
            nb = name.encode(encoding, on_error) + b"\x00"
            ln = len(nb)
            buf.append(t)
            buf.append(ln)
            buf.extend(nb)
            buf.extend(b"\x00" * (((ln + 1) & 0xFFFFFFFE) - ln))
            if val is None:
                kids = children.get(path_tuple, [])
                buf.extend(struct.pack("<H", len(kids)))
                for k in kids:
                    emit(k)
            else:
                vb = val.encode(encoding, on_error)
                try:
                    if val.encode(encoding, "strict") != vb:
                        stats["replaced"] += 1
                        if len(stats["paths"]) < 20:
                            stats["paths"].append(".".join(path_tuple))
                except UnicodeEncodeError:
                    stats["replaced"] += 1
                    if len(stats["paths"]) < 20:
                        stats["paths"].append(".".join(path_tuple))
                vlen = len(vb) + 2
                buf.extend(struct.pack("<H", vlen))
                buf.extend(struct.pack("<H", tag if tag is not None else 0))
                buf.extend(vb)
                buf.extend(b"\x00" * ((((vlen + 1) & 0xFFFFFFFE) + 2) - (2 + vlen)))

        for r in roots:
            emit(r)
        self.last_ser_stats = stats
        return bytes(buf)

    def rebuild(self, encoding=DEFAULT_ENCODING, on_error="replace", pad_to=None):
        """Rebuild the file.

        header[0x30] holds the DATA-REGION size, measured from 0x34 to len-12.
        The blob itself starts at 0x36, so:
            data_region = (blob_start - 0x34) + len(blob)
        The engine walks the directory using this value; if the rewritten blob is
        SHORTER, the reader runs past EOF and aborts with
        "Failed reading N bytes from block file". Therefore pad the blob back to
        its original size and always resync 0x30.

        pad_to: original BLOB size (blob_end - blob_start).
        """
        body = self.serialize(encoding, on_error)
        if pad_to is not None and len(body) < pad_to:
            body = body + b"\x00" * (pad_to - len(body))
        out = bytearray(self.header + self.pre + body + self.tail)
        data_region = (self.blob_start - 0x34) + len(body)
        struct.pack_into("<I", out, 0x30, data_region)
        return bytes(out)

    # ---- JSON ----
    def to_json(self):
        return {
            "format": "amrts-docb-language",
            "header_b64": base64.b64encode(self.header).decode("ascii"),
            "pre_b64": base64.b64encode(self.pre).decode("ascii"),
            "tail_b64": base64.b64encode(self.tail).decode("ascii"),
            "blob_start": self.blob_start,
            "data_size": self.blob_end - self.blob_start,
            "nodes": [
                {"path": p, "value": v, "tag": t}
                for (p, v, t) in self.nodes
            ],
        }

    @staticmethod
    def from_json(obj, original_size=None):
        d = Dat.__new__(Dat)
        d.header = base64.b64decode(obj["header_b64"])
        d.pre = base64.b64decode(obj.get("pre_b64", ""))
        d.tail = base64.b64decode(obj.get("tail_b64", ""))
        d.blob_start = obj.get("blob_start", DEFAULT_BLOB_START)
        d.data_size = obj.get("data_size")   # original data-region size, for padding
        d.blob_end = d.blob_start + (obj.get("data_size") or 0)
        d.nodes = []
        for it in obj["nodes"]:
            path = it["path"]
            val = it["value"]
            tag = it.get("tag")
            d.nodes.append((path, val, tag))
        d.raw = b""
        d.end = 0
        d.parse_ok = True
        return d


# ---------------------------------------------------------------- 命令

def cmd_info(args):
    d = Dat(open(args.dat, "rb").read())
    ok = d.parse(encoding=args.encoding)
    size = len(d.raw)
    leaves = [x for x in d.nodes if x[1] is not None]
    print("文件        : %s" % args.dat)
    print("大小        : %d 字节 (0x%X)" % (size, size))
    print("头          : %d 字节" % len(d.header))
    print("blob        : [0x%X, 0x%X)  %d 字节" % (d.blob_start, d.blob_end, d.blob_end - d.blob_start))
    print("尾          : %d 字节" % len(d.tail))
    print("解析        : %s  (结束于 0x%X, 目标 0x%X)" % ("成功" if ok else "失败", d.end, d.blob_end))
    print("节点总数    : %d" % len(d.nodes))
    print("叶子(可翻译): %d" % len(leaves))
    print("容器        : %d" % (len(d.nodes) - len(leaves)))
    # 顶层结构
    tops = [x for x in d.nodes if len(x[0]) == 1]
    print("顶层节点    : %s" % ", ".join("%s(%s)" % (x[0][0], "容器" if x[1] is None else "值") for x in tops[:20]))


def cmd_unpack(args):
    raw = open(args.dat, "rb").read()
    d = Dat(raw)
    if not d.parse(encoding=args.encoding):
        print("解析失败", file=sys.stderr)
        return 1
    obj = d.to_json()
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    leaves = sum(1 for x in d.nodes if x[1] is not None)
    print("解包完成: %s -> %s" % (args.dat, args.json))
    print("  节点 %d 个（叶子 %d 个可翻译），结束于 0x%X" % (len(d.nodes), leaves, d.end))
    return 0


def cmd_pack(args):
    obj = json.load(open(args.json, encoding="utf-8"))
    d = Dat.from_json(obj)
    # Auto-pad to the ORIGINAL data-region size: the engine reads the directory
    # using header[0x30], so a shorter blob would make it read past EOF.
    pad_to = None if args.no_pad else getattr(d, "data_size", None)
    out = d.rebuild(encoding=args.encoding, on_error=args.on_error, pad_to=pad_to)
    with open(args.dat, "wb") as f:
        f.write(out)
    print("打包完成: %s -> %s (%d 字节, 编码=%s)" % (args.json, args.dat, len(out), args.encoding))
    if pad_to:
        print("  数据区补齐到 %d 字节, 头部 0x30 已同步" % pad_to)
    st = getattr(d, "last_ser_stats", None)
    if st and st["replaced"]:
        print("  警告: %d 条值含目标编码无法表示的字符，已按 --on-error=%s 处理" % (st["replaced"], args.on_error))
        print("  示例路径: %s" % ", ".join(st["paths"][:5]))
        print("  提示: 原文含 CP1252 专有字符(如 ®)，GBK 不支持；建议在 tsv 里改写成 (R) 等 ASCII 近似")
    return 0


def cmd_export(args):
    """导出待翻译表：TSV  path <TAB> value"""
    obj = json.load(open(args.json, encoding="utf-8"))
    d = Dat.from_json(obj)
    rows = [(x[0], x[1]) for x in d.nodes if x[1] is not None]
    with open(args.tsv, "w", encoding="utf-8", newline="") as f:
        f.write("# path\tvalue\t(注释：path 是游戏内部键，不可翻译；只改第三列)\n")
        f.write("# 共 %d 条\n" % len(rows))
        for path, val in rows:
            f.write("%s\t%s\n" % (".".join(path), val.replace("\t", "\\t").replace("\n", "\\n")))
    print("导出 %d 条 -> %s" % (len(rows), args.tsv))
    return 0


def cmd_apply(args):
    """把翻译后的 TSV 应用回 JSON（只替换值，键与 tag 不动）"""
    obj = json.load(open(args.json, encoding="utf-8"))
    d = Dat.from_json(obj)
    trans = {}
    with open(args.tsv, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            key = parts[0]
            val = parts[1].replace("\\t", "\t").replace("\\n", "\n")
            trans[key] = val
    changed = 0
    for i, (path, val, tag) in enumerate(d.nodes):
        if val is None:
            continue
        k = ".".join(path)
        if k in trans and trans[k] != val:
            d.nodes[i] = (path, trans[k], tag)
            changed += 1
    out_obj = d.to_json()
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, ensure_ascii=False, indent=1)
    print("应用翻译: 命中 %d / %d 条 -> %s" % (changed, len(trans), args.out))
    return 0


def cmd_verify(args):
    """往返自检：解析后重建，必须与原始字节完全一致"""
    raw = open(args.dat, "rb").read()
    d = Dat(raw)
    if not d.parse(encoding=args.encoding):
        print("解析失败", file=sys.stderr)
        return 1
    rebuilt = d.rebuild(encoding=args.encoding, on_error="strict")
    orig_blob = raw[d.blob_start:d.blob_end]
    new_blob = d.serialize(encoding=args.encoding, on_error="strict")
    ok = (new_blob == orig_blob)
    print("blob 原始 : %d 字节 [0x%X,0x%X)" % (len(orig_blob), d.blob_start, d.blob_end))
    print("blob 重建 : %d 字节" % len(new_blob))
    print("解析结束  : 0x%X (目标 0x%X)" % (d.end, d.blob_end))
    print("IDENTICAL : %s" % ok)
    if not ok:
        for k in range(min(len(new_blob), len(orig_blob))):
            if new_blob[k] != orig_blob[k]:
                print("首个差异 +%d (0x%X): 重建=%02X 原始=%02X" % (k, d.blob_start + k, new_blob[k], orig_blob[k]))
                break
        else:
            print("  前缀一致，长度差 %d" % (len(orig_blob) - len(new_blob)))
    return 0 if ok else 2


def main():
    ap = argparse.ArgumentParser(description="Army Men RTS language .dat (DOCB) 解包/打包工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info", help="查看 .dat 结构信息")
    p.add_argument("dat")
    p.add_argument("--encoding", default=DEFAULT_ENCODING, help="原文编码，默认 latin1；GBK 包用 gbk")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("unpack", help=".dat -> .json（保留 tag，无损）")
    p.add_argument("dat"); p.add_argument("json")
    p.add_argument("--encoding", default=DEFAULT_ENCODING, help="原文编码，默认 latin1；GBK 包用 gbk")
    p.set_defaults(func=cmd_unpack)

    p = sub.add_parser("pack", help=".json -> .dat")
    p.add_argument("json"); p.add_argument("dat")
    p.add_argument("--encoding", default=DEFAULT_ENCODING, help="值编码，默认 latin1；中文用 gbk")
    p.add_argument("--on-error", default="replace", choices=["replace", "strict", "ignore"],
                   help="目标编码无法表示字符时的处理，默认 replace(->?)")
    p.add_argument("--no-pad", action="store_true",
                   help="不把数据区补齐到原始大小（默认补齐，避免头部尺寸失配崩溃）")
    p.set_defaults(func=cmd_pack)

    p = sub.add_parser("export", help=".json -> .tsv（待翻译表，只翻值）")
    p.add_argument("json"); p.add_argument("tsv"); p.set_defaults(func=cmd_export)

    p = sub.add_parser("apply", help=".tsv 翻译 -> 新 .json")
    p.add_argument("json"); p.add_argument("tsv"); p.add_argument("out")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("verify", help="往返自检，应输出 IDENTICAL: True")
    p.add_argument("dat")
    p.add_argument("--encoding", default=DEFAULT_ENCODING)
    p.set_defaults(func=cmd_verify)

    args = ap.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
