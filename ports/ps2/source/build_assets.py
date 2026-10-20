"""Canonical full text/font assets using the verified native serializers."""
import collections
import hashlib
import importlib.util
import json
import re
import struct
import sys
from pathlib import Path

from PIL import ImageFont

HERE = Path(__file__).resolve().parent
SAMPLE = Path('inputs/menu-sample/work')
SRC = Path('inputs/source')
sys.dont_write_bytecode = True
sys.path.insert(0, str(SAMPLE))
from build_sample import parse_font, encode_font, rasterize
from inspect_menu import leaves
from native_strings import records as native_records


def rebuild_docb(source, records):
    original = leaves(source)
    assert records.keys() == original.keys()

    def node(p, parent):
        start = p
        kind, size = source[p:p + 2]
        key = parent + '/' + source[p + 2:p + 2 + size - 1].decode('ascii')
        p += 2 + ((size + 1) & ~1)
        n = struct.unpack_from('<H', source, p)[0]
        p += 2
        if kind == 4:
            end = p + ((n + 1) & ~1)
            value = source[p:p + 2] + records[key]
            item = source[start:p - 2] + struct.pack('<H', len(value)) + value
            return item + (b'\0' if len(value) & 1 else b''), end
        assert kind == 6
        item = source[start:p]
        for _ in range(n):
            child, p = node(p, key)
            item += child
        return item, p

    p = 0x36
    tree = source[0x34:0x36]
    for _ in range(struct.unpack_from('<H', source, 0x34)[0]):
        item, p = node(p, '')
        tree += item
    assert source[p:p + 4] == bytes.fromhex('fbb82b72')
    result = bytearray(source[:0x34]) + tree + source[p:p + 12]
    struct.pack_into('<I', result, 0x30, len(tree))
    assert len(result) <= len(source)
    result += bytes(len(source) - len(result))
    parsed = leaves(result)
    assert parsed.keys() == original.keys()
    assert all(parsed[k] == original[k][:2] + records[k] for k in original)
    return bytes(result)


def main():
    dest = HERE / 'assets'
    dest.mkdir(exist_ok=True)
    source = (SRC / 'ps2/ENGLISH.DAT').read_bytes()
    original = leaves(source)
    pc = leaves((SRC / 'chs_patch/update/library/language/english.dat').read_bytes())
    accepted = json.loads((SAMPLE / 'menu-translations.json').read_text(encoding='utf-8'))
    overrides = {
        '/game/info/oos/with': "检测到玩家“{1:s}”在第 {2:d} 个周期与本机不同步。",
        '/game/info/oos/message': '游戏状态已与其他玩家不同步，\r\n继续游戏可能导致结果不一致。\r\n\r\n要继续游戏，还是中止？',
        '/game/messages/eliminated_human': '敌方玩家 {1:s} 已被消灭。',
    }
    tutorial = json.loads((HERE / 'tutorial-translations.json').read_text(encoding='utf-8'))
    assert all(key in original and key.startswith('/missions/bc_s/t0') and '/objective' in key for key in tutorial)
    overrides.update(tutorial)
    units = json.loads((HERE / 'unit-translations.json').read_text(encoding='utf-8'))
    assert units.keys() <= original.keys()
    overrides.update(units)
    # NATO team names are intentional identifiers; keep them consistent with the PC patch.
    texts = {k: pc[k][2:].decode('gbk') if k in pc else v[2:].decode('latin1')
             for k, v in original.items()}
    texts.update(accepted)
    texts.update(overrides)
    # The PC patch has four literal backslash-r + LF sequences; PS2 expects actual CRLF.
    normalized = [key for key, value in texts.items() if '\\r\n' in value or '\\r\\n' in value]
    texts = {key: value.replace('\\r\\n', '\r\n').replace('\\r\n', '\r\n') for key, value in texts.items()}
    encoded = {k: value.encode('gbk') for k, value in texts.items()}
    token_mismatches = [k for k in original if collections.Counter(re.findall(rb'\{[^}]*\}', original[k][2:]))
                        != collections.Counter(re.findall(rb'\{[^}]*\}', encoded[k]))]
    assert not token_mismatches
    assert all(b'\0' not in value for value in encoded.values())
    assert all(b'\\r' not in value and b'\\n' not in value for value in encoded.values())
    percent = rb'%(?:[-+ #0]*\d*(?:\.\d+)?[diuoxXfFeEgGcsp%])'
    assert all(collections.Counter(re.findall(percent, original[key][2:])) == collections.Counter(re.findall(percent, value))
               for key, value in encoded.items())
    records = [{'key': k, 'source': original[k][2:].decode('latin1'), 'target': texts[k],
                'metadata_hex': original[k][:2].hex(),
                'origin': 'override' if k in overrides else 'accepted_menu' if k in accepted else 'pc_patch' if k in pc else 'original'}
               for k in original]
    (HERE / 'texts.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    native = native_records((SRC / 'ps2/SLUS_202.06.elf').read_bytes())
    (HERE / 'native-strings.json').write_text(json.dumps(native, ensure_ascii=False, indent=2), encoding='utf-8')
    corpus = [*texts.values(), *(row['target'] for row in native)]
    (HERE / 'corpus.txt').write_text('\n'.join(corpus), encoding='utf-8')
    (dest / 'ENGLISH.DAT').write_bytes(rebuild_docb(source, encoded))

    coverage_script = Path('inputs/check_font_coverage.py')
    spec = importlib.util.spec_from_file_location('font_coverage_tool', coverage_script)
    coverage_tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(coverage_tool)
    font_path = Path('C:/Windows/Fonts/msyh.ttc')
    covered, formats, _ = coverage_tool.font_coverage(font_path, 0)
    chars = sorted({ch for value in corpus for ch in value if ord(ch) > 127})
    assert all(ord(ch) in covered for ch in chars)
    double_codes = {int.from_bytes(ch.encode('gbk'), 'big'): ch for ch in chars}
    assert all(len(ch.encode('gbk')) == 2 for ch in chars)
    baseline_dir = HERE / 'revisions/v0.2.4'
    baseline_report = json.loads((baseline_dir / 'assets-validation.json').read_text(encoding='utf-8'))
    baseline_fonts = {row['alias']: row for row in baseline_report['fonts']}
    reports = []
    for original_name, alias, px, baseline in (
        ('font_arial_10.fff', 'font_arial_cn.fff', 14, 16),
        ('font_stencil_24.fff', 'font_stencil_cn.fff', 24, 26),
        ('font_arial_memcard_10.fff', 'font_arial_memcard_cn.fff', 14, 16),
    ):
        assert len(alias) == len(original_name)
        source_font = (SRC / 'ps2/base_extract' / original_name).read_bytes()
        height, original_glyphs = parse_font(source_font)
        baseline_data = (baseline_dir / 'fonts' / alias).read_bytes()
        assert hashlib.sha256(baseline_data).hexdigest() == baseline_fonts[alias]['sha256']
        baseline_height, glyphs = parse_font(baseline_data)
        assert baseline_height == height
        face = ImageFont.truetype(str(font_path), px, index=0)
        for code, ch in double_codes.items():
            if code not in glyphs:
                glyphs[code] = rasterize(ch, code, face, baseline, height)
        output = encode_font(height, glyphs)
        assert parse_font(output) == (height, glyphs)
        assert all(glyphs[k] == v for k, v in original_glyphs.items())
        assert all(code in glyphs for code in double_codes)
        (dest / alias).write_bytes(output)
        reports.append({'source': original_name, 'alias': alias, 'height': height, 'raster_px': px,
                        'glyph_count': len(glyphs), 'file_bytes': len(output),
                        'record_bytes': len(glyphs) * 40,
                        'descriptor_temp_bytes': len(glyphs) * 8,
                        'bitmap_pixels': sum(len(value[1]) - 2 for value in glyphs.values()),
                        'max_bucket_count': max(collections.Counter(code & 255 for code in glyphs).values()),
                        'sha256': hashlib.sha256(output).hexdigest()})
    report = {'keys': len(records), 'native_message_cells': len(native), 'gbk_double_glyphs': len(double_codes),
              'cjk_characters': sum('\u4e00' <= ch <= '\u9fff' for ch in chars),
              'metadata_controls_preserved': True, 'normalized_pc_newline_keys': normalized,
              'intentional_reflow_keys': ['/game/info/oos/message'], 'unicode_cmap_formats': formats,
              'unicode_missing_glyphs': [], 'fonts': reports,
              'untranslated_ascii_identifiers': {k: v for k, v in texts.items() if k.startswith('/multiplayer/setup/teams/')},
              'retained_font_baseline': 'revisions/v0.2.4/fonts',
              'unit_terminology_override_keys': list(units), 'runtime_tested': False}
    (HERE / 'assets-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
