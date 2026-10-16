import sys, os, struct
sys.stdout.reconfigure(encoding='utf-8')

EX = r"I:\LocalGames\Army men Rts\_extract"

# sub_4A26F0 的打包逻辑（IDA 反汇编确认）：
#   Source 从 1 开始，每字形 Source += w+1
#   若 Source + w + 1 > 127 则换行：v68 += v66(本行高); Source = 1; v66 = 0
#   顶点：*((float*)glyph+6) = Source*0.0078125 + surface.u0
#         *((float*)glyph+7) = v68   *0.0078125 + surface.v0
#         *((float*)glyph+8) = (Source+w) *0.0078125 + surface.u0
#         *((float*)glyph+9) = (v68+h) *0.0078125 + surface.v0
# 0.0078125 = 1/128
#
# 关键：运行时字形记录里的 UV 是【加载时算出来的】，不是 .fff 里的。
# 所以 .fff 里我只提供 (w,h) 和像素，引擎负责算 UV —— 这一点已由
# 日志里的 tex=NN 和 glyph 指针非空证实。
#
# 那么"实心方块"最可能是：像素内容本身有问题，或纹理上传格式不对。

d = open(os.path.join(EX, "font_stencil_14.fff"), "rb").read()
n = struct.unpack_from("<H", d, 4)[0]
o = 9
ent = []
for _ in range(n):
    c, adv, l, t, r, b = struct.unpack_from("<H5B", d, o)
    ent.append((c, adv, l, t, r, b)); o += 7

# 找 'B' (0x42)，模拟引擎打包，算出它的 UV，反推像素在纹理里的位置
Source, y, rowH = 1, 0, 0
target = None
for i in range(n):
    c, adv, l, t, r, b = ent[i]
    w, h = d[o], d[o+1]
    if Source + w + 1 > 127:
        y += rowH; Source = 1; rowH = 0
    if c == 0x42:
        u0 = Source * 0.0078125
        v0 = y * 0.0078125
        u1 = (Source + w) * 0.0078125
        v1 = (y + h) * 0.0078125
        target = (w, h, u0, v0, u1, v1)
        px = d[o+2:o+2+w*h]
        break
    Source += w + 1
    rowH = max(rowH, h + 1)
    o += 2 + w*h

w, h, u0, v0, u1, v1 = target
print("原版 'B': w=%d h=%d" % (w, h))
print("  模拟 UV: u0=%.4f v0=%.4f u1=%.4f v1=%.4f" % (u0, v0, u1, v1))
print("  换算像素: x %d..%d, y %d..%d" % (u0*128, u1*128, v0*128, v1*128))
print()
print("=== 该字形像素统计 ===")
print("  非零像素: %d / %d" % (sum(1 for b in px if b), len(px)))
print("  值分布 top: %s" % sorted(set(px))[:10])
print("  是否含 255(纯白实心): %s" % (255 in px))
