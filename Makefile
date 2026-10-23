# math-shared — make test builds the sample component end to end and checks it.
# See README.md. grading.mk is the file courses include; this Makefile only
# drives it against examples/.

PYTHON   ?= python3
TEST_OUT := build/test

.PHONY: test test-python test-build clean

test: test-python test-build

test-python:
	$(PYTHON) -m unittest discover -s tests -t . -v

# The sample: blank + key + manifests + check, three covers and personalized
# copies, one single-student copy, then the QR / pixel / page-order checks and
# the name grep. Last, a document that still defines \GradingStudentName must
# build with a warning and without printing the name.
LEGACY_PRETEX := \def\GradingStudentID{K7QM2P}\def\GradingStudentName{Legacy Testname}
test-build:
	rm -rf $(TEST_OUT)
	$(MAKE) --no-print-directory -f grading.mk grading-manifest grading-personalized \
	    COMPONENT=examples/exit_ticket ROSTER=examples/roster-map.csv \
	    GRADING_OUT=$(TEST_OUT) TEXINPUTS=$(CURDIR)/examples/shared:
	$(MAKE) --no-print-directory -f grading.mk grading-student STUDENT=H3NR8V \
	    COMPONENT=examples/exit_ticket ROSTER=examples/roster-map.csv \
	    GRADING_OUT=$(TEST_OUT) TEXINPUTS=$(CURDIR)/examples/shared:
	$(PYTHON) tests/check_build.py $(TEST_OUT) examples/roster-map.csv
	$(PYTHON) scripts/check_names.py $(TEST_OUT) examples/roster-map.csv
	cd examples/exit_ticket && TEXINPUTS=.:$(CURDIR):$(CURDIR)/examples/shared: \
	    latexmk -xelatex -interaction=nonstopmode -halt-on-error -jobname=legacy \
	    -usepretex='$(LEGACY_PRETEX)' -outdir=$(CURDIR)/$(TEST_OUT)/legacy main.tex > /dev/null
	grep -q 'GradingStudentName is defined but ignored' $(TEST_OUT)/legacy/legacy.log
	! pdftotext $(TEST_OUT)/legacy/legacy.pdf - | grep -q Testname
	pdftotext $(TEST_OUT)/legacy/legacy.pdf - | grep -q 'ID: K7QM2P'

clean:
	rm -rf build
