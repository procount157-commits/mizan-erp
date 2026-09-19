#!/usr/bin/env python3
"""Remove OCA Arabic translation files whose contents are question marks.

OCA ships ar.po files where every translation is a run of "?" instead of
Arabic — over 1,700 strings across payroll, purchase requests, contracts,
assets and the financial reports. Loading them replaces those labels with
"????", which is worse than leaving them in English and cannot be undone from
inside Odoo once the terms are in the database.

    python3 scripts/strip_corrupt_ar_po.py third_party/OCA
"""
import re
import sys
from pathlib import Path

MSGSTR = re.compile(r'^msgstr\s+"(.*)"\s*$')
CONT = re.compile(r'^"(.*)"\s*$')


def translations(path):
    """Yield each non-empty msgstr value in a .po file."""
    current, collecting = [], False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = MSGSTR.match(line)
        if match:
            if collecting and current:
                yield "".join(current)
            current, collecting = [match.group(1)], True
        elif collecting and CONT.match(line):
            current.append(CONT.match(line).group(1))
        elif collecting:
            if current:
                yield "".join(current)
            current, collecting = [], False
    if collecting and current:
        yield "".join(current)


def is_corrupt(path):
    values = [v for v in translations(path) if v.strip()]
    if not values:
        return False, 0, 0
    # A translation that is nothing but question marks and punctuation carries
    # no information at all.
    bad = sum(1 for v in values if not re.search(r"[^\s?\-–—:/()\[\].,%]", v))
    return bad > len(values) * 0.5, bad, len(values)


root = Path(sys.argv[1] if len(sys.argv) > 1 else "third_party/OCA")
removed = kept = 0
# rglob, so this works both on the OCA clones (repo/module/i18n) and on
# the flattened addons volume (module/i18n).
for po in sorted(root.rglob("i18n/ar*.po")):
    corrupt, bad, total = is_corrupt(po)
    module = po.parent.parent.name
    if corrupt:
        po.unlink()
        removed += 1
        print("removed %-34s %d/%d translations were question marks" % (module, bad, total))
    else:
        kept += 1
        print("kept    %-34s %d/%d suspicious" % (module, bad, total))
print("\nremoved %d file(s), kept %d" % (removed, kept))
