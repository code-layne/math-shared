#!/usr/bin/env python3
"""Check \\gradedquestion and question= from the TeX side.

    check_groups.py OUT [SAMPLE_OUT]

Builds tests/groups/main.tex into OUT: as written and as a key, each of which
must write the expected "group" lines and grouped items, and then once for
each broken case, each of which must stop the build with its error:

  - undeclared: an item names a question no \\gradedquestion declares;
  - empty: a \\gradedquestion has no items;
  - duplicate: the same question id is declared twice with different keys;
  - points: a \\gradedquestion sets points=.

With SAMPLE_OUT (the test-build output), also checks the sample's manifest:
its one ap-stats group, the question field and 0 points on its parts, and the
total points.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "groups"
failures = []


def fail(msg):
    failures.append(msg)
    print(f"FAIL: {msg}")


def latexmk(out, pretex=""):
    env = dict(os.environ, TEXINPUTS=f".:{ROOT}:{ROOT / 'examples' / 'shared'}:")
    cmd = ["latexmk", "-xelatex", "-interaction=nonstopmode", "-halt-on-error",
           f"-outdir={out}"]
    if pretex:
        cmd.append(f"-usepretex={pretex}")
    cmd.append("main.tex")
    r = subprocess.run(cmd, cwd=FIXTURE, env=env, capture_output=True, text=True)
    return r.returncode, out / "main.log"


def log_text(log):
    """The log with grading's wrapped message lines joined back up."""
    raw = log.read_text(errors="replace") if log.exists() else ""
    return " ".join(re.sub(r"\n\(grading\)\s+", " ", raw).split())


def records(grading):
    return [json.loads(l) for l in Path(grading).read_text().splitlines() if l.strip()]


GROUPS = [
    {"kind": "group", "assignment": "test-groups", "id": "q1", "scheme": "ap-stats",
     "points": 4, "rubric": "rubrics/test-groups-q1.yaml"},
    {"kind": "group", "assignment": "test-groups", "id": "q2", "scheme": "ap-stats",
     "points": 4, "rubric": "../rubrics/test-groups-q2.yaml"},
]
# id -> (question, points)
ITEMS = {"q1a": ("q1", 0), "q1b": ("q1", 0), "q2a": ("q2", 0), "q2b": ("q2", 0),
         "e1": (None, 2)}


def check_good(label, out, pretex=""):
    code, log = latexmk(out, pretex)
    if code != 0:
        fail(f"{label}: the build failed, see {log}")
        return
    recs = records(out / "main.grading")
    groups = [r for r in recs if r["kind"] == "group"]
    if groups != GROUPS:
        fail(f"{label}: group lines {groups}")
    kinds = [r["kind"] for r in recs]
    if kinds.index("group") < kinds.index("qr") or \
            max(i for i, k in enumerate(kinds) if k == "group") > kinds.index("item"):
        fail(f"{label}: group lines are not between the qr line and the items: {kinds}")
    items = {r["id"]: (r.get("question"), r["points"]) for r in recs if r["kind"] == "item"}
    if items != ITEMS:
        fail(f"{label}: items {items}")
    text = log_text(log)
    if "Item 'q1b' belongs to question 'q1': its 'points=3' is ignored" not in text:
        fail(f"{label}: no warning for points=3 on the grouped item q1b")
    if "Item 'q2b' belongs" in text:
        fail(f"{label}: a warning for points=0 on q2b")
    print(f"  {label}: {len(groups)} group lines and {len(items)} items as expected")


BROKEN = {
    "undeclared": "Item 'z1' names question 'zz', but no \\gradedquestion declares 'zz'.",
    "empty": "Question 'q9' has no items: no \\gradedblank has 'question=q9'.",
    "duplicate": "Question id 'q1' is declared twice in this document, with different keys.",
    "points": "a question with scheme=ap-stats is always worth 4 points",
}


def check_broken(out):
    for case, message in BROKEN.items():
        code, log = latexmk(out / case, f"\\def\\GroupsCase{{{case}}}")
        text = log_text(log)
        if code == 0:
            fail(f"{case}: the build succeeded; it must stop with an error")
        elif message not in text:
            fail(f"{case}: the build failed without the expected message {message!r}")
        else:
            print(f"  {case}: stops with its error")


def check_sample(sample):
    for name in ("manifest.json", "key-manifest.json"):
        if not (sample / name).is_file():
            fail(f"sample: no {sample / name}; run make test-build first")
            return
        m = json.loads((sample / name).read_text())
        want = [{"id": "et7", "scheme": "ap-stats", "points": 4,
                 "rubric": "rubrics/sample-u0-l1-et-et7.yaml",
                 "items": ["et7a", "et7b", "et7c"]}]
        if m.get("groups") != want:
            fail(f"sample {name}: groups {m.get('groups')}")
        for q in m["questions"]:
            grouped = q["id"].startswith("et7")
            if grouped and (q.get("question") != "et7" or q["points"] != 0):
                fail(f"sample {name}: {q['id']} has question {q.get('question')!r}, "
                     f"points {q['points']}")
            if not grouped and "question" in q:
                fail(f"sample {name}: {q['id']} has a question field")
        ungrouped = sum(q["points"] for q in m["questions"] if "question" not in q)
        if m.get("points") != ungrouped + 4 or m.get("points") != 15:
            fail(f"sample {name}: total points {m.get('points')}, expected 11 + 4 = 15")
    print("  sample manifests: one ap-stats group, 15 points")


def main():
    out = Path(sys.argv[1]).resolve()
    check_good("blank", out / "blank")
    check_good("key", out / "key", "\\PassOptionsToPackage{key}{grading}")
    check_broken(out)
    if len(sys.argv) > 2:
        check_sample(Path(sys.argv[2]))
    if failures:
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("check_groups: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
