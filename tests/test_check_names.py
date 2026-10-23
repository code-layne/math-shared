import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import blank_page  # noqa: E402
import check_names  # noqa: E402

ROSTER = ROOT / "examples" / "roster-map.csv"


class CheckNamesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        (self.out / "students").mkdir()
        (self.out / "students" / "K7QM2P.log").write_text(
            "**\\def\\GradingStudentID{K7QM2P}\\input{main.tex}\n"
            "(./example-article.sty) sample-u0-l1-et|1|K7QM2P\n")
        (self.out / "covers").mkdir()
        (self.out / "covers" / "cover-K7QM2P.log").write_text("Avery Example\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self):
        return check_names.main([str(self.out), str(ROSTER)])

    def test_clean_build_passes(self):
        # Covers may hold names; a lowercase or partial-word match is not a name.
        self.assertEqual(self.run_check(), 0)

    def test_each_form_of_a_name_fails(self):
        for text in ["Avery", "Example", "Zoë", "Zo{\\char235}", "O’Testperson",
                     "Testperson", "O{\\char39}Testperson", "Margaret", "Maggie Sample"]:
            log = self.out / "students" / "T4WX9C.out"
            log.write_text(f"latexmk ... {text}.\n")
            self.assertEqual(self.run_check(), 1, text)
            log.unlink()

    def test_a_name_in_blank_or_key_fails(self):
        (self.out / "key").mkdir()
        (self.out / "key" / "main.aux").write_text("\\def\\x{Maggie}\n")
        self.assertEqual(self.run_check(), 1)

    def test_no_personalized_build_is_an_error(self):
        shutil.rmtree(self.out / "students")
        self.assertEqual(self.run_check(), 1)

    @unittest.skipUnless(shutil.which("pdfinfo"), "needs poppler")
    def test_blank_page_is_one_letter_page(self):
        pdf = self.out / "blank.pdf"
        blank_page.main([str(pdf)])
        info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True,
                              check=True).stdout
        self.assertIn("Pages:           1", info)
        self.assertIn("612 x 792 pts", info)


if __name__ == "__main__":
    unittest.main()
