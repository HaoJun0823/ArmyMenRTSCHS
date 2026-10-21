import os, sys, shutil, glob
sys.stdout.reconfigure(encoding='utf-8')

# 用法: python _deploy_full.py [游戏根目录]
# 默认取本仓库所在目录（本仓库即游戏安装副本）。
PROJ = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else PROJ
BUILD = os.path.join(PROJ, "build_full")
SD = os.path.join(GAME, "scripts")
LANG = os.path.join(GAME, "update", "library", "language")

ASI_SRC = os.path.join(PROJ, "ArmyRTS_CHINESE", "Release", "ArmyRTS_CHINESE.dll")
if not os.path.exists(ASI_SRC):
    sys.exit("缺少插件产物 %s，请先 msbuild ArmyRTS_CHINESE\\ArmyRTS_CHINESE.vcxproj /p:Configuration=Release /p:Platform=Win32" % ASI_SRC)
for f in ("chs_index.bin", "english.dat"):
    if not os.path.exists(os.path.join(BUILD, f)):
        sys.exit("缺少 %s，请先运行 python _build_full.py" % f)
os.makedirs(LANG, exist_ok=True)

# 1) ASI + 配置 —— 放 scripts\（Ultimate ASI Loader 在此目录生效，已验证）
shutil.copy2(ASI_SRC, os.path.join(SD, "ArmyRTS_CHINESE.asi"))
shutil.copy2(os.path.join(PROJ, "ArmyRTS_CHINESE", "chs_config.ini"),
             os.path.join(SD, "chs_config.ini"))
print("asi ->", os.path.getsize(os.path.join(SD, "ArmyRTS_CHINESE.asi")), "B")

# 2) 索引
shutil.copy2(os.path.join(BUILD, "chs_index.bin"), os.path.join(SD, "chs_index.bin"))
print("index ->", os.path.getsize(os.path.join(SD, "chs_index.bin")), "B")

# 3) 字库页：只覆盖 chs_g*_p*.fff，其余同名文件不动
pages = sorted(glob.glob(os.path.join(BUILD, "chs_g*.fff")))
if not pages:
    sys.exit("build_full 下没有 chs_g*.fff，请先运行 python _build_full.py")
for pg in pages:
    shutil.copy2(pg, os.path.join(LANG, os.path.basename(pg)))
print("pages -> update\\library\\language\\  (%d 个)" % len(pages))

# 4) 中文 dat
shutil.copy2(os.path.join(BUILD, "english.dat"), os.path.join(LANG, "english.dat"))
print("english.dat ->", os.path.getsize(os.path.join(LANG, "english.dat")), "B")

# 5) 清日志（跟着 asi 走 scripts\）
log = os.path.join(SD, "chs_debug.log")
if os.path.exists(log):
    os.remove(log)

print("\n=== scripts\\ ===")
for e in sorted(os.listdir(SD)):
    print("   %-28s %d B" % (e, os.path.getsize(os.path.join(SD, e))))
print("=== update\\library\\language\\ ===")
for e in sorted(os.listdir(LANG)):
    print("   %-28s %d B" % (e, os.path.getsize(os.path.join(LANG, e))))
