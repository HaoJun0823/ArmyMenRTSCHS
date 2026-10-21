import sys, os, json, subprocess
sys.stdout.reconfigure(encoding='utf-8')

# 路径全部相对本仓库；不再依赖 G:\Projects 工作副本。
# 前置条件：仓库根（游戏安装副本目录）内有 library\language\english.dat（原版英文资源，不入库）。
PROJ = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(PROJ, "translate")
BUILD = os.path.join(PROJ, "build_full")
DATTOOL = os.path.join(PROJ, "Tools", "dat_tool.py")
GENFFF = os.path.join(PROJ, "Tools", "gen_fff.py")
EN_DAT = os.path.join(PROJ, "library", "language", "english.dat")
MSYH = r"C:\Windows\Fonts\msyh.ttc"
os.makedirs(BUILD, exist_ok=True)

# ---- 1) 中文 english.dat ----
# 从原版 .dat 解出带 tag/结构的 JSON（缓存），再把 merged.json 应用进去并 GBK 打包。
en_json = os.path.join(BUILD, "en_base.json")
if not os.path.exists(en_json):
    if not os.path.exists(EN_DAT):
        sys.exit("缺少原版英文资源: %s（游戏安装目录内的 library\\language\\english.dat，不入库）" % EN_DAT)
    subprocess.run([sys.executable, DATTOOL, "unpack", EN_DAT, en_json, "--encoding", "latin1"], check=True)

rows = json.load(open(os.path.join(TR, "merged.json"), encoding="utf-8"))
print("合并译文: %d 条" % len(rows))

tsv = os.path.join(BUILD, "full.tsv")
with open(tsv, "w", encoding="utf-8", newline="") as f:
    for r in rows:
        zh = r["zh"].replace("\t", "\\t")
        f.write("%s\t%s\n" % (r["k"], zh))

zh_json = os.path.join(BUILD, "zh.json")
subprocess.run([sys.executable, DATTOOL, "apply", en_json, tsv, zh_json], check=True)

out_dat = os.path.join(BUILD, "english.dat")
subprocess.run([sys.executable, DATTOOL, "pack", zh_json, out_dat, "--encoding", "gbk"], check=True)
print("dat ->", out_dat, os.path.getsize(out_dat), "B")

# ---- 2) 中文字库 .fff + chs_index.bin ----
# --baselines 的 30:29 取自 font_stencil_24_resource.fff（metric 27 组另属一组，勿改）。
subprocess.run([sys.executable, GENFFF,
                "--ttf", MSYH,
                "--chars-file", os.path.join(TR, "chars.txt"),
                "--groups", "16:13,19:18,30:31",
                "--baselines", "16:13,19:18,30:29",
                "--out", os.path.join(BUILD, "chs.fff")], check=True)
print("font -> %s chs_g*_p*.fff + chs_index.bin" % BUILD)
