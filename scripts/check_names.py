#!/usr/bin/env python3
"""Fail if a student name appears anywhere in the graded build output.

    check_names.py GRADING_OUT ROSTER

Scans every file grading.mk writes for graded pages: blank/, key/ and
students/ (the personalized component builds: PDFs, logs, aux, .grading,
latexmk's command transcript), and the *.out logs beside them. PDFs are read
with pdftotext and pdfinfo; XDV and DVI files by their opcodes, keeping every
string they carry (specials, font names, comments, XeTeX's actual text) and
skipping glyph and position bytes, where a short name would match by chance;
every other file as text. The cover sheets
(covers/), the joined packets (packets/, personalized.pdf, student-*.pdf) and
nothing else may hold names, and they are not scanned.

Each roster row contributes its preferred name, legal last name, each legal
given name, the full legal name and the printed name, plain and TeX-escaped as
roster_tex.py writes them, and each run of three or more letters inside them
("Testperson" in "O'Testperson"). A match is case-sensitive and on word
boundaries, with curly apostrophes read as straight ones.
Exits 1 on any match, naming the file and the tracking id and field, never the
name itself.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roster_import import RosterError, display_name, last_name, read_map  # noqa: E402
from roster_tex import tex_escape  # noqa: E402

SCANNED_DIRS = ("blank", "key", "students")


def names(row):
    """(field, text) pairs to look for, for one roster row."""
    legal = row["legal_name"]
    given = legal.split(",", 1)[1] if "," in legal else ""
    found = [("preferred name", row["preferred_name"]),
             ("last name", last_name(legal)),
             ("legal name", legal),
             ("printed name", display_name(row))]
    found += [("given name", g) for g in given.split()]
    out = []
    for field, text in found:
        text = text.strip()
        if len(text) < 2:
            continue
        out.append((field, text))
        if tex_escape(text) != text:
            out.append((field + ", TeX-escaped", tex_escape(text)))
        out += [(field + ", part", part) for part in re.findall(r"[^\W\d_]{3,}", text)
                if part != text]
    return out


def pattern(text):
    return re.compile(r"(?<!\w)" + re.escape(text) + r"(?!\w)")


# Bytes of fixed-size parameters after each DVI/XDV opcode; the opcodes that
# carry strings are handled in xdv_text().
_DVI_FIXED = {132: 8, 137: 8, 138: 0, 139: 44, 140: 0, 141: 0, 142: 0, 248: 28}
for _base, _first in [(127, 128), (132, 133), (142, 143), (147, 148), (152, 153),
                      (156, 157), (161, 162), (166, 167), (234, 235)]:
    _DVI_FIXED.update({_first + i: _first + i - _base for i in range(4)})
_DVI_FIXED.update({op: 0 for op in [*range(128), 147, 152, 161, 166, *range(171, 235)]})


def xdv_text(data):
    """The strings in a DVI or XDV (version 7) file, one per line.

    Raises ValueError on anything it cannot parse."""
    def take(n):
        nonlocal i
        if i + n > len(data):
            raise ValueError("truncated")
        i += n
        return data[i - n:i]

    def num(n):
        return int.from_bytes(take(n), "big")

    i, out = 0, []
    if data[:2] not in (b"\xf7\x02", b"\xf7\x07"):
        raise ValueError("not DVI or XDV 7")
    while True:
        op = num(1)
        if op in _DVI_FIXED:
            take(_DVI_FIXED[op])
        elif 239 <= op <= 242:                      # xxx: special
            out.append(take(num(op - 238)))
        elif 243 <= op <= 246:                      # fnt_def
            take(op - 242 + 12)
            a, l = num(1), num(1)
            out.append(take(a + l))
        elif op == 247:                             # pre
            take(13)
            out.append(take(num(1)))
        elif op == 249:                             # post_post
            break
        elif op == 252:                             # native_font_def
            take(8)
            flags = num(2)
            out.append(take(num(1)))
            take(4 + 4 * sum(bool(flags & f) for f in (0x0200, 0x1000, 0x2000, 0x4000)))
        elif op == 253:                             # glyphs
            take(4)
            take(10 * num(2))
        elif op == 254:                             # text_and_glyphs
            out.append(take(2 * num(2)).decode("utf-16-be", errors="replace").encode())
            take(4)
            take(10 * num(2))
        else:
            raise ValueError(f"unknown opcode {op}")
    return "\n".join(s.decode("utf-8", errors="replace") for s in out)


def text_of(path):
    if path.suffix in (".xdv", ".dvi"):
        data = path.read_bytes()
        try:
            return xdv_text(data)
        except ValueError:
            pass                                    # unparseable: scan it all, as text
        return data.decode("utf-8", errors="replace")
    if path.suffix == ".pdf":
        return "\n".join(
            subprocess.run([tool, str(path)] + extra, capture_output=True,
                           text=True, check=True).stdout
            for tool, extra in [("pdftotext", ["-"]), ("pdfinfo", [])])
    return path.read_bytes().decode("utf-8", errors="replace")


def scanned(out):
    for d in SCANNED_DIRS:
        if (out / d).is_dir():
            yield from sorted(p for p in (out / d).rglob("*") if p.is_file())
    yield from sorted(out.glob("*.out"))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("roster")
    args = ap.parse_args(argv)
    try:
        rows = read_map(args.roster)
    except RosterError as e:
        print(f"check_names: {e}", file=sys.stderr)
        return 1
    if not rows:
        print(f"check_names: no students in {args.roster}", file=sys.stderr)
        return 1
    needles = [(r["tracking_id"], field, pattern(text)) for r in rows for field, text in names(r)]
    out = Path(args.out)
    files = list(scanned(out))
    if not any(p.parent.name == "students" for p in files):
        print(f"check_names: no personalized builds under {out / 'students'}", file=sys.stderr)
        return 1
    hits = 0
    for path in files:
        text = (path.name + "\n" + text_of(path)).replace("\u2019", "'")
        for tid, field, rx in needles:
            if rx.search(text):
                hits += 1
                print(f"check_names: {path.relative_to(out)}: {field} of {tid}", file=sys.stderr)
    if hits:
        print(f"check_names: FAILED, {hits} student name(s) in graded build output",
              file=sys.stderr)
        return 1
    print(f"check_names: no student names in {len(files)} graded build files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
