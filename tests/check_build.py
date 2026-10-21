#!/usr/bin/env python3
"""Check a grading.mk build of the sample component.

    check_build.py GRADING_OUT ROSTER

Expects GRADING_OUT to hold blank/, key/, students/, manifest.json,
key-manifest.json and personalized.pdf. Checks that

  - the blank, the key and every personalized copy have the same page count;
  - every QR code on every page decodes to "assignment|page|trackingid"
    (MASTER for the blank and key builds, the roster's ids in roster order for
    personalized.pdf);
  - every box in manifest.json lands on a drawn box: the border is dark, the
    inside is empty in the blank and holds ink in the key;
  - the registration marks and QR code are where the .grading file says, and
    nothing grading.sty draws enters the text block or the paginate.tex band;
  - the name strip is empty in the blank and holds the name in each copy;
  - each personalized page matches the blank page everywhere outside the
    strip and the QR code.

Renders with pdftoppm and decodes with zbarimg (or the zxingcpp module), the
same poppler tools the course builds already use; pixels are read from PGM, so
no imaging library is needed.
"""

import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DPI = 150
QR_DPI = 300
DARK = 110        # a border/mark pixel is darker than this
WHITE = 235       # an empty pixel is lighter than this
PT = 72 / 72.27   # one TeX point in PDF points
BAND = (10 * PT, 42 * PT)              # paginate.tex white band, bp above the page bottom
TEXT_BLOCK = (54.0, 54.0, 504.0, 694.8)  # margins 0.75in, top 0.6in, bottom 0.75in

failures = []


def fail(msg):
    failures.append(msg)
    print(f"  FAIL  {msg}")


def pages(pdf):
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, check=True).stdout
    return int(next(l.split()[1] for l in out.splitlines() if l.startswith("Pages:")))


class Page:
    """A grayscale render; coordinates in PDF points from the lower-left."""

    def __init__(self, pdf, page, dpi, tmp):
        prefix = Path(tmp) / f"r{page}"
        subprocess.run(["pdftoppm", "-gray", "-r", str(dpi), "-f", str(page), "-l", str(page),
                        "-singlefile", str(pdf), str(prefix)], check=True)
        self.path = prefix.with_suffix(".pgm")
        data = self.path.read_bytes()
        fields, pos = [], 0
        while len(fields) < 4:  # P5 width height maxval, whitespace-separated
            while data[pos:pos + 1].isspace():
                pos += 1
            start = pos
            while not data[pos:pos + 1].isspace():
                pos += 1
            fields.append(data[start:pos])
        assert fields[0] == b"P5"
        self.w, self.h = int(fields[1]), int(fields[2])
        self.px = data[pos + 1:]
        self.s = dpi / 72

    def at(self, x, y):
        i = min(max(int(x * self.s), 0), self.w - 1)
        j = min(max(int((self.page_h - y) * self.s), 0), self.h - 1)
        return self.px[j * self.w + i]

    def region(self, x, y, w, h):
        """Pixel values in the rectangle (bp, lower-left origin)."""
        i0, i1 = int(x * self.s), int((x + w) * self.s)
        j0, j1 = int((self.page_h - y - h) * self.s), int((self.page_h - y) * self.s)
        for j in range(max(j0, 0), min(j1, self.h)):
            row = j * self.w
            yield from self.px[row + max(i0, 0):row + min(i1, self.w)]

    def darkest(self, x, y, w, h):
        return min(self.region(x, y, w, h), default=255)

    def lightest(self, x, y, w, h):
        return max(self.region(x, y, w, h), default=0)


def decode_qr(pdf, page, tmp):
    r = Page(pdf, page, QR_DPI, tmp)
    if shutil.which("zbarimg"):
        out = subprocess.run(["zbarimg", "-q", "--raw", str(r.path)],
                             capture_output=True, text=True)
        return out.stdout.split()
    import zxingcpp  # noqa: F401  (fallback when zbar is not installed)
    from PIL import Image
    return [b.text for b in zxingcpp.read_barcodes(Image.open(r.path))]


def overlaps(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def render(pdf, page, tmp, page_h):
    p = Page(pdf, page, DPI, tmp)
    p.page_h = page_h
    return p


def check_box(p, q, key):
    x, y, w, h = q["box"]
    e = 1.0  # bp of slack around the 0.6bp border
    edges = {
        "bottom": (x + w * 0.3, y - e, w * 0.4, 2 * e + 0.6),
        "top": (x + w * 0.3, y + h - 0.6 - e, w * 0.4, 2 * e + 0.6),
        "left": (x - e, y + h * 0.3, 2 * e + 0.6, h * 0.4),
        "right": (x + w - 0.6 - e, y + h * 0.3, 2 * e + 0.6, h * 0.4),
    }
    for name, rect in edges.items():
        # Every pixel column/row across the edge must cross the dark border.
        if p.darkest(*rect) > DARK:
            fail(f"{q['id']}: no border on the {name} edge of {q['box']} (page {q['page']})")
            return
    inside = (x + 3, y + 3, w - 6, h - 6)
    if key:
        if p.darkest(*inside) > DARK:
            fail(f"{q['id']}: key box is empty")
    elif min(p.region(*inside)) < WHITE:
        fail(f"{q['id']}: blank box has ink inside")


def main(out, roster):
    out = Path(out)
    manifest = json.loads((out / "manifest.json").read_text())
    key_manifest = json.loads((out / "key-manifest.json").read_text())
    with open(roster, newline="", encoding="utf-8") as f:
        ids = [r["tracking_id"] for r in csv.DictReader(f)]
    assignment, n = manifest["assignment"], manifest["pages"]
    page_w, page_h = manifest["paper"]
    blank, key = out / "blank/main.pdf", out / "key/main.pdf"
    personalized = out / "personalized.pdf"

    print("page counts")
    for pdf in [blank, key] + [out / "students" / f"{i}.pdf" for i in ids]:
        if pages(pdf) != n:
            fail(f"{pdf.name}: {pages(pdf)} pages, the manifest says {n}")
    if pages(personalized) != n * len(ids):
        fail(f"personalized.pdf: {pages(personalized)} pages, expected {n * len(ids)}")

    print("furniture geometry")
    furniture = {"strip": manifest["strip"], "qr": manifest["qr"],
                 **{f"mark {c}": b for c, b in manifest["marks"].items()}}
    for name, (x, y, w, h) in furniture.items():
        if overlaps((x, y, w, h), TEXT_BLOCK):
            fail(f"{name} {[x, y, w, h]} overlaps the text block")
        if y < BAND[1] + 1:
            fail(f"{name} {[x, y, w, h]} reaches into the paginate.tex band")
    if set(manifest["marks"]) != {"tl", "tr", "bl", "br"}:
        fail(f"marks: {sorted(manifest['marks'])}")

    with tempfile.TemporaryDirectory() as tmp:
        print("QR codes")
        expected = []
        for pdf, who in [(blank, ["MASTER"]), (key, ["MASTER"]), (personalized, ids)]:
            k = 0
            for tid in who:
                for pg in range(1, n + 1):
                    k += 1
                    want = f"{assignment}|{pg}|{tid}"
                    got = decode_qr(pdf, k, tmp)
                    expected.append(want)
                    if got != [want]:
                        fail(f"{pdf.name} page {k}: QR {got}, expected {want}")
        print(f"  {len(expected)} pages decoded")

        print("boxes, marks, strip, band")
        renders = {}
        for label, pdf, m in [("blank", blank, manifest), ("key", key, key_manifest)]:
            Path(tmp, label).mkdir()
            for pg in range(1, n + 1):
                p = renders[label, pg] = render(pdf, pg, f"{tmp}/{label}", page_h)
                for q in m["questions"]:
                    if q["page"] == pg:
                        check_box(p, q, key=label == "key")
                for c, (x, y, w, h) in m["marks"].items():
                    if p.lightest(x + 1, y + 1, w - 2, h - 2) > DARK:
                        fail(f"{label} page {pg}: mark {c} is not solid at {[x, y, w, h]}")
                    if p.darkest(x - 4, y - 4, w + 8, 2) < WHITE:
                        fail(f"{label} page {pg}: ink just below mark {c}")
                qx, qy, qw, qh = m["qr"]
                if p.darkest(qx, qy, qw, qh) > DARK:
                    fail(f"{label} page {pg}: no QR at {m['qr']}")
                if min(p.region(*m["strip"])) < WHITE:
                    fail(f"{label} page {pg}: the name strip is not empty in a MASTER build")
                # The band paginate.tex whites out: only the centred page
                # number may be there, and it is not ours.
                for x0, x1 in [(0, page_w / 2 - 40), (page_w / 2 + 40, page_w)]:
                    if p.darkest(x0, BAND[0], x1 - x0, BAND[1] - BAND[0]) < WHITE:
                        fail(f"{label} page {pg}: ink in the paginate.tex band")

        print("personalized copies")
        sx, sy, sw, sh = manifest["strip"]
        qx, qy, qw, qh = manifest["qr"]
        Path(tmp, "s").mkdir()
        for k, tid in enumerate(ids):
            for pg in range(1, n + 1):
                p = render(personalized, k * n + pg, f"{tmp}/s", page_h)
                if p.darkest(*manifest["strip"]) > DARK:
                    fail(f"{tid} page {pg}: no name in the strip")
                b = renders["blank", pg]
                diff = 0
                for j in range(p.h):
                    y = page_h - (j + 0.5) / p.s
                    in_strip_rows = sy <= y <= sy + sh
                    in_qr_rows = qy <= y <= qy + qh
                    row = j * p.w
                    if p.px[row:row + p.w] == b.px[row:row + p.w]:
                        continue
                    for i in range(p.w):
                        if p.px[row + i] != b.px[row + i]:
                            x = (i + 0.5) / p.s
                            if (in_strip_rows and sx <= x <= sx + sw) or \
                               (in_qr_rows and qx <= x <= qx + qw):
                                continue
                            diff += 1
                if diff:
                    fail(f"{tid} page {pg}: {diff} pixels differ from the blank "
                         f"outside the strip and QR code")
        print(f"  {len(ids)} copies x {n} pages compared")

    if failures:
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("\nall build checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
