import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import manifest  # noqa: E402

META = {"kind": "meta", "format": 1, "course": "example", "student": "MASTER",
        "key": False, "pages": 2, "paper": [612, 792]}
FURNITURE = [
    {"kind": "strip", "box": [54, 756, 504, 26]},
    {"kind": "mark", "corner": "tl", "box": [21, 764, 12, 12]},
    {"kind": "mark", "corner": "tr", "box": [579, 764, 12, 12]},
    {"kind": "mark", "corner": "bl", "box": [21, 60, 12, 12]},
    {"kind": "mark", "corner": "br", "box": [579, 60, 12, 12]},
    {"kind": "qr", "box": [566, 720, 32, 32]},
]
ITEMS = [
    {"id": "et1", "type": "choice", "points": 1, "answer": "C", "check": "",
     "page": 1, "box": [72, 540.2, 108, 43.2]},
    {"id": "et2", "type": "short", "points": 2, "answer": "3/2", "check": "expression",
     "page": 1, "box": [72, 460, 108, 43.2]},
    {"id": "et3", "type": "rubric", "points": 4, "answer": "", "check": "",
     "page": 2, "box": [72, 300, 432, 180]},
]


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def grading(self, name, key=False, change=None, groups=()):
        items = [dict(i, kind="item", assignment="alg2-3.4-et") for i in ITEMS]
        if change:
            change(items)
        path = self.dir / name
        lines = [dict(META, key=key), *FURNITURE, *groups, *items]
        path.write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")
        return path

    def build(self, **kw):
        m, _ = manifest.build(self.grading("x.grading", **kw))
        return m

    def test_design_doc_format(self):
        m = self.build()
        self.assertEqual(m["groups"], [])
        self.assertEqual(m["points"], 7)
        self.assertEqual(m["assignment"], "alg2-3.4-et")
        self.assertEqual(m["course"], "example")
        self.assertEqual(m["pages"], 2)
        self.assertEqual(m["questions"], [
            {"id": "et1", "type": "choice", "points": 1, "answer": "C",
             "page": 1, "box": [72, 540.2, 108, 43.2]},
            {"id": "et2", "type": "short", "points": 2, "answer": "3/2",
             "check": "expression", "page": 1, "box": [72, 460, 108, 43.2]},
            {"id": "et3", "type": "rubric", "points": 4,
             "rubric": "rubrics/alg2-3.4-et-et3.yaml", "page": 2, "box": [72, 300, 432, 180]},
        ])
        self.assertEqual(m["strip"], [54, 756, 504, 26])
        self.assertEqual(sorted(m["marks"]), ["bl", "br", "tl", "tr"])

    def test_check_passes_when_only_layout_moves(self):
        def nudge(items):
            items[0]["box"] = [72, 538.5, 108, 43.2]
        errors, warnings = manifest.check(self.build(), self.build(key=True, change=nudge))
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)

    def test_check_fails_on_any_key_difference(self):
        for field, value in [("answer", "1.5"), ("points", 3), ("type", "choice"),
                             ("check", "numeric")]:
            def change(items, field=field, value=value):
                items[1][field] = value
            errors, _ = manifest.check(self.build(), self.build(key=True, change=change))
            self.assertTrue(any(field in e for e in errors), (field, errors))

    def test_check_fails_on_missing_item(self):
        errors, _ = manifest.check(self.build(), self.build(key=True, change=lambda i: i.pop()))
        self.assertEqual(errors, ["et3: in the blank, not in the key"])

    def test_cli_check_exit_status(self):
        blank = self.dir / "blank.json"
        key = self.dir / "key.json"
        self.assertEqual(manifest.main(["write", str(self.grading("b.grading")), "-o", str(blank)]), 0)
        def wrong(items):
            items[0]["answer"] = "D"
        self.assertEqual(manifest.main(["write", str(self.grading("k.grading", True, wrong)),
                                        "-o", str(key)]), 0)
        self.assertEqual(manifest.main(["check", str(blank), str(blank)]), 0)
        self.assertEqual(manifest.main(["check", str(blank), str(key)]), 1)

    def test_cover_tex(self):
        path = self.grading("c.grading")
        lines = path.read_text().splitlines()
        lines[0] = json.dumps(dict(META, assignment="alg2-3.4-et",
                                   title="Lesson 3.4 Exit Ticket: f(x) & 50%"))
        path.write_text("\n".join(lines) + "\n")
        self.assertEqual(manifest.cover_tex(path),
                         "\\def\\CoverAssignment{alg2-3.4-et}\\def\\CoverCourse{example}"
                         "\\def\\CoverTitle{Lesson 3.4 Exit Ticket{\\char58} f{\\char40}x"
                         "{\\char41} {\\char38} 50{\\char37}}"
                         "\\def\\CoverQRSize{32bp}\\def\\CoverQRInset{14bp}"
                         "\\def\\CoverQRTop{40bp}")
        self.assertEqual(self.build()["title"], "")

    def test_cover_tex_refuses_unsafe_assignment(self):
        def unsafe(items):
            for i in items:
                i["assignment"] = 'et"; rm -rf ~'
        with self.assertRaises(manifest.ManifestError):
            manifest.cover_tex(self.grading("u.grading", change=unsafe))

    def test_unresolved_positions_are_an_error(self):
        def unplaced(items):
            items[0]["page"] = 0
        with self.assertRaises(manifest.ManifestError):
            self.build(change=unplaced)

    def test_interval_check_is_accepted(self):
        def interval(items):
            items[1].update(answer="(-\\infty ,\\,-1)", check="interval")
        q = self.build(change=interval)["questions"][1]
        self.assertEqual((q["check"], q["answer"]), ("interval", "(-\\infty ,\\,-1)"))

    def test_unknown_check_is_an_error(self):
        def bad(items):
            items[1]["check"] = "range"
        with self.assertRaises(manifest.ManifestError):
            self.build(change=bad)


GROUP = {"kind": "group", "assignment": "apstats-u02-test", "id": "t12", "scheme": "ap-stats",
         "points": 4, "rubric": "rubrics/apstats-u02-test-t12.yaml"}
FRQ_ITEMS = [
    {"id": "t11", "type": "choice", "points": 1, "answer": "B", "check": "",
     "page": 1, "box": [72, 600, 36, 36]},
    {"id": "t12a", "type": "rubric", "points": 0, "question": "t12", "answer": "", "check": "",
     "page": 1, "box": [72, 400, 468, 144]},
    {"id": "t12b", "type": "short", "points": 0, "question": "t12", "answer": "365",
     "check": "numeric", "page": 2, "box": [400, 600, 86.4, 28.8]},
    {"id": "t12c", "type": "rubric", "points": 0, "question": "t12", "answer": "", "check": "",
     "page": 2, "box": [72, 300, 468, 144]},
    {"id": "t13", "type": "short", "points": 2, "answer": "0.05", "check": "numeric",
     "page": 2, "box": [400, 200, 86.4, 28.8]},
]
RUBRIC = """\
scheme: ap-stats
id: t12
points: 4
task: >-
  Interpret a slope, make a prediction, and interpret a residual.
sections:
  - id: s1
    items: [t12a]
    E: >-
      Interprets the slope in context as a predicted change.
    P: >-
      Includes two of the three components.
  - id: s2
    items: [t12b]
    E: Predicts 365 with work shown.
    P: Correct substitution with an arithmetic error.
  - id: s3
    items: [t12c]
    weight: 2
    E: Calculates and interprets the residual in context.
    P: Calculates the residual but does not interpret it.
    I: Does not meet the criteria for P.
notes: Do not penalize rounding.
"""


class GroupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "rubrics").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def grading(self, name="g.grading", key=False, groups=None, change=None):
        items = [dict(i, kind="item", assignment="apstats-u02-test") for i in FRQ_ITEMS]
        groups = [dict(GROUP)] if groups is None else groups
        if change:
            change(groups, items)
        path = self.dir / name
        lines = [dict(META, key=key, assignment="apstats-u02-test"), *FURNITURE, *groups, *items]
        path.write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")
        return path

    def build(self, lesson_dir=None, **kw):
        return manifest.build(self.grading(**kw), lesson_dir=lesson_dir)

    def rubric(self, text=RUBRIC):
        (self.dir / "rubrics" / "apstats-u02-test-t12.yaml").write_text(text, encoding="utf-8")

    def test_group_line_is_read(self):
        _, _, _, _, groups, items = manifest.read_grading(self.grading())
        self.assertEqual(groups, [GROUP])
        self.assertEqual(len(items), 5)

    def test_manifest_groups_and_total(self):
        m, warnings = self.build()
        self.assertEqual(warnings, [])
        self.assertEqual(m["groups"], [
            {"id": "t12", "scheme": "ap-stats", "points": 4,
             "rubric": "rubrics/apstats-u02-test-t12.yaml", "items": ["t12a", "t12b", "t12c"]}])
        by_id = {q["id"]: q for q in m["questions"]}
        for qid in ("t12a", "t12b", "t12c"):
            self.assertEqual((by_id[qid]["question"], by_id[qid]["points"]), ("t12", 0))
        self.assertNotIn("question", by_id["t11"])
        self.assertEqual(by_id["t12b"]["type"], "short")
        self.assertEqual(by_id["t12b"]["check"], "numeric")
        # 1 (t11) + 2 (t13) + 4 (t12)
        self.assertEqual(m["points"], 7)
        self.assertEqual(manifest.total_points(m["questions"], m["groups"]), 7)

    def test_group_rubric_defaults_and_explicit_path(self):
        def no_rubric(groups, items):
            groups[0]["rubric"] = ""
        m, _ = self.build(change=no_rubric)
        self.assertEqual(m["groups"][0]["rubric"], "rubrics/apstats-u02-test-t12.yaml")
        def other(groups, items):
            groups[0]["rubric"] = "../rubrics/apstats-u02-actual-test-t12.yaml"
        m, _ = self.build(change=other)
        self.assertEqual(m["groups"][0]["rubric"], "../rubrics/apstats-u02-actual-test-t12.yaml")

    def test_undeclared_question_is_an_error(self):
        def stray(groups, items):
            items[0]["question"] = "t99"
            items[0]["points"] = 0
        with self.assertRaisesRegex(manifest.ManifestError, "t99"):
            self.build(change=stray)

    def test_empty_group_is_an_error(self):
        def empty(groups, items):
            groups.append(dict(GROUP, id="t14", rubric=""))
        with self.assertRaisesRegex(manifest.ManifestError, "t14 has no items"):
            self.build(change=empty)

    def test_group_errors(self):
        cases = {
            "declared twice": lambda g, i: g.append(dict(GROUP)),
            "unknown scheme": lambda g, i: g[0].update(scheme="ap-calc"),
            "worth 4 points": lambda g, i: g[0].update(points=6),
            "not 0": lambda g, i: i[1].update(points=1),
            "both a question id and an item id": lambda g, i: g[0].update(id="t11"),
        }
        for message, change in cases.items():
            with self.assertRaisesRegex(manifest.ManifestError, message):
                self.build(change=change)

    def test_grouped_rubric_item_needs_no_rubric_file(self):
        self.rubric()
        _, warnings = self.build(lesson_dir=self.dir)
        self.assertEqual(warnings, [])

    def test_missing_group_rubric_is_a_warning(self):
        _, warnings = self.build(lesson_dir=self.dir)
        self.assertEqual(len(warnings), 1)
        self.assertIn("question t12: rubric file", warnings[0])

    def check_rubric(self, text):
        self.rubric(text)
        with self.assertRaises(manifest.ManifestError) as cm:
            self.build(lesson_dir=self.dir)
        return str(cm.exception)

    def test_rubric_weights_must_sum_to_4(self):
        msg = self.check_rubric(RUBRIC.replace("weight: 2", "weight: 1"))
        self.assertIn("section weights sum to 3, not 4", msg)

    def test_rubric_must_cover_every_item(self):
        msg = self.check_rubric(RUBRIC.replace("items: [t12b]", "items: [t12a]"))
        self.assertIn("item t12b is in no section", msg)

    def test_rubric_rejects_unknown_item(self):
        msg = self.check_rubric(RUBRIC.replace("items: [t12c]", "items: [t12c, t12d]"))
        self.assertIn("lists 't12d', which is not an item of question t12", msg)

    def test_rubric_other_rules(self):
        cases = {
            "section id 's1' is used twice": RUBRIC.replace("id: s2", "id: s1"),
            "has no P description": RUBRIC.replace("    P: Correct substitution with an "
                                                   "arithmetic error.\n", ""),
            "scheme is 'ap-precalc'": RUBRIC.replace("scheme: ap-stats", "scheme: ap-precalc"),
            "id is 't13'": RUBRIC.replace("id: t12", "id: t13"),
            "points is 5": RUBRIC.replace("points: 4", "points: 5"),
            "weight -1": RUBRIC.replace("weight: 2", "weight: -1"),
        }
        for message, text in cases.items():
            self.assertIn(message, self.check_rubric(text))

    def test_valid_rubric_passes(self):
        self.rubric()
        m, warnings = self.build(lesson_dir=self.dir)
        self.assertEqual((warnings, m["points"]), ([], 7))

    def test_sample_rubric_is_valid(self):
        sample = ROOT / "examples" / "rubrics" / "sample-u0-l1-et-et7.yaml"
        manifest.validate_ap_stats_rubric(
            sample, {"id": "et7", "items": ["et7a", "et7b", "et7c"]})

    def test_check_compares_groups(self):
        blank, _ = self.build()
        key, _ = self.build(key=True)
        self.assertEqual(manifest.check(blank, key), ([], []))
        cases = {
            "question t12: in the blank, not in the key":
                lambda g, i: (g.clear(), [x.pop("question") for x in i if "question" in x]),
            "question t12: items differs": lambda g, i: i[3].update(question="t15") or
                g.append(dict(GROUP, id="t15")),
            "question t12: rubric differs": lambda g, i: g[0].update(rubric="other.yaml"),
            "t12b: question differs": lambda g, i: (g.append(dict(GROUP, id="t15")),
                                                    i[2].update(question="t15")),
        }
        for message, change in cases.items():
            key, _ = self.build(key=True, change=change)
            errors, _ = manifest.check(blank, key)
            self.assertTrue(any(e.startswith(message) for e in errors), (message, errors))

    def test_cli_check_fails_on_group_mismatch(self):
        blank, key = self.dir / "blank.json", self.dir / "key.json"
        self.assertEqual(manifest.main(["write", str(self.grading("b.grading")),
                                        "-o", str(blank)]), 0)
        def other(groups, items):
            groups[0]["rubric"] = "other.yaml"
        self.assertEqual(manifest.main(["write", str(self.grading("k.grading", True, change=other)),
                                        "-o", str(key)]), 0)
        self.assertEqual(manifest.main(["check", str(blank), str(blank)]), 0)
        self.assertEqual(manifest.main(["check", str(blank), str(key)]), 1)


if __name__ == "__main__":
    unittest.main()
