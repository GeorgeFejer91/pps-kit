# Native Signal SVG Pipeline

PPS-kit signal graphics are generated directly as SVG. The pipeline does not
open a screenshot, draw to a canvas, trace pixels, or embed a raster image.

## Pipeline

`For-AI/engineering/tooling/generate_noise_mode_svgs.py` performs four deterministic stages:

1. It calls the toolkit renderer's seeded Gaussian-noise, DynaSpace burst, and
   tactile waveform primitives.
2. It applies the declared representative approach model. The source widgets
   use a linear-distance trajectory with the renderer's reciprocal-distance
   (`1/r`) gain. The DynaSpace widget resolves 33 raised-cosine 30 ms bursts at
   the canonical 95 ms target period.
3. It reduces each sample array into per-column minimum and maximum values.
   Those values become closed SVG `path` geometry, preserving silence, peaks,
   burst boundaries, and tactile onset without a bitmap.
4. It builds the frame, grid, envelopes, markers, labels, legends, and metadata
   as native SVG elements through `xml.etree.ElementTree`.
5. It embeds light and dark palette variables in every SVG. The dark palette is
   selected by `prefers-color-scheme` inside the SVG; the dashboard passes its
   explicit theme to each external image with the inherited `color-scheme`
   property, so the artwork follows the app toggle rather than remaining a
   fixed light document.

The same run generates:

- Full burst-train and continuous reference diagrams.
- Compact, transparent burst-train and continuous source-mode control previews.
- The three-channel architecture audiogram.
- Seven baseline strategy pictograms with audio and tactile lanes.

The interface previews deliberately omit duplicated editorial chrome. Their
outer canvas is transparent, leaving the HTML control responsible for the
border, surface, hover, focus, and selected state. This keeps the generated
signal geometry reusable while making it read as part of the toolkit UI.

Each SVG embeds deterministic JSON metadata containing its recipe, seed, sample
rate, signal roles, reduction method, and relevant timing parameters. The
audiogram explicitly remains an illustrative stereo channel preview rather
than claiming to be an HRTF render.

## Commands

Regenerate package and dashboard copies:

```bash
python For-AI/engineering/tooling/generate_noise_mode_svgs.py
```

Verify that every committed copy matches the pipeline without writing files:

```bash
python For-AI/engineering/tooling/generate_noise_mode_svgs.py --check
```

Generate an isolated review set:

```bash
python For-AI/engineering/tooling/generate_noise_mode_svgs.py --output-dir /tmp/pps-signal-svg-review
```

After changing dashboard references or SVG bytes, rebuild
`apps/designer/frontend/compiled/` with its Vite build.

## Contract

`tests/test_signal_svg_generation.py` enforces reproducible bytes, package and
dashboard parity, compiled interface-asset parity, semantic waveform/channel
layers, compact transparent compositions, app-theme bridging, canonical burst
timing, and a vector-only policy. It rejects raster/external resource elements,
links, data URIs, and base64 payloads.
