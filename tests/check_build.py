#!/usr/bin/env python3
"""Check a grading.mk build of the sample component.

    check_build.py GRADING_OUT ROSTER

Expects GRADING_OUT to hold blank/, key/, students/, covers/, packets/,
manifest.json, key-manifest.json and personalized.pdf. Checks that

  - the blank, the key and every personalized copy have the same page count,
    and each cover is one page;
  - personalized.pdf is, for each student in roster order, her cover, a blank
    back, then her copy padded with blank pages to an even count: every cover
    starts on an odd page and every copy on a fresh sheet;
  - every QR code on every page decodes to "assignment|page|trackingid"
    (MASTER for the blank and key builds, the roster's ids in roster order for
    personalized.pdf), each cover's to "COVER|assignment|trackingid", and the
    blank backs and padding pages carry nothing;
  - every box in manifest.json lands on a drawn box: the border is dark, the
    inside is empty in the blank and holds ink in the key;
  - the registration marks and QR code are where the .grading file says, and
    nothing grading.sty draws enters the text block or the paginate.tex band;
  - each cover's QR code fills the graded pages' QR rectangle, and the cover
    has no registration marks and nothing in the strip;
  - the id strip is empty in the blank and reads "ID: <tracking id>" in each
    copy;
  - each personalized page matches the blank page everywhere outside the
    strip and the QR code.

The name grep is scripts/check_names.py, which make test runs separately.

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


def strip_text(pdf, page, strip, page_h):
    """The text pdftotext finds inside the strip rectangle."""
    x, y, w, h = strip
    out = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), "-r", "72",
         "-x", str(int(x)), "-y", str(int(page_h - y - h)), "-W", str(int(w) + 1),
         "-H", str(int(h) + 1), str(pdf), "-"], capture_output=True, text=True, check=True)
    return " ".join(out.stdout.split())


def ink_bbox(p, x, y, w, h):
    """Bounding box [x, y, w, h] in bp of the dark pixels in a rectangle."""
    i0, i1 = int(x * p.s), int((x + w) * p.s)
    j0, j1 = int((p.page_h - y - h) * p.s), int((p.page_h - y) * p.s)
    cols, rows = [], []
    for j in range(max(j0, 0), min(j1, p.h)):
        for i in range(max(i0, 0), min(i1, p.w)):
            if p.px[j * p.w + i] < DARK:
                cols.append(i)
                rows.append(j)
    if not cols:
        return None
    return [min(cols) / p.s, p.page_h - (max(rows) + 1) / p.s,
            (max(cols) + 1 - min(cols)) / p.s, (max(rows) + 1 - min(rows)) / p.s]


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
    single = sorted(out.glob("student-*.pdf"))

    # One student's run in personalized.pdf: cover, back, copy, padding.
    per = 2 + n + n % 2
    layout = ["cover", "back"] + [pg for pg in range(1, n + 1)] + ["pad"] * (n % 2)

    print("page counts")
    for pdf in [blank, key] + [out / "students" / f"{i}.pdf" for i in ids]:
        if pages(pdf) != n:
            fail(f"{pdf.name}: {pages(pdf)} pages, the manifest says {n}")
    for i in ids:
        if pages(out / "covers" / f"cover-{i}.pdf") != 1:
            fail(f"cover-{i}.pdf: {pages(out / 'covers' / f'cover-{i}.pdf')} pages, expected 1")
    for pdf in [out / "packets" / f"{i}.pdf" for i in ids] + single:
        if pages(pdf) != per or pages(pdf) % 2:
            fail(f"{pdf.name}: {pages(pdf)} pages, expected an even {per}")
    if pages(personalized) != per * len(ids):
        fail(f"personalized.pdf: {pages(personalized)} pages, expected {per * len(ids)}")

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

    def wanted(tid, what):
        if what == "cover":
            return [f"COVER|{assignment}|{tid}"]
        if what in ("back", "pad"):
            return []
        return [f"{assignment}|{what}|{tid}"]

    with tempfile.TemporaryDirectory() as tmp:
        print("QR codes and page order")
        decoded = 0
        for pdf, who in [(blank, ["MASTER"]), (key, ["MASTER"])]:
            for pg in range(1, n + 1):
                want, got = wanted("MASTER", pg), decode_qr(pdf, pg, tmp)
                decoded += 1
                if got != want:
                    fail(f"{pdf.name} page {pg}: QR {got}, expected {want}")
        runs = [(personalized, k * per, tid) for k, tid in enumerate(ids)]
        runs += [(pdf, 0, pdf.stem.split("-", 1)[1]) for pdf in single]
        for pdf, base, tid in runs:
            if pdf == personalized and (base + 1) % 2 != 1:
                fail(f"{tid}: cover on page {base + 1}, an even page")
            for k, what in enumerate(layout, base + 1):
                want, got = wanted(tid, what), decode_qr(pdf, k, tmp)
                decoded += 1
                if got != want:
                    fail(f"{pdf.name} page {k} ({tid} {what}): QR {got}, expected {want}")
            if (base + 3) % 2 != 1:
                fail(f"{tid}: graded copy starts on page {base + 3}, an even page")
        print(f"  {decoded} pages decoded")

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
                    fail(f"{label} page {pg}: the id strip is not empty in a MASTER build")
                # The band paginate.tex whites out: only the centred page
                # number may be there, and it is not ours.
                for x0, x1 in [(0, page_w / 2 - 40), (page_w / 2 + 40, page_w)]:
                    if p.darkest(x0, BAND[0], x1 - x0, BAND[1] - BAND[0]) < WHITE:
                        fail(f"{label} page {pg}: ink in the paginate.tex band")

        print("covers")
        qx, qy, qw, qh = manifest["qr"]
        Path(tmp, "c").mkdir()
        for k, tid in enumerate(ids):
            p = render(personalized, k * per + 1, f"{tmp}/c", page_h)
            got = ink_bbox(p, qx - 10, qy - 10, qw + 20, qh + 20)
            if got is None or any(abs(a - b) > 1.0 for a, b in zip(got, manifest["qr"])):
                fail(f"{tid} cover: QR ink at {got}, expected {manifest['qr']}")
            for c, box in manifest["marks"].items():
                if min(p.region(*box)) < WHITE:
                    fail(f"{tid} cover: a registration mark ({c}) is printed")
            if min(p.region(*manifest["strip"])) < WHITE:
                fail(f"{tid} cover: ink in the id strip")
            text = subprocess.run(["pdftotext", "-f", str(k * per + 1), "-l", str(k * per + 1),
                                   str(personalized), "-"], capture_output=True, text=True,
                                  check=True).stdout
            if "Remove this sheet before turning in. Do not scan it." not in " ".join(text.split()):
                fail(f"{tid} cover: no remove-before-scanning line")
            if f"ID: {tid}" not in text:
                fail(f"{tid} cover: no tracking id")
        print(f"  {len(ids)} covers checked")

        print("personalized copies")
        sx, sy, sw, sh = manifest["strip"]
        Path(tmp, "s").mkdir()
        for k, tid in enumerate(ids):
            for off, what in enumerate(layout):
                page = k * per + 1 + off
                if what in ("back", "pad"):
                    p = render(personalized, page, f"{tmp}/s", page_h)
                    if min(p.px) < WHITE:
                        fail(f"{tid} {what} page {page}: not blank")
                    continue
                if what == "cover":
                    continue
                pg = what
                p = render(personalized, page, f"{tmp}/s", page_h)
                if strip_text(personalized, page, manifest["strip"], page_h) != f"ID: {tid}":
                    fail(f"{tid} page {pg}: strip reads "
                         f"{strip_text(personalized, page, manifest['strip'], page_h)!r}, "
                         f"expected 'ID: {tid}'")
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
        print(f"  {len(ids)} runs x {per} pages checked")

    if failures:
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("\nall build checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
