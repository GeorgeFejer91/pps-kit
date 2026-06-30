# Behavior Research Methods Submission Workspace

This workspace is for preparing a PPS Toolkit manuscript for Springer Nature's
`Behavior Research Methods` journal.

## Template Source

- Template package: Springer Nature LaTeX author template, December 2024 ZIP.
- Official source page: https://www.springernature.com/gp/authors/campaigns/latex-author-support
- Download URL used: https://cms-resources.apps.public.k8s.springernature.io/springer-cms/rest/v1/content/18782940/data/v12
- Overleaf gallery entry: https://www.overleaf.com/latex/templates/springer-nature-latex-template/myxmhdsbzkyd
- Downloaded on: 2026-06-30
- ZIP SHA-256: `812E76DCAA9C28DC1BFF1FB6065D51729B67D4EA140552A05088317414A3ECAE`

The template package is preserved unmodified under
`springer-nature-latex-template/`. The original downloaded ZIP is kept beside
the extracted copy so the template can be refreshed or compared later.

## Local Layout

- `springer-nature-latex-template-dec-2024.zip`: original downloaded template
  package.
- `springer-nature-latex-template/sn-article-template/`: extracted Springer
  Nature article template, class file, bibliography styles, sample manuscript,
  and user manual.
- `manuscript/`: PPS Toolkit Behavior Research Methods draft sources, including
  the Springer `sn-apa` manuscript, BibTeX file, build config, and
  design-decision evidence matrix.

For this journal, start from
`springer-nature-latex-template/sn-article-template/sn-article.tex` and check
the current journal instructions before submission. Behavior Research Methods
uses psychology/social-science conventions, so the likely Springer Nature class
option is `sn-apa`, for example:

```tex
\documentclass[pdflatex,sn-apa]{sn-jnl}
```

For a review draft, consider adding the template's review options:

```tex
\documentclass[referee,lineno,pdflatex,sn-apa]{sn-jnl}
```

Existing repository manuscript fragments that may be useful when drafting:

- `methods.tex`
- `methods_references.bib`

The current draft under `manuscript/` is intentionally a methods/software paper
and not a formal meta-analysis. It treats tactile hit-rate decline as anecdotal
design motivation unless future traceable run artifacts are supplied.

## Boundary

The Springer Nature template files are third-party author-support materials and
are not part of the PPS Toolkit MIT license grant. Keep upstream notices intact
when editing or redistributing derived manuscript materials.
