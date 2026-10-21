# grading.mk — personalized copies and manifests for a graded component.
#
# Include it from a course Makefile (after lesson.mk, if any), or run it
# directly with make -f. It works on ONE component directory at a time:
#
#   make -f math-shared/grading.mk grading-manifest \
#        COMPONENT=unit03/lesson01/exit_ticket
#   make -f math-shared/grading.mk grading-personalized \
#        COMPONENT=unit03/lesson01/exit_ticket ROSTER=~/Rosters/alg2/roster-map.csv
#
# Variables:
#   COMPONENT      the component directory holding main.tex (required)
#   KEY_COMPONENT  its key; default $(COMPONENT)_key, used when it exists
#   ROSTER         roster-map.csv (required by the personalized targets)
#   SECTION        build only this section of the roster (optional)
#   STUDENT        tracking id, for grading-student
#   GRADING_OUT    output directory; default target/grading/<component name>
#   TEXINPUTS      the course's TeX search path, e.g. $(PROJECT_ROOT)/shared//:
#                  The build searches the component directory first, then this
#                  directory (non-recursively: math-shared/examples holds
#                  main.tex files a recursive path would find), then TEXINPUTS.
#
# Targets:
#   grading-blank         the ordinary build (QR tracking id MASTER, empty
#                         name strip) -> $(GRADING_OUT)/blank/main.pdf
#   grading-key           the key build -> $(GRADING_OUT)/key/main.pdf
#   grading-manifest      blank build -> $(GRADING_OUT)/manifest.json; if the
#                         key exists, also key-manifest.json and the check
#                         that both agree on every item
#   grading-personalized  one copy per student, in roster order, joined into
#                         $(GRADING_OUT)/personalized.pdf
#   grading-student       one student's copy -> $(GRADING_OUT)/student-$(STUDENT).pdf
#   grading-clean         remove $(GRADING_OUT)
#
# Personalized builds put student names in their PDFs and LaTeX logs. Keep
# GRADING_OUT inside an ignored build directory (target/ is ignored in every
# course repo) and never commit it.

GRADING_ROOT     := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
GRADING_SCRIPTS  := $(GRADING_ROOT)/scripts
GRADING_PYTHON   ?= python3

COMPONENT        ?=
KEY_COMPONENT    ?= $(patsubst %/,%,$(COMPONENT))_key
ROSTER           ?=
SECTION          ?=
STUDENT          ?=
GRADING_OUT      ?= target/grading/$(notdir $(patsubst %/,%,$(COMPONENT)))

GRADING_TEXINPUTS = .:$(GRADING_ROOT):$(TEXINPUTS)
GRADING_LATEXMK  ?= latexmk -xelatex -interaction=nonstopmode -halt-on-error -file-line-error

GR_COMP     = $(abspath $(COMPONENT))
GR_KEY      = $(abspath $(KEY_COMPONENT))
GR_HAS_KEY  = $(wildcard $(GR_KEY)/main.tex)
GR_OUT      = $(abspath $(GRADING_OUT))
GR_STUDENTS = $(GR_OUT)/students

.PHONY: grading-blank grading-key grading-manifest grading-personalized \
        grading-student grading-clean grading-need-component grading-need-roster

grading-need-component:
	@test -n "$(COMPONENT)" || { echo "grading.mk: set COMPONENT=<component directory>"; exit 1; }
	@test -f "$(GR_COMP)/main.tex" || { echo "grading.mk: no main.tex in $(GR_COMP)"; exit 1; }

grading-need-roster:
	@test -n "$(ROSTER)" || { echo "grading.mk: set ROSTER=<path to roster-map.csv>"; exit 1; }
	@test -f "$(ROSTER)" || { echo "grading.mk: $(ROSTER) does not exist"; exit 1; }

# $1 = source directory, $2 = output directory, $3 = extra latexmk arguments,
# $4 = log file. Fails loudly with the first TeX errors.
define grading-latexmk
	@mkdir -p "$2"
	@cd "$1" && TEXINPUTS="$(GRADING_TEXINPUTS)" $(GRADING_LATEXMK) $3 \
	    -outdir="$2" main.tex > "$4" 2>&1 \
	  || { echo "!  LaTeX failed in $1 — see $4"; \
	       grep -hE "^(!|l\.|.*:[0-9]+: )" "$2"/*.log | head -10; exit 1; }
endef

grading-blank: grading-need-component
	$(call grading-latexmk,$(GR_COMP),$(GR_OUT)/blank,,$(GR_OUT)/blank.out)
	@echo "✓  blank   → $(GR_OUT)/blank/main.pdf"

grading-key: grading-need-component
	@test -f "$(GR_KEY)/main.tex" || { echo "grading.mk: no key at $(GR_KEY)"; exit 1; }
	$(call grading-latexmk,$(GR_KEY),$(GR_OUT)/key,,$(GR_OUT)/key.out)
	@echo "✓  key     → $(GR_OUT)/key/main.pdf"

grading-manifest: grading-blank $(if $(GR_HAS_KEY),grading-key)
	@$(GRADING_PYTHON) "$(GRADING_SCRIPTS)/manifest.py" write "$(GR_OUT)/blank/main.grading" \
	    -o "$(GR_OUT)/manifest.json" --lesson-dir "$(dir $(GR_COMP))"
ifneq ($(GR_HAS_KEY),)
	@$(GRADING_PYTHON) "$(GRADING_SCRIPTS)/manifest.py" write "$(GR_OUT)/key/main.grading" \
	    -o "$(GR_OUT)/key-manifest.json" --lesson-dir "$(dir $(GR_COMP))"
	@$(GRADING_PYTHON) "$(GRADING_SCRIPTS)/manifest.py" check \
	    "$(GR_OUT)/manifest.json" "$(GR_OUT)/key-manifest.json"
endif

# One personalized compile: -jobname is the tracking id, and the pretex is
#   \def\GradingStudentID{ID}\def\GradingStudentName{NAME}\input{main.tex}
# Runs in the shell with $$id and $$name set; NAME comes from roster_tex.py,
# which encodes everything but [A-Za-z0-9 .,-] as {\char<n>}, so it is safe
# inside latexmk's double quotes.
define grading-one-student
	cd "$(GR_COMP)" && TEXINPUTS="$(GRADING_TEXINPUTS)" $(GRADING_LATEXMK) \
	    -jobname="$$id" \
	    -usepretex="\def\GradingStudentID{$$id}\def\GradingStudentName{$$name}" \
	    -outdir="$(GR_STUDENTS)" main.tex > "$(GR_STUDENTS)/$$id.out" 2>&1 \
	  || { echo "!  LaTeX failed for $$id — see $(GR_STUDENTS)/$$id.log"; \
	       grep -E "^(!|l\.|.*:[0-9]+: )" "$(GR_STUDENTS)/$$id.log" | head -10; exit 1; }
endef

grading-personalized: grading-need-component grading-need-roster
	@mkdir -p "$(GR_STUDENTS)"
	@set -e; \
	ids=$$($(GRADING_PYTHON) "$(GRADING_SCRIPTS)/roster_tex.py" "$(ROSTER)" --ids-only \
	        $(if $(SECTION),--section "$(SECTION)")); \
	$(GRADING_PYTHON) "$(GRADING_SCRIPTS)/roster_tex.py" "$(ROSTER)" \
	    $(if $(SECTION),--section "$(SECTION)") | \
	while IFS='	' read -r id name; do \
	  echo "   $$id"; \
	  $(grading-one-student); \
	done; \
	pdfs=; n=0; \
	for id in $$ids; do pdfs="$$pdfs $(GR_STUDENTS)/$$id.pdf"; n=$$((n + 1)); done; \
	pdfunite $$pdfs "$(GR_OUT)/personalized.pdf"; \
	echo "✓  $$n personalized copies, roster order → $(GR_OUT)/personalized.pdf"

grading-student: grading-need-component grading-need-roster
	@test -n "$(STUDENT)" || { echo "grading.mk: set STUDENT=<tracking id>"; exit 1; }
	@mkdir -p "$(GR_STUDENTS)"
	@set -e; \
	$(GRADING_PYTHON) "$(GRADING_SCRIPTS)/roster_tex.py" "$(ROSTER)" --id "$(STUDENT)" | \
	while IFS='	' read -r id name; do \
	  $(grading-one-student); \
	done; \
	cp "$(GR_STUDENTS)/$(STUDENT).pdf" "$(GR_OUT)/student-$(STUDENT).pdf"; \
	echo "✓  $(STUDENT) → $(GR_OUT)/student-$(STUDENT).pdf"

grading-clean:
	rm -rf "$(GR_OUT)"
