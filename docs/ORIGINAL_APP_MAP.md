# Map of the Original Shiny Dashboard

Source read: `Fellowship Project/git_repo/shiny-dashboard/` (92 Python files, all read).
Nothing in the original tree was modified.

This document is the authoritative reference for the rebuild. Where the blueprint
(`fellowship-dashboard-blueprint.md`) and the actual code disagree, **the code wins** and
the divergence is flagged in [Divergences](#divergences-blueprint-vs-actual-code).

---

## 1. Entry point and composition

```
app.py                    page_fluid → panel_title("Course Dependency & Program Analytics")
 ├─ app.css               injected inline; Tailwind 3.4 CDN; Lato font; Font Awesome 6.5
 └─ layout_sidebar(
       sidebar_ui(),      sidebar/sidebar_ui.py   — 300px, conditional panels keyed to input.main_tabs
       main_view_ui()     main_view/main_view_ui.py — navset_tab(id="main_tabs")
    )
server.py                 loads all data ONCE, builds shared get_graph() reactive, wires 4 sub-servers
```

**Tab count reality check:** `main_view_ui()` registers **4** tabs. `student_preference`
(Course Planner) and `admin_demand` (Demand Forecast) are commented out in both
`main_view_ui.py` and `server.py`. Per `README.md §3.2` they are "UI fully designed and coded;
disabled pending a live data pipeline." Their UI and server code is complete and readable —
which is why the Demand Forecast tab can be rebuilt at full fidelity.

| # | `value=` | Label | Status |
|---|----------|-------|--------|
| 1 | `graph_view` | Graph View | **active** |
| 2 | `program_metrics` | Program Metrics | **active** |
| 3 | `course_metrics` | Course Metrics | **active** |
| 4 | `redundancy_analysis` | Redundancy Analysis | **active** |
| 5 | `student_preference` | Course Planner | disabled (no data feed) |
| 6 | `admin_demand` | Demand Forecast (Admin View) | disabled (no data feed) |

Tabs 7–9 in the blueprint (Executive Summary, Temporal Analysis, Term-to-Term Correlation)
come from a **superseded Plotly Dash dashboard that is not present in this codebase**.
`grep -rl "import dash"` returns nothing; `grep -ri "responsiveness"` returns nothing.
They must be rebuilt from the blueprint's written spec, not from source.

---

## 2. The shared reactive chain

Everything flows through one cached graph object built in `server.py:get_graph()`.

```
input.department ──┐
input.program   ──┤ mutually exclusive: selecting one resets the other to "all"
                  │   (server.py:78-86, via ui.update_select)
input.admin_terms─┤ multi-select term codes
input.concentration┤ CONC:/PATH:/OPT: prefixed, only rendered when program has them
input.main_tabs  ──┘ gates course_mode: "all" only on program_metrics tab w/ view_all_courses ON
                  │
                  ▼
      get_filtered_courses()   ── term filter → get_courses_by_terms(selected_terms)
                  ▼
      create_course_graph(...) ── lru_cache(32), args JSON-frozen for hashability
                  ▼
              NetworkX DiGraph  G
                  ▼
   ┌──────────────┼──────────────┬─────────────────────┐
   ▼              ▼              ▼                     ▼
graph_view    program_metrics  redundancy      course_metrics
                                              (does NOT use G — uses behavioral_data)
```

### Cascading filter rules (exact behaviour, `sidebar/filters/filters_server.py`)

1. **Department ⊥ Program.** Committing one clears the other (`server.py:78-86`). Two
   separate `reactive.Value`s (`selected_program_committed`, `selected_department_committed`)
   hold *committed* selections so mid-typing selectize states don't trigger rebuilds.
2. **Terms → Departments.** With terms selected, the department dropdown is intersected with
   departments that actually have a course whose `enrollment_series.terms` includes a selected term.
3. **Terms → Programs.** With terms selected, the program dropdown is restricted to programs with
   ≥1 version whose `effective_period` overlaps a selected term (`program_active_in_term`).
4. **Program → Terms.** Selecting a program restricts the term dropdown to that program's
   active terms (across **all** versions, not just the most recent).
5. **Department → Terms.** Restricts terms to those in which the department offers courses.
6. **Auto-select.** Selecting a program when no term is chosen auto-selects that program's
   **most recent** term.
7. **Self-healing.** If a selected program becomes inactive for the current terms, `get_graph()`
   silently resets the program filter to `"all"` (`server.py:92-98`).
8. **Program dropdown is optgrouped** into Undergraduate / Graduate / Concentration / Other–Doctoral,
   keyed off `degree_type` prefix sets: UG = {BA,BS,BFA,BARCH}, GRAD = {MA,MS,MBA,MPH,MFA,PHD}.
9. Program codes that collide with department codes are excluded from the program dropdown.

### Sidebar contents per tab

| Control | Tabs shown on |
|---|---|
| Department / Program / Concentration / Term selectize | all 4 active tabs (+ admin_demand) |
| `removed_courses` selectize ("Courses to Grey Out") | graph_view |
| `highlight_shared` checkbox | graph_view |
| `highlight_bottlenecks` checkbox | graph_view |
| Graph legend (levels, edge types, cross-program) | graph_view |
| `similarity_threshold` slider 0.60→0.95 step 0.05, default **0.80** | redundancy_analysis |
| Redundancy legend | redundancy_analysis |

---

## 3. Graph construction (`graphs.py`)

### Node set selection
- `program_filter != "all"` → `extract_program_courses(prog, mode=course_mode, version=...)`.
  When `course_mode == "all"`, elective **ranges** are additionally resolved against the full
  course catalog (`_resolve_range`: dept prefix + level_min/level_max + exceptions).
- `department != "all"` → all codes starting `"{DEPT} "`.
- else → every course.
- Program courses absent from the catalog become **placeholder nodes** titled `"(not in dataset)"`,
  and the set is stashed on `G.graph["missing_courses"]`.

### Node attributes
`title`, `level` (first digit of the catalog number), `is_elective`, `elective_context`,
plus from `enrich_courses_with_program_data`: `programs` (list), `program_count` (int),
`requirement_types` ({program_code: core|elective|pathway|concentration}).

### Edges
- `prerequisite`: `prereq → code`, added when the prereq is already a node and `prereq != code`
  (self-loops dropped).
- `corequisite`: `code → coreq`, added only if no reverse edge already exists.

### Layout — **hierarchical, not force-directed**
`create_hierarchical_layout(G)`: group nodes by `level`, sort alphabetically within level,
distribute horizontally centred on x=0 with `x_spacing=150`, stack levels downward with
`y_spacing=100`. Levels ascend top→bottom.

### Plotly figure (`create_plotly_figure`)
- **Chart type:** `go.Scatter` traces — one per edge-type group (`mode="lines"`) plus one node
  trace (`mode="markers+text"` when `n_nodes < 80`, else `"markers"`).
- `node_size = max(15, min(35, 500/n))`; `edge_width = max(1, min(3, 50/n))`.
- Edge colors: prerequisite `#10b981` solid, corequisite `#f59e0b` dashed. Greyed edges drop to
  `opacity 0.15` and leave the legend.
- **Node color priority (first match wins):**
  1. explicitly removed → `#374151`
  2. downstream of a removed course → `#d1d5db`
  3. `highlight_bottlenecks` → `#dc2626` if score ≥ 0.5 else `#808080`
  4. `highlight_shared` → by `program_count`: 1 `#3b82f6`, 2 `#8b5cf6`, 3 `#ec4899`, 4+ `#dc2626`, 0 `#9ca3af`
  5. by level: 0 `#6b7280`, 1 `#ef4444`, 2 `#f59e0b`, 3 `#eab308`, 4 `#22c55e`, 5 `#3b82f6`, 6 `#8b5cf6`, 7 `#ec4899`
  - Elective tints exist in code (`elective_colors`) but are **never applied** — dead code.
- **Cascade grey-out:** `compute_grey_nodes` BFS's forward from every removed course over both
  prerequisite successors *and* corequisite out-edges. This is the tab's most distinctive
  interaction and is absent from the blueprint.
- Layout: `height=750`, `dragmode="pan"`, axes hidden, `plot_bgcolor #ffffff`,
  `paper_bgcolor #f9fafb`, title `"Course Dependency Graph (N courses, M connections)"`.
- Config: `scrollZoom: True`, `displaylogo: False`, lasso/select removed.
- Wrapped by `fullscreen_graph()` — a ⤢ / ✖ button pair that toggles a `position: fixed`
  `z-index: 9999` overlay.

### Hover text (node)
```
<b>{code}</b> / {title} / Level: {level}00
Prerequisites: {count of prerequisite in-edges}
Corequisites: {comma list}            (only if any)
Unlocks: {out_degree} courses
── elective block, if is_elective ──   section name + choice label (or "Elective (Open Range)")
── Programs: {n} ──                    up to 5 as "• {code} ({requirement_type})", then "… and N more"
```

---

## 4. Tab-by-tab specification

### Tab 1 — Graph View
- **Layout:** card(fullscreen graph) above card("Graph Statistics").
- **Charts:** the node-link scatter described above.
- **Graph Statistics card** (`graph_stats_server.py`), four sections, every row tooltipped:
  - *Summary* — Total Courses, Total Dependencies (Connections)
  - *Complexity* — Avg Prerequisites (`Σin_degree/n`, 1dp), Max Prerequisites
  - *Key Courses* — top 5 by `out_degree`, rendered `"{code}  {d} unlocks"`, zero-degree excluded
  - *Total Courses By Level* — count per level, ascending
- **Data:** `courses.json` (nodes/edges), `programs/*.json` (program tags),
  `bottleneck_scores.json` (highlight), CourseLeaf CSVs (term filter).

### Tab 2 — Program Metrics
- **Controls:** `selected_programs` multi-select (in-panel, populated once on first visit to the
  tab), `view_all_courses` switch → `course_mode = "all" | "required"`.
- **Sidebar program selection auto-appends** into `selected_programs`.
- **Output:** one card per program, **sorted by `max_depth` descending**. No charts — all
  numeric stat rows. Metrics come from `calculate_program_metrics`, computed on the
  **program subgraph** (`G.subgraph(program's courses)`):

  | Card section | Metric | Formula |
  |---|---|---|
  | header | `total_credits` | `program_metadata.total_credits` |
  | Size & Complexity | `total_courses` | subgraph node count `n` |
  | | `num_connections` | subgraph edge count |
  | | `density` | `edges / (n(n-1)/2)` — **undirected max, directed numerator** |
  | Network Insights | `cross_program_share` | share of nodes with `program_count > 1` |
  | | `avg_unlocks` | `Σ out_degree / n` |
  | | `modularity_proxy` | `len(connected_components(subgraph.to_undirected()))` |
  | | `foundational_ratio` | share of nodes with `level <= 3` |
  | | `level_ratios` | per-level % of nodes, 1dp |
  | Prerequisite Structure | `avg_prereqs` | `Σ in_degree / n` |
  | | `max_prereqs` | `max(in_degree)` |
  | | `max_depth` | `nx.dag_longest_path_length(subgraph)`, 0 if cyclic |
  | Bottleneck Courses | `bottleneck_courses` | top **3** by RF score (>0) within program; UI shows up to 5 |

  Also computed but unused by the UI: `degree_type`.

### Tab 3 — Course Metrics
- **Controls:** `selected_courses` multi-select, server-side filtered by dept/program/term.
  Courses in the selected program but missing from the catalog appear as `"(not in dataset)"`.
- **Output:** one card per selected course.
  - *Course Context* — **Programs**: count + collapsible list of program **titles**;
    **Bottleneck Flags**: comma-joined, `"None"` if empty.
  - *Enrollment Metrics* — Average Fill Rate (%, 2dp), Average Waitlist (2dp),
    Waitlist Frequency (%, 2dp), Sections per Semester (2dp), Offering Frequency (%, 2dp).
    Each renders `"N/A"` when the value is not numeric.
  - *Enrollment Trend* — only when `len(enrollment_series.terms) >= 2`.
- **Chart** (`enrollment_trend_graph.py`): `go.Scatter` **markers only**, blue `size 8`,
  plus a dashed `np.polyfit(x, y, 1)` trend line. Per-card radio toggle
  `enrollment | fill_rate`. `height=260`. Hover: `Term / {metric} / Instructor`.
- **Bottleneck flag strings** (`bottleneck_pipeline.is_bottleneck`), exact text:
  - `"ML bottleneck (RF pipeline)"` — RF score ≥ 0.5
  - `"High program demand"` — ≥ 2 programs
  - `"Low section availability"` — `sections_per_semester < 2`
  - `"High waitlist frequency"` — `waitlist_frequency > 0.2`

### Tab 4 — Redundancy Analysis
- **Controls:** sidebar `similarity_threshold` slider only.
- **Layout:** card(fullscreen bottleneck→substitute graph) above card("Detailed Analysis").
- **Chart** (`create_bottleneck_substitute_network`) — a **bipartite column layout**, not a
  force graph:
  - Bottlenecks (score ≥ 0.5) in a left column at `x=0`, `y = -i*200`, top 15 by centrality.
  - Up to **3** substitutes each at `x=300`, `y = b_y + (i-1)*60`.
  - Bottleneck nodes: `size 25`, `#dc2626`, label `middle left`.
  - Substitute nodes: `size 20`, `#22c55e` if `is_better_access` else `#64748b`, label `middle right`.
  - Edges: `width 2`, color lerped grey→red over similarity `t = (sim-0.60)/0.35`,
    `rgb(156→220, 163→38, 175→38)`.
  - `height = max(700, n_bottlenecks*120 + 200)`.
  - Empty state is an annotation listing three remediation hints.
- **`is_better_access`** = `substitute_prereqs <= bottleneck_prereqs AND substitute_unlocks >= bottleneck_unlocks * 0.5`.
- **Mutual-bottleneck dedup:** when both courses are bottlenecks, keep one direction only —
  higher score wins, ties broken by lexical order.
- **Detailed Analysis card:** *Redundancy Analysis Summary* — Similarity Threshold,
  Total Courses Analyzed, Bottleneck Courses, Total Substitute Options, Mutual Bottleneck Pairs,
  Redundant Clusters Found. Then *Redundant Course Clusters* — top 5 clusters, each showing
  Avg Similarity, Total Unlocks, Same Dept yes/no, and its course list.
- **Clusters** (`find_redundant_course_clusters`) — DFS over similarity edges at a **fixed
  0.85** threshold (independent of the slider), size > 1, sorted by avg similarity desc.
- A `create_redundancy_heatmap` (`go.Heatmap`, `RdYlBu_r`, top 25 by connection count) exists
  and is **commented out** of the UI pending performance review.

### Tab 6 (disabled) — Demand Forecast
Fully coded; this is the blueprint's "Demand Forecast" tab.
- **KPI cards ×3:** Total Student Plans Submitted (unique student+term pairs),
  Courses with Shortages (`shortage > 0`), Additional Sections Needed (`Σ sections_needed`).
- **Table**, top 20, sortable by radio {shortage | weighted_demand | total_requests | ml_risk}:
  `Course, Total Requests, #1 Choices, #2 Choices, #3 Choices, Weighted Demand,
  Current Cap., Shortage, Sections Needed, ML Risk, Fill Rate`.
  - ML Risk badge: `>0.8` 🔴 HIGH danger, `>0.6` 🟠 MODERATE warning, else 🟢 LOW success.
  - Shortage text class: `>40` danger-bold, `>20` warning-bold, else muted. `0` renders `—`.
- **Demand vs. Capacity:** paired horizontal progress bars per course (demand `bg-primary`,
  capacity `bg-success`), normalised to max demand, sorted by `weighted_demand - current_capacity` desc.
- **High-Risk Courses with High Demand:** `ml_risk > 0.7 AND weighted_demand > 30`,
  sorted by `priority_score`, top 10, as bordered cards.
- **Exports:** `demand_forecast_report.csv`, `recommendations.txt`
  (numbered list of course / Action / Urgency / Impact / Reason).
- **Formulas** (`demand_aggregator.py`) — reproduce exactly:
  ```
  rank_weights      = {1: 1.0, 2: 0.8, 3: 0.6}   (ranks > 3 discarded)
  weighted_demand   = Σ rank_r_count * weight_r
  current_capacity  = max_enrollment_capacity * sections_per_semester
  shortage          = max(0, weighted_demand - current_capacity)
  sections_needed   = ceil(shortage / 40) if shortage > 0 else 0
  priority_score    = shortage*0.4 + ml_risk*100*0.3 + weighted_demand*0.3
  defaults          → max_enrollment 40, sections 1, ml_risk 0.5, fill_rate 0.75
  ```

---

## 5. Data dependencies

| File / dir | Real shape | Consumed by |
|---|---|---|
| `data/courses.json` | dict keyed by code, **8,587** entries | graph nodes/edges, course metrics, all ML features |
| `data/programs/*.json` | **1,017** files, mean **3.74** versions each (max 54) | program tags, program metrics, program & term filters |
| `data/CourseLeaf/UG_*.csv` | **21** term files, Fall 2021 – Fall 2025 | behavioral features, enrollment series, term filter |
| `data/similar_courses.csv` | **25,431** rows | redundancy analysis |
| `ml_models/.../results/bottleneck_scores.json` | `{course: RF probability}` | graph highlight, program metrics, redundancy, course flags |
| `data/degree_audits/` | one student audit | Course Planner only (disabled) |
| `data/mock_admin_preferences.json` | seed preferences | Demand Forecast only (disabled) |

### `courses.json` entry
```json
{ "course_code": "CS 2500", "department": "CS", "number": "2500",
  "title": "Fundamentals of Computer Science 1", "credits": "4", "credits_raw": "4",
  "prerequisite_text": "CS 2500 with a minimum grade of D", "corequisite_text": "CS 2511",
  "prereq_logic": "SINGLE", "catalog_years": ["2024-2025","2023-2024","2021-2022"],
  "prerequisites": ["CS 2500"], "corequisites": ["CS 2511"] }
```
Note the **self-loop** (`CS 2500` requires `CS 2500`) — a genuine catalog-parsing artifact.
`prereq_logic ∈ {NONE, SINGLE, OR, AND, COMPLEX}` drives `parse_prerequisite_groups`:
`SINGLE`/`OR` → one OR-group; `AND` → one group per prereq; `COMPLEX` → split
`prerequisite_text` on `;` into AND-groups, `or` within a group.

### Program JSON
```
program_code, program_title, version_count,
versions[]:
  effective_period{start_date, end_date}      m/d/YYYY
  program_metadata{code,title,degree_type,transcript_title,total_credits,colleges{...}}
  base_requirements{sections[]}
  concentrations{CODE:{name, sections[]}}
  program_statistics{...}                     rebuilt at load time by _process_version
```
Section types observed across all programs:
`required` 17,177 · `choice` 7,222 · `info` 4,871 · `credits` 3,459 · `advisor` 823 ·
`supplemental` 309 · `range` 18 · `experiential` 15 · `pathway` 2.
Extraction rules: `required` → `core` (both modes); `choice|credits|advisor` → `elective`
(mode `all` only); `pathway` → recurse; `info|experiential` → skipped.
Degree types: BS 861, *(blank)* 855, MS 484, BA 422, PhD 257, then MSECE/MSCS/Minor/MSIS/MA/MPS/Certificate/BFA/BSCmpE/BSME.

### CourseLeaf CSV → behavioral features (`aggregate_by_course`)
Source columns used: `Subject Code`, `Catalog Number`, `Term`, `Term Code`, `Instructor`,
`Enrollment`, `Maximum Enrollment`, `Wait List`, `Cross-list Enrollment`.
Per-course output (this is the `behavioral_data` contract the React app must match):
```
avg_enrollment, max_enrollment_capacity, avg_fill_rate, max_fill_rate,
avg_waitlist, max_waitlist, waitlist_frequency, total_waitlist_semesters,
total_sections, terms_offered, capacity_variance,
avg_crosslist_enrollment, has_crosslist,
sections_per_semester = total_sections / terms_offered,
offering_frequency    = terms_offered / total_terms,
enrollment_trend      = polyfit slope of enrollment vs term index,
enrollment_series     = { terms[], enrollment[], fill_rate[], professor[] }
```
`fill_rate = Enrollment / Maximum Enrollment` where max > 0, else NaN→0.

### `similar_courses.csv`
`course_1, course_1_title, course_1_dept, course_2, course_2_title, course_2_dept,
similarity_score, same_department, potential_redundancy`.
Loaded into a **bidirectional** map and pre-filtered at 0.80.

---

## 6. ML pipeline (`bottleneck_identification/bottleneck_pipeline.py`)

Reproducing this faithfully is what makes the mock defensible.

**Ground truth** — derived from student pathways, not from enrollment:
```
for each course with parsed prereq groups:
    eligible students = those who satisfied EVERY prereq group (AND across groups,
                        OR within a group), walking terms forward cumulatively
    completion_term   = first term at which all groups are satisfied
    delay             = semesters from completion_term to first enrolment at/after it
    stalled           = completed prereqs, never enrolled, and had >= 3 (STALLING_WINDOW)
                        post-completion semesters
    drop course if eligible < 10 (MIN_ELIGIBLE_STUDENTS)
    median_delay      = median(delays), or 3.0 if nobody enrolled
    stalling_rate     = n_stalled / n_eligible
min-max normalise both → composite = 0.5*delay_norm + 0.5*stalling_norm
label = 1 where composite >= 75th percentile (BOTTLENECK_PERCENTILE) → 25% base rate
```

**Features** — `FEATURE_COLS`, all 9 (the blueprint lists only 6):
```
behavioral_score, in_degree, out_degree, betweenness,
program_count, level, cascade_impact, prereq_chain_depth, avg_fill_rate
```
- `behavioral_score` = `+1 if avg_fill_rate > 0.95` `+2 if waitlist_frequency > 0.3`
  `+1 if sections_per_semester < 1.5` (range 0–4)
- `betweenness` = `nx.betweenness_centrality`
- `prereq_chain_depth` = longest incoming path, topological DP
- `cascade_impact` = `len(nx.descendants(G, node))`
- Cycles are broken before analysis by removing the last→first edge of each `simple_cycle`.

**Split:** temporal by student entry term — train on pre-Fall-2023 entrants, test on Fall 2023+
(`FALL_2023_TERM = 202410`).

**Models:** threshold rule, logistic regression, random forest. `compute_rule_based_score`:
```
score  = behavioral_score
        + 0.5 if out_degree > 0
        + 0.5 if in_degree > 3
        + 1.0 if betweenness > 0.1
        + 0.5 if program_count > 1
        + 0.25 if level <= 2
```
**Runtime contract:** the dashboard only ever reads the cached
`results/bottleneck_scores.json` via `get_bottleneck_scores()`; it never trains.
`BOTTLENECK_SCORE_THRESHOLD = 0.5`.

Reported results (blueprint §Reference, to calibrate against): RF AUC 0.772,
Precision@20 0.85, base rate 25%; Markov Recall@10 50.3%; RF demand MAE 11.16 (28.7% over naive);
NLP 25,431 pairs @0.80 / 334 clusters; graph 8,579 nodes / 8,072 edges / 5,575 components.

---

## 7. Visual language of the original

`app.css` tokens — the rebuild must **replace** these (blueprint: not Northeastern red):
```
--nu-red #C8102E   --nu-gold #C8A978   --nu-blue #0033A0   --nu-black #000
--nu-gray-50 #F8F9FA  -100 #E9ECEF  -200 #DEE2E6  -700 #495057  -900 #212529
font-family: 'Lato'
```
Chart colors (`graphs.py`, `redundancy_visualizations.py`) are a **separate**, generic
Tailwind-ish palette and carry no institutional branding — those transfer as-is.

Structural patterns worth keeping: 300px fixed sidebar with conditional panels; card with
`h3` + red accent bar; every stat row tooltipped via Bootstrap; ⤢ fullscreen on graphs.

---

## 8. Latent issues found in the original

Recording these because the rebuild must decide, not inherit, each one.

1. **Two conflicting term-code maps.** `term_utils.TERM_CODE_MAP` says
   `Spring=10, Summer1=20, SummerFull=25, Summer2=30, Fall=40`; but
   `load_courseleaf_enrollment.season_map` and `program_utils._TERM_CODE_SEASON` say
   `Fall=10, Spring=20, Summer1=30, Summer2=40, SummerFull=50, Winter=05`.
   `semester_index()` agrees with neither on the *year* axis, which is the deeper problem:
   it assumes **academic-year** Banner coding (Fall 2022 → `202310`, Spring 2023 → `202330`),
   whereas `get_terms_list` derives codes from **calendar-year** filenames
   (`Fall_2021.csv` → `202110`). Under calendar coding, `term_delay(Fall 2021, Spring 2022)`
   returns **3** semesters instead of 1 — so the delay arithmetic feeding the ML ground truth
   is skewed for any pair spanning a Fall→Spring boundary.
   `config.FALL_2023_TERM = 202410` confirms academic-year coding is the intended scheme.
   → The rebuild uses **one** scheme, the `semester_index`-correct one:
   academic-year Banner codes with `Fall=10, Spring=30, Summer=50`
   (Fall 2022 → `202310`, Spring 2023 → `202330`, Summer 2023 → `202350`).
   These sort chronologically as strings and yield `term_delay == 1` between consecutive terms.
2. **Self-loops in `courses.json`** (e.g. `CS 2500` requires itself). Filtered at three
   separate call sites rather than at the source.
3. **Cycles** in the prereq graph, broken heuristically at pipeline time — and broken
   **non-reproducibly**. `bottleneck_pipeline.build_prereq_graph` iterates
   `list(nx.simple_cycles(G))` and removes each cycle's last→first edge. That iteration
   order depends on Python's per-process string hashing, so a different set of edges is
   removed on each run, and every metric computed downstream of the graph — betweenness,
   chain depth, cascade impact, therefore the RF features and its scores — shifts with it.
   The count of cycles broken is stable; which edges disappear is not.
   → The rebuild canonicalises each cycle (rotated to start at its smallest node) and
   sorts the list before removing anything. Verified byte-identical across five runs.
4. **`density` mixes conventions** — directed edge count over undirected max pairs, so a fully
   connected DAG can exceed 0.5. Kept as-is for parity; documented.
5. **`elective_colors` is dead code** — computed, never assigned.
6. **`color_by="structural"`** is threaded through `create_plotly_figure` and never read.
7. **`CS 3500` debug logging** left in `course_metrics_server.py`.
8. **Broken symlinks:** `data/CourseLeaf/*.csv` point at `/Users/satya/Desktop/Fellowship Project/…`,
   which no longer exists after the project moved. Real CSVs live in
   `Fellowship Project/Courseleaf_enrollment/`.
9. **`get_terms_list` reads only filenames**, so the term list depends on files on disk.

---

## Divergences: blueprint vs. actual code

| # | Blueprint says | Code actually does | Rebuild decision |
|---|---|---|---|
| 1 | Graph View is a **force-directed** graph | `create_hierarchical_layout` — levels stacked, alphabetical within level | Ship **precomputed hierarchical** positions (exact algorithm parity, no layout jank on 800 nodes); force layout available as an optional toggle |
| 2 | Nodes colored by **RF bottleneck probability gradient** green→red | Binary `#dc2626` / `#808080` at threshold 0.5, and only when the checkbox is on | Keep the binary threshold mode for parity; add a continuous gradient mode as an enhancement (data supports both — scores are floats) |
| 3 | Program metrics = `chain_depth, gateway_count, density, modularity, cross_dept_pct` | `max_depth, avg_prereqs, max_prereqs, density, cross_program_share, avg_unlocks, foundational_ratio, level_ratios, modularity_proxy, bottleneck_courses` | Use the **real 10**; they're strictly richer |
| 4 | Bottleneck features: 6 | `FEATURE_COLS` has **9** | Use all 9 |
| 5 | Redundancy = table of pairs + "possibly a UMAP scatter" | Bipartite bottleneck→substitute network + written report; heatmap exists but disabled | Build the **bipartite network + report**; heatmap as a toggle since the code exists |
| 6 | Demand Forecast = department **growth-% slider** (5/10/15/20) | Student rank-1/2/3 **preference aggregation** — and, separately, a RandomForest enrollment forecaster trained in R (`model_data/demand_model_rf.rds`) that was never wired into the dashboard | Do **all three**: generate synthetic preferences, run the exact `DemandAggregator` formulas, pre-compute the table at 0/5/10/15/20% growth for the slider, and reproduce the R-side forecaster so its "MAE 11.16, 28.7% over naive" headline is measured rather than quoted |
| 7 | Program metrics filter = "multi-select for comparison", charts = radar/spider | Multi-select ✓, but **no charts at all** — numeric cards only | Keep cards as the parity view; add a radar chart as the comparison affordance the blueprint asks for |
| 8 | 6 terms, Fall/Spring only | 21 term files across **five** seasons — Fall, Spring, Summer 1, Summer 2, Summer Full | Follow the code: **25 terms, five academic years, all five seasons** (Fall 2021 – Summer Full 2025), matching the original's CourseLeaf window. Tab 7 explicitly wants Fall/Spring/Summer comparison, which Fall/Spring-only data cannot supply; and the demand forecaster's edge over its naive lag baseline scales with how many same-season observations per course exist, so window length is not cosmetic |
| 9 | ~800 courses, ~80 programs | 8,587 courses, 1,017 programs | Generate at **blueprint scale** for browser payload; preserve real *ratios* and state real scale in the disclaimer |
| 10 | Tabs 7–9 from "the Plotly Dash dashboard" | **Not in this codebase** — no Dash imports anywhere, no `responsiveness` string anywhere | Build from the blueprint's written spec, applied literally (40/30/30 weighting, 36% at-capacity, 31.9% waitlist). Classification thresholds are unspecified → terciles of the observed distribution rather than invented cut-points. One caveat is surfaced rather than silently corrected: all three weighted components measure demand pressure, not response, so a low-demand department scores well by doing nothing. A `demand_response_correlation` diagnostic that isolates response is reported alongside but kept out of the score |
| 11 | Cascade grey-out | Not mentioned in the blueprint at all | **Keep it** — it is the single most distinctive interaction in the original |
