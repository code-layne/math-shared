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
#   STUDENT        tracking id, for grading-student (and grading-covers)
#   GRADING_OUT    output directory; default target/grading/<component name>
#   TEXINPUTS      the course's TeX search path, e.g. $(PROJECT_ROOT)/shared//:
#                  The build searches the component directory first, then this
#                  directory (non-recursively: math-shared/examples holds
#                  main.tex files a recursive path would find), then TEXINPUTS.
#
# Targets:
#   grading-blank         the ordinary build (QR tracking id MASTER, empty
#                         id strip) -> $(GRADING_OUT)/blank/main.pdf
#   grading-key           the key build -> $(GRADING_OUT)/key/main.pdf
#   grading-manifest      blank build -> $(GRADING_OUT)/manifest.json; if the
#                         key exists, also key-manifest.json and the check
#                         that both agree on every item
#   grading-covers        one name cover sheet per student (cover.tex)
#                         -> $(GRADING_OUT)/covers/cover-<id>.pdf
#   grading-personalized  one copy per student, in roster order, joined into
#                         $(GRADING_OUT)/personalized.pdf; each student's run is
#                         her cover, a blank back, then her graded copy padded
#                         with blank pages to an even count
#   grading-student       one student's run -> $(GRADING_OUT)/student-$(STUDENT).pdf
#   grading-clean         remove $(GRADING_OUT)
#
# Graded pages carry only the tracking id: scans go to an outside API. The
# component builds get \GradingStudentID and nothing else, and both personalized
# targets end with scripts/check_names.py, which fails if any roster name is in
# blank/, key/ or students/. Student names are only in covers/, packets/,
# personalized.pdf and student-*.pdf. Keep GRADING_OUT inside an ignored build
# directory (target/ is ignored in every course repo) and never commit it.

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
GR_COVERS   = $(GR_OUT)/covers
GR_PACKETS  = $(GR_OUT)/packets
GR_BACK     = $(GR_OUT)/blank-page.pdf
GR_SELECT   = $(if $(SECTION),--section "$(SECTION)")

.PHONY: grading-blank grading-key grading-manifest grading-covers grading-personalized \
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
#   \def\GradingStudentID{ID}\input{main.tex}
# Runs in the shell with $$id set. The id is [A-Z0-9]{6} (roster_tex.py checks
# it); no name is passed, so none can reach a graded page or its log.
define grading-one-student
	( cd "$(GR_COMP)" && TEXINPUTS="$(GRADING_TEXINPUTS)" $(GRADING_LATEXMK) \
	    -jobname="$$id" \
	    -usepretex="\def\GradingStudentID{$$id}" \
	    -outdir="$(GR_STUDENTS)" main.tex > "$(GR_STUDENTS)/$$id.out" 2>&1 ) \
	  || { echo "!  LaTeX failed for $$id — see $(GR_STUDENTS)/$$id.log"; \
	       grep -E "^(!|l\.|.*:[0-9]+: )" "$(GR_STUDENTS)/$$id.log" | head -10; exit 1; }
endef

# One cover sheet, in the shell with $$id, $$pref, $$last and $$meta set. The
# names come from roster_tex.py and $$meta from manifest.py cover-tex, which
# encode everything but [A-Za-z0-9 .,-] as {\char<n>} (the assignment is
# checked to be [A-Za-z0-9._-]), so all of it is safe inside latexmk's double
# quotes.
define grading-one-cover
	( cd "$(GRADING_ROOT)" && TEXINPUTS="$(GRADING_TEXINPUTS)" $(GRADING_LATEXMK) \
	    -jobname="cover-$$id" \
	    -usepretex="\def\GradingStudentID{$$id}\def\CoverPreferredName{$$pref}\def\CoverLastName{$$last}$$meta" \
	    -outdir="$(GR_COVERS)" cover.tex > "$(GR_COVERS)/cover-$$id.out" 2>&1 ) \
	  || { echo "!  LaTeX failed for the cover of $$id — see $(GR_COVERS)/cover-$$id.log"; \
	       grep -E "^(!|l\.|.*:[0-9]+: )" "$(GR_COVERS)/cover-$$id.log" | head -10; exit 1; }
endef

# One student's run, in the shell with $$id set: cover, blank back, graded
# copy, and one more blank page if the copy has an odd page count. Every run
# is even, so in the joined PDF each cover starts on an odd page and each
# graded copy on a fresh sheet.
define grading-packet
	pages=$$(pdfinfo "$(GR_STUDENTS)/$$id.pdf" | awk '/^Pages:/ { print $$2 }'); \
	pad=; if [ $$((pages % 2)) -eq 1 ]; then pad="$(GR_BACK)"; fi; \
	pdfunite "$(GR_COVERS)/cover-$$id.pdf" "$(GR_BACK)" "$(GR_STUDENTS)/$$id.pdf" $$pad \
	    "$(GR_PACKETS)/$$id.pdf"
endef

grading-covers: grading-blank grading-need-roster
	@mkdir -p "$(GR_COVERS)"
	@set -e; \
	meta=$$($(GRADING_PYTHON) "$(GRADING_SCRIPTS)/manifest.py" cover-tex "$(GR_OUT)/blank/main.grading"); \
	rows=$$($(GRADING_PYTHON) "$(GRADING_SCRIPTS)/roster_tex.py" "$(ROSTER)" \
	    $(GR_SELECT) $(if $(STUDENT),--id "$(STUDENT)")); \
	printf '%s\n' "$$rows" | while IFS='	' read -r id pref last; do \
	  echo "   cover $$id"; \
	  $(grading-one-cover); \
	done
	@echo "✓  covers  → $(GR_COVERS)"

grading-personalized: grading-need-component grading-need-roster grading-covers
	@test -z "$(STUDENT)" || { echo "grading.mk: grading-personalized builds the whole roster; unset STUDENT"; exit 1; }
	@mkdir -p "$(GR_STUDENTS)" "$(GR_PACKETS)"
	@$(GRADING_PYTHON) "$(GRADING_SCRIPTS)/blank_page.py" "$(GR_BACK)"
	@set -e; \
	ids=$$($(GRADING_PYTHON) "$(GRADING_SCRIPTS)/roster_tex.py" "$(ROSTER)" --ids-only $(GR_SELECT)); \
	pdfs=; n=0; \
	for id in $$ids; do \
	  echo "   $$id"; \
	  $(grading-one-student); \
	  $(grading-packet); \
	  pdfs="$$pdfs $(GR_PACKETS)/$$id.pdf"; n=$$((n + 1)); \
	done; \
	pdfunite $$pdfs "$(GR_OUT)/personalized.pdf"; \
	echo "✓  $$n personalized copies with covers, roster order → $(GR_OUT)/personalized.pdf"
	@$(GRADING_PYTHON) "$(GRADING_SCRIPTS)/check_names.py" "$(GR_OUT)" "$(ROSTER)"

grading-student: grading-need-component grading-need-roster grading-covers
	@test -n "$(STUDENT)" || { echo "grading.mk: set STUDENT=<tracking id>"; exit 1; }
	@mkdir -p "$(GR_STUDENTS)" "$(GR_PACKETS)"
	@$(GRADING_PYTHON) "$(GRADING_SCRIPTS)/blank_page.py" "$(GR_BACK)"
	@set -e; \
	ids=$$($(GRADING_PYTHON) "$(GRADING_SCRIPTS)/roster_tex.py" "$(ROSTER)" --ids-only --id "$(STUDENT)"); \
	for id in $$ids; do \
	  $(grading-one-student); \
	  $(grading-packet); \
	done; \
	cp "$(GR_PACKETS)/$(STUDENT).pdf" "$(GR_OUT)/student-$(STUDENT).pdf"; \
	echo "✓  $(STUDENT) → $(GR_OUT)/student-$(STUDENT).pdf"
	@$(GRADING_PYTHON) "$(GRADING_SCRIPTS)/check_names.py" "$(GR_OUT)" "$(ROSTER)"

grading-clean:
	rm -rf "$(GR_OUT)"
