#!/usr/bin/env python3
"""Build the Stage 2 box-environment vote page.

For every environment (and the few helper commands) defined in the four
courses' <prefix>-boxes.sty, this compiles one sample page per course with the
course's own packages, swaps every course color for one neutral palette, and
rasterizes the result. It then writes vote.html, which shows the four versions
of each environment side by side and saves the choices to votes.json.

Usage:
    python3 vote/build.py --courses DIR

DIR holds clones of the four course repos (algebra_2, precalculus,
stats_analysis_algebraic_reasoning, advanced_statistics). Needs pdflatex,
pdftoppm and Pillow.
"""

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent

COURSES = [
    {"key": "algebra_2", "name": "Algebra 2", "prefix": "algebra2"},
    {"key": "precalculus", "name": "Precalculus", "prefix": "precalculus"},
    {"key": "stats_analysis_algebraic_reasoning", "name": "SAAR", "prefix": "saar"},
    {"key": "advanced_statistics", "name": "AP Statistics", "prefix": "apstats"},
]

# One vote per item. The first name in `defs` decides whether a course has the
# item; the rest are the helpers that travel with it and are compared with it.
ITEMS = [
    ("notesbox", "env", ["notesbox"]),
    ("practicebox", "env", ["practicebox"]),
    ("vocabbox", "env", ["vocabbox"]),
    ("hookbox", "env", ["hookbox"]),
    ("work", "env", ["work", "workrowsep"]),
    ("probgrid", "env", ["probgrid", "pcell"]),
    ("guidednotes", "env", ["guidednotes", "mainidea", "mainideawidth", "notesprompt", "stepnum"]),
    ("objectivebox", "env", ["objectivebox"]),
    ("learningtargetbox", "env", ["learningtargetbox"]),
    ("spiralbox", "env", ["spiralbox"]),
    ("scenariobox", "env", ["scenariobox"]),
    ("headlinebox", "env", ["headlinebox"]),
    ("blurbbox", "env", ["blurbbox"]),
    ("reflectionbox", "env", ["reflectionbox"]),
    ("extensionbox", "env", ["extensionbox"]),
    ("skillbox", "env", ["skillbox"]),
    ("fixedskillbox", "env", ["fixedskillbox"]),
    ("teachernote", "env", ["teachernote", "teachernotestyle"]),
    ("tocbox", "env", ["tocbox"]),
    ("remindbox", "env", ["remindbox"]),
    ("steptable", "env", ["steptable", "step", "steprel"]),
    ("writespace", "cmd", ["writespace"]),
    ("labelbox", "cmd", ["labelbox"]),
    ("componenttable", "cmd", ["componenttable"]),
    ("boxguard", "cmd", ["boxguard"]),
]

# The neutral palette. Every color a course defines is mapped to one of these
# by its lightness, so a dark frame stays dark and a pale fill stays pale. All
# frame and accent colors share one dark: a finer split would make the same
# color name (greenacc, say) land on different grays in different courses.
NEUTRAL = {
    "dark": "3B4048",   # every frame, title and accent color
    "mid": "9AA1AB",    # write lines (linegray)
    "tint": "D4D7DC",   # mid tints
    "bg": "F2F3F5",     # pale fills
    "key": "CC0000",    # answer ink
}


def strip_comments(text):
    return re.sub(r"(?<!\\)%.*", "", text)


def consume(text, pos, nbraces):
    """Skip [..] and {..} groups from pos until nbraces brace groups are read."""
    seen = 0
    n = len(text)
    while pos < n and seen < nbraces:
        c = text[pos]
        if c.isspace():
            pos += 1
        elif c in "[{":
            close = "]" if c == "[" else "}"
            depth = 0
            while pos < n:
                ch = text[pos]
                if ch == "\\":
                    pos += 2
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                if close == "]" and ch == "]" and depth == 0:
                    pos += 1
                    break
                if close == "}" and ch == "}" and depth == 0:
                    pos += 1
                    break
                pos += 1
            if c == "{":
                seen += 1
        elif c == "*":
            pos += 1
        else:
            break
    return pos


DEF_PATTERNS = [
    (re.compile(r"\\newtcolorbox\{(\w+)\}"), 1),
    (re.compile(r"\\NewDocumentEnvironment\{(\w+)\}"), 3),
    (re.compile(r"\\newenvironment\{(\w+)\}"), 2),
    (re.compile(r"\\newcommand\{?\\(\w+)\}?"), 1),
    (re.compile(r"\\tcbset\{(\w+)/\.style"), None),
    (re.compile(r"\\newlength\{\\(\w+)\}.*"), 0),
]


def parse_defs(text):
    """Return {name: source} for every definition in a comment-stripped file."""
    defs = {}
    for pat, nbraces in DEF_PATTERNS:
        for m in pat.finditer(text):
            name = m.group(1)
            if nbraces is None:  # \tcbset{name/.style={...}}
                end = consume(text, m.start() + len("\\tcbset"), 1)
            elif nbraces == 0:
                end = m.end()
            else:
                end = consume(text, m.end(), nbraces)
            src = text[m.start():end]
            src = re.sub(r"\n\s*\n+", "\n", src).strip()
            defs.setdefault(name, src)
    return defs


def luminance(hexcode):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexcode[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def parse_palette(text):
    """Return {color name: role} for every color the course's colors.sty defines."""
    text = strip_comments(text)
    values = {}
    for m in re.finditer(r"\\(definecolor\{(\w+)\}\{HTML\}\{(\w{6})\}|colorlet\{(\w+)\}\{(\w+)\})", text):
        if m.group(2):
            values[m.group(2)] = m.group(3)
        else:
            values[m.group(4)] = values.get(m.group(5), "FFFFFF")
    roles = {}
    for name, val in values.items():
        if name in ("keyred", "linegray"):
            roles[name] = "key" if name == "keyred" else "mid"
            continue
        lum = luminance(val)
        roles[name] = "bg" if lum > 0.8 else "tint" if lum > 0.5 else "dark"
    return roles


def normalize(src, prefix_tok, roles):
    """Code with comments, the internal prefix and color names factored out."""
    s = src.replace(prefix_tok + "@", "P@")
    for name, role in sorted(roles.items(), key=lambda kv: -len(kv[0])):
        s = re.sub(r"(?<![A-Za-z@\\])" + name + r"(?![A-Za-z@])", "<" + role + ">", s)
    return re.sub(r"\s+", " ", s).strip()


def harness(course, info, sample_body):
    neutral = "\n".join(
        f"\\definecolor{{{name}}}{{HTML}}{{{NEUTRAL[role]}}}"
        for name, role in info["roles"].items())
    tok = info["work_prefix"]
    return rf"""\documentclass[10pt]{{article}}
\usepackage{{{course['prefix']}-article}}
\usepackage{{{course['prefix']}-key}}
% Neutral palette: every course color, remapped by lightness.
{neutral}
\definecolor{{sampledark}}{{HTML}}{{{NEUTRAL['dark']}}}
\definecolor{{samplebg}}{{HTML}}{{{NEUTRAL['bg']}}}
\makeatletter
\newcommand{{\SampleWorkHidden}}{{\{tok}@workvisiblefalse}}
\newcommand{{\SampleWorkShown}}{{\{tok}@workvisibletrue}}
\makeatother
\newif\ifSampleHasProbgridStar
{"\\SampleHasProbgridStartrue" if info["probgrid_star"] else ""}
\pagestyle{{empty}}
\begin{{document}}
{sample_body}
\end{{document}}
"""


def render(course, info, item_id, sample_body, workdir, out_png):
    tex = workdir / f"{item_id}.tex"
    tex.write_text(harness(course, info, sample_body))
    env = {"TEXINPUTS": f"{info['shared']}//:", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    proc = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex.name],
        cwd=workdir, env=env, capture_output=True, text=True)
    pdf = workdir / f"{item_id}.pdf"
    if proc.returncode != 0 or not pdf.exists():
        log = (workdir / f"{item_id}.log").read_text(errors="replace")
        err = [l for l in log.splitlines() if l.startswith("!")][:3]
        return {"ok": False, "error": " ".join(err) or "pdflatex failed"}
    pages = int(re.search(r"Pages:\s+(\d+)",
                          subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout).group(1))
    stem = workdir / f"{item_id}-r"
    subprocess.run(["pdftoppm", "-r", "150", "-f", "1", "-l", "1", "-png", "-singlefile",
                    str(pdf), str(stem)], check=True)
    img = Image.open(f"{stem}.png").convert("RGB")
    bbox = ImageChops.difference(img, Image.new("RGB", img.size, "white")).getbbox()
    if bbox:
        pad = 24
        img = img.crop((max(bbox[0] - pad, 0), max(bbox[1] - pad, 0),
                        min(bbox[2] + pad, img.width), min(bbox[3] + pad, img.height)))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.quantize(colors=96, method=Image.Quantize.MEDIANCUT).save(out_png, optimize=True)
    return {"ok": True, "pages": pages, "w": img.width, "h": img.height}


def git_rev(path):
    return subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--courses", required=True, type=Path,
                    help="directory holding the four course clones")
    args = ap.parse_args()

    infos = {}
    for c in COURSES:
        shared = (args.courses / c["key"] / "shared").resolve()
        boxes = (shared / f"{c['prefix']}-boxes.sty").read_text()
        code = strip_comments(boxes)
        defs = parse_defs(code)
        work_prefix = re.search(r"\\newif\\if(\w+)@workvisible", code).group(1)
        pg = re.search(r"\\NewDocumentEnvironment\{probgrid\}\{(\w)", code)
        infos[c["key"]] = {
            "shared": shared,
            "defs": defs,
            "roles": parse_palette((shared / f"{c['prefix']}-colors.sty").read_text()),
            "work_prefix": work_prefix,
            "probgrid_star": bool(pg and pg.group(1) == "s"),
            "lines": boxes.count("\n"),
            "rev": git_rev(args.courses / c["key"]),
        }

    img_dir = HERE / "img"
    if img_dir.exists():
        shutil.rmtree(img_dir)
    covered = {d for _, _, defs in ITEMS for d in defs}
    items_out = []
    with tempfile.TemporaryDirectory() as tmp:
        for item_id, kind, names in ITEMS:
            sample_path = HERE / "samples" / f"{item_id}.tex"
            sample = sample_path.read_text() if sample_path.exists() else None
            versions = {}
            norm_groups = {}
            for c in COURSES:
                info = infos[c["key"]]
                if names[0] not in info["defs"]:
                    continue
                src = "\n".join(info["defs"][n] for n in names if n in info["defs"])
                norm = normalize(src, info["work_prefix"], info["roles"])
                group = norm_groups.setdefault(norm, len(norm_groups))
                v = {"source": src, "group": group, "missing_helpers": [n for n in names if n not in info["defs"]]}
                if sample is not None:
                    wd = Path(tmp) / c["key"]
                    wd.mkdir(exist_ok=True)
                    png = img_dir / item_id / f"{c['key']}.png"
                    r = render(c, info, item_id, sample, wd, png)
                    v.update(r)
                    if r["ok"]:
                        v["img"] = f"img/{item_id}/{c['key']}.png"
                    print(f"{item_id:18} {c['key']:36} {'ok' if r['ok'] else 'FAIL ' + r['error']}")
                versions[c["key"]] = v
            items_out.append({"id": item_id, "kind": kind, "defs": names,
                              "rendered": sample is not None, "versions": versions,
                              "groups": len(norm_groups)})

    # Anything defined in a -boxes.sty that no item covers is listed on the page
    # so nothing gets silently left out of the vote.
    uncovered = {}
    for c in COURSES:
        for n in infos[c["key"]]["defs"]:
            if n not in covered:
                uncovered.setdefault(n, []).append(c["key"])

    data = {
        "courses": [{"key": c["key"], "name": c["name"], "prefix": c["prefix"],
                     "rev": infos[c["key"]]["rev"], "lines": infos[c["key"]]["lines"],
                     "colors": infos[c["key"]]["roles"]}
                    for c in COURSES],
        "items": items_out,
        "uncovered": uncovered,
        "neutral": NEUTRAL,
    }
    template = (HERE / "template.html").read_text()
    payload = json.dumps(data, indent=None).replace("</", "<\\/")
    (HERE / "vote.html").write_text(template.replace("/*__DATA__*/null", payload))
    print("wrote", HERE / "vote.html")


if __name__ == "__main__":
    main()
