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

    def grading(self, name, key=False, change=None):
        items = [dict(i, kind="item", assignment="alg2-3.4-et") for i in ITEMS]
        if change:
            change(items)
        path = self.dir / name
        lines = [dict(META, key=key), *FURNITURE, *items]
        path.write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")
        return path

    def build(self, **kw):
        m, _ = manifest.build(self.grading("x.grading", **kw))
        return m

    def test_design_doc_format(self):
        m = self.build()
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


if __name__ == "__main__":
    unittest.main()
