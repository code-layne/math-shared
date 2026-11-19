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


def xdv(page):
    """A one-page XDV 7 file whose page holds the given opcodes."""
    pre = b"\xf7\x07" + (25400000).to_bytes(4, "big") + (473628672).to_bytes(4, "big") \
        + (1000).to_bytes(4, "big") + b"\x00"
    bop = b"\x8b" + bytes(40) + (-1).to_bytes(4, "big", signed=True)
    font = b"\xfc" + (1).to_bytes(4, "big") + (655360).to_bytes(4, "big") + b"\x00\x00" \
        + bytes([len(b"[lmroman10-regular.otf]")]) + b"[lmroman10-regular.otf]" + bytes(4)
    post = b"\xf8" + bytes(28)
    return pre + font + bop + page + b"\x8c" + post + b"\xf9" + bytes([0, 0, 0, 0, 7]) + b"\xdf" * 4


def glyphs(raw):
    """A glyphs opcode whose glyph-id bytes are exactly raw."""
    n = len(raw) // 2
    return b"\xfd" + bytes(4) + n.to_bytes(2, "big") + bytes(8 * n) + raw


def special(text):
    return b"\xef" + bytes([len(text)]) + text


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

    def test_name_bytes_in_xdv_glyph_data_pass(self):
        # A 2-letter given name between non-printing bytes, as XeTeX glyph ids
        # and positions produce by chance, is not text on the page.
        roster = self.out / "roster.csv"
        roster.write_text("tracking_id,legal_name,preferred_name,class_year,section\n"
                          'Q2ZT7K,"Testcase, Bo",Bo,2028,Algebra 2 - A\n')
        page = glyphs(b"@2\x02Bo\xff\x00\x01Zo\xc3\xab\x00")
        (self.out / "students" / "K7QM2P.xdv").write_bytes(xdv(page))
        self.assertEqual(check_names.main([str(self.out), str(roster)]), 0)
        self.assertEqual(self.run_check(), 0)

    def test_name_in_xdv_special_fails(self):
        page = glyphs(b"\x00\x01") + special(b"pdf:docinfo << /Author (Avery) >>")
        (self.out / "students" / "K7QM2P.xdv").write_bytes(xdv(page))
        self.assertEqual(self.run_check(), 1)

    def test_name_in_xdv_actual_text_fails(self):
        text = "Zo\u00eb".encode("utf-16-be")
        page = b"\xfe" + (len(text) // 2).to_bytes(2, "big") + text + bytes(4) + bytes(2)
        (self.out / "students" / "K7QM2P.xdv").write_bytes(xdv(page))
        self.assertEqual(self.run_check(), 1)

    def test_unparseable_xdv_is_scanned_whole(self):
        data = xdv(glyphs(b"\x00\x01") + special(b"Avery"))
        (self.out / "students" / "K7QM2P.xdv").write_bytes(data[:-12] + b"\xfb")
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
