"""Independently read back ISO9660, mutation digests and native archive payloads."""
import hashlib
import json
import struct
from pathlib import Path

from inventory import nork
from build_assets import leaves
from build_disc import ALIASES

HERE = Path(__file__).resolve().parent


def u32both(data, offset):
    little = struct.unpack_from('<I', data, offset)[0]
    assert little == struct.unpack_from('>I', data, offset + 4)[0]
    return little


def main():
    report = json.loads((HERE / 'disc-validation.json').read_text(encoding='utf-8'))
    path = Path(report['image'])
    entries = {}
    with path.open('rb') as disc:
        disc.seek(16 * 2048)
        pvd = disc.read(2048)
        assert pvd[:7] == b'\x01CD001\x01' and u32both(pvd, 80) * 2048 == path.stat().st_size

        def walk(lba, size, parent):
            assert lba > 0 and size > 0 and lba * 2048 + size <= path.stat().st_size
            disc.seek(lba * 2048)
            data = disc.read(size)
            cursor = 0
            while cursor < size:
                length = data[cursor]
                if not length:
                    cursor = (cursor // 2048 + 1) * 2048
                    continue
                assert length >= 34 and cursor + length <= size and cursor % 2048 + length <= 2048
                row = data[cursor:cursor + length]
                name = row[33:33 + row[32]]
                if name not in (b'\0', b'\1'):
                    name = name.split(b';')[0].decode('ascii')
                    key = parent + '/' + name
                    assert key not in entries
                    extent, amount = u32both(row, 2), u32both(row, 10)
                    assert extent * 2048 + amount <= path.stat().st_size
                    directory = bool(row[25] & 2)
                    entries[key] = dict(lba=extent, size=amount, directory=directory)
                    if directory:
                        walk(extent, amount, key)
                cursor += length

        walk(u32both(pvd, 158), u32both(pvd, 166), '')
        original = json.loads(Path('inputs/iso-evidence.json').read_text(encoding='utf-8'))['iso']['entries']
        original = {row['path']: row for row in original}
        assert entries.keys() == original.keys()
        for key, row in entries.items():
            assert row['directory'] == original[key]['directory']
            if key != '/DIR_LIST.LST':
                assert row['lba'] == original[key]['lba']
            if key != '/BASE.X':
                assert row['size'] == original[key]['size']
        ranges = sorted((row['lba'], row['lba'] + (row['size'] + 2047) // 2048, key)
                        for key, row in entries.items() if row['size'])
        assert all(end <= following for (_, end, _), (following, _, _) in zip(ranges, ranges[1:]))
        for mutation in report['mutations']:
            disc.seek(mutation['offset'])
            actual = hashlib.sha256(disc.read(mutation['size'])).hexdigest()
            assert actual == mutation['sha256'], mutation['why']
        for archive in report['archives']:
            row = entries[archive['archive']]
            disc.seek(row['lba'] * 2048)
            payload = disc.read(row['size'])
            files, _ = nork(payload)
            for binding in archive['bindings']:
                data = payload[binding['offset']:binding['offset'] + binding['size']]
                assert all(before.encode() not in data for before in ALIASES)
            if archive['archive'] == '/BASE.X':
                for alias in ALIASES.values():
                    matches = [item for item in files if item['name'] == alias]
                    assert len(matches) == 1
                    item = matches[0]
                    assert item['offset'] % 128 == 0
                    assert payload[item['offset']:item['offset'] + item['size']] == (HERE / 'assets' / alias).read_bytes()
        row = entries['/DIR_LIST.LST']
        disc.seek(row['lba'] * 2048)
        cache = disc.read(row['size'])
        cursor, cache_base_size = 4, None
        for _ in range(struct.unpack_from('<I', cache)[0]):
            _, amount, length = struct.unpack_from('<IIH', cache, cursor)
            cursor += 10
            name = cache[cursor:cursor + length].rstrip(b'\0')
            cursor += length
            if name == b'base.x':
                cache_base_size = amount
        assert cursor == len(cache) and cache_base_size == entries['/BASE.X']['size']
        row = entries['/LIBRARY/LANGUAGE/ENGLISH.DAT']
        disc.seek(row['lba'] * 2048)
        text = disc.read(row['size'])
        assert text == (HERE / 'assets/ENGLISH.DAT').read_bytes() and len(leaves(text)) == 838
        row = entries['/SLUS_202.06']
        disc.seek(row['lba'] * 2048)
        assert disc.read(row['size']) == (HERE / 'assets/SLUS_202.06').read_bytes()
        disc.seek(0)
        digest = hashlib.sha256()
        while block := disc.read(8 * 1024 * 1024):
            digest.update(block)
        assert digest.hexdigest() == report['sha256']
    result = dict(iso_entries=len(entries), metadata_both_endian='PASS', nonoverlapping_extents='PASS',
                  mutation_payload_digests='PASS', archive_binding_resources=sum(len(x['bindings']) for x in report['archives']),
                  new_font_payload_alignment=128, original_payload_offsets='preserved',
                  root_directory_cache='PASS', text_keys=838, sha256=report['sha256'], status='PASS')
    (HERE / 'independent-disc-check.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
