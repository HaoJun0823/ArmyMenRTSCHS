import sys, os, struct
sys.stdout.reconfigure(encoding='utf-8')

LANG = r"I:\LocalGames\Army Men\Army Men RTS STEAM\update\library\language"

def parse(path):
    d = open(path, "rb").read()
    n = struct.unpack_from("<H", d, 4)[0]
    m = d[6]
    o = 9
    ent = []
    for _ in range(n):
        c, adv, l, t, r, b = struct.unpack_from("<H5B", d, o)
        ent.append((c, adv, l, t, r, b)); o += 7
    gl = []
    for _ in range(n):
        w, h = d[o], d[o+1]; o += 2 + w*h
        gl.append((w, h))
    return m, ent, gl

# 引擎打包方式（sub_4A26F0）: 
#   Source 从 1 起, 每字 Source += w+1; 若 Source + w+1 > 127 则换行 (v68 += v66)
#   行高由该行最高字形决定
# → 实际容量取决于 128 宽能放多少列 × 128 高能放多少行
# 保守估算：按平均字形尺寸算
for gi in range(3):
    m, ent, gl = parse(os.path.join(LANG, "chs_g%d_p00.fff" % gi))
    tot = sum((w+1)*(h+1) for w, h in gl)
    avg_w = sum(w for w, h in gl)/len(gl)
    avg_h = sum(h for w, h in gl)/len(gl)
    print("g%d: metric=%d n=%d 平均字形 %.1fx%.1f 单页需 %d px (容量16384)"
          % (gi, m, len(gl), avg_w, avg_h, tot))

print()
print("=== 推算安全每页容量（按 128x128 网格模拟打包）===")
def simulate(gl):
    """模拟引擎打包: 返回 (放置数, 是否全部放下)"""
    Source = 1
    v68 = 0        # 当前行 y
    v66 = 0        # 当前行最高
    placed = 0
    for w, h in gl:
        if Source + w + 1 > 127:
            v68 += v66
            Source = 1
            v66 = 0
        if v68 + h + 1 > 127:
            break   # 放不下
        Source += w + 1
        if h + 1 > v66:
            v66 = h + 1
        placed += 1
    return placed

for gi in range(3):
    m, ent, gl = parse(os.path.join(LANG, "chs_g%d_p00.fff" % gi))
    n = simulate(gl)
    print("  g%d: 200 字形里能放下 %d 个 -> 安全页容量约 %d" % (gi, n, n))
