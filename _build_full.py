import sys, os, json, subprocess
sys.stdout.reconfigure(encoding='utf-8')

PROJ = r"G:\Projects\ArmyMenRTSCHS"
TR = os.path.join(PROJ, "translate")
BUILD = os.path.join(PROJ, "build_full")
DATTOOL = r"I:\LocalGames\Army men Rts\Tools\dat_tool.py"
ENJSON = r"I:\LocalGames\Army men Rts\Tools\english.json"
os.makedirs(BUILD, exist_ok=True)

# merged.json: [{k,en,zh}]  ->  tsv for dat_tool apply
rows = json.load(open(os.path.join(TR, "merged.json"), encoding="utf-8"))
print("合并译文: %d 条" % len(rows))

tsv = os.path.join(BUILD, "full.tsv")
with open(tsv, "w", encoding="utf-8", newline="") as f:
    for r in rows:
        zh = r["zh"].replace("\t", "\\t")
        f.write("%s\t%s\n" % (r["k"], zh))
print("tsv ->", tsv)

zh_json = os.path.join(BUILD, "zh.json")
subprocess.run([r"C:\Python314\python.exe", DATTOOL, "apply", ENJSON, tsv, zh_json], check=True)

out_dat = os.path.join(BUILD, "english.dat")
subprocess.run([r"C:\Python314\python.exe", DATTOOL, "pack", zh_json, out_dat,
                "--encoding", "gbk"], check=True)
print("dat ->", out_dat, os.path.getsize(out_dat), "B")
