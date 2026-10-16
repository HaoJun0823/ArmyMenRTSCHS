import os, sys, shutil, glob, json
sys.stdout.reconfigure(encoding='utf-8')

GAME = r"I:\LocalGames\Army Men\Army Men RTS STEAM"
PROJ = r"G:\Projects\ArmyMenRTSCHS"
BUILD = os.path.join(PROJ, "build_full")
SD = os.path.join(GAME, "scripts")
LANG = os.path.join(GAME, "update", "library", "language")
os.makedirs(LANG, exist_ok=True)

p = None
# 1) ASI + 配置 —— 放 scripts\（Ultimate ASI Loader 在此目录生效，已验证）
shutil.copy2(os.path.join(PROJ, "ArmyRTS_CHINESE", "Release", "ArmyRTS_CHINESE.dll"),
             os.path.join(SD, "ArmyRTS_CHINESE.asi"))
shutil.copy2(os.path.join(PROJ, "ArmyRTS_CHINESE", "chs_config.ini"),
             os.path.join(SD, "chs_config.ini"))
print("asi ->", os.path.getsize(os.path.join(SD, "ArmyRTS_CHINESE.asi")), "B")

# 2) 索引
shutil.copy2(os.path.join(BUILD, "chs_index.bin"), os.path.join(SD, "chs_index.bin"))
print("index ->", os.path.getsize(os.path.join(SD, "chs_index.bin")), "B")

# 3) 清掉旧的 .fff（旧单字号 + 旧命名），再放新的 15 页
trash = os.path.join(PROJ, "_trash", "fff_old")
os.makedirs(trash, exist_ok=True)
for old in glob.glob(os.path.join(LANG, "chs_*.fff")) + glob.glob(os.path.join(SD, "chs_*.fff")):
    dst = os.path.join(trash, os.path.basename(old))
    if os.path.exists(dst):
        os.remove(dst)
    shutil.move(old, dst)
    print("  moved old:", os.path.basename(old))

pages = sorted(glob.glob(os.path.join(BUILD, "chs_g*.fff")))
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
