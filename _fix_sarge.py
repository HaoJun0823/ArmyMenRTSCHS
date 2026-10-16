import sys, os, json, re
sys.stdout.reconfigure(encoding='utf-8')

TR = r"G:\Projects\ArmyMenRTSCHS\translate"
merged = os.path.join(TR, "merged.json")

rows = json.load(open(merged, encoding="utf-8"))
n = 0
for r in rows:
    if "萨奇" in r["zh"]:
        r["zh"] = r["zh"].replace("萨奇", "中士")
        n += 1
print("替换 萨奇 -> 中士 : %d 条" % n)
for r in rows:
    if "中士" in r["zh"]:
        print("   %-46s %s" % (r["k"], r["zh"][:46]))

json.dump(rows, open(merged, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("已写回", merged)

# 同步更新各分片 out.tsv，保持一致
for part in ("part1", "part2", "part3", "part4", "part5"):
    p = os.path.join(TR, part + ".out.tsv")
    if not os.path.exists(p):
        continue
    txt = open(p, encoding="utf-8").read()
    if "萨奇" in txt:
        txt = txt.replace("萨奇", "中士")
        open(p, "w", encoding="utf-8", newline="").write(txt)
        print("  已更新", part + ".out.tsv")
