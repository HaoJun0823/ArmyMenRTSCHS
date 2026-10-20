"""Exhaustive glyph/packing checks and explicitly analytic native memory budgets."""
import collections
import json
import re
from pathlib import Path

from build_assets import parse_font, SRC

HERE = Path(__file__).resolve().parent


def packing(glyphs):
    # Mirrors native 0x2648C4..0x264928: one-pixel gutters and strict <128 bounds.
    pages, x, y, row_height = 1, 1, 1, 0
    placements = []
    for code, (_, bitmap) in sorted(glyphs.items()):
        width, height = bitmap[:2]
        assert width < 101 and height < 101
        if not width:
            continue
        if x + width + 1 >= 128:
            x, y, row_height = 1, y + row_height, 0
        row_height = max(row_height, height + 1)
        if y + row_height >= 128:
            pages, x, y, row_height = pages + 1, 1, 1, height + 1
        assert 0 < x < x + width < 128 and 0 < y < y + height < 128
        placements.append((pages, x, y, width, height, code))
        x += width + 1
    # A pixel ownership map independently catches collisions and page overruns.
    occupied = [bytearray(128 * 128) for _ in range(pages)]
    for page, x, y, width, height, code in placements:
        for row in range(y, y + height):
            start = row * 128 + x
            assert not any(occupied[page - 1][start:start + width]), hex(code)
            occupied[page - 1][start:start + width] = bytes([1]) * width
    assert pages < 512  # Native stack holds 512 page handles.
    return pages


def main():
    records = json.loads((HERE / 'texts.json').read_text(encoding='utf-8'))
    native = json.loads((HERE / 'native-strings.json').read_text(encoding='utf-8'))
    corpus = [row['target'] for row in records + native]
    required = {ord(ch) if ord(ch) < 128 else int.from_bytes(ch.encode('gbk'), 'big')
                for text in corpus for ch in text if ch not in '\r\n\t'}
    fonts = []
    for name, original in [('font_arial_cn.fff', 'font_arial_10.fff'),
                           ('font_stencil_cn.fff', 'font_stencil_24.fff'),
                           ('font_arial_memcard_cn.fff', 'font_arial_memcard_10.fff')]:
        data = (HERE / 'assets' / name).read_bytes()
        height, glyphs = parse_font(data)
        old_data = (SRC / 'ps2/base_extract' / original).read_bytes()
        _, old = parse_font(old_data)
        assert not required - glyphs.keys(), sorted(required - glyphs.keys())
        pages, old_pages = packing(glyphs), packing(old)
        buckets = collections.Counter(code & 255 for code in glyphs)
        assert max(buckets.values()) < 65536 and len(glyphs) < 65536
        # Known allocations only. Texture objects, allocator headers and residency are measured at runtime.
        known = len(data) + len(glyphs) * (8 + 4 + 40) + pages * (16384 + 1024)
        old_known = len(old_data) + len(old) * (8 + 4 + 40) + old_pages * (16384 + 1024)
        fonts.append(dict(name=name, height=height, glyphs=len(glyphs), missing=[],
                          packed_pages=pages, original_pages=old_pages,
                          texture_image_bytes=pages * 16384, palette_bytes=pages * 1024,
                          known_load_live_bytes_upper_sum=known,
                          known_load_delta=known - old_known,
                          excludes='native object/header overhead, other loaded fonts, texture residency'))
    report = dict(full_text_records=len(records), native_cells=len(native), required_codes=len(required),
                  all_fonts_missing_glyphs=[], fonts=fonts, native_packing_bounds='PASS',
                  analytic_budget_only=True, observed_native_peak=None)
    (HERE / 'memory-glyph-audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
