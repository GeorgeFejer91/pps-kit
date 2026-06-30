# PPS Toolkit BRM Manuscript Draft

This folder contains the draft Springer Nature/Behavior Research Methods
manuscript for PPS Toolkit.

## Files

- `main.tex`: single-file Springer Nature `sn-apa` manuscript draft with the
  design-decision matrix and reporting checklist.
- `references.bib`: bibliography assembled from Consensus searches, existing
  repo paper-audit notes, and Springer/software policy pointers.
- `evidence_matrix.csv`: source-pointer design-decision matrix mapping visible
  PPS Toolkit GUI/runner controls to literature variation and caveats.
- `critical_review.md`: self-review audit recording critique points and
  revision decisions for the manuscript draft.
- `latexmkrc`: local build configuration that points LaTeX/BibTeX at the
  preserved Springer Nature template under
  `../springer-nature-latex-template/sn-article-template/`.

## Build

From this folder:

```powershell
latexmk -pdf main.tex
```

Do not commit generated LaTeX build artifacts or compiled PDFs unless a release
workflow explicitly asks for an archived submission snapshot.

## Draft Boundaries

- The draft is a methods/software manuscript, not a formal meta-analysis.
- The evidence matrix is a structured literature audit scaffold, not a PRISMA
  extraction log.
- The tactile hit-rate decline noted during pilot use is treated only as
  anecdotal design motivation until traceable runner artifacts are attached.
- No copyrighted paper PDFs, participant outputs, local SOFA files, or private
  generated stimuli belong in this folder.
