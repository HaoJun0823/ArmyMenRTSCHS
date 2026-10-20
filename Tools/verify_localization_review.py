"""Check the five-row terminology contribution against its recorded Git base."""
import ast
import collections
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    manifest = json.loads((ROOT / 'docs/localization-review-2026-10-21.json').read_text(encoding='utf-8'))
    base = manifest['base_commit']
    original = json.loads(subprocess.check_output(['git', 'show', f'{base}:translate/merged.json'], cwd=ROOT))
    revised = json.loads((ROOT / 'translate/merged.json').read_text(encoding='utf-8'))
    assert len(original) == len(revised) == 846
    assert [row['k'] for row in original] == [row['k'] for row in revised]
    old = {row['k']: row for row in original}
    new = {row['k']: row for row in revised}
    expected = {row['key']: row for row in manifest['corrections']}
    assert len(expected) == 5
    assert {key for key in old if old[key] != new[key]} == expected.keys()
    controls = re.compile(r'\{[^}]*\}|%(?:[-+ #0]*\d*(?:\.\d+)?[diuoxXfFeEgGcsp%])|\\+[rnt]')
    for key in old:
        assert old[key]['en'] == new[key]['en']
        assert collections.Counter(controls.findall(old[key]['zh'])) == collections.Counter(controls.findall(new[key]['zh']))
        assert set(old[key]) == set(new[key])
        new[key]['zh'].encode('gbk')
        if key in expected:
            assert old[key]['zh'] == expected[key]['before'] and new[key]['zh'] == expected[key]['after']
    occurrences = collections.Counter()
    for path in sorted((ROOT / 'translate').glob('part*.out.tsv')):
        previous = subprocess.check_output(['git', 'show', f'{base}:translate/{path.name}'], cwd=ROOT).decode('utf-8')
        current = path.read_text(encoding='utf-8')
        previous_lines, current_lines = previous.splitlines(), current.splitlines()
        assert len(previous_lines) == len(current_lines)
        for before_line, after_line in zip(previous_lines, current_lines):
            key, separator, text = before_line.partition('\t')
            assert separator
            if key in expected:
                assert text == expected[key]['before']
                assert after_line == key + '\t' + expected[key]['after']
                occurrences[key] += 1
            else:
                assert before_line == after_line
    assert occurrences == collections.Counter({key: 1 for key in expected})
    old_chars = subprocess.check_output(['git', 'show', f'{base}:translate/chars.txt'], cwd=ROOT).decode('utf-8').rstrip('\r\n')
    chars = (ROOT / 'translate/chars.txt').read_text(encoding='utf-8').rstrip('\r\n')
    assert chars == old_chars + '吉'
    required = {ch for row in revised for ch in row['zh'] if ord(ch) > 127}
    assert not required - set(chars)
    source = ROOT / 'ports/ps2/source'
    for path in source.rglob('*.py'):
        code = path.read_text(encoding='utf-8')
        ast.parse(code, filename=str(path.relative_to(ROOT)))
        assert not re.search(r'[CE]:[/\\](?:Users|Codex|deepseek-harness)', code, re.I)
    provenance = json.loads((ROOT / 'ports/ps2/source-provenance.json').read_text(encoding='utf-8'))
    for row in provenance:
        normalized = (source / row['file']).read_text(encoding='utf-8').encode('utf-8')
        assert hashlib.sha256(normalized).hexdigest() == row['exported_sha256_lf']
    print(json.dumps(dict(status='PASS', records=846, changed_records=5, synchronized_tsv_records=5,
                          appended_characters='吉', missing_characters=[], controls_and_escapes_preserved=True,
                          ps2_reference_sources_parse=True, pc_runtime_tested=False), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
