# math-shared

Shared LaTeX and build code for the packet-based courses (Algebra 2, AP
Statistics, Precalculus, SAAR). The plan is in
[grading-system-design.md](grading-system-design.md).

Stage 1 is the build side of grading. It adds only new files, and the
per-course style packages stay where they are:

| File | What it does |
| --- | --- |
| `grading.sty` | `\gradedblank` answer boxes, registration marks, page QR codes, the name strip, and the `.grading` output |
| `grading.mk` | Make targets for the blank, the key, `manifest.json`, and one personalized copy per student |
| `scripts/manifest.py` | Turns a `.grading` file into `manifest.json`, and checks a key against its blank |
| `scripts/roster_import.py` | Turns a Blackbaud Course Roster export into `roster-map.csv` |
| `scripts/roster_tex.py` | Reads `roster-map.csv` for `grading.mk` (tracking id and TeX-safe printed name) |
| `examples/` | A sample exit ticket with one item of each type, its key, a rubric, and an invented three-student roster |
| `tests/` | `make test` |

## Requirements

- TeX Live with `xelatex`, `latexmk`, `zref` and `qrcode` (a full TeX Live has
  all of them). `grading.sty` needs LaTeX 2022-06 or later.
- poppler: `pdfunite`, `pdfinfo`, `pdftoppm`. The course builds already use these.
- Python 3.9+ and `xlrd` (`pip install xlrd`) to read the `.xls` roster export.
- For `make test`: `zbarimg` (`brew install zbar`), or the Python
  `zxing-cpp` and Pillow packages.

## Adding it to a course

```sh
git submodule add https://github.com/code-layne/math-shared math-shared
```

Put the submodule at the project root, not under `shared/`. `lesson.mk`
searches `$(PROJECT_ROOT)/shared//` recursively, and `math-shared/examples`
holds `main.tex` files. kpathsea finds a file on `TEXINPUTS` before it looks
in the current directory, so with the submodule under `shared/`, a component
build could compile an example's `main.tex` instead of its own. Add the
submodule directory non-recursively:

```make
TEXINPUTS := $(PROJECT_ROOT)/shared//:$(PROJECT_ROOT)/math-shared:
```

`grading.mk` builds with `.` and the `math-shared` directory ahead of the
course's `TEXINPUTS`.

Then load the package in the course article preamble, or in a single
component:

```latex
\usepackage{grading}
\gradingassignment{alg2-u3-l1-et}   % required: the id in every QR code
\gradingcourse{algebra_2}           % optional: the "course" field of the manifest
```

The course key package switches on key mode with one line. It must come after
`grading` is loaded:

```latex
% algebra2-key.sty
\RequirePackage{grading}
\gradingkeytrue
```

`\usepackage[key]{grading}` does the same thing. The flag is read each time a
box is drawn, so it can be set anywhere in the preamble.

## grading.sty

### `\gradedblank[keys]{width}{height}`

```latex
\gradedblank[id=et2, type=short, points=2, answer={3/2}]{1.5in}{0.5in}
```

This draws a bordered box exactly `width` × `height`, centered vertically on
the line it sits in. It works inline, inside `enumerate` items, and inside
`tabular` cells. Write the same line in the blank and in the key. The blank
leaves the box empty. The key prints the answer in `keyred` (or dark red if
the course has no `keyred` color) and shrinks the answer to fit if it has to.
The box never changes size, so the key keeps every line and page break of the
blank.

| Key | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Unique within the document, e.g. `et2`. Two items with the same id are an error. |
| `type` | yes | `choice`, `short` or `rubric` |
| `points` | yes | A number |
| `answer` | not for `rubric` | The machine answer, written to the manifest as typed (`3/2`, `D`, `-2, 2`, `reject H0`) |
| `check` | `short` only | `expression` (default), `numeric`, `set`, `text` |
| `tolerance` | no | For `check=numeric` |
| `rubric` | no | Rubric path relative to the lesson directory. Default `rubrics/<assignment>-<id>.yaml` |
| `display` | no | What the key prints when it should differ from `answer`, e.g. a model response for a rubric item |

By default the key prints `short` answers in math mode (`$3/2$`), except
`check=text`. `choice` answers print as text. A `rubric` item prints only its
`display`, as a paragraph.

Each box's lower-left and upper-right corners are saved with `zref-savepos`,
along with the absolute page. Positions come from the previous LaTeX run, so
build with `latexmk`. It reruns until the positions settle. A build with
missing positions warns `Rerun to get them right`, and `manifest.py` refuses
its output.

### Page furniture

The `shipout/background` hook draws the following on every page. Coordinates
are in PDF points from the lower-left corner of a letter page:

| Element | Box `[x, y, w, h]` | Where |
| --- | --- | --- |
| Registration marks: solid 12bp squares | `[21, 764, 12, 12]`, `[579, 764, 12, 12]`, `[21, 60, 12, 12]`, `[579, 60, 12, 12]` | Centered in the left and right margins. The top pair sits in the top margin. The bottom pair sits above the bottom margin. |
| QR code, 32bp, level M | `[566, 720, 32, 32]` | Right margin, under the top-right mark, 8bp clear of the text block |
| Name strip | `[54, 756, 504, 26]` | Top margin, above the text block |

None of these touch the text block (0.75in sides, 0.6in top, 0.75in bottom)
or the band `shared/paginate.tex` whites out (10pt–42pt above the bottom
edge). The bottom marks start at 60bp, and `grading.sty` stops with an error
if they are moved below 44pt.

- The QR code encodes `assignment|page|trackingid`, e.g.
  `alg2-u3-l1-et|2|K7QM2P`. `page` is the component's own page number, the
  same numbering as `page` in the manifest. It is not the packet-wide number
  `paginate.tex` prints.
- The tracking id is `\GradingStudentID` when that macro is defined, and
  `MASTER` otherwise.
- The name strip prints `\GradingStudentName` when it is defined, and is
  empty otherwise. An ordinary `make student` defines neither, so it builds
  as before, with `MASTER` QR codes and an empty strip.
- The name is set in 11pt bold sans, scaled down if it would overrun the
  strip. Ingest blanks the whole strip rectangle, which is recorded in the
  `.grading` file and in `manifest.json`.

Every position is a length you can reset after loading the package:
`\gradingmarksize`, `\gradingmarkinset`, `\gradingmarktop`,
`\gradingmarkbottom`, `\gradingqrsize`, `\gradingqrinset`, `\gradingqrtop`,
`\gradingstripleft`, `\gradingstripright`, `\gradingstriptop`,
`\gradingstripheight` and `\gradingboxrule`. The box's vertical centre is the
macro `\gradingboxcenter` (default `0.25em`), and the strip's font is
`\gradingstripfont`. The recorded positions follow whatever you set.

### `\jobname.grading`

The `.grading` file is written next to the PDF and has one JSON object per
line. (XeTeX writes a tab character as the text `^^I`, so a tab-separated
file wouldn't survive.) It holds:

```
{"kind":"meta","format":1,"course":"example","student":"MASTER","key":false,"pages":2,"paper":[612,792]}
{"kind":"strip","box":[54,756,504,26]}
{"kind":"mark","corner":"tl","box":[21,764,12,12]}      … tr, bl, br
{"kind":"qr","box":[566,720,32,32]}
{"kind":"item","assignment":"sample-u0-l1-et","id":"et2","type":"short","points":2,"answer":"3/2","check":"expression","page":1,"box":[450,500.11,108,36]}
```

Each graded item gets one `item` line. Boxes are in PDF points (bp) from the
lower-left corner, measured to the outside of the border. The file never
contains a student name.

## scripts/manifest.py

```sh
scripts/manifest.py write build/blank/main.grading -o manifest.json [--course algebra_2] [--lesson-dir unit03/lesson01]
scripts/manifest.py check manifest.json key-manifest.json
```

`write` produces the format in the design doc: `assignment`, `course`,
`pages`, and `questions`, each with `id`, `type`, `points`, `answer`,
`check`, `rubric`, `page` and `box`. It also adds what ingest needs: `paper`,
`strip`, `marks`, `qr`, and `key` (whether it was built in key mode). With
`--lesson-dir`, it warns when a rubric file is missing.

`check` exits 1 if an item is missing from either manifest, or if any item's
id, type, points, answer or check differs between the blank and the key. A
box that moved, or a different page count, only produces a warning. Scans are
aligned to the blank's layout.

## scripts/roster_import.py

```sh
scripts/roster_import.py ~/Downloads/CourseRoster.xls ~/Rosters/algebra2/ --section "Algebra 2 - A"
```

The input is the Course Roster export: class page, Roster, Run Roster/Student
Reports, Course Roster, Export Data to Excel. The importer reads real `.xls`
files, and also the HTML or SpreadsheetML files Blackbaud sometimes saves
under an `.xls` name. It finds the name column, `Last, First (Preferred)
'YY`, by its format, skips the continuation rows for extra parents, and keeps
only the legal name, preferred name and class year. Parent names, emails,
phones and every other column are discarded. If there's no parenthesised
preferred name, the preferred name is the first-name field as written.

The output is `roster-map.csv`:

```
tracking_id,legal_name,preferred_name,class_year,section
K7QM2P,"Example, Avery Jordan",Avery,2028,Algebra 2 - A
```

- New students get a random six-character id from
  `ABCDEFGHJKMNPQRSTUVWXYZ23456789`, which leaves out 0, O, 1, I and L.
- On re-import, students are matched by legal name (ignoring case and spacing),
  so existing ids never change. Preferred name, class year and section are
  updated.
- A student missing from the new export stays in the map and is reported.
- Rows are sorted by section, then last name, which is gradebook order.
  `grading.mk` builds in that order.
- The file is written atomically with mode 600.

The script refuses to write anywhere inside a git work tree, so
`roster-map.csv` cannot end up in a course repository. Keep it in its own
folder, e.g. `~/Rosters/algebra2/`. The `.gitignore` here also ignores
`roster-map.csv`, except the invented `examples/roster-map.csv`.

## grading.mk

Include it from a course Makefile, or run it with `make -f`. It works on one
component directory at a time:

```sh
# blank + key, manifest.json, key-manifest.json, and the blank/key check
make -f math-shared/grading.mk grading-manifest COMPONENT=unit03/lesson01/exit_ticket \
     TEXINPUTS=$PWD/shared//:

# one copy per student, joined in roster order
make -f math-shared/grading.mk grading-personalized COMPONENT=unit03/lesson01/exit_ticket \
     ROSTER=~/Rosters/algebra2/roster-map.csv TEXINPUTS=$PWD/shared//:

# a lost packet or a late joiner
make -f math-shared/grading.mk grading-student STUDENT=K7QM2P COMPONENT=… ROSTER=…
```

| Target | Output, under `GRADING_OUT` |
| --- | --- |
| `grading-blank` | `blank/main.pdf`, `blank/main.grading`: the ordinary MASTER build |
| `grading-key` | `key/main.pdf`, `key/main.grading` from `KEY_COMPONENT` |
| `grading-manifest` | `manifest.json` from the blank. If the key exists, also `key-manifest.json` and `manifest.py check` |
| `grading-personalized` | `students/<id>.pdf` for each student, and `personalized.pdf` joined with `pdfunite` in roster order |
| `grading-student` | `student-<STUDENT>.pdf` |
| `grading-clean` | Removes `GRADING_OUT` |

| Variable | Default |
| --- | --- |
| `COMPONENT` | Required. A directory with `main.tex`. |
| `KEY_COMPONENT` | `$(COMPONENT)_key` |
| `ROSTER` | Required by the personalized targets |
| `SECTION` | All sections |
| `STUDENT` | Required by `grading-student` |
| `GRADING_OUT` | `target/grading/<component name>` |
| `TEXINPUTS` | The course's search path |

Each student is one `latexmk -xelatex` run in the component directory:

```
latexmk -xelatex -jobname=K7QM2P \
  -usepretex='\def\GradingStudentID{K7QM2P}\def\GradingStudentName{Maggie Sample}' main.tex
```

latexmk runs this as `xelatex … "\def…\input{main.tex}"`. Names are passed as
TeX in which every character except `[A-Za-z0-9 .,-]` is written as
`{\char<n>}`. Apostrophes, accents and shell metacharacters therefore never
reach the shell or latexmk unquoted.

Personalized PDFs and their LaTeX logs contain student names. Keep
`GRADING_OUT` inside the ignored `target/` directory.

## make test

```sh
pip install xlrd      # plus xlwt, only to regenerate tests/fixtures
make test
```

- `test-python` runs the unit tests. The roster import tests use invented
  `.xls` and HTML exports with parent continuation rows, check re-import id
  stability, and check that the git guard refuses inside a work tree. The
  manifest tests cover the format and every way `check` can fail.
- `test-build` builds the sample blank and key, writes both manifests and
  checks them, builds the three personalized copies and one single-student
  copy, then runs `tests/check_build.py`, which:
  - checks that the blank, the key and every copy have the same page count;
  - decodes the QR code on every page with zbarimg, expecting `MASTER` for
    the blank and the key and the roster's ids, in order, for the joined PDF;
  - renders each page and samples pixels: each manifest box's four borders
    are dark, its inside is empty in the blank and inked in the key, each
    registration mark is solid where recorded, and the QR code is present;
  - checks that nothing reaches the text block or the paginate.tex band;
  - checks that the strip is empty in the blank and holds a name in each copy;
  - compares each personalized page with the blank page pixel for pixel
    outside the strip and the QR code.

## Notes

- The design doc sketches a `gradedquestion` environment with `\answerbox`.
  Stage 1 implements the single macro `\gradedblank`, as briefed. The
  environment can wrap it later without changing the `.grading` format.
- `\gradedblank` works inside `tabularx` cells and `tcolorbox` boxes, which
  typeset their contents more than once to measure them. A repeat with the
  same keys is treated as one of those trial passes. The same id with
  different keys is an error. An item actually printed twice is also an
  error: each shipped box writes a marker to the aux file, and the next run
  counts them.
- The QR code is computed in TeX by the `qrcode` package, which costs a
  fraction of a second per page. That adds up across a class set of long
  packets.
