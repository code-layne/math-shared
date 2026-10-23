#!/usr/bin/env python3
"""Fail if a student name appears anywhere in the graded build output.

    check_names.py GRADING_OUT ROSTER

Scans every file grading.mk writes for graded pages: blank/, key/ and
students/ (the personalized component builds: PDFs, logs, aux, .grading,
latexmk's command transcript), and the *.out logs beside them. PDFs are read
with pdftotext and pdfinfo; every other file as text. The cover sheets
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


def text_of(path):
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
