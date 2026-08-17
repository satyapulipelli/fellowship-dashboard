# Fellowship Dashboard — Public Mock Rebuild

A public-facing rebuild of a Northeastern University Registrar fellowship dashboard, using
entirely synthetic data for a fictional institution (**Pacific Ridge University**). The
original is a Python Shiny multi-tab dashboard built during a 9-month fellowship with the
Office of the University Registrar; its data is protected under an institutional agreement
and cannot be shown publicly.

The goal is a functional replica: same methodology, same architecture, same
visualisations, synthetic inputs.

> This dashboard demonstrates analytical tools built during a fellowship with a university
> registrar's office. All data shown is synthetic. The methodology, architecture, and
> visualizations replicate the production system, which operates on protected
> institutional data.

## Status

### Decisions taken

- **Palette** — Northeastern brand chrome (`#C8102E` / `#C8A978` / `#0033A0`, Lato), copied
  from the original's `app.css`. The dashboard looks like the real tool; only the data is
  fictional, and the disclaimer says so. Hex codes are public brand information, not
  protected data — the blueprint's "not Northeastern red" line was a design preference,
  now overridden. The chart palette was never branded and transfers unchanged.
- **Graph layout** — layered DAG (tier = course level, ordering crossing-minimised) as the
  default, force-directed as a toggle. See the layout table below.

| Phase | State |
|---|---|
| 0 — Read and map the original codebase | **done** → [`docs/ORIGINAL_APP_MAP.md`](docs/ORIGINAL_APP_MAP.md) |
| 1 — Mock data generation | **done** → 14 JSON files, 57/57 validation checks pass |
| 2 — React + Vite scaffold | not started |
| 3 — Build tabs | not started |
| 4 — Polish | not started |
| 5 — Portfolio integration | not started |

Nothing outside this folder has been modified. The original codebase in
`../Fellowship Project/` is read-only input.

## Layout

```
mock-dashboard/
├── docs/
│   ├── ORIGINAL_APP_MAP.md      Map of the original Shiny app: tabs, charts,
│   │                            filter chains, data dependencies, latent bugs,
│   │                            and every divergence from the blueprint
│   ├── DATA_CONTRACT.md         Schema of every generated JSON file — the spec
│   │                            Phase 2 builds against
│   └── VALIDATION_REPORT.md     Generated: measured values vs calibration targets
├── public/data/                 14 generated JSON files (3.5 MB, ~700 KB gzipped)
├── scripts/
│   ├── pru_config.py            All tuning constants and the university definition
│   ├── generate_mock_data.py    The generator (17 stages)
│   ├── validate_mock_data.py    Calibration and structural checks
│   └── intermediate/            Full student pathways and section rows (not shipped)
└── src/                         Phase 2 React app (empty)
```

## Running it

```bash
python3 -m venv .venv && .venv/bin/pip install numpy pandas scikit-learn networkx scipy
```

```bash
.venv/bin/python scripts/generate_mock_data.py
```

```bash
.venv/bin/python scripts/validate_mock_data.py
```

Generation takes about 6 seconds. `--quick` runs with 1,500 students instead of 8,000 for
faster iteration.

Output is byte-identical across runs (verified over five), with the single exception of the
`generated_at` timestamp in `summary_stats.json`. Reaching that took two fixes: the
generator re-execs itself with `PYTHONHASHSEED=0`, and — the substantive one —
`nx.simple_cycles` returns cycles in a hash-dependent order, so the original's
cycle-breaking step removed a *different set of prerequisite edges on every run*, shifting
betweenness, chain depth, cascade impact and therefore every RF score downstream. Cycles
are now canonicalised and sorted before any edge is removed. See
`ORIGINAL_APP_MAP.md §8.3`.

## What the generator actually does

The principle throughout: **reproduce the original's methodology, not just its output
shape.** Where the original ran a real algorithm, this runs that same real algorithm over
synthetic inputs, so the reported model metrics are measured rather than asserted.

- **Prerequisite graph** — built and analysed with NetworkX, using the original's own
  functions: `betweenness_centrality`, topological-DP chain depth, `descendants` for
  cascade impact, `dag_longest_path_length` for program depth, and the same heuristic
  cycle-breaking (remove the last→first edge of each `simple_cycle`).
- **Bottleneck ground truth** — 8,000 students are simulated walking the graph under
  per-course "friction". Median enrollment delay and stalling rate are then measured from
  their transcripts exactly as `compute_ground_truth` does: min-max normalised, combined
  50/50 into a composite, top quartile labelled bottleneck, courses with fewer than 10
  eligible students dropped.
- **Bottleneck model** — a real `RandomForestClassifier` over the original's exact 9
  `FEATURE_COLS`, split temporally by student entry cohort (pre-Fall-2023 train,
  Fall-2023+ test), alongside the original's threshold rule and logistic regression.
- **Similarity** — real TF-IDF cosine similarity over the generated course text. The
  original used sentence-transformer embeddings; TF-IDF is a genuine text-similarity
  computation with no model download, and the descriptions are themselves built from topic
  keyword pools, so the cluster structure being measured is real structure in the text.
- **Demand** — both of the original's demand paths. The dashboard path
  (`DemandAggregator`) aggregates synthesised ranked student preferences through the exact
  published formulas; the second path is the RandomForest enrollment forecaster the
  original trained in R and never wired in, evaluated against the same
  `same_season_last_year_enrollment` naive baseline.
- **Enrollment calibration** — a two-pass bisection on section fill and waitlist
  probability, landing the at-capacity and waitlist rates on the real system's published
  36.0% / 31.9%.

## Graph layout

The original places nodes within a tier alphabetically, which ignores the edges — so
prerequisite-linked courses routinely sit at opposite ends of a row. The shipped default
keeps the tiers (vertical distance still means prerequisite depth) and reorders each tier
by barycentre over 8 alternating sweeps. Spacing is adaptive.

| | original (alphabetical, 150px) | shipped default |
|---|---|---|
| Edge crossings | 10,621 | **4,712** (−55.6%) |
| Total width | 38,250 px | **11,427 px** (−70.1%) |
| Mean edge horizontal span | 4,913 px | **1,241 px** (−74.7%) |
| Edges within 100 px of vertical | 22 | **152** (7×) |

Three separate mechanisms, and they do different jobs: barycentre ordering cuts crossings
but neither narrows the layout nor shortens edges; adaptive spacing cuts width; and a
priority coordinate-assignment pass is what actually shortens edges. I asserted at first
that reordering alone would narrow things — it cannot, since a tier's node count is fixed.

Both coordinate sets ship (`x`/`y` layered, `x_hier`/`y_hier` the original's exact output)
so the two can be compared. Force-directed needs no precomputed coordinates and runs
client-side from the edge list.

Even at 11,427 px the unfiltered graph is wide, which is why the original prompted users to
filter first (`server.py:49-54`). A program-filtered view is 3–33 courses and reads
comfortably.

## Measured results

Targets are the real system's published figures. Full table in
[`docs/VALIDATION_REPORT.md`](docs/VALIDATION_REPORT.md).

| Measure | Real system | This mock |
|---|---|---|
| Sections at or over capacity | 36.0% | 36.0% |
| Sections with a waitlist | 31.9% | 31.9% |
| RF bottleneck AUC | 0.772 | 0.807 |
| RF bottleneck base rate | 0.25 | 0.263 |
| Precision@20 | 0.85 | 0.95 |
| Longest prerequisite chain | 6–8 | 7 |
| Similarity pairs at 0.80 | 2.96 per course | 2.96 per course (2,681) |
| Demand RF improvement over naive | 28.7% | 17.1% |

The demand-model gap is the one target not reached, and it is a consequence of window
length rather than method: the forecaster's edge over the naive lag depends on how many
same-season observations per course it can average over. Three academic years yields
+9.7%, five yields +17.1%. Five is the original's own CourseLeaf window
(Fall 2021 – Fall 2025), so extending further would improve the number while no longer
reproducing the original's setup.

## Scale

Generated at roughly a tenth of the real system's scale, so the whole dataset can be
served as static JSON to a browser. Structural *ratios* are preserved.

| | Real | Mock |
|---|---|---|
| Courses | 8,587 | 820 |
| Programs | 1,017 | 80 |
| Prerequisite edges | 8,072 | 1,115 |
| Terms | 21 | 25 |
| Similarity pairs at 0.80 | 25,431 | 2,681 |

The real figures are carried in `summary_stats.json → real_system_context` so the
dashboard can state them in its disclaimer. They are the only real numbers anywhere in the
output.

## Fidelity policy

Where the original codebase specifies a behaviour, it is reproduced exactly — field names,
formulas, thresholds, colour values, sort orders, even conventions that look like mistakes
(`density` mixes a directed numerator with an undirected maximum; preserved and
documented). Independent decisions were made only where the original is silent, and each
one is recorded in `ORIGINAL_APP_MAP.md`. The notable cases:

- **Term coding.** The original contains three mutually inconsistent season-code maps and
  a calendar-vs-academic-year conflict that skews the ML delay arithmetic. Resolved to the
  one scheme consistent with `semester_index()`, confirmed by `FALL_2023_TERM = 202410`
  and by the modelling CSVs.
- **Responsiveness classification thresholds.** Not specified anywhere, and the Dash
  dashboard that produced that tab is absent from the codebase. Terciles of the observed
  distribution are used rather than invented cut-points. The formula itself is applied
  literally as specified, with a documented caveat that all three of its components
  measure demand rather than response.
- **`generate_recommendations`.** Called by the original's export button but never
  defined anywhere in the codebase. Reimplemented from its call signature and the
  fields the UI renders.
