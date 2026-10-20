"""Read every native archive to locate font copies and binding references."""
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, 'inputs/menu-sample/work')
from inspect_menu import ISO


def nork(b):
    assert b[:4] == b'NORK'
    count, paths, file_count, table = struct.unpack_from('<4I', b, 8)
    p = paths
    directories = {0: ''}
    for i in range(1, count + 1):
        n = b[p]
        p += 1
        directories[i] = b[p:p + n].decode('ascii')
        p += n
    assert p == len(b), (count, p, len(b))
    p = table
    entries = []
    while p < paths:
        directory, n = struct.unpack_from('<IB', b, p)
        p += 5
        name = b[p:p + n].decode('ascii')
        p += n
        offset, size = struct.unpack_from('<II', b, p)
        assert offset + size <= len(b) and directory in directories
        entries.append({'directory': directory, 'name': name, 'path': directories[directory] + '/' + name,
                        'offset': offset, 'size': size, 'size_field': p + 4, 'offset_field': p})
        p += 8
    assert p == paths
    assert len(entries) == file_count
    return entries, directories


def main():
    audit = json.loads(Path('inputs/iso-evidence.json').read_text(encoding='utf-8'))
    out = HERE / 'ui'
    out.mkdir(exist_ok=True)
    found = []
    with ISO.open('rb') as disc:
        for item in audit['iso']['entries']:
            if item['directory'] or not item['path'].endswith('.X'):
                continue
            disc.seek(item['lba'] * 2048)
            b = disc.read(item['size'])
            if b[:4] != b'NORK':
                continue
            entries, dirs = nork(b)
            fonts, refs = [], []
            for entry in entries:
                if entry['name'].endswith('.fff'):
                    payload = b[entry['offset']:entry['offset'] + entry['size']]
                    fonts.append({**entry, 'sha256': hashlib.sha256(payload).hexdigest()})
                if entry['name'].endswith('.cfg'):
                    payload = b[entry['offset']:entry['offset'] + entry['size']]
                    names = sorted(set(re.findall(rb'font_[a-zA-Z0-9_]+\.fff', payload)))
                    if names:
                        refs.append({**entry, 'font_names': [x.decode() for x in names]})
                    if entry['name'].startswith('if_') and payload.startswith(b'//'):
                        target = out / (item['path'].strip('/').replace('/', '_') + '__' + entry['name'])
                        target.write_bytes(payload)
            if fonts or refs:
                found.append({'archive': item['path'], 'lba': item['lba'], 'size': len(b),
                              'fonts': fonts, 'references': refs})
            if item['path'] == '/BASE.X':
                (HERE / 'base-paths.json').write_text(json.dumps(dirs, indent=2), encoding='utf-8')
    (HERE / 'archive-fonts.json').write_text(json.dumps(found, indent=2), encoding='utf-8')
    print(json.dumps({'archives_with_fonts_or_bindings': len(found),
                      'font_copies': sum(len(row['fonts']) for row in found),
                      'binding_resources': [(row['archive'], x['path'], x['font_names']) for row in found for x in row['references']]}, indent=2))


if __name__ == '__main__':
    main()
