import sys, os, struct
sys.stdout.reconfigure(encoding='utf-8')

EX = r"I:\LocalGames\Army men Rts\_extract"

def metric_of(p):
    d = open(p, "rb").read()
    return struct.unpack_from("<H", d, 4)[0], d[6]

print("=== 游戏字体 metric ===")
for f in sorted(os.listdir(EX)):
    if f.endswith(".fff"):
        n, m = metric_of(os.path.join(EX, f))
        print("  %-32s count=%3d metric=%d" % (f, n, m))

# 对应关系（if_fonts.cfg）:
#   System/Console/WindowTitle/Tiny/Button/HeaderSmall -> font_arial_10.fff (metric 16)
#   Debriefing                                          -> font_stencil_14.fff (metric 19)
#   Movie/Resource                                      -> font_stencil_24.fff  (metric 30)
print()
print("=== 字号映射（metric -> 建议 GDI size）===")
print("  metric 16 (arial_10, 拉丁高10) -> GDI 13")
print("  metric 19 (stencil_14, 拉丁高15) -> GDI 18~19")
print("  metric 30 (stencil_24, 拉丁高26) -> GDI 28")
