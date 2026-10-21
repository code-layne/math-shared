# Stage 2 vote: box environments

`vote.html` shows every environment from the four courses' `<prefix>-boxes.sty`
side by side, one section per environment, and saves a choice for each to
`votes.json`. Open it from a local checkout (it reads the pictures in `img/`).

- Each picture is the same sample (`samples/<name>.tex`) compiled with that
  course's own `-article`, `-key` and `-boxes` packages.
- Every color a course defines is remapped by lightness to one neutral palette
  (dark gray frames, pale gray fills, red answer ink), so the pictures differ only
  in structure. The page lists each definition's own colors under its picture.
- The green or amber tag compares the definitions after removing comments,
  color names and each course's internal prefix (`alg@`, `pc@`, `saar@`, `aps@`).
- Environments that are missing from some courses are listed in their own section.
- Choices are kept in the browser; **Download votes.json** saves them, and
  **Load votes.json** reads a saved file back. Each choice is a course key
  (`algebra_2`, `precalculus`, `stats_analysis_algebraic_reasoning`,
  `advanced_statistics`) or `needs-discussion`, with an optional note.

## Rebuilding

Needs `pdflatex` (with tcolorbox, xltabular, pgfplots, cm-super), `pdftoppm`,
`pdfinfo` and Pillow. Clone the four course repos into one directory, then:

    python3 vote/build.py --courses path/to/clones

This rewrites `img/` and `vote.html` from `template.html`. Edit the template
and samples, not `vote.html`.
