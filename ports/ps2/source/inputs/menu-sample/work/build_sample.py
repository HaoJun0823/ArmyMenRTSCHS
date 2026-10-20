"""Build and verify an independent PS2 menu prototype without ELF changes."""
import collections
import hashlib
import json
import math
import os
import re
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from inspect_menu import ISO, SRC, leaves

HERE = Path(__file__).resolve().parent
OUTPUT = HERE.parent / 'outputs'
FONT_PATH = Path('C:/Windows/Fonts/msyh.ttc')
SOURCE_SHA = '08e0acf4cf204d234e78c672166c8c06d99629a2a7604cf9885f51eed56b6d7f'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_font(b):
    assert b[:4] == b'BORK'
    n = struct.unpack_from('<H', b, 4)[0]
    assert 9 + n * 7 <= len(b)
    p = 9 + n * 7
    glyphs = {}
    for i in range(n):
        desc = b[9 + 7 * i:16 + 7 * i]
        code = struct.unpack_from('<H', desc)[0]
        assert code not in glyphs and p + 2 <= len(b)
        w, h = b[p:p + 2]
        end = p + 2 + w * h
        assert w < 101 and h < 101 and end <= len(b)
        glyphs[code] = (desc, b[p:end])
        p = end
    assert p == len(b)
    return b[6], glyphs


def encode_font(height, glyphs):
    keys = sorted(glyphs)
    return (b'BORK' + struct.pack('<HBBB', len(keys), height, 0, 0)
            + b''.join(glyphs[k][0] for k in keys)
            + b''.join(glyphs[k][1] for k in keys))


def rasterize(ch, code, font, baseline, height):
    canvas = Image.new('L', (64, height), 0)
    ImageDraw.Draw(canvas).text((4, baseline), ch, font=font, fill=255, anchor='ls')
    bounds = canvas.getbbox()
    assert bounds is not None
    x0, y0, x1, y1 = bounds
    assert 0 <= x0 - 4 < x1 - 4 < 100 and 0 <= y0 < y1 <= height
    # A larger canvas proves the chosen baseline does not crop the glyph.
    proof = Image.new('L', (64, 64), 0)
    ImageDraw.Draw(proof).text((4, baseline + 16), ch, font=font, fill=255, anchor='ls')
    full = proof.getbbox()
    assert full == (x0, y0 + 16, x1, y1 + 16)
    advance = math.ceil(font.getlength(ch)) + 1
    desc = struct.pack('<H5B', code, advance, x0 - 4, y0, x1 - 4, y1)
    bitmap = bytes((x1 - x0, y1 - y0)) + canvas.crop(bounds).tobytes()
    return desc, bitmap


def rebuild_font(source, mapping, protected):
    height, original = parse_font(source)
    baseline = 16 if height == 20 else 26
    candidates = (16, 15, 14, 13) if height == 20 else (24,)
    for px in candidates:
        face = ImageFont.truetype(str(FONT_PATH), px, index=0)
        glyphs = {code: item for code, item in original.items()
                  if code < 128 or code in protected}
        for ch, code in mapping.items():
            assert code in original and code not in protected
            glyphs[code] = rasterize(ch, code, face, baseline, height)
        output = encode_font(height, glyphs)
        if len(output) <= len(source):
            assert parse_font(output) == (height, glyphs)
            assert all(glyphs[k] == v for k, v in original.items() if k < 128 or k in protected)
            return output, glyphs, {'height': height, 'raster_px': px,
                                     'glyphs': len(glyphs), 'size': len(output), 'allocation': len(source)}
    raise ValueError('Chinese glyphs do not fit the original font allocation')


def rebuild_docb(source, translations, mapping):
    original = leaves(source)
    encoded = {k: bytes(ord(c) if ord(c) < 128 else mapping[c] for c in value)
               for k, value in translations.items()}
    assert encoded.keys() <= original.keys()

    def node(p, parent):
        start = p
        kind, size = source[p:p + 2]
        key = parent + '/' + source[p + 2:p + 2 + size - 1].decode('ascii')
        p += 2 + ((size + 1) & ~1)
        n = struct.unpack_from('<H', source, p)[0]
        p += 2
        if kind == 4:
            end = p + ((n + 1) & ~1)
            if key not in encoded:
                return source[start:end], end
            before = source[p:p + n]
            value = before[:2] + encoded[key]
            assert collections.Counter(re.findall(rb'\{[^}]*\}', before[2:])) == collections.Counter(re.findall(rb'\{[^}]*\}', value[2:]))
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
    output = bytearray(source[:0x34]) + tree + source[p:p + 12]
    struct.pack_into('<I', output, 0x30, len(tree))
    assert len(output) <= len(source)
    output += bytes(len(source) - len(output))
    actual = leaves(output)
    assert actual.keys() == original.keys() and len(actual) == 838
    for k, value in original.items():
        assert actual[k] == value[:2] + encoded.get(k, value[2:])
    return bytes(output), encoded


def nork_entries(b):
    assert b[:4] == b'NORK'
    p, end = struct.unpack_from('<I', b, 20)[0], struct.unpack_from('<I', b, 12)[0]
    entries = []
    while p < end:
        directory, n = struct.unpack_from('<IB', b, p)
        p += 5
        assert n and p + n + 8 <= end
        name = b[p:p + n].decode('ascii')
        p += n
        off, size = struct.unpack_from('<II', b, p)
        assert off + size <= len(b)
        entries.append({'name': name, 'offset': off, 'size': size, 'size_field': p + 4})
        p += 8
    assert p == end
    return entries


def proof_image(fonts, translations, encoded):
    image = Image.new('RGB', (1000, 850), '#152019')
    draw = ImageDraw.Draw(image)
    label = ImageFont.truetype(str(FONT_PATH), 17)
    draw.text((28, 18), 'PS2 菜单中文小样｜实际字库位图检查（非游戏截图）', font=label, fill='#f0eac9')
    draw.text((28, 49), '保留原生字体高度与英文；中文用独立单字节槽位。', font=label, fill='#a9bdad')
    for col, name in enumerate(('font_arial_10.fff', 'font_stencil_24.fff')):
        glyphs = fonts[name]
        xbase = 28 + col * 485
        draw.text((xbase, 90), name, font=label, fill='#b8c98b')
        keys = list(translations)[:23]
        for row, key in enumerate(keys):
            x, y = xbase, 126 + row * 29
            for code in encoded[key]:
                desc, bitmap = glyphs[code]
                w, h = bitmap[:2]
                if w and h:
                    mask = Image.frombytes('L', (w, h), bitmap[2:])
                    image.paste('#e7e4c5', (x + desc[3], y + desc[4]), mask)
                x += desc[2]
            assert x - xbase < 455
    image.save(OUTPUT / 'menu-glyph-proof.png')


def main():
    OUTPUT.mkdir(exist_ok=True)
    translations = json.loads((HERE / 'menu-translations.json').read_text(encoding='utf-8'))
    coverage = json.loads((HERE / 'font-coverage.json').read_text(encoding='utf-8'))
    assert coverage['coverage_ok'] and coverage['missing_count'] == 0
    original_dat = (SRC / 'ps2/ENGLISH.DAT').read_bytes()
    protected = {code for value in leaves(original_dat).values() for code in value[2:] if code >= 128}
    assert protected == {169, 174}
    chars = sorted({c for value in translations.values() for c in value if ord(c) >= 128})
    slots = [code for code in range(128, 256) if code not in protected]
    assert len(chars) <= len(slots)
    mapping = dict(zip(chars, slots))
    new_dat, encoded = rebuild_docb(original_dat, translations, mapping)
    reverse = {value: key for key, value in mapping.items()}
    assert all(''.join(chr(c) if c < 128 else reverse[c] for c in encoded[k]) == value for k, value in translations.items())
    fonts, payloads, font_stats = {}, {}, {}
    for name in ('font_arial_10.fff', 'font_stencil_24.fff'):
        source = (SRC / 'ps2/base_extract' / name).read_bytes()
        payloads[name], fonts[name], font_stats[name] = rebuild_font(source, mapping, protected)
        (HERE / name).write_bytes(payloads[name])
    (HERE / 'ENGLISH.DAT').write_bytes(new_dat)
    proof_image(fonts, translations, encoded)
    (HERE / 'glyph-map.json').write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding='utf-8')

    # The archived audit supplies ISO locations; validate every source payload below.
    audit = json.loads(Path('inputs/iso-evidence.json').read_text(encoding='utf-8'))
    iso_entries = {item['path']: item for item in audit['iso']['entries']}
    patches = []
    contexts = []
    with ISO.open('rb') as original:
        for path in ('/BASE.X', '/MISSIONS/SHELLS/MAIN.X'):
            info = iso_entries[path]
            base = info['lba'] * 2048
            original.seek(base)
            archive = original.read(info['size'])
            entries = nork_entries(archive)
            for name, payload in payloads.items():
                entry = next(e for e in entries if e['name'] == name)
                old = (SRC / 'ps2/base_extract' / name).read_bytes()
                assert archive[entry['offset']:entry['offset'] + entry['size']] == old
                assert len(payload) <= entry['size']
                patches.append((base + entry['offset'], payload + bytes(entry['size'] - len(payload)), path + '/' + name))
                patches.append((base + entry['size_field'], struct.pack('<I', len(payload)), path + '/' + name + ':size'))
                contexts.append({'archive': path, 'font': name, 'old_size': entry['size'], 'new_size': len(payload)})
        info = iso_entries['/LIBRARY/LANGUAGE/ENGLISH.DAT']
        offset = info['lba'] * 2048
        original.seek(offset)
        assert original.read(info['size']) == original_dat
        patches.append((offset, new_dat, '/LIBRARY/LANGUAGE/ENGLISH.DAT'))
    patches.sort()
    for left, right in zip(patches, patches[1:]):
        assert left[0] + len(left[1]) <= right[0]
    total = ISO.stat().st_size
    assert total == 1344634880
    temporary = OUTPUT / 'Army_Men_RTS_PS2_CHS_Menu_Sample_v0.1.iso.partial'
    destination = temporary.with_suffix('')
    assert not temporary.exists() and not destination.exists(), 'Refusing to replace an existing build'
    print(json.dumps({'phase': 'assets_ready', 'fonts': font_stats, 'strings': len(translations), 'chinese_glyphs': len(chars)}, ensure_ascii=False), flush=True)
    source_hash = hashlib.sha256()
    with ISO.open('rb') as original, temporary.open('xb') as output:
        while chunk := original.read(4 * 1024 * 1024):
            source_hash.update(chunk)
            output.write(chunk)
    assert source_hash.hexdigest() == SOURCE_SHA, 'Original ISO fingerprint differs'
    with temporary.open('r+b') as output:
        for offset, payload, _ in patches:
            output.seek(offset)
            output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    # Compare every byte of untouched intervals, not only selected files.
    expected_hash, verified_source_hash = hashlib.sha256(), hashlib.sha256()
    ranges = []
    with ISO.open('rb') as original, temporary.open('rb') as output:
        p = 0
        for offset, payload, name in patches + [(total, b'', 'end')]:
            remaining = offset - p
            while remaining:
                n = min(remaining, 4 * 1024 * 1024)
                a, b = original.read(n), output.read(n)
                assert len(a) == n and a == b, ('Untouched bytes differ', p)
                verified_source_hash.update(a)
                expected_hash.update(b)
                p += n
                remaining -= n
            if payload:
                before, actual = original.read(len(payload)), output.read(len(payload))
                assert actual == payload
                verified_source_hash.update(before)
                expected_hash.update(actual)
                ranges.append({'offset': offset, 'size': len(payload), 'asset': name,
                               'before_sha256': digest(before), 'after_sha256': digest(payload)})
                p += len(payload)
        assert original.read(1) == output.read(1) == b''
    assert verified_source_hash.hexdigest() == SOURCE_SHA
    assert temporary.stat().st_size == total
    # Explicitly confirm native font configuration, menu bindings, and ELF preservation.
    with temporary.open('rb') as image:
        exe = iso_entries['/SLUS_202.06']
        image.seek(exe['lba'] * 2048)
        assert digest(image.read(exe['size'])) == audit['elf']['sha256']
        for path in ('/BASE.X', '/MISSIONS/SHELLS/MAIN.X'):
            item = iso_entries[path]
            image.seek(item['lba'] * 2048)
            archive = image.read(item['size'])
            for entry in nork_entries(archive):
                if entry['name'] in payloads:
                    payload = archive[entry['offset']:entry['offset'] + entry['size']]
                    assert payload == payloads[entry['name']]
                    assert all(c in parse_font(payload)[1] for value in encoded.values() for c in value)
    temporary.rename(destination)
    report = {'version': '0.1', 'target': 'USA SLUS-20206', 'source_sha256': SOURCE_SHA,
              'sample_sha256': expected_hash.hexdigest(), 'iso_size': total,
              'sample_path': str(destination), 'translated_strings': len(translations),
              'chinese_glyphs': len(chars), 'mapping': mapping, 'font_builds': font_stats,
              'font_contexts': contexts, 'modified_ranges': ranges,
              'source_unchanged_verified': True, 'all_other_iso_bytes_identical': True,
              'elf_unchanged': True, 'unicode_cmap_coverage': coverage,
              'runtime_tested': False, 'preview_is_game_screenshot': False}
    (OUTPUT / 'build-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'phase': 'verified', 'path': str(destination), 'sha256': expected_hash.hexdigest()}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
