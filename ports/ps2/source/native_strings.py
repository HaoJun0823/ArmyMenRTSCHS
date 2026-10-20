"""Fixed-cell PS2 memory-card messages; pointers and allocations stay unchanged."""
import collections
import re

START = 0x411160
TARGETS = [
    '是', '否', '继续',
    '记忆卡（PS2）空间不足。保存游戏需要至少 %dKB 空间。要不保存并继续吗？',
    '未插入记忆卡（PS2）。保存游戏需要至少 %dKB 空间。要不保存并继续吗？',
    '正在检查记忆卡（PS2）。',
    '请插入记忆卡（PS2）。',
    '记忆卡（PS2）尚未格式化。要格式化记忆卡吗？',
    '记忆卡（PS2）不会被格式化。要不保存并继续吗？',
    '确定要格式化已插入的记忆卡（PS2）吗？',
    '正在格式化。请勿拔出记忆卡（PS2）。',
    '格式化完成',
    '格式化失败。请重试或插入另一张记忆卡（PS2）。',
    '本游戏不支持此记忆卡。要不保存并继续吗？',
    '本游戏不支持 PocketStation。要不保存并继续吗？',
    '正在保存。请勿拔出记忆卡（PS2）、关闭电源或重启主机。',
    '保存完成',
    '保存失败。请重试或插入另一张记忆卡（PS2）。',
    '正在读取。请勿拔出记忆卡（PS2）。',
    '记忆卡（PS2）中没有 %s 的存档。',
    '读取完成',
    '读取失败。请重试或插入另一张记忆卡（PS2）。',
    '读取失败。记忆卡（PS2）尚未格式化。',
    '读取失败。未插入记忆卡（PS2）。',
    '保存失败。',
    '保存失败。要重试吗？',
    '保存失败。记忆卡（PS2）尚未格式化。',
    '保存失败。未插入记忆卡（PS2）。保存游戏需要至少 %dKB 空间。要不保存并继续吗？',
    '保存失败。记忆卡（PS2）空间不足。保存游戏需要至少 %dKB 空间。要不保存并继续吗？',
    '记忆卡（PS2）尚未格式化。保存游戏需要至少 %dKB 空间。要使用未格式化的记忆卡继续吗？',
    '记忆卡（PS2）中已有存档。要覆盖该存档吗？',
    '确定要覆盖该存档吗？',
    '存档不会被覆盖。',
    '记忆卡（PS2）空间不足。保存游戏需要至少 %dKB 空间。要开始游戏吗？',
    '未插入记忆卡（PS2）。保存游戏需要至少 %dKB 空间。要开始游戏吗？',
]


def records(source):
    result = []
    assert START + (len(TARGETS) - 1) * 2100 == 0x422848
    for index, text in enumerate(TARGETS):
        for language in range(2):
            va = START + index * 2100 + language * 350
            offset = va - 0xFF000
            old = source[offset:offset + 350].split(b'\0', 1)[0].decode('ascii')
            assert old and len(text.encode('gbk')) < 350
            assert collections.Counter(re.findall(r'%[ds]', old)) == collections.Counter(re.findall(r'%[ds]', text))
            result.append(dict(va=va, offset=offset, size=350, source=old, target=text))
    return result
