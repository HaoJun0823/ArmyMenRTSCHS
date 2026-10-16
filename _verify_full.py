import sys, os, struct
sys.stdout.reconfigure(encoding='utf-8')

GAME = r"I:\LocalGames\Army Men\Army Men RTS STEAM"
SD = os.path.join(GAME, "scripts")
LANG = os.path.join(GAME, "update", "library", "language")

# ---- 精确模拟 C++ 的读取逻辑 ----
idx = open(os.path.join(SD, "chs_index.bin"), "rb").read()
assert idx[:4] == b"CHSI", idx[:4]
count, gcount = struct.unpack_from("<IH", idx, 4)
plen = idx[10]
prefix = idx[11:11+plen].decode("ascii")
off = 11 + plen
print("count=%d groupCount=%d prefix=%r" % (count, gcount, prefix))

groups = []
for i in range(gcount):
    metric, pages = struct.unpack_from("<HH", idx, off); off += 4
    groups.append((metric, pages))
print("groups:", groups)

recs = []
for i in range(count):
    u, g, p, s, adv = struct.unpack_from("<IHHHB", idx, off)
    off += 12
    recs.append((u, g, p, s, adv))
print("records=%d 消费=%d/%d %s" % (len(recs), off, len(idx), "OK" if off == len(idx) else "BAD"))

# ---- 每个 (group,page) 的槽位范围 ----
from collections import defaultdict
bypg = defaultdict(list)
for u, g, p, s, adv in recs:
    bypg[(g, p)].append((s, u, adv))

print("\n=== 页文件校验（用引擎语义：条目起点=9）===")
allok = True
for (g, p), items in sorted(bypg.items()):
    fn = os.path.join(LANG, "chs_g%d_p%02d.fff" % (g, p))
    if not os.path.exists(fn):
        print("  MISSING %s" % fn); allok = False; continue
    d = open(fn, "rb").read()
    n = struct.unpack_from("<H", d, 4)[0]
    metric = d[6]
    o = 9
    slots = []
    for _ in range(n):
        code, adv, l, t, r, b = struct.unpack_from("<H5B", d, o)
        slots.append(code); o += 7
    # 跳过字形
    for _ in range(n):
        w, h = d[o], d[o+1]; o += 2 + w*h
    ok = (o == len(d))
    want = sorted(s for s, _, _ in items)
    match = (slots == want)
    if not (ok and match):
        allok = False
    print("  g%d p%02d: metric=%2d count=%3d 消费=%s slots=%s" %
          (g, p, metric, n, "OK" if ok else "BAD(%d/%d)" % (o, len(d)),
           "MATCH" if match else "MISMATCH want=%s got=%s" % (want[:5], slots[:5])))

print("\n整体:", "ALL OK" if allok else "有问题")

# ---- metric 与组匹配 ----
print("\n=== metric 映射（引擎按字体 metric 选组）===")
for i, (m, pages) in enumerate(groups):
    print("  group %d metric=%d pages=%d" % (i, m, pages))
