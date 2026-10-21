import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import roster_import  # noqa: E402
import roster_tex  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
PARENT_DATA = ["Pat Example", "pat@example.com", "555-01", "Example Rd", "Teacher, A", "Ray"]


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class RosterImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        # The guard must not fire on the test's own scratch directory.
        self.assertIsNone(roster_import.git_work_tree(self.dir))
        self.out = self.dir / "roster-map.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def run_import(self, export, *extra, out=None):
        return roster_import.main([str(export), str(out or self.out), *extra])

    def test_parses_students_and_drops_everything_else(self):
        self.assertEqual(self.run_import(FIXTURES / "course-roster.xls", "--section", "A"), 0)
        rows = read(self.out)
        self.assertEqual(
            [(r["legal_name"], r["preferred_name"], r["class_year"], r["section"]) for r in rows],
            [("Example, Avery Jordan", "Avery Jordan", "2028", "A"),
             ("O'Testperson, Zoë", "Zoë", "2028", "A"),
             ("Sample, Margaret", "Maggie", "2027", "A")])
        self.assertEqual(list(rows[0]), roster_import.FIELDS)
        text = self.out.read_text(encoding="utf-8")
        for parent in PARENT_DATA:
            self.assertNotIn(parent, text)

    def test_tracking_ids(self):
        self.run_import(FIXTURES / "course-roster.xls")
        ids = [r["tracking_id"] for r in read(self.out)]
        self.assertEqual(len(set(ids)), 3)
        for tid in ids:
            self.assertEqual(len(tid), 6)
            self.assertTrue(set(tid) <= set(roster_import.ALPHABET))
            self.assertFalse(set(tid) & set("0O1IL"))

    def test_reimport_keeps_ids_and_adds_new_student(self):
        self.run_import(FIXTURES / "course-roster.xls")
        before = {r["legal_name"]: r["tracking_id"] for r in read(self.out)}
        self.assertEqual(self.run_import(FIXTURES / "course-roster-later.xls"), 0)
        after = {r["legal_name"]: r["tracking_id"] for r in read(self.out)}
        for name, tid in before.items():
            self.assertEqual(after[name], tid)
        self.assertEqual(set(after) - set(before), {"Newcomer, Riley"})
        self.assertNotIn(after["Newcomer, Riley"], before.values())
        # Importing the earlier export again drops nobody and changes nothing.
        self.run_import(FIXTURES / "course-roster.xls")
        self.assertEqual({r["legal_name"]: r["tracking_id"] for r in read(self.out)}, after)

    def test_html_export(self):
        export = self.dir / "roster.xls"
        export.write_text(
            "<html><body><table>"
            "<tr><th>Student</th><th>Parent</th><th>Parent Email</th></tr>"
            "<tr><td>Example, Avery Jordan '28</td><td>Pat Example</td><td>pat@example.com</td></tr>"
            "<tr><td></td><td>Sam Example</td><td>sam@example.com</td></tr>"
            "<tr><td>Sample, Margaret (Maggie) '27</td><td>Kim Sample</td><td>kim@example.com</td></tr>"
            "</table></body></html>", encoding="utf-8")
        self.assertEqual(self.run_import(export), 0)
        self.assertEqual([r["preferred_name"] for r in read(self.out)], ["Avery Jordan", "Maggie"])
        self.assertNotIn("example.com", self.out.read_text(encoding="utf-8"))

    def test_output_directory(self):
        self.assertEqual(self.run_import(FIXTURES / "course-roster.xls", out=self.dir), 0)
        self.assertTrue(self.out.exists())

    def test_refuses_to_write_inside_a_git_work_tree(self):
        repo = self.dir / "repo"
        (repo / "sub").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        for out in [repo / "roster-map.csv", repo / "sub", repo / "sub" / "roster-map.csv"]:
            self.assertEqual(self.run_import(FIXTURES / "course-roster.xls", out=out), 1)
        self.assertEqual(list(repo.rglob("*.csv")), [])
        # This repository too.
        self.assertEqual(
            self.run_import(FIXTURES / "course-roster.xls", out=ROOT), 1)

    def test_roster_tex(self):
        self.run_import(FIXTURES / "course-roster.xls")
        rows = {r["legal_name"]: r for r in read(self.out)}
        self.assertEqual(roster_import.display_name(rows["Sample, Margaret"]), "Maggie Sample")
        self.assertEqual(roster_tex.tex_escape("Zoë O'Testperson"),
                         "Zo{\\char235} O{\\char39}Testperson")


class NameParseTest(unittest.TestCase):
    def test_forms(self):
        m = roster_import.NAME_RE.match
        self.assertEqual(m("Smith, Jane (Janie) '28").group("last", "first", "preferred", "yy"),
                         ("Smith", "Jane", "Janie", "28"))
        self.assertEqual(m("de la Cruz, Ana María ’29").group("last", "first", "yy"),
                         ("de la Cruz", "Ana María", "29"))
        self.assertIsNone(m("Smith, Pat"))  # a parent name: no class year
        self.assertIsNone(m("Student"))


if __name__ == "__main__":
    unittest.main()
