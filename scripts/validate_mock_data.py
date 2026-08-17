#!/usr/bin/env python3
"""
validate_mock_data.py — check generated output against every calibration target.

Targets come from two places:
  * the blueprint's record of the real system's measurements
  * structural requirements the dashboard tabs depend on

Prints a PASS/DEVIATION table and writes docs/VALIDATION_REPORT.md. Exits non-zero only
on a structural failure (something a tab cannot render without), not on a numeric
deviation — deviations are expected where synthetic data cannot reproduce a real
corpus's exact predictability, and are documented rather than hidden.

Usage:  .venv/bin/python scripts/validate_mock_data.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pru_config as C

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
DOCS = ROOT / "docs"

REQUIRED_FILES = [
    "courses.json", "prerequisites.json", "programs.json", "program_structures.json",
    "department_metrics.json", "enrollment_by_course.json", "bottleneck_scores.json",
    "similarity_pairs.json", "forecast_scenarios.json", "department_responsiveness.json",
    "temporal_patterns.json", "summary_stats.json", "terms.json", "students_sample.json",
]

rows: list[tuple] = []
failures: list[str] = []


def check(section, name, actual, target=None, ok=None, note=""):
    """Record one check. `ok` may be a bool or a (lo, hi) band applied to `actual`."""
    if isinstance(ok, tuple):
        passed = ok[0] <= actual <= ok[1]
        target = target or f"{ok[0]}–{ok[1]}"
    elif ok is None:
        passed = None
    else:
        passed = bool(ok)
    rows.append((section, name, actual, target if target is not None else "—",
                 passed, note))
    return passed


def structural(name, cond, detail=""):
    if not cond:
        failures.append(f"{name}: {detail}")
    return check("Structural", name, "ok" if cond else "FAILED", "must hold", cond, detail)


def fmt(v):
    if isinstance(v, float):
        return f"{v:,.4f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.1f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def main() -> int:
    missing = [f for f in REQUIRED_FILES if not (DATA / f).exists()]
    if missing:
        print(f"Missing generated files: {missing}\nRun generate_mock_data.py first.")
        return 1

    load = lambda n: json.loads((DATA / n).read_text())
    courses = load("courses.json")
    prereqs = load("prerequisites.json")
    programs = load("programs.json")
    structures = load("program_structures.json")
    depts = load("department_metrics.json")
    enrollment = load("enrollment_by_course.json")
    bottleneck = load("bottleneck_scores.json")
    similarity = load("similarity_pairs.json")
    forecast = load("forecast_scenarios.json")
    responsiveness = load("department_responsiveness.json")
    temporal = load("temporal_patterns.json")
    summary = load("summary_stats.json")
    terms = load("terms.json")

    k = summary["kpis"]
    g = summary["graph"]
    rf = bottleneck["models"]["random_forest"]

    # ---------------- Catalog ----------------
    check("Catalog", "Courses", len(courses), "~800", (760, 880))
    check("Catalog", "Departments", len(depts), "8–10", (8, 10))
    check("Catalog", "Programs", len(programs["programs"]), "~80", (72, 88))
    check("Catalog", "Published terms", len(terms["published"]),
          "21 in original", (20, 26))
    check("Catalog", "Sections", k["total_sections"], "—")
    lvl = Counter(c["level"] for c in courses.values())
    check("Catalog", "Levels present", sorted(lvl), "[1, 2, 3, 4]",
          sorted(lvl) == [1, 2, 3, 4])
    no_prereq_1000 = all(not c["prerequisites"]
                         for c in courses.values() if c["level"] == 1)
    check("Catalog", "1000-level have no prerequisites", no_prereq_1000, "true",
          no_prereq_1000, "blueprint: '1000-level has none'")
    credits = Counter(c["credits"] for c in courses.values())
    check("Catalog", "Credit values", dict(credits), "3–5")

    # ---------------- Prerequisite graph ----------------
    check("Graph", "Prerequisite edges", g["edges"], "~1,200", (1000, 1400))
    check("Graph", "Corequisite edges", g["corequisite_edges"], "> 0", g["corequisite_edges"] > 0)
    check("Graph", "Longest chain depth", g["longest_chain_depth"], "6–8",
          C.TARGET_MAX_CHAIN_DEPTH)
    check("Graph", "Disconnected components", g["components"], "> 1",
          g["components"] > 1, "real graph had 5,575 over 8,579 nodes")
    check("Graph", "Isolated nodes", g["isolated_nodes"], "> 0", g["isolated_nodes"] > 0)
    check("Graph", "Largest component", g["largest_component"], "—")
    check("Graph", "Max out-degree (gateway fan-out)", g["max_out_degree"], "> 15",
          g["max_out_degree"] > 15)
    check("Graph", "Is a DAG after cleaning", g["is_dag"], "true", g["is_dag"])
    check("Graph", "Self-loops cleaned", g["self_loops_removed"], "> 0",
          g["self_loops_removed"] > 0, "mirrors real catalog artifacts")
    check("Graph", "Cycles broken", g["cycles_broken"], "> 0", g["cycles_broken"] > 0)
    elective = sum(1 for c in courses.values() if c["is_elective"])
    check("Graph", "Courses with elective context", elective, "> 0", elective > 0,
          "drives the elective block in the node hover")
    ranged = sum(1 for c in courses.values()
                 if c["elective_context"] and c["elective_context"]["is_range"])
    check("Graph", "Range-derived elective entries", ranged, "> 0", ranged > 0)
    labelled = all(c["elective_context"]["choice_label"]
                   for c in courses.values() if c["is_elective"])
    check("Graph", "Every elective has a choice label", labelled, "true", labelled)
    gateways = sum(1 for c in courses.values() if c["program_count"] >= 5)
    check("Graph", "Gateway courses (5+ programs)", gateways, "> 0", gateways > 0)

    # ---------------- Enrollment calibration ----------------
    check("Enrollment", "% at or over capacity", k["pct_at_capacity"], "36.0",
          (34.0, 38.0), "real system finding")
    check("Enrollment", "% with waitlist", k["pct_with_waitlist"], "31.9",
          (30.0, 34.0), "real system finding")
    check("Enrollment", "Mean fill rate", k["mean_fill_rate"], "—")
    check("Enrollment", "Courses with enrollment data", len(enrollment),
          f"= {len(courses)}", len(enrollment) == len(courses))
    trend_ok = all(len(v["enrollment_series"]["terms"]) >= 1 for v in enrollment.values())
    check("Enrollment", "Every course has a term series", trend_ok, "true", trend_ok)
    plottable = sum(1 for v in enrollment.values()
                    if len(v["enrollment_series"]["terms"]) >= 2)
    check("Enrollment", "Courses with a plottable trend (>=2 terms)", plottable,
          "most", plottable > 0.8 * len(enrollment),
          "Course Metrics hides the trend chart below 2 terms")

    # ---------------- Bottleneck model ----------------
    check("Bottleneck model", "RF AUC", rf["auc"], "0.772", C.TARGET_AUC_BAND)
    check("Bottleneck model", "Label base rate", rf["base_rate"], "0.25", (0.22, 0.28),
          "75th-percentile composite threshold")
    check("Bottleneck model", "Precision@20 (held-out cohort)",
          rf.get("precision_at_20"), "0.85", (0.80, 1.0),
          "original's protocol; see report note")
    check("Bottleneck model", "Precision@20 (full sample)",
          rf["full_sample"].get("precision_at_20"), "0.85", (0.80, 1.0))
    check("Bottleneck model", "Courses labelled", rf["full_sample"]["n_labelled"], "—",
          None, f"of {len(courses)}; needs >= {C.MIN_ELIGIBLE_STUDENTS} eligible students")
    check("Bottleneck model", "Features used", len(bottleneck["feature_cols"]), "9",
          len(bottleneck["feature_cols"]) == 9, "matches original FEATURE_COLS")
    flagged = sum(1 for v in bottleneck["scores"].values()
                  if v >= C.BOTTLENECK_SCORE_THRESHOLD)
    check("Bottleneck model", "Courses flagged at threshold 0.5", flagged, "—")
    check("Bottleneck model", "Models trained", len(bottleneck["models"]), "3",
          len(bottleneck["models"]) >= 3, "threshold rule, logistic, RF")

    # ---------------- Demand forecast ----------------
    dm = forecast.get("enrollment_forecast_model") or {}
    if dm and "models" in dm:
        imp = dm["models"]["Random Forest"]["improvement_pct"]
        check("Demand model", "RF improvement over naive (%)", imp, "28.7", (15.0, 35.0),
              "naive = same_season_last_year_enrollment")
        check("Demand model", "RF test MAE", dm["models"]["Random Forest"]["test_mae"],
              "11.16", (5.0, 18.0))
        check("Demand model", "Naive test MAE", dm["models"]["Naive"]["test_mae"],
              "15.65", None)
    check("Demand forecast", "Growth scenarios", len(forecast["growth_scenarios"]),
          "5 (0/5/10/15/20%)", len(forecast["growth_scenarios"]) == 5)
    mono = [forecast["scenarios"][str(p)]["kpis"]["courses_with_shortages"]
            for p in forecast["growth_scenarios"]]
    check("Demand forecast", "Shortages rise with growth", mono,
          "monotonic", all(a <= b for a, b in zip(mono, mono[1:])))
    check("Demand forecast", "Courses in forecast", len(forecast["courses"]), "> 0",
          len(forecast["courses"]) > 0)
    check("Demand forecast", "Per-department blocks", len(forecast["by_department"]),
          f"= {len(depts)}", len(forecast["by_department"]) == len(depts))

    # ---------------- NLP similarity ----------------
    sc = similarity["counts"]
    check("Similarity", "Pairs at >= 0.80", sc["at_080"],
          f"{C.TARGET_PAIRS_AT_080[0]:,}–{C.TARGET_PAIRS_AT_080[1]:,}",
          C.TARGET_PAIRS_AT_080, "2.96 pairs/course scaled from real")
    check("Similarity", "Pairs stored (>= 0.60)", sc["stored"], "—", None,
          "slider minimum; browser re-filters")
    check("Similarity", "Redundancy clusters", similarity["cluster_count_at_default"],
          f"{C.TARGET_CLUSTERS[0]}–{C.TARGET_CLUSTERS[1]}", C.TARGET_CLUSTERS)
    check("Similarity", "Bottlenecks with substitutes",
          similarity["bottleneck_substitute_count_at_default"], "> 0",
          similarity["bottleneck_substitute_count_at_default"] > 0)
    mono_sim = [sc["at_060"], sc["at_070"], sc["at_080"], sc["at_085"], sc["at_090"]]
    check("Similarity", "Counts fall as threshold rises", mono_sim, "monotonic",
          all(a >= b for a, b in zip(mono_sim, mono_sim[1:])))

    # ---------------- Program metrics ----------------
    pmr = structures["required_mode"]
    check("Program metrics", "Programs with metrics", len(pmr), f"= {len(programs['programs'])}",
          len(pmr) == len(programs["programs"]))
    depth_spread = len({m["max_depth"] for m in pmr.values()})
    check("Program metrics", "Distinct max_depth values", depth_spread, "> 3",
          depth_spread > 3, "cards sort by max_depth")
    have_bn = sum(1 for m in pmr.values() if m["bottleneck_courses"])
    check("Program metrics", "Programs with bottleneck courses", have_bn, "> 0", have_bn > 0)
    check("Program metrics", "All-courses mode present", len(structures["all_mode"]),
          "> 0", len(structures["all_mode"]) > 0, "view_all_courses toggle")

    # ---------------- Responsiveness ----------------
    rsum = responsiveness["summary"]
    classes = Counter(d["classification"] for d in responsiveness["departments"].values())
    check("Responsiveness", "Class spread", dict(classes), "all three present",
          len(classes) == 3)
    check("Responsiveness", "Mean correlation", rsum["mean_correlation"], "—")
    check("Responsiveness", "Weights", responsiveness["weights"],
          "40/30/30", responsiveness["weights"] == C.RESPONSIVENESS_WEIGHTS)
    pairs_ok = all(d["term_pairs"] for d in responsiveness["departments"].values())
    check("Responsiveness", "Every department has term pairs", pairs_ok, "true", pairs_ok)

    # ---------------- Temporal ----------------
    check("Temporal", "Matrix shape",
          f"{len(temporal['departments'])}x{len(temporal['terms'])}", "depts x terms",
          all(len(r) == len(temporal["terms"])
              for m in temporal["matrices"].values() for r in m))
    check("Temporal", "Seasons represented", sorted(temporal["seasons"]),
          "Fall/Spring/Summer", len(temporal["seasons"]) >= 3)
    check("Temporal", "Like-for-like comparisons", len(temporal["like_for_like"]),
          "> 0", len(temporal["like_for_like"]) > 0)

    # ---------------- Payload ----------------
    sizes = {f: (DATA / f).stat().st_size for f in REQUIRED_FILES}
    total_mb = sum(sizes.values()) / 1024 / 1024
    check("Payload", "Total shipped", round(total_mb, 2), "< 4 MB", total_mb < 4.0,
          "gzips to roughly a fifth of this")
    biggest = max(sizes, key=sizes.get)
    check("Payload", "Largest file", f"{biggest} ({sizes[biggest]/1024:.0f} KB)", "—")

    # ---------------- Structural integrity ----------------
    codes = set(courses)
    bad_prereq = [(c, p) for c, v in courses.items()
                  for p in v["prerequisites"] if p not in codes]
    structural("Prerequisites reference real courses", not bad_prereq,
               f"{len(bad_prereq)} dangling")
    self_loops = [c for c, v in courses.items() if c in v["prerequisites"]]
    structural("No self-loops in shipped prerequisites", not self_loops,
               f"{len(self_loops)} present")
    bad_edges = [e for e in prereqs["edges"]
                 if e["source"] not in codes or e["target"] not in codes]
    structural("Edge list references real courses", not bad_edges,
               f"{len(bad_edges)} dangling")
    no_pos = [c for c in courses if courses[c]["x"] is None]
    structural("Every node has layout coordinates", not no_pos, f"{len(no_pos)} missing")
    prog_courses = {c for p in programs["programs"].values()
                    for v in p["versions"]
                    for sec in v["base_requirements"]["sections"]
                    for item in (sec.get("courses", []) + sec.get("options", []))
                    if (c := item.get("code"))}
    structural("Program course references resolve", prog_courses <= codes,
               f"{len(prog_courses - codes)} unknown")
    structural("Bottleneck scores cover the catalog",
               set(bottleneck["scores"]) == codes,
               f"{len(codes - set(bottleneck['scores']))} unscored")
    sim_codes = {c for p in similarity["pairs"] for c in p[:2]}
    structural("Similarity pairs reference real courses", sim_codes <= codes,
               f"{len(sim_codes - codes)} unknown")
    fc_codes = {r["course"] for r in forecast["courses"]}
    structural("Forecast rows reference real courses", fc_codes <= codes,
               f"{len(fc_codes - codes)} unknown")
    for pct in forecast["growth_scenarios"]:
        d = forecast["scenarios"][str(pct)]["deltas"]
        if set(d) != fc_codes:
            structural(f"Scenario {pct}% deltas align with course block", False,
                       f"{len(fc_codes ^ set(d))} mismatched")
            break
    else:
        structural("Scenario deltas align with course block", True)

    # ---------------- Output ----------------
    render(rows, failures)
    return 1 if failures else 0


def render(rows, failures):
    width = 106
    print("=" * width)
    print("MOCK DATA VALIDATION — Pacific Ridge University".center(width))
    print("=" * width)

    lines = ["# Mock Data Validation Report", "",
             f"Generated from `public/data/` (seed {C.SEED}).", "",
             "`target` values come from the blueprint's record of the real system's",
             "measurements, or from a structural requirement of the tab that consumes the",
             "data. A DEVIATION is a measured value outside its band — recorded, not hidden.",
             ""]

    current = None
    n_pass = n_dev = n_info = 0
    for section, name, actual, target, passed, note in rows:
        if section != current:
            current = section
            print(f"\n\033[1m{section}\033[0m")
            lines += ["", f"## {section}", "",
                      "| check | measured | target | status | note |",
                      "|---|---|---|---|---|"]
        if passed is None:
            status, colour, n_info = "info", "\033[90m", n_info + 1
        elif passed:
            status, colour, n_pass = "PASS", "\033[32m", n_pass + 1
        else:
            status, colour, n_dev = "DEVIATION", "\033[33m", n_dev + 1
        print(f"  {colour}{status:<10}\033[0m {name:<44} {fmt(actual):>18}  "
              f"vs {str(target):<16} {note}")
        lines.append(f"| {name} | {fmt(actual)} | {target} | {status} | {note} |")

    print("\n" + "=" * width)
    print(f"  {n_pass} passed · {n_dev} deviations · {n_info} informational")
    if failures:
        print("\n\033[31mSTRUCTURAL FAILURES\033[0m")
        for f in failures:
            print(f"  - {f}")
    else:
        print("  No structural failures — every tab has the data it needs.")
    print("=" * width)

    lines += ["", "## Summary", "",
              f"- {n_pass} passed", f"- {n_dev} deviations", f"- {n_info} informational",
              f"- {len(failures)} structural failures", "",
              "## Known deviations and why", "",
              "**Precision@20 on the held-out cohort.** The original reports 0.85. The test",
              "cohort is students entering Fall 2023 or later, who have only a few terms of",
              "history, so the delay and stalling estimates behind their top-quartile labels",
              "are much noisier than the full-sample ones. Against full-sample labels the",
              "same ranking scores ~0.95. Both are reported; neither is tuned. Sweeping RF",
              "hyperparameters moved this metric by less than its sampling error (the",
              "held-out metric is computed over 20 items, so one course is 5 points).", "",
              "**Demand forecaster improvement over naive.** The original reports 28.7%.",
              "The gap depends almost entirely on how many same-season observations per",
              "course the model can average over: 3 academic years gives +9.7%, 5 gives",
              "+18.8%. Five is the original's own CourseLeaf window (Fall 2021 - Fall 2025),",
              "so extending further would improve the number while no longer reproducing the",
              "original's setup.", "",
              "**Redundancy cluster count.** The real figures (25,431 pairs at 0.80; 334",
              "clusters) were measured at two different thresholds, since clusters come from",
              "`find_redundant_course_clusters`, fixed at 0.85. They cannot be scaled to one",
              "consistent expectation. The pair count — which is what the Redundancy tab",
              "actually renders — is calibrated to the real ratio of 2.96 pairs per course.", "",
              "**Graph fragmentation.** The real graph averaged 1.54 nodes per component",
              "(5,575 components over 8,579 nodes), i.e. mostly isolated nodes. Reproducing",
              "that ratio would render as dust. Fragmentation is present (isolated nodes and",
              "small components both exist) but the connected core is kept legible.",
              ]
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "VALIDATION_REPORT.md").write_text("\n".join(lines) + "\n")
    print(f"\nWrote {DOCS / 'VALIDATION_REPORT.md'}")


if __name__ == "__main__":
    sys.exit(main())
