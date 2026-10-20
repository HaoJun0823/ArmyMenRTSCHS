"""Read-only inventory of menu strings, font slots, and UI references."""
import collections
import json
import struct
from pathlib import Path

SRC = Path('inputs/source')
ISO = Path('inputs/original.iso')
OUT = Path(__file__).resolve().parent


def leaves(b):
    records = {}

    def node(p, parent):
        kind, size = b[p:p + 2]
        name = b[p + 2:p + 2 + size].rstrip(b'\0').decode('ascii')
        key = parent + '/' + name
        p += 2 + ((size + 1) & ~1)
        n = struct.unpack_from('<H', b, p)[0]
        p += 2
        if kind == 4:
            records[key] = b[p:p + n]
            return p + ((n + 1) & ~1)
        assert kind == 6
        for _ in range(n):
            p = node(p, key)
        return p

    p = 0x36
    for _ in range(struct.unpack_from('<H', b, 0x34)[0]):
        p = node(p, '')
    return records


def main():
    data = leaves((SRC / 'ps2/ENGLISH.DAT').read_bytes())
    used = sorted(set(b''.join(v[2:] for v in data.values())))
    print('ORIGINAL HIGH BYTES', [x for x in used if x >= 128])
    print('MENU KEYS')
    for k, v in data.items():
        if k.startswith('/shell/') and ('/missions/' not in k):
            print(k, repr(v[2:].decode('latin1')))
    for path in (SRC / 'ps2/base_extract').glob('*.fff'):
        b = path.read_bytes()
        n = struct.unpack_from('<H', b, 4)[0]
        desc = [list(b[9 + i * 7:16 + i * 7]) for i in range(n)]
        print('FONT', path.name, len(b), 'height', b[6], 'count', n,
              'highslots', [d[0] for d in desc if d[0] >= 128],
              'metrics', [d for d in desc if d[0] in (65, 97, 32, 128, 255)])
    entries = []
    for line in (SRC / 'ps2_base_entries.txt').read_text(encoding='utf-8').splitlines():
        directory, name, offset, size = line.split('\t')
        entries.append((int(directory), name, int(offset), int(size)))
    found = []
    with ISO.open('rb') as f:
        for directory, name, offset, size in entries:
            if not name.endswith(('.cfg', '.fpd')):
                continue
            f.seek(560141 * 2048 + offset)
            b = f.read(size)
            if any(s in b.lower() for s in (b'#shell', b'shell.main', b'shell/menu', b'shell/main')):
                found.append({'directory': directory, 'name': name, 'offset': offset, 'size': size})
                OUT.joinpath('ui-' + name).write_bytes(b)
    OUT.joinpath('ui-references.json').write_text(json.dumps(found, indent=2), encoding='utf-8')
    print('UI REFERENCES', found)
    print('ALL SHELL KEYS', len([k for k in data if k.startswith('/shell/')]))
    audit = json.loads(Path('inputs/iso-evidence.json').read_text(encoding='utf-8'))
    with ISO.open('rb') as f:
        for item in audit['iso']['entries']:
            if item['path'] not in ('/CLIENT/S/SHELL.X', '/MISSIONS/SHELLS/MAIN.X'):
                continue
            f.seek(item['lba'] * 2048)
            b = f.read(item['size'])
            assert b[:4] == b'NORK'
            p = struct.unpack_from('<I', b, 20)[0]
            stop = struct.unpack_from('<I', b, 12)[0]
            print('ARCHIVE', item['path'])
            while p < stop:
                directory, n = struct.unpack_from('<IB', b, p)
                p += 5
                name = b[p:p + n].decode('ascii')
                p += n
                offset, size = struct.unpack_from('<II', b, p)
                p += 8
                if name.endswith(('.cfg', '.fff')):
                    print('  ENTRY', name, offset, size)
                    if name.endswith('.cfg'):
                        payload = b[offset:offset + size]
                        OUT.joinpath('shell-' + name).write_bytes(payload)
                        if b'shell' in payload.lower():
                            print(payload[:200].decode('latin1'))


if __name__ == '__main__':
    main()
