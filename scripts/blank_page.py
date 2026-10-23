#!/usr/bin/env python3
"""Write a one-page empty PDF, the padding grading.mk puts between copies.

    blank_page.py OUT.pdf [--paper W H]     (PDF points; default letter)

Each student's run in personalized.pdf is her cover sheet, this page (the
cover's back), and her graded copy padded with this page to an even count.
"""

import argparse
import sys
from pathlib import Path


def blank_pdf(width, height):
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width:g} {height:g}] "
        f"/Resources << >> /Contents 4 0 R >>".encode(),
        b"<< /Length 0 >>\nstream\n\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    return bytes(out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("output")
    ap.add_argument("--paper", nargs=2, type=float, default=[612, 792], metavar=("W", "H"))
    args = ap.parse_args(argv)
    Path(args.output).write_bytes(blank_pdf(*args.paper))
    return 0


if __name__ == "__main__":
    sys.exit(main())
