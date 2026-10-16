# -*- coding: utf-8 -*-
"""Independent self-check: out vs in for part1."""
import re, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(HERE, "part1.in.tsv")
OUT = os.path.join(HERE, "part1.out.tsv")

PH = re.compile(r"\{[^{}]*\}")


def load(p):
    with open(p, "r", encoding="utf-8", newline="") as f:
        raw = f.read()
    nl = raw.endswith("\n")
    rows = [l.rstrip("\r") for l in raw.split("\n")]
    if nl:
        rows = rows[:-1]
    out = []
    for i, l in enumerate(rows, 1):
        assert l != "", "blank line %d in %s" % (i, p)
        assert "\t" in l, "no tab line %d" % i
        a, b = l.split("\t", 1)
        out.append((a, b))
    return out, nl


src, src_nl = load(IN)
dst, dst_nl = load(OUT)

errs = []
print("in lines      :", len(src))
print("out lines     :", len(dst))
if len(src) != len(dst):
    errs.append("line count differs")

print("in trailing NL:", src_nl, "| out trailing NL:", dst_nl)
if src_nl != dst_nl:
    errs.append("trailing newline differs")

n_ph = 0
n_ident = 0
longer = []
for i, ((p1, v1), (p2, v2)) in enumerate(zip(src, dst), 1):
    if p1 != p2:
        errs.append("path differs line %d: %r vs %r" % (i, p1, p2))
    a = sorted(PH.findall(v1))
    b = sorted(PH.findall(v2))
    if a:
        n_ph += 1
    if a != b:
        errs.append("placeholder differs line %d (%s): %s vs %s" % (i, p1, a, b))
    if v1 == v2:
        n_ident += 1
        errs.append("untranslated line %d (%s): %r" % (i, p1, v1))
    for bad, name in (("\u00ae", "(R)"), ("\u00a9", "(C)")):
        if bad in v2:
            errs.append("forbidden %s at line %d" % (name, i))
    if v2 != v2.strip():
        errs.append("stray whitespace line %d" % i)
    if '"' in v2 or "\u201c" in v2 or "\u201d" in v2:
        errs.append("quote char line %d" % i)
    if len(v2) > len(v1) * 1.2:
        longer.append((i, p1, len(v1), len(v2)))

print("lines w/ placeholders:", n_ph)
print("identical values    :", n_ident)
print("over-length (1.2x)  :", len(longer))
for x in longer:
    print("   L%-4d %-42s en=%d zh=%d" % x)

# duplicate path check
paths = [p for p, _ in src]
dups = set(p for p in paths if paths.count(p) > 1)
print("duplicate paths     :", sorted(dups))

print()
if errs:
    print("FAIL: %d problem(s)" % len(errs))
    for e in errs[:50]:
        print("  -", e)
    sys.exit(1)
print("PASS: lines/paths/placeholders/encoding all OK")
