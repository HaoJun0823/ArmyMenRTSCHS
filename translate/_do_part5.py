# -*- coding: utf-8 -*-
"""part5 英译中：读写 TSV + 占位符/转义自检。临时辅助脚本。"""
import re, sys, io

IN = r'G:\Projects\ArmyMenRTSCHS\translate\part5.in.tsv'
OUT = r'G:\Projects\ArmyMenRTSCHS\translate\part5.out.tsv'

T = {
    'client.unitdisplay.prereq': '需要建造',
    'client.unitdisplay.unavailable': '不可用',
    'client.unitdisplay.firepower': '火力',
    'client.unitdisplay.infantry': '步兵',
    'client.unitdisplay.air': '空军',
    'client.unitdisplay.cost': '费用',
    'client.unitdisplay.upgrade': '升级',
    'client.unitdisplay.armor': '装甲',
    'client.restart.restart': '重新开始',
    'client.restart.text1': '确定吗？',
    'client.restart.title': '重开任务',
    'client.abort.abort': '中止',
    'client.abort.text1': '确定吗？',
    'client.abort.title': '中止任务',
    'client.facility.title': '建造',
    'client.chat.title': '聊天',
    'client.comms.title': '给予物品',
    'client.comms.selectedoff': '选择玩家',
    'client.comms.selectedon': '点击要给予的物品',
    'client.comms.units': '已选单位',
    'client.objectives.title': '目标',
    'client.objectives.ps2_2': '查看你的目标',
    'client.objectives.ps2_1': '按 Start 键',
    'client.objectives.pc2': '查看你的目标',
    'client.objectives.pc1': '按 Escape 键',
    'client.minimap.title': '地图',
    'client.options.difficulty.easy': '简单',
    'client.options.difficulty.title': '难度',
    'client.options.difficulty.normal': '普通',
    'client.options.difficulty.hard': '困难',
    'client.options.low': '低',
    'client.options.title': '设置',
    'client.options.gameplay.keyscroll': '键盘滚动速度',
    'client.options.gameplay.rightscroll': '右键滚动速度',
    'client.options.gameplay.edgescroll': '边缘滚动速度',
    'client.options.gameplay.title': '游戏设置',
    'client.options.gameplay.reset': '恢复默认',
    'client.options.gameplay.zoomspeed': '缩放速度',
    'client.options.gameplay.cameraspeed': '镜头速度',
    'client.options.gameplay.titleps2': '镜头设置',
    'client.options.high': '高',
    'client.options.audio.music': '音乐音量',
    'client.options.audio.title': '音频设置',
    'client.options.audio.master': '主音量',
    'client.options.vibration.off': '关',
    'client.options.vibration.title': '震动',
    'client.options.vibration.on': '开',
    'client.options.video.gamma': '亮度',
    'client.options.video.title': '画面设置',
    'client.options.video.world': '世界细节',
    'client.options.video.texture': '纹理细节',
    'client.options.video.resolution': '分辨率与色深',
    'client.options.medium': '中',
    'client.squad.title': '小队',
    'client.squad.1': '1',
    'client.squad.3': '3',
    'client.squad.2': '2',
    'client.squad.4': '4',
    'client.quit.text2': '退出吗？',
    'client.quit.text1': '你确定要',
    'client.quit.title': '退出',
    'client.zoom.zoom': '视角',
    'client.code.title': '输入密码',
    'client.medalgoals.GoalNum1': '2.',
    'client.medalgoals.GoalNum0': '1.',
    'client.medalgoals.title': '勋章目标',
    'client.medalgoals.hidden': '机密',
    'client.menu.restart': '重开任务',
    'client.menu.abort': '中止任务',
    'client.menu.resumePS2': '继续',
    'client.menu.back': '返回',
    'client.menu.objectives': '任务目标',
    'client.menu.select': '选择',
    'client.menu.options': '设置',
    'client.menu.objectivesPS2': '目标',
    'client.menu.resume': '继续游戏',
    'client.menu.quit': '退出',
    'client.menu.medalgoals': '勋章目标',
    'client.menu.saveload': '存档与读档',
    'client.menu.paused': '已暂停',
    'client.saveload.empty': '- 无存档 -',
    'client.saveload.title': '存档与读档',
    'client.saveload.saving': '正在保存，请稍候...',
    'client.saveload.confirmload.title': '确认读档',
    'client.saveload.confirmload.message': '确定要载入此存档吗？',
    'client.saveload.load': '载入',
    'client.saveload.save': '保存',
    'client.saveload.confirmsave.title': '确认保存',
    'client.saveload.confirmsave.message': '确定要覆盖之前的存档吗？',
    'mods.ruleset.protecthq.title': '保卫总部',
    'mods.ruleset.protecthq.objective': '你必须在计时结束前建造一座总部',
    'mods.ruleset.protecthq.objective2': '消灭所有敌方玩家',
    'mods.ruleset.protecthq.3minally': '你的盟友 {1:s} 有 3 分钟建造总部',
    'mods.ruleset.protecthq.3minself': '你有 3 分钟建造总部',
    'mods.ruleset.koth.s_built': '你已占领高地！',
    'mods.ruleset.koth.a_holding': '{1:s} 还需防守高地 {2:s} 分钟',
    'mods.ruleset.koth.e_built': '你的敌人 {1:s} 已在高地上建造！',
    'mods.ruleset.koth.objective': '在高地上建造总部并坚守 5 分钟',
    'mods.ruleset.koth.pre_5min': '高地将在 5 分钟后开放',
    'mods.ruleset.koth.a_built': '你的盟友 {1:s} 已在高地上建造！',
    'mods.ruleset.koth.e_holding': '{1:s} 仍占据高地。你还有 {2:s} 分钟',
    'mods.ruleset.koth.s_holding': '你还需防守高地 {1:s} 分钟',
    'mods.ruleset.koth.pre_open': '高地已开放！',
    'std.buttons.abort': '中止',
    'std.buttons.exit': '退出',
    'std.buttons.cancel': '取消',
    'std.buttons.back': '返回',
    'std.buttons.done': '完成',
    'std.buttons.ok': '确定',
    'std.buttons.play': '开始游戏',
    'std.buttons.continue': '继续',
}

# ---------- 读取 ----------
with io.open(IN, 'r', encoding='utf-8', newline='') as f:
    raw = f.read()

# 保尾换行信息
has_trailing_nl = raw.endswith('\n')
body = raw[:-1] if has_trailing_nl else raw
in_lines = body.split('\n')
in_lines = [l for l in in_lines if l != '']  # 去掉可能的空行

# 保留 CRLF 风格
crlf = '\r\n' in raw

out_lines = []
missing = []
for l in in_lines:
    if '\t' in l:
        path, val = l.split('\t', 1)
    else:
        path, val = l, ''
    if path not in T:
        missing.append(path)
        out_lines.append(path + '\t' + val)
    else:
        out_lines.append(path + '\t' + T[path])

sep = '\r\n' if crlf else '\n'
out_text = sep.join(out_lines) + (sep if has_trailing_nl else '')
with io.open(OUT, 'w', encoding='utf-8', newline='') as f:
    f.write(out_text)

# ---------- 自检 ----------
PH = re.compile(r'\{[0-9]+:[a-zA-Z]\}')
ESC = re.compile(r'\\[nrt]')

def ph(s):
    return sorted(PH.findall(s))

def esc(s):
    return sorted(ESC.findall(s))

errs = []
n_in = len(in_lines)
with io.open(OUT, 'r', encoding='utf-8', newline='') as f:
    o = f.read()
o_body = o[:-1] if o.endswith('\n') else o
o_lines = [l for l in o_body.split('\n') if l != '']

if len(o_lines) != n_in:
    errs.append('行数不一致: in=%d out=%d' % (n_in, len(o_lines)))

for i, (a, b) in enumerate(zip(in_lines, o_lines), 1):
    pa = a.split('\t', 1)[0]
    pb = b.split('\t', 1)[0]
    va = a.split('\t', 1)[1] if '\t' in a else ''
    vb = b.split('\t', 1)[1] if '\t' in b else ''
    if pa != pb:
        errs.append('第%d行 path 不一致: %r != %r' % (i, pa, pb))
    if ph(va) != ph(vb):
        errs.append('第%d行 占位符丢失/改变: %r -> %r (%r / %r)' % (i, pa, ph(va), ph(vb), va, vb))
    if esc(va) != esc(vb):
        errs.append('第%d行 转义序列改变: %r -> %r' % (i, pa, esc(va), esc(vb)))
    if va and (vb != vb.strip()):
        errs.append('第%d行 译文首尾有空白: %r' % (i, vb))
    if '®' in va or '©' in va:
        if '®' in vb or '©' in vb:
            errs.append('第%d行 仍含 ®/©' % i)

# 未翻译检测
untranslated = []
for b in o_lines:
    path, val = b.split('\t', 1) if '\t' in b else (b, '')
    if val and not re.search(r'[\u4e00-\u9fff]', val) and path in T:
        untranslated.append((path, val))

print('输入行数:', n_in)
print('输出行数:', len(o_lines))
print('行数一致:', n_in == len(o_lines))
print('path 顺序/内容一致:', not any('path' in e for e in errs))
print('占位符自检:', '通过' if not any('占位符' in e for e in errs) else '失败')
print('转义序列自检:', '通过' if not any('转义' in e for e in errs) else '失败')
print('CRLF:', crlf, '尾换行:', has_trailing_nl)
print('未翻译(纯符号/数字属正常):', untranslated)
print('缺失词条:', missing)
print('错误数:', len(errs))
for e in errs:
    print(' -', e)

# 长度检查
print('--- 长度超 1.2 倍条目 ---')
for a, b in zip(in_lines, o_lines):
    path, va = a.split('\t', 1) if '\t' in a else (a, '')
    vb = b.split('\t', 1)[1] if '\t' in b else ''
    if va and len(vb) > len(va) * 1.2:
        print('  %s  %d -> %d  %r -> %r' % (path, len(va), len(vb), va, vb))
