#!/usr/bin/env python3
"""Print roster-map.csv as build input for grading.mk, in roster order.

Each line is "TRACKINGID<TAB>PREFERRED<TAB>LAST": the student's preferred name
and legal last name, for her cover sheet, encoded as TeX that is safe to pass
through the shell and latexmk: letters, digits, space, period, comma and
hyphen as is, every other character as {\\char<code>}. Only the cover build
reads the names; component builds use --ids-only, so a name never reaches a
graded page.

    roster_tex.py ROSTER [--section NAME] [--id TRACKINGID] [--ids-only]
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roster_import import RosterError, last_name, read_map  # noqa: E402

SAFE = re.compile(r"[A-Za-z0-9 .,\-]")
ID_RE = re.compile(r"^[A-Z0-9]{6}$")


def tex_escape(text):
    return "".join(c if SAFE.match(c) else f"{{\\char{ord(c)}}}" for c in text)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("roster")
    ap.add_argument("--section", default="")
    ap.add_argument("--id", default="", help="only this tracking id")
    ap.add_argument("--ids-only", action="store_true")
    args = ap.parse_args(argv)
    try:
        if not Path(args.roster).is_file():
            raise RosterError(f"{args.roster} does not exist")
        rows = read_map(args.roster)
    except RosterError as e:
        print(f"roster_tex: {e}", file=sys.stderr)
        return 1
    if args.section:
        rows = [r for r in rows if r["section"] == args.section]
    if args.id:
        rows = [r for r in rows if r["tracking_id"] == args.id]
    if not rows:
        print("roster_tex: no matching students", file=sys.stderr)
        return 1
    for r in rows:
        if not ID_RE.match(r["tracking_id"]):
            print(f"roster_tex: bad tracking id {r['tracking_id']!r}", file=sys.stderr)
            return 1
        if args.ids_only:
            print(r["tracking_id"])
        else:
            print(f"{r['tracking_id']}\t{tex_escape(r['preferred_name'].strip())}"
                  f"\t{tex_escape(last_name(r['legal_name']))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
