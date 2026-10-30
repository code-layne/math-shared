#!/usr/bin/env python3
"""Build manifest.json from a .grading file, or check a key against a blank.

    manifest.py write BUILD.grading -o manifest.json [--course C] [--lesson-dir DIR]
    manifest.py check BLANK.json KEY.json
    manifest.py cover-tex BUILD.grading

write reads the .grading file grading.sty leaves next to the PDF (JSON Lines:
one meta line, the id strip, the four registration marks, the QR code, one
line per \\gradedquestion group, then one line per graded item) and writes the
manifest the grader works from. Build it from the blank component's build; a
key build may be written too, for check. A group is a free-response question
scored as a whole: its items record 0 points, the group carries the points (4
for scheme ap-stats), and the manifest's total "points" is the sum of the
ungrouped items' points plus each group's points. With --lesson-dir, write
warns about a missing rubric file and validates each ap-stats group's rubric
YAML (see validate_ap_stats_rubric).

check compares a blank manifest with its key's and exits 1 if any item's id,
type, points, answer, check or question differs, any group's scheme, points,
rubric or items differ, or an item or group is missing from either. A moved
box or a different page count is reported as a warning: the blank's layout is
the one the scans are aligned to.

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
# Points of a question, by scoring scheme. The author never sets them.
SCHEME_POINTS = {"ap-stats": 4}


class ManifestError(Exception):
    pass


def number(x):
    return int(x) if float(x).is_integer() else float(x)


def read_grading(path):
    meta, strip, marks, qr, groups, items = None, None, {}, None, [], []
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
            elif kind == "group":
                groups.append(rec)
            elif kind == "item":
                items.append(rec)
            else:
                raise ManifestError(f"{path}:{n}: unknown record kind {kind!r}")
    if meta is None:
        raise ManifestError(f"{path}: no meta record (was the build interrupted?)")
    if meta.get("format") != 1:
        raise ManifestError(f"{path}: unsupported .grading format {meta.get('format')!r}")
    return meta, strip, marks, qr, groups, items


def build(path, course=None, lesson_dir=None):
    meta, strip, marks, qr, groups, items = read_grading(path)
    assignments = {i["assignment"] for i in items} | {g["assignment"] for g in groups}
    if meta.get("assignment") not in (None, "UNSET"):
        assignments.add(meta["assignment"])
    if len(assignments) > 1:
        raise ManifestError(f"{path}: items from several assignments: {sorted(assignments)}")
    assignment = assignments.pop() if assignments else None
    if not assignment or assignment == "UNSET":
        raise ManifestError(f"{path}: the document has no \\gradingassignment")

    declared = {}
    for g in groups:
        if g["id"] in declared:
            raise ManifestError(f"{path}: question {g['id']} is declared twice")
        if g.get("scheme") not in SCHEME_POINTS:
            raise ManifestError(f"{path}: question {g['id']}: unknown scheme {g.get('scheme')!r}")
        if number(g["points"]) != SCHEME_POINTS[g["scheme"]]:
            raise ManifestError(f"{path}: question {g['id']}: a {g['scheme']} question is worth "
                                f"{SCHEME_POINTS[g['scheme']]} points, not {g['points']}")
        declared[g["id"]] = g
    item_ids = {i["id"] for i in items}
    for qid in declared.keys() & item_ids:
        raise ManifestError(f"{path}: {qid} is both a question id and an item id")

    questions, warnings = [], []
    members = {qid: [] for qid in declared}
    for i in items:
        if i["page"] == 0:
            raise ManifestError(
                f"{path}: item {i['id']} has no position yet; rerun LaTeX (latexmk does)")
        if i["type"] not in TYPES:
            raise ManifestError(f"{path}: item {i['id']}: unknown type {i['type']!r}")
        q = {"id": i["id"], "type": i["type"], "points": number(i["points"])}
        group = i.get("question")
        if group is not None:
            if group not in declared:
                raise ManifestError(f"{path}: item {i['id']} names question {group}, "
                                    f"which no \\gradedquestion declares")
            if q["points"] != 0:
                raise ManifestError(f"{path}: item {i['id']} belongs to question {group} "
                                    f"but records {q['points']} points, not 0")
            members[group].append(i["id"])
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
            # A part of a question is rated by the question's rubric.
            if (group is None and lesson_dir
                    and not (Path(lesson_dir) / q["rubric"]).is_file()):
                warnings.append(f"item {i['id']}: rubric file {q['rubric']} not found "
                                f"in {lesson_dir}")
        if group is not None:
            q["question"] = group
        q["page"] = i["page"]
        q["box"] = i["box"]
        questions.append(q)

    group_list = []
    for qid, g in declared.items():
        if not members[qid]:
            raise ManifestError(f"{path}: question {qid} has no items")
        entry = {"id": qid, "scheme": g["scheme"], "points": number(g["points"]),
                 "rubric": g.get("rubric") or f"rubrics/{assignment}-{qid}.yaml",
                 "items": members[qid]}
        if lesson_dir:
            rubric = Path(lesson_dir) / entry["rubric"]
            if not rubric.is_file():
                warnings.append(f"question {qid}: rubric file {entry['rubric']} not found "
                                f"in {lesson_dir}")
            elif entry["scheme"] == "ap-stats":
                validate_ap_stats_rubric(rubric, entry)
        group_list.append(entry)

    manifest = {
        "assignment": assignment,
        "course": course or meta.get("course") or "",
        "title": meta.get("title") or "",
        "pages": meta["pages"],
        "points": total_points(questions, group_list),
        "questions": questions,
        "groups": group_list,
        "paper": meta["paper"],
        "strip": strip,
        "marks": marks,
        "qr": qr,
        "key": meta["key"],
    }
    return manifest, warnings


def total_points(questions, groups):
    """Ungrouped items' points plus each group's points (4 per ap-stats group)."""
    total = sum(q["points"] for q in questions if "question" not in q)
    total += sum(g["points"] for g in groups)
    return number(total)


def validate_ap_stats_rubric(path, group):
    """Raise ManifestError unless the YAML at path is a valid ap-stats rubric for group.

    The file holds scheme: ap-stats, the group's id, points: 4, a task, and a
    list of sections, each with a unique id, the items (box ids) it rates, an
    optional weight (default 1), and E and P descriptions (I is optional).
    The weights sum to 4, every item of the group is in at least one section,
    and every item in a section belongs to the group.
    """
    try:
        import yaml
    except ImportError:
        raise ManifestError("validating an ap-stats rubric needs PyYAML (pip install pyyaml)")
    where = f"{path}"
    try:
        doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ManifestError(f"{where}: not YAML ({e})")
    errors = []
    if not isinstance(doc, dict):
        raise ManifestError(f"{where}: an ap-stats rubric must be a mapping")
    if doc.get("scheme") != "ap-stats":
        errors.append(f"scheme is {doc.get('scheme')!r}, expected 'ap-stats'")
    if str(doc.get("id")) != group["id"]:
        errors.append(f"id is {doc.get('id')!r}, expected {group['id']!r}")
    if doc.get("points") != SCHEME_POINTS["ap-stats"]:
        errors.append(f"points is {doc.get('points')!r}, expected {SCHEME_POINTS['ap-stats']}")
    if not isinstance(doc.get("task"), str) or not doc["task"].strip():
        errors.append("task is missing")
    sections = doc.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append("sections is missing or empty")
        sections = []
    seen_ids, covered, total = set(), set(), 0
    for n, sec in enumerate(sections, 1):
        if not isinstance(sec, dict):
            errors.append(f"section {n} is not a mapping")
            continue
        sid = sec.get("id")
        label = f"section {sid!r}" if sid is not None else f"section {n}"
        if sid is None:
            errors.append(f"{label} has no id")
        elif sid in seen_ids:
            errors.append(f"section id {sid!r} is used twice")
        seen_ids.add(sid)
        items = sec.get("items")
        if not isinstance(items, list) or not items:
            errors.append(f"{label} lists no items")
            items = []
        for item in items:
            if str(item) not in group["items"]:
                errors.append(f"{label} lists {item!r}, which is not an item of "
                              f"question {group['id']} ({', '.join(group['items'])})")
            covered.add(str(item))
        weight = sec.get("weight", 1)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
            errors.append(f"{label} has weight {weight!r}; it must be a positive number")
        else:
            total += weight
        for rating in ("E", "P"):
            if not isinstance(sec.get(rating), str) or not sec[rating].strip():
                errors.append(f"{label} has no {rating} description")
        if "I" in sec and (not isinstance(sec["I"], str) or not sec["I"].strip()):
            errors.append(f"{label} has an empty I description")
    if sections and abs(total - SCHEME_POINTS["ap-stats"]) > 1e-9:
        errors.append(f"section weights sum to {number(total)}, not "
                      f"{SCHEME_POINTS['ap-stats']}")
    for item in group["items"]:
        if item not in covered:
            errors.append(f"item {item} is in no section")
    if errors:
        raise ManifestError(f"{where}: invalid ap-stats rubric for question {group['id']}: "
                            + "; ".join(errors))


ASSIGNMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def cover_tex(path):
    """The \\def lines cover.tex reads, from a blank build's .grading file."""
    meta, _, _, qr, _, items = read_grading(path)
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


SAME = ("type", "points", "answer", "check", "question")
GROUP_SAME = ("scheme", "points", "rubric", "items")


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
    bg = {g["id"]: g for g in blank.get("groups", [])}
    kg = {g["id"]: g for g in key.get("groups", [])}
    for gid in bg.keys() - kg.keys():
        errors.append(f"question {gid}: in the blank, not in the key")
    for gid in kg.keys() - bg.keys():
        errors.append(f"question {gid}: in the key, not in the blank")
    for gid in [g["id"] for g in blank.get("groups", []) if g["id"] in kg]:
        for field in GROUP_SAME:
            if bg[gid].get(field) != kg[gid].get(field):
                errors.append(f"question {gid}: {field} differs: blank {bg[gid].get(field)!r}, "
                              f"key {kg[gid].get(field)!r}")
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
            n = len(manifest["groups"])
            groups = f", {n} group{'s' * (n != 1)}" if n else ""
            print(f"manifest: {len(manifest['questions'])} questions{groups}, "
                  f"{manifest['points']} points, {manifest['pages']} pages -> {args.output}")
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
        groups = blank.get("groups", [])
        print(f"manifest check: blank and key agree on {len(blank['questions'])} questions"
              + (f" and {len(groups)} group{'s' * (len(groups) != 1)}" if groups else ""))
        return 0
    except (ManifestError, OSError, KeyError, json.JSONDecodeError) as e:
        print(f"manifest: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
