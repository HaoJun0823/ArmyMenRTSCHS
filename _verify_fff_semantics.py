import sys, struct, glob, os
sys.stdout.reconfigure(encoding='utf-8')

# 引擎 sub_4A26F0 的真实语义（反汇编逐条确认）：
#   v7 = data+4                     (magic 之后)
#   BORK: count = *(u16*)v7 ; v7 += 2      -> v7 = data+6
#         metric = *v7                        -> data[6]
#         v11 = v7 + 3                        -> data+9  <<< 条目表起点 = 9
#   条目 7 字节: u16 code, u8 adv, u8 l, u8 t, u8 r, u8 b
#   字形: u8 w, u8 h, w*h 字节
#
# 我之前 make_fff.py / gen_fff.py 写成 metric(1)+3字节 => 条目起点 10，差 1 字节！

def parse_as_engine(d, hdr_before_entries):
    assert d[:4] == b"BORK"
    n = struct.unpack_from("<H", d, 4)[0]
    metric = d[6]
    off = hdr_before_entries
    entries = []
    for _ in range(n):
        code, adv, a, b, c, e = struct.unpack_from("<H5B", d, off)
        entries.append((code, adv, a, b, c, e))
        off += 7
    glyphs = []
    for _ in range(n):
        w, h = d[off], d[off+1]
        off += 2 + w*h
        glyphs.append((w, h))
    return n, metric, entries, glyphs, off

for f in sorted(glob.glob(r"I:\LocalGames\Army men Rts\_extract\*.fff")):
    d = open(f, "rb").read()
    for hdr in (9, 10):
        try:
            n, metric, entries, glyphs, off = parse_as_engine(d, hdr)
        except Exception as ex:
            print("%-34s hdr=%d EXC %s" % (os.path.basename(f), hdr, ex))
            continue
        ok = (off == len(d))
        codes = [e[0] for e in entries]
        ws = [g[0] for g in glyphs]; hs = [g[1] for g in glyphs]
        good = all(1 <= w <= 100 and h <= 100 for w, h in glyphs)
        print("%-34s hdr=%d 消费=%d/%d %s | count=%d metric=%d code %d..%d 字形w %d..%d h %d..%d %s" %
              (os.path.basename(f), hdr, off, len(d), "OK " if ok else "BAD",
               n, metric, min(codes), max(codes), min(ws), max(ws), min(hs), max(hs),
               "SANE" if good else "INSANE"))
    print()
