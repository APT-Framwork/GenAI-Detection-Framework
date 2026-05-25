# Build every standalone TikZ diagram under this directory.
# Usage:
#   make        # build all PDFs
#   make clean  # remove aux files
#   make veryclean  # also remove PDFs

TEX := pdflatex -interaction=nonstopmode -halt-on-error

SOURCES := $(filter-out _%.tex, $(wildcard *.tex))
PDFS    := $(SOURCES:.tex=.pdf)

all: $(PDFS)

%.pdf: %.tex _style.tex
	$(TEX) $< >/dev/null

clean:
	rm -f *.aux *.log *.out

veryclean: clean
	rm -f *.pdf *-1.png

.PHONY: all clean veryclean
