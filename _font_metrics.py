import sys, os, struct
sys.stdout.reconfigure(encoding='utf-8')

GAME = r"I:\LocalGames\Army Men\Army Men RTS STEAM"
EX = r"I:\LocalGames\Army men Rts\_extract"

# 主菜单按钮用的是哪个字体？从 if_fonts.cfg 的映射推断 + 日志里 glyph 的 metric/尺寸
print("=== 原版字体度量（metric = 行高）===")
for f in sorted(os.listdir(EX)):
    if not f.endswith(".fff"):
        continue
    d = open(os.path.join(EX, f), "rb").read()
    n = struct.unpack_from("<H", d, 4)[0]
    metric = d[6]
    # 统计字形高度
    o = 9
    for _ in range(n):
        o += 7
    hs = []
    for _ in range(n):
        w, h = d[o], d[o+1]
        if h: hs.append(h)
        o += 2 + w*h
    print("  %-32s count=%3d metric=%2d 字形高 %d..%d 常见=%d" %
          (f, n, metric, min(hs), max(hs),
           max(set(hs), key=hs.count)))

print("\n=== 我们生成的字体 ===")
ours = os.path.join(GAME, "update", "library", "language", "chs_p00.fff")
d = open(ours, "rb").read()
n = struct.unpack_from("<H", d, 4)[0]
print("  chs_p00.fff count=%d metric=%d" % (n, d[6]))

print("\n=== 日志中游戏的字体对象与字形高度 ===")
log = os.path.join(GAME, "scripts", "chs_debug.log")
if os.path.exists(log):
    txt = open(log, encoding="utf-8", errors="replace").read()
    for line in txt.splitlines():
        if "draw#" in line:
            print("  ", line[:110])
