# math-shared — make test builds the sample component end to end and checks it.
# See README.md. grading.mk is the file courses include; this Makefile only
# drives it against examples/.

PYTHON   ?= python3
TEST_OUT := build/test

.PHONY: test test-python test-build clean

test: test-python test-build

test-python:
	$(PYTHON) -m unittest discover -s tests -t . -v

# The sample: blank + key + manifests + check, three personalized copies, one
# single-student copy, then the QR / pixel / page-count checks.
test-build:
	rm -rf $(TEST_OUT)
	$(MAKE) --no-print-directory -f grading.mk grading-manifest grading-personalized \
	    COMPONENT=examples/exit_ticket ROSTER=examples/roster-map.csv \
	    GRADING_OUT=$(TEST_OUT) TEXINPUTS=$(CURDIR)/examples/shared:
	$(MAKE) --no-print-directory -f grading.mk grading-student STUDENT=H3NR8V \
	    COMPONENT=examples/exit_ticket ROSTER=examples/roster-map.csv \
	    GRADING_OUT=$(TEST_OUT) TEXINPUTS=$(CURDIR)/examples/shared:
	$(PYTHON) tests/check_build.py $(TEST_OUT) examples/roster-map.csv

clean:
	rm -rf build
