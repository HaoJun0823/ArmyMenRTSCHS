"""Build an independent ISO with unchanged payload offsets and audited edits."""
import hashlib
import json
import os
import shutil
import struct
from pathlib import Path

from inventory import nork
from inspect_menu import ISO

HERE = Path(__file__).resolve().parent
ALIASES = {'font_arial_10.fff': 'font_arial_cn.fff',
           'font_stencil_24.fff': 'font_stencil_cn.fff',
           'font_arial_memcard_10.fff': 'font_arial_memcard_cn.fff'}
SOURCE_SHA = '08e0acf4cf204d234e78c672166c8c06d99629a2a7604cf9885f51eed56b6d7f'


def archive(source, base=False):
    entries, dirs = nork(source)
    result = bytearray(source)
    edits = []
    for row in entries:
        if not row['name'].endswith('.cfg'):
            continue
        off, size = row['offset'], row['size']
        old = source[off:off + size]
        new = old
        for before, after in ALIASES.items():
            assert len(before) == len(after)
            new = new.replace(before.encode(), after.encode())
        if new != old:
            result[off:off + size] = new
            edits.append(dict(path=row['path'], offset=off, size=size))
    added = []
    if base:
        old_paths, table = struct.unpack_from('<I', source, 12)[0], struct.unpack_from('<I', source, 20)[0]
        assert all(row['offset'] + row['size'] <= table for row in entries)
        result = result[:table]
        extra = bytearray()
        for name, alias in ALIASES.items():
            matches = [row for row in entries if row['name'] == name]
            assert len(matches) == 1 and not any(row['name'] == alias for row in entries)
            original = matches[0]
            result += bytes((-len(result)) % 128)
            off = len(result)
            font = (HERE / 'assets' / alias).read_bytes()
            result += font
            encoded = alias.encode()
            extra += struct.pack('<IB', original['directory'], len(encoded)) + encoded + struct.pack('<II', off, len(font))
            added.append(dict(name=alias, offset=off, size=len(font), alignment=128))
        new_table = len(result)
        result += source[table:old_paths] + extra
        new_paths = len(result)
        result += source[old_paths:]
        struct.pack_into('<I', result, 12, new_paths)
        struct.pack_into('<II', result, 16, len(entries) + len(added), new_table)
    actual, actual_dirs = nork(result)
    assert actual_dirs == dirs and len(actual) == len(entries) + len(added)
    for old, new in zip(entries, actual):
        assert all(old[key] == new[key] for key in ('directory', 'name', 'path', 'offset', 'size'))
        if not any(old['path'] == row['path'] for row in edits):
            assert source[old['offset']:old['offset'] + old['size']] == result[new['offset']:new['offset'] + new['size']]
    for row in added:
        assert row['offset'] % 128 == 0
        match = [item for item in actual if item['name'] == row['name']]
        assert len(match) == 1 and match[0]['offset'] == row['offset'] and match[0]['size'] == row['size']
    return bytes(result), dict(bindings=edits, added=added, original_payload_offsets_preserved=True)


def both(value):
    return struct.pack('<I', value) + struct.pack('>I', value)


def root_records(block):
    p = 0
    while p < len(block):
        size = block[p]
        if not size:
            p = (p // 2048 + 1) * 2048
            continue
        assert p + size <= len(block)
        name = bytes(block[p + 33:p + 33 + block[p + 32]]).split(b';')[0]
        yield p, name
        p += size


def build():
    output = HERE / 'candidates'
    output.mkdir(exist_ok=True)
    target = output / 'Army_Men_RTS_PS2_CHS_Full_v0.2.5_test.iso'
    temporary = target.with_suffix('.iso.building')
    assert not target.exists() and not temporary.exists()
    evidence = json.loads(Path('inputs/iso-evidence.json').read_text(encoding='utf-8'))
    files = {row['path']: row for row in evidence['iso']['entries'] if not row['directory']}
    mutations, reports = [], []
    source_hash = hashlib.sha256()
    with ISO.open('rb') as src, temporary.open('xb') as dst:
        while block := src.read(8 * 1024 * 1024):
            source_hash.update(block)
            dst.write(block)
    assert source_hash.hexdigest() == SOURCE_SHA
    with ISO.open('rb') as src, temporary.open('r+b') as dst:
        def edit(off, payload, why):
            dst.seek(off)
            dst.write(payload)
            mutations.append(dict(offset=off, size=len(payload), why=why, sha256=hashlib.sha256(payload).hexdigest()))

        for path, name in (('/SLUS_202.06', 'SLUS_202.06'), ('/LIBRARY/LANGUAGE/ENGLISH.DAT', 'ENGLISH.DAT')):
            row = files[path]
            payload = (HERE / 'assets' / name).read_bytes()
            assert len(payload) == row['size']
            edit(row['lba'] * 2048, payload, path)
        base_size = None
        for row in files.values():
            if not row['path'].endswith('.X'):
                continue
            src.seek(row['lba'] * 2048)
            data = src.read(row['size'])
            if data[:4] != b'NORK':
                continue
            new, report = archive(data, row['path'] == '/BASE.X')
            if new == data:
                continue
            if row['path'] == '/BASE.X':
                base_size = len(new)
                edit(row['lba'] * 2048, new, 'BASE.X appended aligned font aliases')
            else:
                assert len(new) == len(data)
                for binding in report['bindings']:
                    off, size = binding['offset'], binding['size']
                    edit(row['lba'] * 2048 + off, new[off:off + size], row['path'] + ':' + binding['path'])
            reports.append(dict(archive=row['path'], **report))
        assert base_size is not None
        base = files['/BASE.X']
        listing = files['/DIR_LIST.LST']
        assert base['lba'] + (base['size'] + 2047) // 2048 == listing['lba']
        assert all(row['lba'] <= base['lba'] or row['path'] == '/DIR_LIST.LST' for row in files.values())
        new_listing_lba = base['lba'] + (base_size + 2047) // 2048
        src.seek(listing['lba'] * 2048)
        listing_data = src.read(listing['size'])
        # The game's directory cache stores file sizes in addition to ISO9660 metadata.
        needle = struct.pack('<I', base['size']) + struct.pack('<H', 7) + b'base.x\0'
        assert listing_data.count(needle) == 1
        listing_data = listing_data.replace(needle, struct.pack('<I', base_size) + needle[4:])
        edit(new_listing_lba * 2048, listing_data, 'relocated root DIR_LIST.LST and updated BASE.X cached size')
        src.seek(16 * 2048)
        pvd = bytearray(src.read(2048))
        assert pvd[:7] == b'\x01CD001\x01'
        root_lba, root_size = struct.unpack_from('<II', pvd, 158)[0], struct.unpack_from('<I', pvd, 166)[0]
        src.seek(root_lba * 2048)
        root = bytearray(src.read(root_size))
        found = set()
        for p, name in root_records(root):
            if name == b'BASE.X':
                root[p + 10:p + 18] = both(base_size)
                found.add(name)
            elif name == b'DIR_LIST.LST':
                root[p + 2:p + 10] = both(new_listing_lba)
                found.add(name)
        assert found == {b'BASE.X', b'DIR_LIST.LST'}
        edit(root_lba * 2048, root, 'ISO root directory extents and sizes')
        sectors = max((ISO.stat().st_size + 2047) // 2048, new_listing_lba + 16)
        pvd[80:88] = both(sectors)
        edit(16 * 2048, pvd, 'ISO volume size both-endian')
        dst.truncate(sectors * 2048)
    # Independent full-stream comparison allows changes only in explicitly recorded ranges.
    ranges = sorted((row['offset'], row['offset'] + row['size']) for row in mutations)
    differences = 0
    result_hash = hashlib.sha256()
    with ISO.open('rb') as src, temporary.open('rb') as dst:
        pos = 0
        while new := dst.read(1024 * 1024):
            old = src.read(len(new))
            result_hash.update(new)
            cursor = 0
            for lo, hi in ranges:
                a, b = max(pos, lo) - pos, min(pos + len(new), hi) - pos
                if a >= b:
                    continue
                assert new[cursor:a] == old[cursor:a] + bytes(max(0, a - max(cursor, len(old))))
                differences += sum(x != y for x, y in zip(new[a:b], old[a:b]))
                cursor = max(cursor, b)
            expected = old[cursor:] + bytes(max(0, len(new) - max(cursor, len(old))))
            assert new[cursor:] == expected, hex(pos + cursor)
            pos += len(new)
    os.replace(temporary, target)
    report = dict(image=str(target), source_sha256=SOURCE_SHA, sha256=result_hash.hexdigest(),
                  image_bytes=target.stat().st_size, mutations=mutations, archives=reports,
                  original_payload_offsets_preserved=True, new_font_alignment=128,
                  iso_sector_alignment=2048, full_stream_allowlist_passed=True,
                  changed_existing_bytes=differences, runtime_tested=False)
    (HERE / 'disc-validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('mutations', 'archives')}, indent=2))


if __name__ == '__main__':
    build()
