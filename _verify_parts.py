import sys, os, re
sys.stdout.reconfigure(encoding='utf-8')

TR = r"G:\Projects\ArmyMenRTSCHS\translate"
parts = ["part1", "part2", "part3", "part4", "part5"]

total_in = total_out = 0
all_ok = True
all_rows = []

for p in parts:
    fin = os.path.join(TR, p + ".in.tsv")
    fout = os.path.join(TR, p + ".out.tsv")
    if not os.path.exists(fout):
        print("%s: MISSING out" % p); all_ok = False; continue

    ins = open(fin, encoding="utf-8").read().split("\n")
    outs = open(fout, encoding="utf-8").read().split("\n")
    if ins and ins[-1] == "": ins.pop()
    if outs and outs[-1] == "": outs.pop()

    errs = []
    if len(ins) != len(outs):
        errs.append("line count %d vs %d" % (len(ins), len(outs)))

    ph_re = re.compile(r"\{[^{}]*\}")
    for i, (a, b) in enumerate(zip(ins, outs)):
        pa, _, va = a.partition("\t")
        pb, _, vb = b.partition("\t")
        if pa != pb:
            errs.append("path mismatch line %d: %r vs %r" % (i + 1, pa, pb))
            continue
        sa = sorted(ph_re.findall(va))
        sb = sorted(ph_re.findall(vb))
        if sa != sb:
            errs.append("placeholder mismatch %s: %s vs %s" % (pa, sa, sb))
        # 转义序列
        for esc in ("\\n", "\\r", "\\t"):
            if va.count(esc) != vb.count(esc):
                errs.append("escape %s mismatch %s" % (esc, pa))
        # GBK 可编码
        try:
            vb.encode("gbk")
        except Exception as e:
            errs.append("GBK fail %s: %s" % (pa, e))
        all_rows.append((pa, va, vb))
    total_in += len(ins)
    total_out += len(outs)
    status = "OK" if not errs else "FAIL(%d)" % len(errs)
    print("%s: in=%d out=%d %s" % (p, len(ins), len(outs), status))
    for e in errs[:5]:
        print("    ", e)
    if errs:
        all_ok = False

print()
print("总计 in=%d out=%d  all_ok=%s" % (total_in, total_out, all_ok))

# 统计唯一字符集（用于生成字库）
chars = set()
for _, _, vb in all_rows:
    s = vb.replace("\\n", "").replace("\\r", "").replace("\\t", "")
    s = re.sub(r"\{[^{}]*\}", "", s)
    for c in s:
        if ord(c) > 127:
            chars.add(c)
print("译文唯一非 ASCII 字符数: %d" % len(chars))

# 保存合并结果
import json
with open(os.path.join(TR, "merged.json"), "w", encoding="utf-8") as f:
    json.dump([{"k": k, "en": e, "zh": z} for k, e, z in all_rows], f,
              ensure_ascii=False, indent=1)
print("合并 -> merged.json (%d 条)" % len(all_rows))

with open(os.path.join(TR, "chars.txt"), "w", encoding="utf-8") as f:
    f.write("".join(sorted(chars)))
print("字符集 -> chars.txt")
