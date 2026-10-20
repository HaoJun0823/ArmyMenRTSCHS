"""Minimal native GBK hooks, assembled directly with explicit delay slots."""
import hashlib
import json
import struct
from pathlib import Path
from native_strings import records as native_records

HERE = Path(__file__).resolve().parent
SOURCE = Path('inputs/source/ps2/SLUS_202.06.elf')
BASE = 0x6DE100
FILE_OFFSET = 0x100
HEAP_START = 0x6DF000
DIAGNOSTICS = 0x6DEF00
REG = dict(zip('zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra'.split(), range(32)))
NO_LINE_START = '，。、；：？！…—）》」』】〕〉”’.,!?;:)]}'
NO_LINE_END = '（《「『【〔〈“‘([{'


def r(fn, d, s, t='zero', sa=0):
    return REG[s] << 21 | REG[t] << 16 | REG[d] << 11 | sa << 6 | fn


def i(op, t, s, value):
    assert -32768 <= value <= 65535
    return op << 26 | REG[s] << 21 | REG[t] << 16 | (value & 65535)


def mov(d, s):
    return r(45, d, s)


def add(d, s, t):
    return r(33, d, s, t)


def sub(d, s, t):
    return r(35, d, s, t)


def li(t, value):
    return i(9, t, 'zero', value)


def mem(op, t, offset, s='sp'):
    return i(op, t, s, offset)


def b(eq, s, t, label):
    return ('branch', 4 if eq else 5, REG[s], REG[t], label)


def j(label, link=False):
    return ('jump', 3 if link else 2, label)


def label(name):
    return name + ':'


def push(names, frame):
    assert frame % 16 == 0 and len(names) * 16 <= frame
    return [i(9, 'sp', 'sp', -frame)] + [mem(31, name, k * 16) for k, name in enumerate(names)]


def pop(names, frame):
    return [mem(30, name, k * 16) for k, name in enumerate(names)] + [r(8, 'zero', 'ra'), i(9, 'sp', 'sp', frame)]


def assemble(sequence, base):
    labels, words = {}, []
    for item in sequence:
        if isinstance(item, str):
            assert item.endswith(':') and item[:-1] not in labels
            labels[item[:-1]] = base + len(words) * 4
        else:
            words.append(item)
    for index, item in enumerate(words):
        pc = base + index * 4
        if isinstance(item, tuple):
            if item[0] == 'branch':
                _, op, rs, rt, target = item
                destination = labels[target] if isinstance(target, str) else target
                delta = (destination - (pc + 4)) // 4
                assert -32768 <= delta <= 32767 and destination % 4 == 0
                words[index] = op << 26 | rs << 21 | rt << 16 | (delta & 65535)
            else:
                _, op, target = item
                destination = labels[target] if isinstance(target, str) else target
                assert destination % 4 == 0 and destination >> 28 == (pc + 4) >> 28
                words[index] = op << 26 | (destination >> 2 & 0x3FFFFFF)
    return words, labels


def program():
    c = [label('decode'), b(True, 'a1', 'zero', 'decode_empty'), 0, mem(36, 'v0', 0, 'a0'), li('v1', 1),
         i(11, 't8', 'v0', 0x81), b(False, 't8', 'zero', 'decoded'), 0,
         i(11, 't8', 'v0', 0xFF), b(True, 't8', 'zero', 'decoded'), 0,
         i(11, 't8', 'a1', 2), b(False, 't8', 'zero', 'invalid'), 0,
         mem(36, 't9', 1, 'a0'), i(11, 't8', 't9', 0x40), b(False, 't8', 'zero', 'invalid'), 0,
         i(11, 't8', 't9', 0xFF), b(True, 't8', 'zero', 'invalid'), 0,
         i(14, 't8', 't9', 0x7F), b(True, 't8', 'zero', 'invalid'), 0,
         r(0, 'v0', 'zero', 'v0', 8), r(37, 'v0', 'v0', 't9'), li('v1', 2),
         label('decoded'), r(8, 'zero', 'ra'), 0,
         label('invalid'), li('v0', 63), r(8, 'zero', 'ra'), 0,
         label('decode_empty'), li('v0', 0), r(8, 'zero', 'ra'), li('v1', 0),
         label('decode_font'), mem(35, 't8', 0x114, 'a2'), li('t9', 27),
         b(False, 't8', 't9', 'decode'), 0,
         mem(36, 'v0', 0, 'a0'), r(8, 'zero', 'ra'), li('v1', 1),
         label('lookup'), i(12, 'a1', 'a1', 0xFFFF),
         # Legacy sign-extended u8 callers must retain their original byte semantics.
         i(12, 't0', 'a1', 0xFF00), i(14, 't0', 't0', 0xFF00),
         b(False, 't0', 'zero', 'lookup_bucket'), 0, i(12, 'a1', 'a1', 0xFF),
         label('lookup_bucket'), i(12, 't0', 'a1', 255), r(0, 't0', 'zero', 't0', 3),
         add('t0', 'a0', 't0'), mem(37, 't1', 0x11C, 't0'),
         b(True, 't1', 'zero', 'lookup_none'), 0, mem(35, 't0', 0x120, 't0'),
         label('lookup_loop'), mem(37, 't2', 0, 't0'), b(True, 't2', 'a1', 'lookup_found'), 0,
         i(9, 't1', 't1', -1), b(False, 't1', 'zero', 'lookup_loop'), i(9, 't0', 't0', 40),
         label('lookup_none'), i(11, 't0', 'a1', 256), b(False, 't0', 'zero', 'lookup_none_done'), 0,
         i(15, 't0', 'zero', 0x6E), mem(35, 't1', -0x10F4, 't0'), i(9, 't1', 't1', 1),
         mem(43, 't1', -0x10F4, 't0'), mem(43, 'a1', -0x10F0, 't0'),
         label('lookup_none_done'), r(8, 'zero', 'ra'), li('v0', 0),
         label('lookup_found'), r(8, 'zero', 'ra'), mov('v0', 't0')]

    saved = ['s0', 's1', 's2', 's3', 's4', 'ra']
    c += [label('measure')] + push(saved, 0x60)
    c += [mov('s0', 'a0'), mov('s1', 'a1'), mov('s2', 'a2'), li('s3', 0),
          label('measure_loop'), b(True, 's2', 'zero', 'measure_done'), 0,
          r(42, 'v0', 's2', 'zero'), b(False, 'v0', 'zero', 'measure_done'), 0,
          mem(36, 'v0', 0, 's1'), b(True, 'v0', 'zero', 'measure_done'), 0,
          mov('a0', 's1'), mov('a1', 's2'), j('decode_font', True), mov('a2', 's0'),
          mov('s4', 'v1'), mov('a1', 'v0'), j('lookup', True), mov('a0', 's0'),
          b(True, 'v0', 'zero', 'measure_next'), 0, mem(37, 'v0', 2, 'v0'), add('s3', 's3', 'v0'),
          label('measure_next'), add('s1', 's1', 's4'), j('measure_loop'), sub('s2', 's2', 's4'),
          label('measure_done'), mov('v0', 's3')] + pop(saved, 0x60)

    c += [label('char_width')] + push(['ra'], 16)
    c += [j('lookup', True), 0, b(True, 'v0', 'zero', 'char_done'), 0,
          mem(37, 'v0', 2, 'v0'), label('char_done')] + pop(['ra'], 16)

    # Draw's audited frame has an unused aligned word at sp+0x54.
    c += [label('draw_decode'), mem(35, 'v0', 0x10), mem(35, 'v1', 0x24),
          add('a0', 'v0', 'v1'), mem(35, 'a1', 0x14), sub('a1', 'a1', 'v1'),
          j('decode_font', True), mem(35, 'a2', 4), mem(43, 'v1', 0x54),
          mov('a2', 'v0'), b(True, 'a2', 'zero', 'draw_stop'), 0,
          mem(35, 'a3', 4), i(12, 'a1', 'a2', 255), r(0, 'a1', 'zero', 'a1', 3),
          j(0x264D9C), add('v0', 'a3', 'a1'),
          label('draw_stop'), j(0x265F64), 0,
          label('draw_advance'), mem(35, 'a1', 0x14), mem(35, 'v0', 0x54),
          j(0x265F58), add('a0', 'a0', 'v0')]

    saved = ['s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 'ra']
    c += [label('wrap')] + push(saved, 0xA0)
    c += [mov('s0', 'a0'), mov('s1', 'a0'), mov('s2', 'a1'), mov('s3', 'a2'),
          mov('s4', 'a3'), li('s5', 0), li('s6', 0), mem(43, 'zero', 0x90), mem(43, 'zero', 0x94), mem(43, 'zero', 0x9C),
          label('wrap_loop'), sub('v0', 's1', 's0'), i(15, 'v1', 'zero', 1), r(43, 'v0', 'v0', 'v1'),
          b(True, 'v0', 'zero', 'wrap_end'), 0,
          mem(36, 'v0', 0, 's1'), b(True, 'v0', 'zero', 'wrap_end'), 0,
          li('v1', 10), b(True, 'v0', 'v1', 'wrap_lf'), 0,
          li('v1', 13), b(True, 'v0', 'v1', 'wrap_cr'), 0,
          mov('a0', 's1'), li('a1', 2), j('decode_font', True), mov('a2', 's2'),
          mov('s7', 'v1'), mem(43, 'v0', 0x98), j('no_line_start', True), 0,
          b(False, 'v1', 'zero', 'wrap_width'), 0,
          li('v1', 32), b(True, 'v0', 'v1', 'wrap_width'), 0,
          j('no_line_end', True), mem(35, 'v0', 0x90),
          b(False, 'v1', 'zero', 'wrap_width'), 0,
          mem(43, 's1', 0x94), mem(35, 'v0', 0x90), li('v1', 32),
          b(False, 'v0', 'v1', 'wrap_mark_text'), 0,
          mem(35, 'v0', 0x9C), b(True, 'v0', 'zero', 'wrap_mark_text'), 0,
          mov('s6', 's1'),
          label('wrap_mark_text'), li('v0', 1), mem(43, 'v0', 0x9C),
          label('wrap_width'), mem(35, 'a1', 0x98), mem(43, 'a1', 0x90),
          j('lookup', True), mov('a0', 's2'),
          b(True, 'v0', 'zero', 'wrap_zero'), li('v1', 0), mem(37, 'v1', 2, 'v0'),
          label('wrap_zero'), add('v1', 's5', 'v1'), r(43, 'v0', 's3', 'v1'),
          b(False, 'v0', 'zero', 'wrap_full'), 0,
          mov('s5', 'v1'), j('wrap_loop'), add('s1', 's1', 's7'),
          label('wrap_full'), b(True, 's1', 's0', 'wrap_one'), 0,
          b(True, 's6', 'zero', 'wrap_legal'), 0,
          sub('v1', 's6', 's0'), i(9, 'v1', 'v1', -1), j('wrap_return'), mov('v0', 's6'),
          label('wrap_legal'), mem(35, 'v0', 0x94),
          b(True, 'v0', 'zero', 'wrap_current'), 0,
          b(True, 'v0', 's0', 'wrap_current'), 0,
          j('wrap_return'), sub('v1', 'v0', 's0'),
          # shortcut: narrower-than-group widths force a cluster break; UI widths must fit the punctuation group.
          label('wrap_current'), sub('v1', 's1', 's0'), j('wrap_return'), mov('v0', 's1'),
          label('wrap_one'), mov('v1', 's7'), j('wrap_return'), add('v0', 's1', 's7'),
          label('wrap_lf'), sub('v1', 's1', 's0'), j('wrap_return'), i(9, 'v0', 's1', 1),
          label('wrap_cr'), sub('v1', 's1', 's0'), mem(36, 'v0', 1, 's1'), li('a0', 10),
          b(False, 'v0', 'a0', 'wrap_cr_single'), 0, j('wrap_return'), i(9, 'v0', 's1', 2),
          label('wrap_cr_single'), j('wrap_return'), i(9, 'v0', 's1', 1),
          label('wrap_end'), sub('v1', 's1', 's0'), li('v0', 0),
          label('wrap_return'), mem(43, 'v1', 0, 's4')] + pop(saved, 0xA0)
    for name, chars in (('no_line_start', NO_LINE_START), ('no_line_end', NO_LINE_END)):
        c += [label(name)]
        for char in chars:
            code = int.from_bytes(char.encode('gbk'), 'big')
            c += [i(14, 't8', 'v0', code), b(True, 't8', 'zero', name + '_yes'), 0]
        c += [r(8, 'zero', 'ra'), li('v1', 0),
              label(name + '_yes'), r(8, 'zero', 'ra'), li('v1', 1)]
    # Track every native allocator return, including short-lived font load peaks.
    c += [label('allocation_audit'), i(15, 't8', 'zero', 0x3F), mem(35, 't8', 0x51FC, 't8'),
          b(True, 't8', 'zero', 'allocation_done'), 0,
          mem(35, 't9', 8, 't8'), i(15, 't0', 'zero', 0x6E), mem(35, 't1', -0x1100, 't0'),
          r(43, 't2', 't9', 't1'), b(True, 't2', 'zero', 'allocation_count'), 0,
          mem(43, 't9', -0x1100, 't0'), label('allocation_count'),
          mem(35, 't1', -0x10FC, 't0'), i(9, 't1', 't1', 1), mem(43, 't1', -0x10FC, 't0'),
          b(False, 'v0', 'zero', 'allocation_done'), 0,
          mem(35, 't1', -0x10F8, 't0'), i(9, 't1', 't1', 1), mem(43, 't1', -0x10F8, 't0'),
          label('allocation_done'), mem(30, 'ra', 0xB0), j(0x1159F4), mem(30, 'fp', 0xA0)]
    c += [label('draw_lookup_audit'), b(False, 's7', 'zero', 'draw_lookup_found'), mem(35, 'a0', 0x24),
          i(11, 't8', 'a2', 256), b(False, 't8', 'zero', 'draw_lookup_skip'), 0,
          i(15, 't8', 'zero', 0x6E), mem(35, 't9', -0x10F4, 't8'), i(9, 't9', 't9', 1),
          mem(43, 't9', -0x10F4, 't8'), mem(43, 'a2', -0x10F0, 't8'),
          label('draw_lookup_skip'), j(0x265F50), 0,
          label('draw_lookup_found'), j(0x264DF4), 0]
    return assemble(c, BASE)


def build():
    source = SOURCE.read_bytes()
    assert hashlib.sha256(source).hexdigest() == 'cfe2a769f7cf31e2482f4c8917c6bb1364343f365b7a9e4c6cf73152951f3bae'
    words, labels = program()
    code = struct.pack('<%dI' % len(words), *words)
    assert len(code) <= DIAGNOSTICS - BASE
    payload = code + bytes(DIAGNOSTICS - BASE - len(code)) + struct.pack('<5I', 0xFFFFFFFF, 0, 0, 0, 0)
    assert len(payload) <= 0xF00 and BASE + len(payload) < HEAP_START
    assert not any(source[0x54:0x1000])
    assert struct.unpack_from('<H', source, 44)[0] == 1
    result = bytearray(source)
    allowed, changes = [], []

    def patch(off, data, why):
        result[off:off + len(data)] = data
        allowed.append((off, off + len(data)))
        changes.append({'offset': off, 'size': len(data), 'why': why})

    patch(FILE_OFFSET, payload, 'new segment payload in unused file header padding')
    # Main PT_LOAD stays byte-identical. New code is above the startup clear and below the reserved heap.
    ph = struct.pack('<8I', 1, FILE_OFFSET, BASE, BASE, len(payload), len(payload), 7, 16)
    patch(0x54, ph, 'second PT_LOAD with matched offset/address alignment')
    patch(44, struct.pack('<H', 2), 'program header count')
    va_off = lambda va: va - 0xFF000
    assert struct.unpack_from('<I', source, va_off(0x274924))[0] == 0x2484E08C
    patch(va_off(0x274924), struct.pack('<I', 0x2484F000), 'reserve native heap start at 0x6DF000; 3956 extra bytes')
    # SDK sbrk keeps a separate initialized break; SetupHeap alone does not reserve it.
    for va in (0x405C44, 0x3F6B78):
        assert struct.unpack_from('<I', source, va_off(va))[0] == 0x6DE08C
        patch(va_off(va), struct.pack('<I', HEAP_START), 'SDK sbrk initial break / startup heap metadata')
    expected = {0x266138: [0x0000182D, 0x18C00022],
                0x2660D0: [0x0080382D, 0x30A500FF],
                0x2661D0: [0x0080382D, 0x30A500FF],
                0x264D80: [0x8FA30010, 0x8FA40024],
                0x265F50: [0x8FA50014, 0x24840001],
                0x1758A0: [0x27BDFF80, 0x7FB10010],
                0x1159EC: [0x7BBF00B0, 0x7BBE00A0],
                0x264DEC: [0x12E00458, 0x8FA40024]}
    for va, target in ((0x266138, 'measure'), (0x2660D0, 'lookup'), (0x2661D0, 'char_width'),
                       (0x264D80, 'draw_decode'), (0x265F50, 'draw_advance'), (0x1758A0, 'wrap'),
                       (0x1159EC, 'allocation_audit'), (0x264DEC, 'draw_lookup_audit')):
        assert list(struct.unpack_from('<2I', source, va_off(va))) == expected[va]
        patch(va_off(va), struct.pack('<2I', 0x08000000 | labels[target] >> 2, 0), target)
    for row in native_records(source):
        data = row['target'].encode('gbk') + b'\0'
        patch(row['offset'], data + bytes(row['size'] - len(data)), 'native memory-card text')
    # Prove no existing memory access overlaps the new draw-local scratch word.
    widths = {32: 1, 36: 1, 40: 1, 33: 2, 37: 2, 41: 2, 35: 4, 43: 4, 49: 4, 57: 4, 55: 8, 63: 8, 30: 16, 31: 16}
    for va in range(0x264C28, 0x265FD4, 4):
        w = struct.unpack_from('<I', source, va_off(va))[0]
        op, rs, imm = w >> 26, w >> 21 & 31, w & 65535
        if rs == 29 and op in widths:
            assert not (imm < 0x58 and 0x54 < imm + widths[op]), hex(va)
    # No code or branch may enter an overwritten delay word independently.
    forbidden = {va + 4 for va in expected}
    for va in range(0x100000, 0x3E70E0, 4):
        w = struct.unpack_from('<I', source, va_off(va))[0]
        op, imm = w >> 26, w & 65535
        if op in (2, 3):
            assert (w & 0x3FFFFFF) << 2 not in forbidden
        if op in (1, 4, 5, 6, 7, 20, 21, 22, 23) or op == 17 and (w >> 21 & 31) == 8:
            displacement = imm - 65536 if imm & 32768 else imm
            assert va + 4 + displacement * 4 not in forbidden
    assert len(result) == len(source)
    assert all(any(lo <= n < hi for lo, hi in allowed) for n, (a, b_) in enumerate(zip(source, result)) if a != b_)
    (HERE / 'assets/SLUS_202.06').write_bytes(result)
    control = bytearray(source)
    for change in changes:
        if change['offset'] in (FILE_OFFSET, 0x54, 44, va_off(0x274924), va_off(0x405C44),
                                va_off(0x3F6B78), va_off(0x1159EC)):
            off, size = change['offset'], change['size']
            control[off:off + size] = result[off:off + size]
    (HERE / 'assets/SLUS_202.06.control').write_bytes(control)
    report = {'code_base': hex(BASE), 'code_bytes': len(code), 'segment_bytes': len(payload),
              'diagnostics': hex(DIAGNOSTICS), 'diagnostic_fields': ['minimum_main_heap_free', 'allocator_returns', 'null_returns', 'missing_double_byte_lookups', 'last_missing_code'],
              'heap_start': hex(HEAP_START),
              'extra_heap_reservation': HEAP_START - 0x6DE08C,
              'entry_points': {k: hex(v) for k, v in labels.items()}, 'changes': changes,
              'preserved_dvp_tail': source[0x35FF3C:] == result[0x35FF3C:],
              'sha256': hashlib.sha256(result).hexdigest(), 'runtime_tested': False}
    (HERE / 'native-patch.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'entry_points'}, indent=2))


if __name__ == '__main__':
    build()
