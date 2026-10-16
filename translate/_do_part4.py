# -*- coding: utf-8 -*-
"""Part 4 (multiplayer) EN -> zh-CN translation with self-checks."""
import io, os, re, sys

BASE = r"G:\Projects\ArmyMenRTSCHS\translate"
IN_P = os.path.join(BASE, "part4.in.tsv")
OUT_P = os.path.join(BASE, "part4.out.tsv")

# path -> Chinese translation. Path column is NEVER modified.
TR = {
"multiplayer.session.baduser.title": "名称已被占用",
"multiplayer.session.baduser.message": "已有玩家使用该名称",
"multiplayer.session.create": "创建游戏",
"multiplayer.session.joined": "已加入房间",
"multiplayer.session.title": "多人游戏",
"multiplayer.session.addressbook": "地址簿",
"multiplayer.session.created": "房间已创建",
"multiplayer.session.local": "本地",
"multiplayer.session.messages.joinfail.title": "加入失败",
"multiplayer.session.messages.joinfail.message": "无法加入该房间",
"multiplayer.session.messages.nosession.title": "未选房间",
"multiplayer.session.messages.nosession.message": "未选择房间，请先选择一个房间再加入。",
"multiplayer.session.messages.createfail.title": "创建失败",
"multiplayer.session.messages.createfail.message": "无法创建新房间",
"multiplayer.session.createwindow.title": "创建游戏",
"multiplayer.session.createwindow.subtitle": "请输入游戏名称。",
"multiplayer.session.badsessionname.title": "游戏名称无效",
"multiplayer.session.badsessionname.message": "游戏名称至少需要 3 个字符",
"multiplayer.session.join": "加入",
"multiplayer.session.sessionlocked.title": "游戏已锁定",
"multiplayer.session.sessionlocked.message": "该房间已锁定，无法进入",
"multiplayer.session.sessionexists.title": "房间已存在",
"multiplayer.session.sessionexists.message": "服务器上已存在同名房间",
"multiplayer.session.sessionmigratefailed.title": "迁移失败",
"multiplayer.session.sessionmigratefailed.message": "无法迁移到新的主机",
"multiplayer.session.servermigratefailed.abort": "中止",
"multiplayer.session.servermigratefailed.title": "迁移失败",
"multiplayer.session.servermigratefailed.message": "游戏中的其他玩家均无法成为主机",
"multiplayer.session.servermigratefailed.continue": "继续",
"multiplayer.session.sessionfull.title": "房间已满",
"multiplayer.session.sessionfull.message": "该房间玩家人数已达上限",
"multiplayer.session.changename": "修改名称",
"multiplayer.setup.locked": "游戏现已锁定",
"multiplayer.setup.selectmission.players": "最多 {1:d} 名玩家",
"multiplayer.setup.selectmission.title": "选择任务",
"multiplayer.setup.selectmission.map": "地图",
"multiplayer.setup.host.lock": "锁定游戏",
"multiplayer.setup.host.mission": "选择任务",
"multiplayer.setup.host.addai": "添加电脑玩家",
"multiplayer.setup.teams.1": "Bravo",
"multiplayer.setup.teams.0": "Alpha",
"multiplayer.setup.teams.3": "Delta",
"multiplayer.setup.teams.2": "Charlie",
"multiplayer.setup.teams.5": "Foxtrot",
"multiplayer.setup.teams.4": "Echo",
"multiplayer.setup.teams.7": "Hotel",
"multiplayer.setup.teams.6": "Golf",
"multiplayer.setup.titlebar.players": "玩家",
"multiplayer.setup.titlebar.chat": "聊天",
"multiplayer.setup.choosecolor": "选择颜色",
"multiplayer.setup.missionname": "任务名称",
"multiplayer.setup.error.havemission": "{1:s} 没有当前任务，或其任务版本与你的不同。",
"multiplayer.setup.error.launch": "想要开始游戏",
"multiplayer.setup.error.moreplayers": "至少需要两名玩家。",
"multiplayer.setup.error.wrongversion": "{1:s} 的游戏版本不同。",
"multiplayer.setup.error.needgroups": "你需要把玩家分配到至少两支不同的队伍。",
"multiplayer.setup.error.nomission": "未选择任务。",
"multiplayer.setup.error.toomanyteams": "当前任务玩家过多。请选择其他任务或踢出部分玩家。",
"multiplayer.setup.error.notready": "{1:s} 尚未准备就绪。",
"multiplayer.setup.ainame": "电脑玩家",
"multiplayer.addressbook.edit": "编辑",
"multiplayer.addressbook.title": "地址簿",
"multiplayer.addressbook.remove": "删除",
"multiplayer.addressbook.add": "添加",
"multiplayer.addressbook.data.title": "编辑条目",
"multiplayer.addressbook.data.address": "地址",
"multiplayer.addressbook.data.name": "名称",
"multiplayer.eliminated.title": "你已被淘汰！",
"multiplayer.eliminated.message": "你可以继续作为主机，或\\r\\n中止并让其他玩家担任主机。",
"multiplayer.chat.privmsg": "私聊[{1:s}] {2:s}",
"multiplayer.chat.allymsg": "[盟友] {1:s}",
"multiplayer.chat.type.all": "全体",
"multiplayer.chat.type.ally": "盟友",
"multiplayer.chat.enemymsg": "[敌人] {1:s}",
"multiplayer.chat.playerexit": "{1:s} 已离开游戏。",
"multiplayer.chat.playerdisconnected": "{1:s} 已断开连接。",
"multiplayer.chat.error.noplayer": "找不到玩家 {1:s}。",
"multiplayer.chat.teammsg": "[队伍] {1:s}",
"multiplayer.chat.playerenter": "{1:s} 已进入游戏。",
"multiplayer.connect.playersync": "正在等待玩家",
"multiplayer.connect.migrate": "正在迁移到新主机",
"multiplayer.connect.title": "正在连接...",
"multiplayer.connect.communicating": "正在与网络通信",
"multiplayer.server.disconnected.title": "已断开连接",
"multiplayer.server.disconnected.message": "你已与服务器断开连接",
"multiplayer.server.connectfailed.title": "连接失败",
"multiplayer.server.connectfailed.message": "无法与服务器建立连接",
"multiplayer.server.serverconnect.entering": "正在进入房间",
"multiplayer.server.serverconnect.connect": "已连接到服务器",
"multiplayer.server.serverstart.connecting": "正在连接服务器",
"multiplayer.server.serverstart.started": "服务器已启动",
"multiplayer.server.kicked.title": "已被踢出",
"multiplayer.server.kicked.message": "你已被踢出游戏",
"multiplayer.server.migrated": "房间正在迁移给你。你现在是主机。",
"multiplayer.server.sessionfull.title": "房间已满",
"multiplayer.server.sessionfull.message": "该房间玩家人数已达上限。",
"multiplayer.changename.title": "修改你的名称",
"multiplayer.changename.subtitle": "请输入你的新名称",
}

ESC_RE = re.compile(r"\\[nrt]")
PH_RE = re.compile(r"\{[^{}]*\}")

def read_lines(p):
    with io.open(p, "r", encoding="utf-8", newline="") as f:
        return f.read().split("\n")

in_raw = read_lines(IN_P)
# drop a trailing empty element produced by a final newline, remember whether it existed
trailing_nl = False
if in_raw and in_raw[-1] == "":
    in_raw = in_raw[:-1]
    trailing_nl = True

rows = []
for i, ln in enumerate(in_raw, 1):
    ln = ln.rstrip("\r")
    if ln == "":
        rows.append((i, None, None))
        continue
    if "\t" not in ln:
        print("FATAL: line %d has no TAB" % i); sys.exit(2)
    p, v = ln.split("\t", 1)
    rows.append((i, p, v))

errors = []
out = []
seen = set()
for i, p, v in rows:
    if p is None:
        out.append("")
        continue
    if p in TR:
        zh = TR[p]
    else:
        errors.append("line %d: NO TRANSLATION for path %r (value=%r)" % (i, p, v))
        zh = v
    seen.add(p)

    # placeholder / escape preservation check
    src_ph = sorted(PH_RE.findall(v))
    dst_ph = sorted(PH_RE.findall(zh))
    if src_ph != dst_ph:
        errors.append("line %d [%s]: placeholder mismatch src=%s dst=%s" % (i, p, src_ph, dst_ph))
    if sorted(ESC_RE.findall(v)) != sorted(ESC_RE.findall(zh)):
        errors.append("line %d [%s]: escape mismatch src=%s dst=%s"
                      % (i, p, ESC_RE.findall(v), ESC_RE.findall(zh)))
    # no stray leading/trailing whitespace, no quotes wrapping
    if zh != zh.strip():
        errors.append("line %d [%s]: leading/trailing whitespace" % (i, p))
    if zh.startswith('"') or zh.endswith('"'):
        errors.append("line %d [%s]: wrapped in quotes" % (i, p))
    if "®" in zh or "©" in zh:
        errors.append("line %d [%s]: raw (R)/(C) symbol present" % (i, p))
    out.append(p + "\t" + zh)

unused = set(TR) - seen
for k in sorted(unused):
    errors.append("translation table entry never matched: %r" % k)

text = "\n".join(out) + ("\n" if trailing_nl else "")
with io.open(OUT_P, "w", encoding="utf-8", newline="") as f:
    f.write(text)

# ---- report ----
print("input lines : %d" % len(in_raw))
print("output lines: %d" % len(out))
print("same count  : %s" % (len(in_raw) == len(out)))
bad = 0
for i, p, v in rows:
    if p is None:
        continue
out_raw = read_lines(OUT_P)
if out_raw and out_raw[-1] == "":
    out_raw = out_raw[:-1]
print("output file lines (independent read): %d" % len(out_raw))
order_ok = True
for (i, p, v), o in zip(rows, out_raw):
    if p is None:
        continue
    op = o.split("\t", 1)[0]
    if op != p:
        order_ok = False
        print("PATH ORDER MISMATCH at line %d: %r vs %r" % (i, p, op))
print("path order/identity OK: %s" % order_ok)

# untranslated heuristic: value identical to source and source is not pure symbol/number
same_src = []
for i, p, v in rows:
    if p is None:
        continue
    zh = TR.get(p, v)
    if zh == v and not re.fullmatch(r"[\W\d_]*", v or ""):
        same_src.append((i, p, v))
print("values identical to English (should be callsigns only): %d" % len(same_src))
for t in same_src:
    print("   ", t)

# length budget
print("--- length over 1.2x English ---")
over = []
for i, p, v in rows:
    if p is None:
        continue
    zh = TR.get(p, v)
    if len(zh) > len(v) * 1.2 + 0.001:
        over.append((i, p, v, zh, round(len(zh)/max(len(v),1), 2)))
for t in over:
    print("   ", t)
print("over-budget count: %d" % len(over))

print("--- ERRORS ---")
if errors:
    for e in errors:
        print("  ", e)
else:
    print("   none")
print("ERROR_COUNT: %d" % len(errors))
