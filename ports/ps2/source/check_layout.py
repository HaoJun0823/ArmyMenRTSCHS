"""Audit statically resolvable native UI text bounds; retain unresolved contexts."""
import json
import re
from pathlib import Path

from build_assets import parse_font

HERE = Path(__file__).resolve().parent


def parse(text):
    text = re.sub(r'//[^\r\n]*', '', text)
    root, stack = dict(name='root', args='', children=[]), []
    stack.append(root)
    token = re.compile(r'([\w:]+)\s*\(([^;{}]*?)\)\s*([;{])|([}])', re.S)
    for match in token.finditer(text):
        name, args, ending, closing = match.groups()
        if closing:
            if len(stack) > 1:
                stack.pop()
            continue
        node = dict(name=name, args=args.strip(), children=[])
        stack[-1]['children'].append(node)
        if ending == '{':
            stack.append(node)
    return root


def string(args):
    return re.findall(r'"([^"]*)"', args)


def direct(node):
    return {item['name']: item['args'] for item in node['children']
            if item['name'] in ('Size', 'Font', 'Geometry', 'Style', 'Text')}


def main():
    texts = {row['key']: row['target'] for row in json.loads((HERE / 'texts.json').read_text(encoding='utf-8'))}
    fonts = {name: parse_font((HERE / 'assets' / file).read_bytes())
             for name, file in [('System', 'font_arial_cn.fff'), ('Movie', 'font_stencil_cn.fff')]}
    trees = [(path.name, parse(path.read_text(encoding='latin1'))) for path in sorted((HERE / 'ui').glob('*.cfg'))]
    definitions = {}

    def walk(node):
        yield node
        for child in node['children']:
            yield from walk(child)

    for _, root in trees:
        for node in walk(root):
            if node['name'] == 'DefineControlType':
                names = string(node['args'])
                if len(names) >= 2:
                    definitions[names[0]] = (names[1], direct(node))

    def properties(node):
        props = {}
        names = string(node['args'])
        kind = names[1] if len(names) >= 2 else ''
        seen = set()
        chain = []
        while kind in definitions and kind not in seen:
            seen.add(kind)
            kind, inherited = definitions[kind]
            chain.append(inherited)
        for inherited in reversed(chain):
            props.update(inherited)
        props.update(direct(node))
        return props

    checked, unresolved, overflows = [], [], []
    for path, root in trees:
        for node in walk(root):
            if node['name'] not in ('CreateControl', 'DefineControlType'):
                continue
            props = properties(node)
            refs = string(props.get('Text', ''))
            if not refs or not refs[0].startswith('#'):
                continue
            key = '/' + refs[0][1:].replace('.', '/')
            if key not in texts:
                continue
            row = dict(file=path, control=node['args'], key=key)
            dims = re.fullmatch(r'\s*(\d+)\s*,\s*(\d+)\s*', props.get('Size', ''))
            if not dims or any(x in props.get('Geometry', '') for x in ('ParentWidth', 'ParentHeight', 'AutoSize')):
                unresolved.append(row)
                continue
            width, height = map(int, dims.groups())
            name = string(props.get('Font', '"System"'))[0]
            line_height, glyphs = fonts['Movie' if name == 'Movie' else 'System']
            target = re.sub(r'\{[^}]+\}', '888', texts[key])
            widths = [sum(glyphs[ord(ch) if ord(ch) < 128 else int.from_bytes(ch.encode('gbk'), 'big')][0][2]
                          for ch in line if ch not in '\t') for line in target.replace('\r', '').split('\n')]
            wrap = '"Wrap"' in props.get('Style', '')
            row.update(width=width, height=height, text_width=max(widths), lines=len(widths), font=name, wrap=wrap)
            checked.append(row)
            ink = [glyphs[ord(ch) if ord(ch) < 128 else int.from_bytes(ch.encode('gbk'), 'big')][0]
                   for ch in target if ch not in '\r\n\t ']
            ink_height = max((desc[6] for desc in ink), default=0) - min((desc[4] for desc in ink), default=0)
            row['ink_height'] = ink_height
            if (not wrap and max(widths) > width) or (len(widths) - 1) * line_height + ink_height > height:
                overflows.append(row)
    report = dict(checked_fixed_contexts=len(checked), unresolved_contexts=unresolved,
                  potential_overflows=overflows, contexts=checked,
                  limitation='Inherited dynamic geometry and formatted arguments need runtime QA; widths do not include skin insets.')
    (HERE / 'layout-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(checked=len(checked), unresolved=len(unresolved), overflows=overflows), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
