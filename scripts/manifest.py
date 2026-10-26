#!/usr/bin/env python3
"""Build manifest.json from a .grading file, or check a key against a blank.

    manifest.py write BUILD.grading -o manifest.json [--course C] [--lesson-dir DIR]
    manifest.py check BLANK.json KEY.json
    manifest.py cover-tex BUILD.grading

write reads the .grading file grading.sty leaves next to the PDF (JSON Lines:
one meta line, the id strip, the four registration marks, the QR code, then
one line per graded item) and writes the manifest the grader works from. Build
it from the blank component's build; a key build may be written too, for check.

check compares a blank manifest with its key's and exits 1 if any item's id,
type, points, answer or check differs, or an item is missing from either. A
moved box or a different page count is reported as a warning: the blank's
layout is the one the scans are aligned to.

cover-tex prints, as one line of TeX for cover.tex's -usepretex, what a cover
sheet needs from the blank's .grading file: the assignment, course and title,
and the QR code's size and position, so the cover's QR code sits exactly where
the graded pages' does. Course and title are TeX-escaped like the roster names
(see roster_tex.py); the assignment must be [A-Za-z0-9._-], since it goes into
the QR code as is.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roster_tex import tex_escape  # noqa: E402

CHECKS = {"expression", "numeric", "set", "text", "interval"}
TYPES = {"choice", "short", "rubric"}


class ManifestError(Exception):
    pass


def number(x):
    return int(x) if float(x).is_integer() else float(x)


def read_grading(path):
    meta, strip, marks, qr, items = None, None, {}, None, []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise ManifestError(f"{path}:{n}: not JSON ({e})")
            kind = rec.get("kind")
            if kind == "meta":
                meta = rec
            elif kind == "strip":
                strip = rec["box"]
            elif kind == "mark":
                marks[rec["corner"]] = rec["box"]
            elif kind == "qr":
                qr = rec["box"]
            elif kind == "item":
                items.append(rec)
            else:
                raise ManifestError(f"{path}:{n}: unknown record kind {kind!r}")
    if meta is None:
        raise ManifestError(f"{path}: no meta record (was the build interrupted?)")
    if meta.get("format") != 1:
        raise ManifestError(f"{path}: unsupported .grading format {meta.get('format')!r}")
    return meta, strip, marks, qr, items


def build(path, course=None, lesson_dir=None):
    meta, strip, marks, qr, items = read_grading(path)
    assignments = {i["assignment"] for i in items}
    if meta.get("assignment") not in (None, "UNSET"):
        assignments.add(meta["assignment"])
    if len(assignments) > 1:
        raise ManifestError(f"{path}: items from several assignments: {sorted(assignments)}")
    assignment = assignments.pop() if assignments else None
    if not assignment or assignment == "UNSET":
        raise ManifestError(f"{path}: the document has no \\gradingassignment")

    questions, warnings = [], []
    for i in items:
        if i["page"] == 0:
            raise ManifestError(
                f"{path}: item {i['id']} has no position yet; rerun LaTeX (latexmk does)")
        if i["type"] not in TYPES:
            raise ManifestError(f"{path}: item {i['id']}: unknown type {i['type']!r}")
        q = {"id": i["id"], "type": i["type"], "points": number(i["points"])}
        if i["answer"] != "" or i["type"] != "rubric":
            q["answer"] = i["answer"]
        if i["type"] == "short":
            q["check"] = i["check"] or "expression"
            if q["check"] not in CHECKS:
                raise ManifestError(f"{path}: item {i['id']}: unknown check {q['check']!r}")
            if "tolerance" in i:
                q["tolerance"] = number(i["tolerance"])
        if i["type"] == "rubric":
            q["rubric"] = i.get("rubric") or f"rubrics/{assignment}-{i['id']}.yaml"
            if lesson_dir and not (Path(lesson_dir) / q["rubric"]).is_file():
                warnings.append(f"item {i['id']}: rubric file {q['rubric']} not found "
                                f"in {lesson_dir}")
        q["page"] = i["page"]
        q["box"] = i["box"]
        questions.append(q)

    manifest = {
        "assignment": assignment,
        "course": course or meta.get("course") or "",
        "title": meta.get("title") or "",
        "pages": meta["pages"],
        "questions": questions,
        "paper": meta["paper"],
        "strip": strip,
        "marks": marks,
        "qr": qr,
        "key": meta["key"],
    }
    return manifest, warnings


ASSIGNMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def cover_tex(path):
    """The \\def lines cover.tex reads, from a blank build's .grading file."""
    meta, _, _, qr, items = read_grading(path)
    assignment = meta.get("assignment") or next((i["assignment"] for i in items), "UNSET")
    if assignment == "UNSET":
        raise ManifestError(f"{path}: the document has no \\gradingassignment")
    if not ASSIGNMENT_RE.match(assignment):
        raise ManifestError(f"{path}: assignment {assignment!r} may hold only "
                            f"letters, digits, '.', '_' and '-'")
    if qr is None:
        raise ManifestError(f"{path}: no qr record")
    (pw, ph), (x, y, w, h) = meta["paper"], qr
    defs = {
        "CoverAssignment": assignment,
        "CoverCourse": tex_escape(meta.get("course") or ""),
        "CoverTitle": tex_escape(meta.get("title") or assignment),
        "CoverQRSize": f"{w:g}bp",
        "CoverQRInset": f"{round(pw - x - w, 2):g}bp",
        "CoverQRTop": f"{round(ph - y - h, 2):g}bp",
    }
    return "".join(f"\\def\\{k}{{{v}}}" for k, v in defs.items())


SAME = ("type", "points", "answer", "check")


def check(blank, key):
    """(errors, warnings) comparing a blank manifest with its key's."""
    errors, warnings = [], []
    if blank.get("key"):
        errors.append("the first manifest was built from a key, not the blank")
    if not key.get("key"):
        warnings.append("the second manifest was built without key mode")
    if blank["assignment"] != key["assignment"]:
        errors.append(f"assignment differs: {blank['assignment']} vs {key['assignment']}")
    if blank["pages"] != key["pages"]:
        warnings.append(f"page count differs: blank {blank['pages']}, key {key['pages']}")
    b = {q["id"]: q for q in blank["questions"]}
    k = {q["id"]: q for q in key["questions"]}
    for qid in b.keys() - k.keys():
        errors.append(f"{qid}: in the blank, not in the key")
    for qid in k.keys() - b.keys():
        errors.append(f"{qid}: in the key, not in the blank")
    for qid in [q["id"] for q in blank["questions"] if q["id"] in k]:
        for field in SAME:
            if b[qid].get(field) != k[qid].get(field):
                errors.append(f"{qid}: {field} differs: blank {b[qid].get(field)!r}, "
                              f"key {k[qid].get(field)!r}")
        if b[qid]["page"] != k[qid]["page"] or b[qid]["box"] != k[qid]["box"]:
            warnings.append(f"{qid}: box moved: blank p{b[qid]['page']} {b[qid]['box']}, "
                            f"key p{k[qid]['page']} {k[qid]['box']}")
    return errors, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write", help="build manifest.json from a .grading file")
    w.add_argument("grading")
    w.add_argument("-o", "--output", required=True)
    w.add_argument("--course", help="course name (default: \\gradingcourse)")
    w.add_argument("--lesson-dir", help="directory rubric paths are relative to")
    c = sub.add_parser("check", help="compare a blank manifest with its key's")
    c.add_argument("blank")
    c.add_argument("key")
    t = sub.add_parser("cover-tex", help="print the TeX a cover sheet build reads")
    t.add_argument("grading")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "cover-tex":
            print(cover_tex(args.grading))
            return 0
        if args.cmd == "write":
            manifest, warnings = build(args.grading, args.course, args.lesson_dir)
            for msg in warnings:
                print(f"manifest: warning: {msg}", file=sys.stderr)
            Path(args.output).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(f"manifest: {len(manifest['questions'])} questions, "
                  f"{manifest['pages']} pages -> {args.output}")
            return 0
        blank = json.loads(Path(args.blank).read_text(encoding="utf-8"))
        key = json.loads(Path(args.key).read_text(encoding="utf-8"))
        errors, warnings = check(blank, key)
        for msg in warnings:
            print(f"manifest check: warning: {msg}", file=sys.stderr)
        for msg in errors:
            print(f"manifest check: {msg}", file=sys.stderr)
        if errors:
            print(f"manifest check: FAILED, {len(errors)} difference(s)", file=sys.stderr)
            return 1
        print(f"manifest check: blank and key agree on {len(blank['questions'])} questions")
        return 0
    except (ManifestError, OSError, KeyError, json.JSONDecodeError) as e:
        print(f"manifest: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
