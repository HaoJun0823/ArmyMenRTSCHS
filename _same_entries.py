import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')

PROJ = r"G:\Projects\ArmyMenRTSCHS"
rows = json.load(open(os.path.join(PROJ, "translate", "merged.json"), encoding="utf-8"))

same = [r for r in rows if r["zh"] == r["en"]]
print("译文==原文 的 %d 条（apply 不计入 changed，属正常）:" % len(same))
for r in same:
    print("   %-52s %r" % (r["k"], r["en"][:30]))
