#!/usr/bin/env python3
"""Import a Blackbaud Course Roster export into roster-map.csv.

The export (class page > Roster > Run Roster/Student Reports > Course Roster >
Export Data to Excel) has one row per student followed by continuation rows for
any additional parents, and no student id column. The student's name field
reads

    Last, First (Preferred) 'YY

with the parenthesised preferred name optional. This script keeps the legal
name, the preferred name and the class year of each student, and discards every
other column: parent names, emails, phones and addresses never leave the
export file.

Each student new to the map gets a random six-character tracking id from an
alphabet with no 0/O/1/I/L. Students already in the map are matched by legal
name, so a re-import never changes an existing id. Students missing from the
export stay in the map (their scores are keyed by id) and are reported.

roster-map.csv is the only file where names and tracking ids meet, so it must
never be committed: this script refuses to write anywhere inside a git work
tree.

Usage:
    roster_import.py EXPORT.xls OUT [--section NAME]

OUT is the roster-map.csv to create or update, or a directory to hold one.
"""

import argparse
import csv
import html.parser
import os
import re
import secrets
import subprocess
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0, O, 1, I, L
ID_LENGTH = 6
FIELDS = ["tracking_id", "legal_name", "preferred_name", "class_year", "section"]

# Last, First (Preferred) 'YY  — the class-year suffix is what tells a student
# row from anything else in the sheet (parent names carry no year).
NAME_RE = re.compile(
    r"^\s*(?P<last>[^,]+?)\s*,\s*(?P<first>.+?)\s*"
    r"(?:\((?P<preferred>[^()]*)\))?\s*['‘’`](?P<yy>\d{2})\s*$"
)


class RosterError(Exception):
    pass


# ── Reading the export ───────────────────────────────────────────────────────

def read_rows(path):
    """All cells of the first sheet as lists of strings.

    "Export Data to Excel" files are read whether they are real BIFF .xls,
    HTML or SpreadsheetML saved with an .xls name, or .xlsx/.csv.
    """
    data = Path(path).read_bytes()
    head = data[:512].lstrip().lower()
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        return _read_biff(path)
    if data.startswith(b"PK"):
        return _read_xlsx(path)
    if head.startswith(b"<?xml") and b"urn:schemas-microsoft-com:office:spreadsheet" in data[:4096]:
        return _read_spreadsheetml(data)
    if head.startswith(b"<"):
        return _read_html(data)
    text = data.decode("utf-8-sig", errors="replace")
    return [row for row in csv.reader(text.splitlines())]


def _cell_text(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _read_biff(path):
    try:
        import xlrd
    except ImportError:
        raise RosterError("reading .xls needs xlrd: pip install xlrd")
    sheet = xlrd.open_workbook(path).sheet_by_index(0)
    return [[_cell_text(c) for c in sheet.row_values(r)] for r in range(sheet.nrows)]


def _read_xlsx(path):
    try:
        import openpyxl
    except ImportError:
        raise RosterError("reading .xlsx needs openpyxl: pip install openpyxl")
    sheet = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
    return [["" if c is None else _cell_text(c) for c in row]
            for row in sheet.iter_rows(values_only=True)]


def _read_spreadsheetml(data):
    ns = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}
    root = ET.fromstring(data)
    table = root.find(".//ss:Worksheet/ss:Table", ns)
    rows = []
    for row in table.findall("ss:Row", ns) if table is not None else []:
        cells = []
        for cell in row.findall("ss:Cell", ns):
            index = cell.get("{urn:schemas-microsoft-com:office:spreadsheet}Index")
            if index:
                cells.extend([""] * (int(index) - 1 - len(cells)))
            d = cell.find("ss:Data", ns)
            cells.append("".join(d.itertext()).strip() if d is not None else "")
        rows.append(cells)
    return rows


class _TableParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _read_html(data):
    parser = _TableParser()
    parser.feed(data.decode("utf-8", errors="replace"))
    return parser.rows


def parse_students(rows):
    """Students from the export rows: legal name, preferred name, class year.

    The name column is the one whose cells most often parse as a student name.
    Continuation rows (blank name cell) are skipped; nothing else in any row is
    kept.
    """
    counts = {}
    for row in rows:
        for i, cell in enumerate(row):
            if NAME_RE.match(cell or ""):
                counts[i] = counts.get(i, 0) + 1
    if not counts:
        raise RosterError("no cell looks like a student name (\"Last, First (Preferred) 'YY\")")
    col = max(counts, key=counts.get)

    students, seen = [], set()
    for row in rows:
        cell = row[col] if col < len(row) else ""
        m = NAME_RE.match(cell or "")
        if not m:
            continue  # header, continuation row for another parent, or blank
        last = " ".join(m["last"].split())
        first = " ".join(m["first"].split())
        preferred = " ".join((m["preferred"] or "").split()) or first
        legal = f"{last}, {first}"
        if norm(legal) in seen:
            continue
        seen.add(norm(legal))
        students.append({
            "legal_name": legal,
            "preferred_name": preferred,
            "class_year": str(2000 + int(m["yy"])),
        })
    return students


# ── The roster map ───────────────────────────────────────────────────────────

def norm(name):
    """Legal-name match key: Unicode-normalised, case- and space-insensitive."""
    return " ".join(unicodedata.normalize("NFC", name).casefold().split())


def last_name(legal_name):
    return legal_name.split(",", 1)[0].strip()


def display_name(row):
    """The name printed on a student's packet: preferred first, then last."""
    return f"{row['preferred_name']} {last_name(row['legal_name'])}".strip()


def read_map(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        missing = [k for k in FIELDS if k not in r]
        if missing:
            raise RosterError(f"{path}: missing columns {', '.join(missing)}")
    return rows


def new_id(taken):
    while True:
        tid = "".join(secrets.choice(ALPHABET) for _ in range(ID_LENGTH))
        if tid not in taken:
            taken.add(tid)
            return tid


def merge(existing, students, section):
    """(rows, added, missing): existing rows updated in place, new students
    appended with fresh ids, sorted into gradebook order."""
    taken = {r["tracking_id"] for r in existing}
    rows = [dict(r) for r in existing]
    by_name = {norm(r["legal_name"]): r for r in rows}
    imported, added = set(), []
    for s in students:
        key = norm(s["legal_name"])
        imported.add(key)
        row = by_name.get(key)
        if row is None:
            row = {"tracking_id": new_id(taken), "section": section or "", **s}
            rows.append(row)
            by_name[key] = row
            added.append(row)
        else:
            row["preferred_name"] = s["preferred_name"]
            row["class_year"] = s["class_year"]
            if section:
                row["section"] = section
    missing = [r for r in rows if norm(r["legal_name"]) not in imported
               and (not section or r["section"] == section)]
    rows.sort(key=lambda r: (r["section"], norm(last_name(r["legal_name"])), norm(r["legal_name"])))
    return rows, added, missing


# ── The git guard ────────────────────────────────────────────────────────────

def git_work_tree(directory):
    """The work tree containing directory, or None."""
    d = Path(directory).resolve()
    for p in (d, *d.parents):
        if (p / ".git").exists():
            return p
    try:
        out = subprocess.run(["git", "-C", str(d), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def resolve_out(out):
    out = Path(out).expanduser()
    if out.is_dir():
        out = out / "roster-map.csv"
    if not out.parent.is_dir():
        raise RosterError(f"{out.parent} does not exist")
    tree = git_work_tree(out.parent)
    if tree is not None:
        raise RosterError(
            f"refusing to write {out}: it is inside the git work tree {tree}. "
            "roster-map.csv pairs names with tracking ids and must never be "
            "committed; keep it in its own folder outside every repository.")
    return out


def write_map(path, rows):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".roster-map-", suffix=".csv")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
            w.writeheader()
            for r in rows:
                w.writerow({k: r[k] for k in FIELDS})
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("export", help="Course Roster export (.xls)")
    ap.add_argument("out", help="roster-map.csv to create or update, or its directory")
    ap.add_argument("--section", default="", help="section name recorded for these students")
    args = ap.parse_args(argv)
    try:
        out = resolve_out(args.out)
        students = parse_students(read_rows(args.export))
        rows, added, missing = merge(read_map(out), students, args.section)
        write_map(out, rows)
    except RosterError as e:
        print(f"roster_import: {e}", file=sys.stderr)
        return 1
    print(f"{len(students)} students in the export, {len(added)} new, "
          f"{len(rows)} in {out}")
    for r in added:
        print(f"  new      {r['tracking_id']}  {r['legal_name']}")
    for r in missing:
        print(f"  missing  {r['tracking_id']}  {r['legal_name']}  (kept; not in this export)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
