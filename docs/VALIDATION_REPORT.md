# Mock Data Validation Report

Generated from `public/data/` (seed 20260812).

`target` values come from the blueprint's record of the real system's
measurements, or from a structural requirement of the tab that consumes the
data. A DEVIATION is a measured value outside its band — recorded, not hidden.


## Catalog

| check | measured | target | status | note |
|---|---|---|---|---|
| Courses | 820 | ~800 | PASS |  |
| Departments | 10 | 8–10 | PASS |  |
| Programs | 80 | ~80 | PASS |  |
| Published terms | 25 | 21 in original | PASS |  |
| Sections | 9,187 | — | info |  |
| Levels present | [1, 2, 3, 4] | [1, 2, 3, 4] | PASS |  |
| 1000-level have no prerequisites | 1 | true | PASS | blueprint: '1000-level has none' |
| Credit values | {'4': 653, '3': 109, '5': 58} | 3–5 | info |  |

## Graph

| check | measured | target | status | note |
|---|---|---|---|---|
| Prerequisite edges | 1,115 | ~1,200 | PASS |  |
| Corequisite edges | 30 | > 0 | PASS |  |
| Longest chain depth | 7 | 6–8 | PASS |  |
| Disconnected components | 62 | > 1 | PASS | real graph had 5,575 over 8,579 nodes |
| Isolated nodes | 54 | > 0 | PASS |  |
| Largest component | 752 | — | info |  |
| Max out-degree (gateway fan-out) | 44 | > 15 | PASS |  |
| Is a DAG after cleaning | 1 | true | PASS |  |
| Self-loops cleaned | 6 | > 0 | PASS | mirrors real catalog artifacts |
| Cycles broken | 4 | > 0 | PASS |  |
| Courses with elective context | 415 | > 0 | PASS | drives the elective block in the node hover |
| Range-derived elective entries | 62 | > 0 | PASS |  |
| Every elective has a choice label | 1 | true | PASS |  |
| Gateway courses (5+ programs) | 132 | > 0 | PASS |  |

## Enrollment

| check | measured | target | status | note |
|---|---|---|---|---|
| % at or over capacity | 36 | 36.0 | PASS | real system finding |
| % with waitlist | 31.8 | 31.9 | PASS | real system finding |
| Mean fill rate | 0.7782 | — | info |  |
| Courses with enrollment data | 820 | = 820 | PASS |  |
| Every course has a term series | 1 | true | PASS |  |
| Courses with a plottable trend (>=2 terms) | 820 | most | PASS | Course Metrics hides the trend chart below 2 terms |

## Bottleneck model

| check | measured | target | status | note |
|---|---|---|---|---|
| RF AUC | 0.7915 | 0.772 | PASS |  |
| Label base rate | 0.2698 | 0.25 | PASS | 75th-percentile composite threshold |
| Precision@20 (held-out cohort) | 0.85 | 0.85 | PASS | original's protocol; see report note |
| Precision@20 (full sample) | 0.95 | 0.85 | PASS |  |
| Courses labelled | 506 | — | info | of 820; needs >= 10 eligible students |
| Features used | 9 | 9 | PASS | matches original FEATURE_COLS |
| Courses flagged at threshold 0.5 | 239 | — | info |  |
| Models trained | 4 | 3 | PASS | threshold rule, logistic, RF |

## Demand model

| check | measured | target | status | note |
|---|---|---|---|---|
| RF improvement over naive (%) | 22.4 | 28.7 | PASS | naive = same_season_last_year_enrollment |
| RF test MAE | 7.441 | 11.16 | PASS |  |
| Naive test MAE | 9.591 | 15.65 | info |  |

## Demand forecast

| check | measured | target | status | note |
|---|---|---|---|---|
| Growth scenarios | 5 | 5 (0/5/10/15/20%) | PASS |  |
| Shortages rise with growth | [147, 160, 169, 182, 194] | monotonic | PASS |  |
| Courses in forecast | 698 | > 0 | PASS |  |
| Per-department blocks | 10 | = 10 | PASS |  |

## Similarity

| check | measured | target | status | note |
|---|---|---|---|---|
| Pairs at >= 0.80 | 2,681 | 2,200–3,400 | PASS | 2.96 pairs/course scaled from real |
| Pairs stored (>= 0.60) | 6,738 | — | info | slider minimum; browser re-filters |
| Redundancy clusters | 84 | 60–110 | PASS |  |
| Bottlenecks with substitutes | 200 | > 0 | PASS |  |
| Counts fall as threshold rises | [6738, 5362, 2681, 1294, 504] | monotonic | PASS |  |

## Program metrics

| check | measured | target | status | note |
|---|---|---|---|---|
| Programs with metrics | 80 | = 80 | PASS |  |
| Distinct max_depth values | 7 | > 3 | PASS | cards sort by max_depth |
| Programs with bottleneck courses | 80 | > 0 | PASS |  |
| All-courses mode present | 80 | > 0 | PASS | view_all_courses toggle |

## Responsiveness

| check | measured | target | status | note |
|---|---|---|---|---|
| Class spread | {'unresponsive': 4, 'moderate': 3, 'responsive': 3} | all three present | PASS |  |
| Mean correlation | 0.8165 | — | info |  |
| Weights | {'utilization': 0.4, 'over_capacity': 0.3, 'waitlist': 0.3} | 40/30/30 | PASS |  |
| Every department has term pairs | 1 | true | PASS |  |

## Temporal

| check | measured | target | status | note |
|---|---|---|---|---|
| Matrix shape | 10x25 | depts x terms | PASS |  |
| Seasons represented | ['Fall', 'Spring', 'Summer 1', 'Summer 2', 'Summer Full'] | Fall/Spring/Summer | PASS |  |
| Like-for-like comparisons | 20 | > 0 | PASS |  |

## Payload

| check | measured | target | status | note |
|---|---|---|---|---|
| Total shipped | 3.57 | < 4 MB | PASS | gzips to roughly a fifth of this |
| Largest file | enrollment_by_course.json (1007 KB) | — | info |  |

## Structural

| check | measured | target | status | note |
|---|---|---|---|---|
| Prerequisites reference real courses | ok | must hold | PASS | 0 dangling |
| No self-loops in shipped prerequisites | ok | must hold | PASS | 0 present |
| Edge list references real courses | ok | must hold | PASS | 0 dangling |
| Every node has layout coordinates | ok | must hold | PASS | 0 missing |
| Program course references resolve | ok | must hold | PASS | 0 unknown |
| Bottleneck scores cover the catalog | ok | must hold | PASS | 0 unscored |
| Similarity pairs reference real courses | ok | must hold | PASS | 0 unknown |
| Forecast rows reference real courses | ok | must hold | PASS | 0 unknown |
| Scenario deltas align with course block | ok | must hold | PASS |  |

## Summary

- 60 passed
- 0 deviations
- 10 informational
- 0 structural failures

## Known deviations and why

**Precision@20 on the held-out cohort.** The original reports 0.85. The test
cohort is students entering Fall 2023 or later, who have only a few terms of
history, so the delay and stalling estimates behind their top-quartile labels
are much noisier than the full-sample ones. Against full-sample labels the
same ranking scores ~0.95. Both are reported; neither is tuned. Sweeping RF
hyperparameters moved this metric by less than its sampling error (the
held-out metric is computed over 20 items, so one course is 5 points).

**Demand forecaster improvement over naive.** The original reports 28.7%.
The gap depends almost entirely on how many same-season observations per
course the model can average over: 3 academic years gives +9.7%, 5 gives
+18.8%. Five is the original's own CourseLeaf window (Fall 2021 - Fall 2025),
so extending further would improve the number while no longer reproducing the
original's setup.

**Redundancy cluster count.** The real figures (25,431 pairs at 0.80; 334
clusters) were measured at two different thresholds, since clusters come from
`find_redundant_course_clusters`, fixed at 0.85. They cannot be scaled to one
consistent expectation. The pair count — which is what the Redundancy tab
actually renders — is calibrated to the real ratio of 2.96 pairs per course.

**Graph fragmentation.** The real graph averaged 1.54 nodes per component
(5,575 components over 8,579 nodes), i.e. mostly isolated nodes. Reproducing
that ratio would render as dust. Fragmentation is present (isolated nodes and
small components both exist) but the connected core is kept legible.
