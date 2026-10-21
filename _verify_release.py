import sys, os, struct, json
sys.stdout.reconfigure(encoding='utf-8')

# 校验仓库发布目录 Resource_CHS\（提交前自检，不依赖游戏安装目录）
PROJ = os.path.dirname(os.path.abspath(__file__))
LANG = os.path.join(PROJ, "Resource_CHS", "library", "language")

# ---- 1) 索引：精确模拟 chs_atlas.cpp 的读取 ----
idx = open(os.path.join(LANG, "chs_index.bin"), "rb").read()
assert idx[:4] == b"CHSI", idx[:4]
count, gcount = struct.unpack_from("<IH", idx, 4)
plen = idx[10]
prefix = idx[11:11 + plen].decode("ascii")
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
assert off == len(idx), "索引尾部有多余字节 -> DLL 读到脏数据"

# ---- 2) 页文件：槽位/条目一致，且 r <= adv（绘制截断不变量）----
from collections import defaultdict
bypg = defaultdict(list)
for u, g, p, s, adv in recs:
    bypg[(g, p)].append((s, u, adv))

print("\n=== 页文件校验（引擎语义：条目起点=9）===")
allok = True
rv = adv_mism = 0
for (g, p), items in sorted(bypg.items()):
    fn = os.path.join(LANG, "chs_g%d_p%02d.fff" % (g, p))
    if not os.path.exists(fn):
        print("  MISSING %s" % fn); allok = False; continue
    d = open(fn, "rb").read()
    n = struct.unpack_from("<H", d, 4)[0]
    metric = d[6]
    if metric != groups[g][0]:
        print("  g%d p%02d metric=%d != 索引声明 %d" % (g, p, metric, groups[g][0])); allok = False
    if n > groups[g][1]:
        pass
    ents = {}
    o = 9
    for i in range(n):
        code, adv, l, t, r, b = struct.unpack_from("<H5B", d, o); o += 7
        ents[code] = (adv, l, t, r, b)
    for i in range(n):
        w, h = d[o], d[o + 1]; o += 2 + w * h
    ok = (o == len(d))
    want = sorted(s for s, _, _ in items)
    match = (sorted(ents) == want)
    for s, u, iadv in items:
        adv, l, t, r, b = ents[s]
        if r > adv:
            rv += 1
        if adv != iadv:
            adv_mism += 1
    if not (ok and match):
        allok = False
    print("  g%d p%02d: metric=%2d count=%3d 消费=%s slots=%s" %
          (g, p, metric, n, "OK" if ok else "BAD(%d/%d)" % (o, len(d)),
           "MATCH" if match else "MISMATCH"))

print("\n=== 不变量 ===")
print("  r>adv 违例: %d（>0 会让整串后续字不显示）" % rv)
print("  页/索引 advance 不一致: %d（>0 会累积错位）" % adv_mism)
print("整体:", "ALL OK" if (allok and rv == 0 and adv_mism == 0) else "有问题")

# ---- 3) 文本覆盖闭环：dat 里的每个非 ASCII 字符都要有字形 ----
rows = json.load(open(os.path.join(PROJ, "translate", "merged.json"), encoding="utf-8"))
need = {ord(c) for r in rows for c in r["zh"] if ord(c) > 127}
have = {u for u, *_ in recs}
miss = sorted(need - have)
print("\n=== 字形覆盖 ===")
print("  译文需要 %d 个字形，字库提供 %d，缺失: %s" %
      (len(need), len(have), "".join(chr(m) for m in miss) or "无"))
chars = {ord(c) for c in open(os.path.join(PROJ, "translate", "chars.txt"), encoding="utf-8").read().strip()}
print("  chars.txt 与索引对称差:", "".join(map(chr, sorted(have ^ chars))) or "无")

# ---- 4) dat 内容与 merged.json 一致（防止只改源表忘了重打包）----
import subprocess
DATTOOL = os.path.join(PROJ, "Tools", "dat_tool.py")
tmp = os.path.join(PROJ, "build_full", "_verify_zh.json")
os.makedirs(os.path.dirname(tmp), exist_ok=True)
subprocess.run([sys.executable, DATTOOL, "unpack", os.path.join(LANG, "english.dat"),
                tmp, "--encoding", "gbk"], check=True, stdout=subprocess.DEVNULL)
obj = json.load(open(tmp, encoding="utf-8"))
dvals = {".".join(n["path"]): n["value"] for n in obj["nodes"] if n["value"] is not None}
# 源表经由 TSV 往返，反斜杠转义按 dat_tool.apply 的既定规则还原
# （"\\t"->TAB、"\\n"->LF）；这与已发布 V1 包的行为一致，属管线语义，不是回归。
def norm(s):
    return s.replace("\\t", "\t").replace("\\n", "\n")
bad = [r["k"] for r in rows if dvals.get(r["k"]) != norm(r["zh"])]
print("\n=== dat vs merged.json（按 TSV 转义规则归一）===")
print("  叶子 %d 条，键齐全: %s，与源表不一致: %s" % (
    len(dvals),
    all(r["k"] in dvals for r in rows),
    bad or "无"))

sys.exit(0 if (allok and rv == 0 and adv_mism == 0 and not miss and not bad) else 1)
