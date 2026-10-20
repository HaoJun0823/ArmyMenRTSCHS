"""Execute the actual emitted hook words with strict guarded memory checks."""
import json
import random
import struct
import sys
from pathlib import Path

from native_patch import BASE, DIAGNOSTICS, REG, program

sys.dont_write_bytecode = True
sys.path.insert(0, 'inputs/menu-sample/work')
from build_sample import parse_font

HERE = Path(__file__).resolve().parent
MASK = (1 << 64) - 1


def sign(value, bits):
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


class Memory:
    """Guarded disjoint allocations reject unaligned or out-of-bounds access."""

    def __init__(self):
        self.regions = []

    def add(self, base, data):
        assert all(base + len(data) <= lo or hi <= base for lo, hi, _ in self.regions)
        self.regions.append((base, base + len(data), bytearray(data)))

    def access(self, address, size, value=None):
        address &= 0xFFFFFFFF
        assert size == 1 or address % size == 0, ('unaligned', hex(address), size)
        for lo, hi, data in self.regions:
            if lo <= address and address + size <= hi:
                p = address - lo
                if value is None:
                    return int.from_bytes(data[p:p + size], 'little')
                data[p:p + size] = (value & ((1 << (8 * size)) - 1)).to_bytes(size, 'little')
                return
        raise AssertionError(('out of bounds', hex(address), size))


WORDS, LABELS = program()
CODE = {BASE + k * 4: word for k, word in enumerate(WORDS)}


def execute(entry, memory, arguments, stops=(), max_steps=100000):
    regs = [0] + [((0xC0FFEE + k) << 64) | (0xB0000000 + k) for k in range(1, 32)]
    regs[REG['sp']] = 0x1F01000
    regs[REG['ra']] = 0x0FFF0000
    for name, value in arguments.items():
        regs[REG[name]] = value & MASK
    before = regs.copy()
    pc = LABELS[entry]
    stops = set(stops) | {0x0FFF0000}

    def step(word):
        op, rs, rt, rd, sa, fn = word >> 26, word >> 21 & 31, word >> 16 & 31, word >> 11 & 31, word >> 6 & 31, word & 63
        imm = word & 65535
        si = sign(imm, 16)
        value = None
        if not word:
            return
        if op == 0:
            x, y = regs[rs] & MASK, regs[rt] & MASK
            if fn == 0:
                value = sign((y & 0xFFFFFFFF) << sa, 32) & MASK
            elif fn in (33, 35):
                value = sign(x + y if fn == 33 else x - y, 32) & MASK
            elif fn == 45:
                value = (x + y) & MASK
            elif fn == 37:
                value = x | y
            elif fn == 42:
                value = int(sign(x, 64) < sign(y, 64))
            elif fn == 43:
                value = int(x < y)
            else:
                raise AssertionError(('unsupported R instruction', hex(word)))
            rt = rd
        elif op == 9:
            value = sign(regs[rs] + si, 32) & MASK
        elif op == 11:
            value = int((regs[rs] & MASK) < (si & MASK))
        elif op == 12:
            value = regs[rs] & imm
        elif op == 14:
            value = regs[rs] ^ imm
        elif op == 15:
            value = sign(imm << 16, 32) & MASK
        elif op in (35, 36, 37, 30):
            size = {35: 4, 36: 1, 37: 2, 30: 16}[op]
            value = memory.access(regs[rs] + si, size)
            if op == 35:
                value = sign(value, 32) & MASK
        elif op in (43, 31):
            memory.access(regs[rs] + si, 4 if op == 43 else 16, regs[rt])
        else:
            raise AssertionError(('unsupported instruction', hex(word)))
        if value is not None and rt:
            regs[rt] = value
        regs[0] = 0

    for count in range(max_steps):
        if pc in stops:
            return regs, before, pc, count
        assert pc % 4 == 0 and pc in CODE, ('execution outside emitted words', hex(pc))
        word = CODE[pc]
        op, rs, rt, imm = word >> 26, word >> 21 & 31, word >> 16 & 31, word & 65535
        target = None
        if op in (2, 3):
            target = ((pc + 4) & 0xF0000000) | (word & 0x3FFFFFF) << 2
            if op == 3:
                regs[31] = pc + 8
        elif op in (4, 5):
            taken = regs[rs] == regs[rt]
            if op == 5:
                taken = not taken
            target = pc + 4 + sign(imm, 16) * 4 if taken else pc + 8
        elif op == 0 and word & 63 == 8:
            target = regs[rs] & 0xFFFFFFFF
        if target is None:
            step(word)
            pc += 4
        else:
            step(CODE[pc + 4])
            pc = target
    raise AssertionError(('step budget exceeded', entry))


def base_memory():
    memory = Memory()
    memory.add(0x1F00000, bytes(0x1000))
    memory.add(DIAGNOSTICS, struct.pack('<5I', 0xFFFFFFFF, 0, 0, 0, 0))
    return memory


def load_font(memory, glyphs, height=20):
    font = bytearray(0x930)
    struct.pack_into('<I', font, 0x114, height)
    buckets = {}
    for code, (desc, _) in glyphs.items():
        buckets.setdefault(code & 255, []).append((code, desc[2]))
    pointer = 0x910000
    for bucket, values in sorted(buckets.items()):
        struct.pack_into('<HI', font, 0x11C + bucket * 8, len(values), 0)
        struct.pack_into('<I', font, 0x120 + bucket * 8, pointer)
        data = bytearray(len(values) * 40)
        for n, (code, advance) in enumerate(values):
            struct.pack_into('<HH', data, n * 40, code, advance)
        memory.add(pointer, data)
        pointer = (pointer + len(data) + 15) & ~15
    memory.add(0x900000, font)


def punctuation_regression(glyphs, height):
    text = '移动到撤离点。'
    data = text.encode('gbk')
    memory = base_memory()
    load_font(memory, glyphs, height)
    memory.add(0x800001, data + b'\0')
    memory.add(0x890000, bytes(4))
    width = sum(glyphs[int.from_bytes(ch.encode('gbk'), 'big')][0][2] for ch in text[:-1])
    regs, _, _, _ = execute('wrap', memory, {'a0': 0x800001, 'a1': 0x900000, 'a2': width, 'a3': 0x890000})
    assert regs[2] and not data[regs[2] - 0x800001:].decode('gbk').startswith('。'), 'full stop stranded on next line'


def check_wrapped(memory, data, width, key):
    cursor, lines = 0x800001, 0
    while True:
        regs, before, _, _ = execute('wrap', memory, {'a0': cursor, 'a1': 0x900000, 'a2': width, 'a3': 0x890000})
        count = memory.access(0x890000, 4)
        offset = cursor - 0x800001
        line = data[offset:offset + count].decode('gbk')
        next_cursor = regs[2]
        assert not next_cursor or cursor < next_cursor <= 0x800001 + len(data)
        mregs, _, _, _ = execute('measure', memory, {'a0': 0x900000, 'a1': cursor, 'a2': count})
        assert mregs[2] <= width, (key, width, line)
        assert all(regs[k] == before[k] for k in range(16, 24)) and regs[29] == before[29] and regs[31] == before[31]
        lines += 1
        assert lines <= len(data) + 1
        if not next_cursor:
            assert offset + count == len(data), (key, 'dropped tail')
            break
        next_offset = next_cursor - 0x800001
        gap = data[offset + count:next_offset]
        assert gap in (b'', b' ', b'\r', b'\n', b'\r\n'), (key, 'dropped bytes', gap)
        if gap in (b'', b' '):
            following = data[next_offset:].decode('gbk').lstrip(' ')
            assert not following or following[0] not in '，。、；：？！…—）》」』】〕〉”’.,!?;:)]}', (key, width, line, following)
            assert not line.rstrip(' ') or line.rstrip(' ')[-1:] not in '（《「『【〔〈“‘([{', (key, width, line)
        cursor = next_cursor
    return lines


def main():
    decoder_cases = 0
    for first in range(256):
        for second in range(256):
            for length in (1, 2):
                data = bytes((first, second))[:length]
                memory = base_memory()
                memory.add(0x800001, data)
                regs, before, _, _ = execute('decode', memory, {'a0': 0x800001, 'a1': length})
                dual = length == 2 and 0x81 <= first <= 0xFE and 0x40 <= second <= 0xFE and second != 0x7F
                code = first << 8 | second if dual else 63 if 0x81 <= first <= 0xFE else first
                assert regs[2] == code and regs[3] == (2 if dual else 1), (first, second, length)
                assert all(regs[k] == before[k] for k in range(32) if k not in (2, 3, 24, 25))
                decoder_cases += 1
    memory = base_memory()
    regs, _, _, _ = execute('decode', memory, {'a0': 0x800001, 'a1': 0})
    assert regs[2] == regs[3] == 0

    height, glyphs = parse_font((HERE / 'assets/font_arial_cn.fff').read_bytes())
    punctuation_regression(glyphs, height)
    records = json.loads((HERE / 'texts.json').read_text(encoding='utf-8'))
    records += [dict(key='native/' + str(row['va']), target=row['target'])
                for row in json.loads((HERE / 'native-strings.json').read_text(encoding='utf-8'))]
    measure_cases = wrap_cases = 0
    font_names = ('font_stencil_cn.fff', 'font_arial_memcard_cn.fff', 'font_arial_cn.fff')
    for font_name in font_names:
        height, glyphs = parse_font((HERE / 'assets' / font_name).read_bytes())
        for row in records:
            data = row['target'].encode('gbk')
            memory = base_memory()
            load_font(memory, glyphs, height)
            memory.add(0x800001, data + b'\0')
            memory.add(0x890000, bytes(4))
            regs, before, _, _ = execute('measure', memory, {'a0': 0x900000, 'a1': 0x800001, 'a2': len(data)})
            expected = sum(glyphs[ord(ch) if ord(ch) < 128 else int.from_bytes(ch.encode('gbk'), 'big')][0][2]
                           for ch in row['target'] if (ord(ch) if ord(ch) < 128 else int.from_bytes(ch.encode('gbk'), 'big')) in glyphs)
            assert regs[2] == expected, row['key']
            assert all(regs[k] == before[k] for k in range(16, 24)) and regs[29] == before[29] and regs[31] == before[31]
            measure_cases += 1
            # Large title glyphs need more than 60px for a digit plus two closing marks.
            widths = (100, 200, 260, 300, 320, 400, 430, 500, 580, 600) if height == 30 else (60, 100, 200, 260, 300, 320, 400, 430, 500, 580, 600)
            for width in widths:
                check_wrapped(memory, data, width, row['key'])
                wrap_cases += 1
    # Exercise widths around punctuation groups with a complete synthetic metric font.
    fixture_texts = ('移动到撤离点。', '目标，完成！继续？', '完成（目标）后返回。', '他说：“完成了！”继续。',
                     '继续……返回。', '目标 [Ready], then move.', '目标  ，完成。', '  目标。返回。',
                     '目标。\r\n继续。\n完成。\r返回。')
    fixture_glyphs = dict(glyphs)
    for ch in ''.join(fixture_texts):
        code = int.from_bytes(ch.encode('gbk'), 'big')
        fixture_glyphs.setdefault(code, (struct.pack('<H5B', code, 15, 0, 0, 1, 1), b'\1\1\xff'))
    punctuation_cases = 0
    for text in fixture_texts:
        data = text.encode('gbk')
        for width in range(80, 241):
            memory = base_memory()
            load_font(memory, fixture_glyphs, height)
            memory.add(0x800001, data + b'\0')
            memory.add(0x890000, bytes(4))
            check_wrapped(memory, data, width, 'punctuation fixture')
            punctuation_cases += 1
    narrow_cases = 0
    for width in (0, 1, 14):
        data = '目标。'.encode('gbk')
        memory = base_memory()
        load_font(memory, glyphs, height)
        memory.add(0x800001, data + b'\0')
        memory.add(0x890000, bytes(4))
        cursor = 0x800001
        for _ in range(4):
            regs, _, _, _ = execute('wrap', memory, {'a0': cursor, 'a1': 0x900000, 'a2': width, 'a3': 0x890000})
            if not regs[2]:
                break
            assert cursor < regs[2] <= 0x800001 + len(data)
            cursor = regs[2]
        else:
            raise AssertionError('narrow-width progress failure')
        narrow_cases += 1
    # Draw adapter at an odd text address must not use unaligned halfword reads.
    for value in (b'ABC', '战役模式'.encode('gbk'), b'\x81', b'\0'):
        memory = base_memory()
        load_font(memory, glyphs)
        memory.add(0x800001, value)
        stack = 0x1F00000
        memory.access(stack + 4, 4, 0x900000)
        memory.access(stack + 0x10, 4, 0x800001)
        memory.access(stack + 0x14, 4, len(value))
        memory.access(stack + 0x24, 4, 0)
        regs, _, stop, _ = execute('draw_decode', memory, {'sp': stack}, stops=(0x264D9C, 0x265F64))
        assert stop == (0x265F64 if value[0] == 0 else 0x264D9C)
        assert memory.access(stack + 0x54, 4) in (1, 2)
    memory = base_memory()
    memory.add(0x3F51FC, struct.pack('<I', 0x900000))
    memory.add(0x900000, bytes(16))
    stack = 0x1F00000
    for free, returned in ((9000, 0xA00000), (7000, 0xA00100), (8000, 0)):
        memory.access(0x900008, 4, free)
        memory.access(stack + 0xB0, 16, 0x123456789ABCDEF0)
        memory.access(stack + 0xA0, 16, 0xABCD)
        regs, _, _, _ = execute('allocation_audit', memory, {'sp': stack, 'v0': returned}, stops=(0x1159F4,))
        assert regs[2] == returned and regs[31] == 0x123456789ABCDEF0 and regs[30] == 0xABCD
    assert [memory.access(DIAGNOSTICS + k * 4, 4) for k in range(3)] == [7000, 3, 1]
    memory = base_memory()
    load_font(memory, glyphs)
    regs, _, _, _ = execute('lookup', memory, {'a0': 0x900000, 'a1': 0xEFFF})
    assert regs[2] == 0 and memory.access(DIAGNOSTICS + 12, 4) == 1
    stack = 0x1F00000
    memory.access(stack + 0x24, 4, 7)
    regs, _, stop, _ = execute('draw_lookup_audit', memory, {'sp': stack, 's7': 0, 'a2': 0xEFFF}, stops=(0x265F50, 0x264DF4))
    assert stop == 0x265F50 and regs[4] == 7 and memory.access(DIAGNOSTICS + 12, 4) == 2
    _, _, stop, _ = execute('draw_lookup_audit', memory, {'sp': stack, 's7': 0x910000, 'a2': 65}, stops=(0x265F50, 0x264DF4))
    assert stop == 0x264DF4 and memory.access(DIAGNOSTICS + 12, 4) == 2
    report = {'host_cpu_model_only': True, 'decoder_cases': decoder_cases + 1,
              'measure_corpus_cases': measure_cases, 'wrapping_corpus_cases': wrap_cases,
              'font_metrics_tested': font_names,
              'corpus_widths': {'height_20': [60, 100, 200, 260, 300, 320, 400, 430, 500, 580, 600],
                                'height_30': [100, 200, 260, 300, 320, 400, 430, 500, 580, 600]},
              'punctuation_boundary_cases': punctuation_cases, 'impossible_width_progress_cases': narrow_cases,
              'soft_break_punctuation_and_byte_conservation_checked': True,
              'draw_adapter_cases': 4, 'strict_alignment_and_allocation_guards': True,
              'callee_saved_registers_preserved': True, 'actual_pcsx2_interpreter_tested': False,
              'status': 'PASS'}
    (HERE / 'native-host-tests.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    if '--wrap-regression' in sys.argv:
        punctuation_regression(*reversed(parse_font((HERE / 'assets/font_arial_cn.fff').read_bytes())))
        print('Punctuation regression: PASS')
    else:
        main()
