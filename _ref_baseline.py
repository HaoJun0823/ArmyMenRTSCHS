import sys, os, struct
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"G:\Projects\ArmyMenRTSCHS\Tools")
from gen_fff import Rasterizer

EX = r"I:\LocalGames\Army men Rts\_extract"

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

# 各字体的 Latin 基准: 'H'(0x48) 'B'(0x42) 'x'(0x78)
FONTS = {
    16: "font_arial_10.fff",
    19: "font_stencil_14.fff",
    30: "font_stencil_24.fff",
}
ref = {}
for metric, fn in FONTS.items():
    m, ent, gl = parse(os.path.join(EX, fn))
    rows = []
    for want in (0x42, 0x48, 0x78, 0x67):
        for (c, adv, l, t, r, b), (w, h) in zip(ent, gl):
            if c == want:
                rows.append((chr(c), adv, l, t, r, b, w, h))
                break
    print("metric=%d %s" % (m, fn))
    for ch, adv, l, t, r, b, w, h in rows:
        print("   '%s' adv=%2d l=%2d t=%2d r=%2d b=%2d | glyph %dx%d (r-l=%d b-t=%d)"
              % (ch, adv, l, t, r, b, w, h, r-l, b-t))
    # 用 'B' 作基准
    B = [x for x in rows if x[0] == 'B']
    if B:
        ref[m] = B[0]
    print()

print("=== 参考基准（'B' 的 b 作为基线在行盒中的位置）===")
for m, (ch, adv, l, t, r, b, w, h) in sorted(ref.items()):
    print("  metric=%2d: b_ref=%2d adv_ref=%2d" % (m, b, adv))

print()
print("=== 用 GDI 渲染 'B' 测墨迹位置（同尺寸）===")
for metric, gsize in ((16, 13), (19, 18), (30, 31)):
    rz = Rasterizer(r"C:\Windows\Fonts\msyh.ttc", gsize)
    r = rz.render("B")
    rz.close()
    if r:
        adv, l, t, rt, bt, w, h, pix = r
        print("  metric=%2d GDI=%2d: 'B' ink l=%d t=%d r=%d b=%d (墨迹 %dx%d)"
              % (metric, gsize, l, t, rt, bt, w, h))
