#!/usr/bin/env python3
"""Check the box-sizing fixture, tests/sizing/main.tex.

    check_sizing.py OUT

OUT holds blank/, key/ and reset/ builds of the fixture (see the Makefile).
Checks the recorded sizes in each .grading file against the rules:

  - choice boxes keep their width and are as tall as \\gradingchoiceheight
    (square by default), and each one written at another height leaves an
    info note in the log, not a warning;
  - rubric boxes are max(written height, \\gradingrubricminheight);
  - short boxes are drawn as written;

then renders the blank and key pages with the same border, size and key-fit
checks check_build.py makes on the sample.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_build as cb  # noqa: E402

IN = 72.0
# id -> (width, height) in bp, under the defaults and after the reset.
DEFAULT = {"c1": (36, 36), "c2": (28.8, 28.8), "c3": (32.4, 32.4),
           "s1": (86.4, 21.6), "r1": (None, 144), "r2": (288, 216)}
RESET = {"c1": (36, 21.6), "c2": (28.8, 17.28), "c3": (32.4, 19.44),
         "s1": (86.4, 21.6), "r1": (None, 180), "r2": (288, 216)}
# Choice boxes written at a height other than the drawn one, and the rest.
RESIZED = {"c1", "c2"}
RESET_RESIZED = {"c2", "c3"}  # c1 is written 0.3in, which is 0.6 x 0.5in


def items(grading):
    lines = [json.loads(l) for l in Path(grading).read_text().splitlines()]
    return {o["id"]: o for o in lines if o["kind"] == "item"}


def check_sizes(label, got, want):
    for qid, (w, h) in want.items():
        bw, bh = got[qid]["box"][2:]
        if (w is not None and abs(bw - w) > 0.02) or abs(bh - h) > 0.02:
            cb.fail(f"{label} {qid}: box {bw} x {bh}, expected {w or "any"} x {h}")


def check_log(label, log, resized):
    """An info note for each resized choice box and none for the others."""
    text = Path(log).read_text(errors="replace")
    joined = " ".join(text.split())
    for qid in sorted(resized):
        if f"Item '{qid}': choice box drawn" not in joined:
            cb.fail(f"{label}: no log note for the resized choice box {qid}")
    for qid in sorted({"c1", "c2", "c3"} - resized):
        if f"Item '{qid}': choice box drawn" in joined:
            cb.fail(f"{label}: a log note for {qid}, which was drawn as written")
    if "Package grading Warning" in text:
        cb.fail(f"{label}: grading.sty warned")


def main(out):
    out = Path(out)
    blank, key = items(out / "blank/main.grading"), items(out / "key/main.grading")
    print("sizes")
    check_sizes("blank", blank, DEFAULT)
    check_sizes("key", key, DEFAULT)
    check_sizes("reset", items(out / "reset/main.grading"), RESET)
    for qid in blank:
        if blank[qid]["box"] != key[qid]["box"]:
            cb.fail(f"{qid}: the key box {key[qid]['box']} differs from the blank's")
    print("log notes")
    check_log("blank", out / "blank/main.log", RESIZED)
    check_log("key", out / "key/main.log", RESIZED)
    check_log("reset", out / "reset/main.log", RESET_RESIZED)

    print("rendered boxes")
    meta = json.loads((out / "blank/main.grading").read_text().splitlines()[0])
    page_h = meta["paper"][1]
    with tempfile.TemporaryDirectory() as tmp:
        renders = {}
        for label in ("blank", "key"):
            Path(tmp, label).mkdir()
            renders[label] = {pg: cb.render(out / label / "main.pdf", pg, f"{tmp}/{label}", page_h)
                              for pg in range(1, meta["pages"] + 1)}
        for q in blank.values():
            b, k = renders["blank"][q["page"]], renders["key"][q["page"]]
            cb.check_box(b, q, key=False)
            cb.check_box(k, q, key=True)
            cb.check_size(b, q)
            cb.check_key_fit(k, b, q)

    if cb.failures:
        print(f"\n{len(cb.failures)} sizing check(s) failed")
        return 1
    print("\nall sizing checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
