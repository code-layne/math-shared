# Grading system design

Draft, October 21, 2026. Covers the packet-based courses: Algebra 2, AP Statistics, Precalculus, and SAAR. The first scope is warm-up and exit ticket sections.

## Goal

I scan a stack of completed packets, run one command, and get back a score and a feedback sheet for each student, plus a report for me on what the class missed. Nothing reaches a student until I release it.

## Decisions so far

- Grading runs as a Python script on my Mac that calls the Claude API.
- Each run produces a score report listing every student with a score for each assignment. I enter the scores in Blackbaud myself. No Blackbaud API access is assumed.
- Late work is graded with no deduction. The date received is recorded and never changes the score.
- Code decides correctness wherever it can. The model reads handwriting and applies rubrics. It does not decide whether a math answer is right.
- I review every disagreement and every rubric score until the eval set shows a question type can be trusted.
- An AP Statistics free-response question counts in the gradebook as its AP score, out of 4 points. Its rubric is written by us in College Board style, and official College Board scoring guidelines are never committed, since the course repos are public. Every total that lands on a half point comes to me to round up or down (October 2026).
- Chatham Hall allows student work to go to the API as long as it carries no personal information. Only answer-box crops are sent, each keyed by tracking ID. No name, roster, cover sheet, or full page image ever leaves my Mac. Students are told to write their names only on the lesson cover or a test's name sheet, and no automated check for a name inside an answer box is planned.

## Student identification

Names stay out of the grading system. Each student gets a tracking ID, a random six-character code such as `K7QM2P`, drawn from letters and digits that can't be confused with each other. The ID is assigned once per student per school year and carries no part of her name.

The only place names and IDs meet is `roster-map.csv`, which holds each tracking ID with the student's legal and preferred names, section, and class year. It lives in its own folder, apart from the grading database. Two steps read it: the packet build, to print each student's name on her lesson cover or name sheet, and the final report, to put names on the scores. Everything between those two steps knows students only by tracking ID.

Every packet is personalized. The build produces one combined PDF with a separate copy for each student, printed as one collated job. Every page carries a QR code that encodes the tracking ID along with the assignment and page. Matching a scan to a student is a lookup, and a loose page or a single late page still identifies its owner.

Scanned pages go to an outside API, so a graded page carries no personal information except the tracking ID. The strip at the top of each graded page prints `ID: K7QM2P`, never a name.

Packets are still handed out by name, in one of two ways (October 2026).

- **A lesson packet** prints the student's name on the Name line of the lesson's own cover (the course compiles the cover with `\def\StudentName{…}` ahead of it, with `latexmk -g` because latexmk does not track that pretex). There is no separate name sheet. Every graded component in the packet (homework, AP Practice) is her personalized copy and starts on a fresh sheet, so she tears the graded sheets out and turns them in, and the cover with her name stays in her packet. The lesson cover is never scanned and carries no QR code. Its packet table is a contents list only: no score cells.
- **A test or quiz** starts with a separate name sheet: her preferred name in large type, her legal last name under it, the course, the assignment title, the tracking ID, and the line "Remove this sheet before turning in. Do not scan it." The sheet is removed before the test is turned in, and it is never scanned. Its QR code encodes `COVER|<assignment>|<tracking ID>` in the same position and size as a graded page's, so if a name sheet is scanned anyway, ingest reads it with the same code and discards the page before anything is stored or sent.

In the combined PDF of a test, each student's run is her name sheet, a blank page (its back), and her graded copy, padded with blank pages to an even count. In a lesson's, each student's run is her packet, paginated like the unpersonalized student packet and even. Either way every run starts on an odd page and every graded copy on a fresh sheet, so the stack can be printed duplex.

A lost packet or a student who joins mid-unit gets a single copy, with its cover or name sheet, built on demand from the same source. There is no generic copy and no handwritten-name reading.

## Pipeline

1. Build. LaTeX produces one personalized copy per student. The same build writes the answer-key PDF and a `manifest.json` that holds the same key in machine-readable form.
2. Print, hand out by name (the lesson cover, or a test's name sheet), and collect the graded sheets: torn out of a lesson packet, or a test with its name sheet removed.
3. Scan. Copier scan-to-PDF, one file per stack, pages in any order.
4. Ingest. Split pages, decode QR codes, align each page to the manifest, crop answer boxes.
5. Read. A vision call transcribes each crop.
6. Score. Code scores choice and short-answer items. A rubric call scores discussion items.
7. Verify. A second, independent call checks the first.
8. Review. A local web page shows me disagreements, blanks, low-confidence readings, and rubric scores.
9. Output. A score report by student and assignment, a feedback sheet per student, a summary PDF for me.
10. Release. I upload or print. The script never sends anything to students.

## 1. Answer keys and the manifest

The grader works from the answer keys the curriculum build already generates. When it decodes a page, the assignment ID in the QR code points to that lesson's build output under `~/Mathematics`, and the grader loads the key from there. Nothing is entered into the grader by hand.

The key comes as a machine-readable `manifest.json` written by the same build that produces the answer-key PDF, from the same LaTeX source. The key I post to Blackbaud and the key the grader uses can't drift apart, because changing an answer in the source changes both on the next build.

Graded answer boxes are marked in the LaTeX source with a macro from the shared style package:

```latex
Solve $2x - 3 = 0$.
\gradedblank[id=et2, type=short, points=2, answer={3/2}]{1.5in}{0.5in}
```

`\gradedblank` draws a bordered box and records its page and coordinates with `zref-savepos`. Each box writes a line to a `.grading` file during the build, and `manifest.py`, run by `grading.mk`, assembles those lines into the manifest:

```json
{
  "assignment": "alg2-3.4-et",
  "course": "algebra_2",
  "pages": 2,
  "questions": [
    {"id": "et1", "type": "choice", "points": 1, "answer": "C",
     "page": 1, "box": [72.0, 540.2, 43.2, 43.2]},
    {"id": "et2", "type": "short", "points": 2, "answer": "3/2",
     "check": "expression", "page": 1, "box": [72.0, 460.0, 108.0, 43.2]},
    {"id": "et3", "type": "rubric", "points": 4,
     "rubric": "rubrics/alg2-3.4-et3.yaml", "page": 2, "box": [72.0, 300.0, 432.0, 180.0]}
  ]
}
```

Boxes are in PDF points from the lower-left corner of the page, and record the size actually drawn. Choice boxes are square: the author gives the width and the height follows it. Rubric boxes are at least 2 inches tall, so a written response has room, and the key prints the model answer from the top left of the box. Short-answer boxes are drawn as written. Both rules are settings in the style package.

Short-answer items name how the answer is checked:

- `expression`: SymPy equivalence, so `3/2`, `1.5`, and `x = 3/2` all match. This is the default.
- `numeric`: a value with a tolerance, for rounded answers like a z-score or a p-value.
- `set`: an unordered set of values, for equations with more than one solution.
- `text`: normalized string match, for answers like "reject H0" or "increasing".
- `interval`: any single number inside the key's interval, for a sign chart's test value. The key is written `answer={(-inf, -1)}` or `answer={[0, 2)}`; `\infty` works too.

A matching section is a series of choice items, one per blank.

Rubrics live in YAML files next to the lesson source:

```yaml
id: et3
points: 4
task: Interpret the slope of the regression line in context.
criteria:
  - id: predicted
    points: 1
    full: Says the change is in the predicted or average y, not the actual y.
  - id: value
    points: 1
    full: Gives the slope value, 2.5.
  - id: units
    points: 1
    full: Gives units for both variables, dollars per additional hour.
  - id: context
    points: 1
    full: Names both variables in context.
examples:
  - response: "For each extra hour, pay goes up 2.5."
    scores: {predicted: 0, value: 1, units: 0, context: 1}
```

Graded examples in the rubric file are optional. Adding them is the main way to correct the model when it scores a criterion differently than I would.

### AP Statistics free-response questions

An AP Statistics free-response question (FRQ) is scored holistically from 0 to 4, the way the College Board scores it. The question is divided into sections, and each section is rated E (essentially correct), P (partially correct), or I (incorrect). E counts 1, P counts 1/2, and I counts 0, each times the section's weight. A whole-number total is the score: 4 complete, 3 substantial, 2 developing, 1 minimal, 0 inadequate. A total that falls on a half point is mine to decide: I look at the whole response and score up or down.

The parts of an FRQ are ordinary answer boxes. A `\gradedquestion` line ties them together:

```latex
\gradedquestion[id=t12, scheme=ap-stats]
(a) ... \gradedblank[id=t12a, type=rubric, question=t12]{\linewidth}{2in}
(b) ... \gradedblank[id=t12b, type=short, question=t12, answer=365, check=numeric]{1.2in}{0.4in}
```

`\gradedquestion` draws nothing and is written identically in the blank and the key, before its parts. Each part keeps its own type, which decides how its box is drawn and read, and records 0 points. The question carries the points, which are fixed at 4 for `ap-stats`. The build stops if a part names an undeclared question, a question has no parts, or a question id is declared twice with different keys.

The manifest gets a top-level `groups` list, and each part gets `"question"`:

```json
"groups": [
  {"id": "t12", "scheme": "ap-stats", "points": 4,
   "rubric": "../rubrics/apstats-u02-actual-test-t12.yaml",
   "items": ["t12a", "t12b", "t12c", "t12d", "t12e"]}
]
```

The assignment's total points are the ungrouped items' points plus 4 for each group. The rubric path defaults to `rubrics/<assignment>-<id>.yaml`, like an item's.

The rubric for an FRQ has its own shape:

```yaml
scheme: ap-stats
id: t12
points: 4
task: >-
  One-paragraph summary of the whole question.
sections:
  - id: s1
    items: [t12a, t12b]
    weight: 1
    E: >-
      What an essentially correct response includes.
    P: >-
      What earns partially correct.
    I: >-
      Optional; default "does not meet the criteria for P".
notes: >-
  Optional reader notes: common errors, what not to penalize.
```

Section weights sum to 4, every part of the question appears in at least one section, every item in a section is a part of the question, and section ids are unique. `manifest.py` checks all of this at build time. I write these rubrics myself, in College Board style, for the course's own questions. Official College Board scoring guidelines never go into a repo. The `scheme` field leaves room for an `ap-precalc` scheme later without changing the format; for now only AP Statistics is supported.

Every page carries four corner registration marks and a QR code in a fixed corner. Students show work outside the answer box. In the first scope only what is inside the box is graded.

## 2. Scanning

Copier settings: 300 dpi, grayscale, one PDF per stack, duplex if the packets are printed double-sided. The PDF goes into an inbox folder, and the script picks up everything there on the next run. A late paper is scanned the same way, alone or mixed into another stack.

## 3. Ingest

PyMuPDF renders each page at 300 dpi. zxing-cpp decodes the QR code. A page whose code starts with `COVER` is a test's name sheet that should not have been scanned: it is discarded on the spot, logged by tracking ID, and nothing from it is stored or sent. OpenCV finds the registration marks on every other page and computes the transform from the scan to manifest coordinates, which corrects skew and copier scaling. Each answer box is cropped with a small margin and saved.

A page whose QR code can't be read goes to an unplaced-pages queue in review. A second copy of a page already received for the same student is flagged, not silently replaced.

An answer box with almost no ink is marked blank without an API call. Blanks go to review as one batch to confirm, since light pencil can fall under the ink threshold.

## 4. Read

Each crop is one request. The prompt asks for an exact transcription and tells the model not to solve or correct anything. The response is JSON:

```json
{"reading": "x = 3/2", "latex": "x = \\frac{3}{2}", "confidence": "high", "illegible": false}
```

For choice items the reading is a single letter.

Responses come back through structured output, enforced by a tool schema, so the script never parses prose. Full class sets go through the Batch API. Late papers and reruns use the standard API.

## 5. Score

Choice items compare the reading to the key.

Short-answer items parse the reading and apply the check named in the manifest. A reading that won't parse goes to review with the crop, not to zero.

Rubric items get a second call that includes the rubric and the crop along with the transcription. The model returns, for each criterion, the points awarded, the words from the response that justify them, and a confidence level, plus one feedback note for the student. The answer key and rubric come first in the prompt so they are cached across the whole class.

An FRQ gets one rubric call per student, with all of the question's crops and transcriptions labelled by box id, plus the rubric. The model rates each section E, P, or I with the words that justify the rating and a confidence level, and writes one feedback note for the whole question. Code computes the total from the ratings and weights; the model never computes the score. When the total lands on a half point, the model also suggests rounding up or down, with a one-sentence reason.

Feedback names what is missing and points the student back to it with a question. It does not supply the answer. This is a default I can edit in the prompt.

Before scoring, identical normalized readings are grouped. Each group is scored once and appears in review as one item with a count.

## 6. Verify

A second call gets the crop and manifest entry along with the first call's reading and score. It does not see the first call's reasoning. It returns its own reading and either agrees or disputes.

For choice and short-answer items, a match between the two readings with high confidence on both passes without review. Anything else goes to review.

For rubric items, the second call scores each criterion independently, and every rubric item goes to review in the first phase whether or not the calls agree. Disagreements are sorted to the top.

For an FRQ, the second call rates every section from the crops and rubric without the first call's reasoning. Any section rated differently is a disagreement. Every FRQ goes to review in the first phase, with disagreements and half-point totals first. A half-point total shows the model's suggested rounding, and I choose up or down. Rulings keyed by normalized answer don't apply to FRQs.

## 7. Review

A Flask app on localhost. The queue is grouped by question, then by answer group. Each item shows the crop, the reading, the score, the evidence, and the feedback note. I can approve, fix the reading, change the score, or edit the feedback, all from the keyboard.

Every decision is saved as a ruling keyed by question and normalized answer. Later papers with the same answer, including late ones, get the ruling without coming back to me.

## 8. Outputs

Each run writes one folder named for the run date:

- `scores.pdf`, the grade report. One table per section, with students in gradebook order down the side and a column for each assignment graded in the run. A cell holds the score as points earned out of points possible, or is empty when no pages came in. A run that grades only late papers lists only those students.
- `scores.csv`, the same table for when I want it in a spreadsheet.
- `feedback-sheets.pdf`, one per section. Each student gets one sheet, in gradebook order, with her preferred name and the assignment at the top, her total score, and a row for each question with the points earned and any feedback note. I print the file and staple each sheet to the front or back of the student's packet before handing it back.
- `summary.pdf` for me: the score distribution, the miss rate for each question with the number of students behind it, the common wrong answers with counts, and the list of students with no pages received.

The report step is the only step after the build that reads `roster-map.csv`. It joins scores and feedback to names for the report and the feedback sheets. Inside the grading database the same records are keyed by tracking ID.

I enter scores in the Blackbaud gradebook myself from the report. Teachers have no grade import there, and entered grades stay hidden from students until I commit them.

## 9. Storage

One SQLite file holds assignments, received pages, readings, rulings, scores, and submission dates, all keyed by tracking ID. It holds no names.

A separate roster import reads the Course Roster report (class page, Roster, Run Roster/Student Reports, Course Roster, Export Data to Excel). The export has no student ID column, and each student is one row followed by continuation rows for additional parents. The importer keeps name and class year and discards every other column, so parent contact information is never stored anywhere. It assigns a tracking ID to each new student and writes `roster-map.csv`. A re-import matches on legal name, so a student added mid-year gets a new ID and nobody else changes.

Scans and crops stay on my Mac. What is sent off the machine comes from graded pages, which carry no name: answer-box crops carry neither name nor ID, and a whole page carries only the tracking ID. Lesson covers and name sheets are never scanned, and a name sheet scanned by mistake is discarded at ingest.

## Shared package

The grading macros live in a new public repo, `code-layne/math-shared`, added to each course as a git submodule. Stage 1 holds only new code: `grading.sty`, `cover.tex`, `grading.mk`, and the manifest and roster scripts. The existing per-course style packages stay where they are. Algebra 2 gets the submodule first.

Stage 2 moves the box environments into `math-shared`. The four courses define the same environments with implementations that have drifted apart. Each environment is rendered in all four versions side by side, I vote on which version wins, and each course keeps a small configuration file for what should differ, such as its palette and title.

The build runs as Claude Code cloud sessions, one per stage, briefed in `cloud-session-briefs.md`.

## Build order

1. Write the roster import and `roster-map.csv`. Add `\gradedblank`, registration marks, and QR codes to the style package, and add the roster loop to `lesson.mk` along with a target for a single student's copy. Write one sample Algebra 2 assignment with items of every type.
2. Build a synthetic class set: invented students, likely answers including common misconceptions, rendered in handwriting fonts and degraded like a copier scan, with a file of the correct scores. This is the first eval set. A hand-graded real class set replaces it once the system is in use.
3. Build ingest and test it against the scans of the eval set.
4. Build reading and scoring for choice and short-answer items. Compare to the hand grades.
5. Build the review page and rulings.
6. Build the outputs.
7. Add rubric scoring and verification, measured against the eval set.
8. Add late papers and the missing list.

A question type auto-passes only after it matches my hand grades with zero disagreements across at least two class sets. Rubric items stay in review until I decide otherwise.

## Open questions

None at present.
