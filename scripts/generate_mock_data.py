#!/usr/bin/env python3
"""
generate_mock_data.py — Phase 1 of the Fellowship Dashboard public mock rebuild.

Generates every JSON file the React dashboard consumes, for the fictional
Pacific Ridge University. Fully deterministic given pru_config.SEED.

Design principle: reproduce the original system's *methodology*, not just its output
shape. Where the original computed something with a real algorithm (NetworkX
betweenness, a RandomForest over 9 features, TF-IDF cosine similarity, Pearson
correlation), this script runs that same real algorithm over synthetic inputs.
The reported model metrics are therefore measured, not asserted.

Pipeline
    1  terms                     8 published terms + deeper student-pathway window
    2  courses                   ~820 courses across 10 departments, topic-tagged
    3  prerequisite graph        ~1,200 edges, designed component structure
    4  programs                  80 programs, versioned, with concentrations
    5  sections + enrollment     calibrated to 36% at-capacity / 31.9% waitlist
    6  student pathways          8,000 students walking the graph under course friction
    7  ground truth              median_delay + stalling_rate -> composite -> 75th pctile
    8  features                  the original's exact 9 FEATURE_COLS
    9  RandomForest              temporal cohort split, real AUC / Precision@20
   10  similarity                TF-IDF cosine over generated descriptions
   11  program metrics           exact replication of calculate_program_metrics
   12  demand forecast           exact DemandAggregator formulas x 5 growth scenarios
   13  responsiveness            Pearson corr + 40/30/30 weighted score
   14  temporal patterns         department x term matrices
   15  summary stats             executive KPIs
   16  graph layout              precomputed hierarchical positions
   17  emit                      public/data/*.json + validation report

Usage
    .venv/bin/python scripts/generate_mock_data.py
    .venv/bin/python scripts/generate_mock_data.py --quick    # 1,500 students, faster
"""

from __future__ import annotations

import argparse
import json
import os
import math
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import networkx as nx

import pru_config as C

ROOT = Path(__file__).resolve().parent.parent
DATA_OUT = ROOT / "public" / "data"
INTERMEDIATE = Path(__file__).resolve().parent / "intermediate"

_t0 = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - _t0:6.1f}s] {msg}", flush=True)


# ============================================================
# Term utilities — replicate utils/term_utils.py semantics exactly
# ============================================================

def build_term_code(academic_year: int, season: str) -> str:
    return f"{academic_year}{C.SEASON_CODE[season]}"


def term_display(code: str) -> str:
    """202310 -> 'Fall 2022'. Fall belongs to the prior calendar year."""
    ay = int(code[:4])
    season = {v: k for k, v in C.SEASON_CODE.items()}[code[4:]]
    year = ay - 1 if season == "Fall" else ay
    return f"{season} {year}"


def term_season(code: str) -> str:
    return {v: k for k, v in C.SEASON_CODE.items()}[code[4:]]


def semester_index(term_code: int) -> int:
    """Copied from the original utils/term_utils.py."""
    year = term_code // 100
    sub = term_code % 100
    if sub < 20:
        return year * 2          # Fall
    elif sub < 40:
        return year * 2 + 1      # Spring
    else:
        return year * 2 + 1      # Summer shares the Spring slot


def term_delay(term_a: int, term_b: int) -> int:
    """Copied from the original. Clamped at 0."""
    return max(0, semester_index(term_b) - semester_index(term_a))


def is_summer(code: str) -> bool:
    return term_season(code) in C.SUMMER_SEASONS


def build_terms() -> tuple[list[str], list[str]]:
    """Return (pathway_terms, published_terms). Pathway window is deeper."""
    all_terms = sorted(
        build_term_code(ay, season)
        for ay in C.PATHWAY_ACADEMIC_YEARS
        for season in C.SEASON_ORDER
    )
    published = sorted(
        build_term_code(ay, season)
        for ay in C.PUBLISHED_ACADEMIC_YEARS
        for season in C.SEASON_ORDER
    )
    all_terms = [t for t in all_terms if t <= published[-1]]
    return all_terms, published


# ============================================================
# 2. Courses
# ============================================================

def build_subtopics() -> dict:
    """Split each topic into overlapping sub-topics.

    This is what gives the similarity matrix genuine cluster structure. Every course in
    a topic shares three 'anchor' keywords; each sub-topic adds its own slice of the
    remaining pool and its own title head. Two courses in the same sub-topic therefore
    share most of their vocabulary (cosine ~0.85+), two in the same topic but different
    sub-topics share only the anchors (~0.65-0.80), and two in unrelated topics share
    almost nothing. That is the shape the real sentence-transformer output had, and it
    is what makes "content-equivalent alternative" a meaningful claim in Tab 4.
    """
    subtopics = {}
    for topic, spec in C.TOPICS.items():
        kws = spec["keywords"]
        anchors = kws[:3]
        rest = kws[3:] or kws
        n_sub = 3 if len(rest) >= 5 else 2
        heads = spec["title_heads"]
        subtopics[topic] = [
            {
                "key": f"{topic}#{i}",
                "anchors": anchors,
                "slice": rest[i::n_sub] or rest,
                "heads": heads[i::n_sub] or heads,
            }
            for i in range(n_sub)
        ]
    return subtopics


def generate_courses(rng: random.Random, np_rng: np.random.Generator,
                     subtopics: dict) -> dict:
    """Build the course catalog. Each course carries a topic + sub-topic tag that
    drives its title, description and keyword set."""
    topics_by_dept = defaultdict(list)
    for topic, spec in C.TOPICS.items():
        for d in spec["depts"]:
            topics_by_dept[d].append(topic)

    courses: dict[str, dict] = {}
    levels = list(C.LEVEL_WEIGHTS)
    level_p = [C.LEVEL_WEIGHTS[l] for l in levels]

    for dept in C.DEPARTMENTS:
        code = dept["code"]
        dept_topics = topics_by_dept[code]
        # Deterministic per-level sequence counters so codes look like a real catalog
        seq = {l: 0 for l in levels}
        n_by_level = np_rng.multinomial(dept["n_courses"], level_p)

        for level, n in zip(levels, n_by_level):
            for _ in range(int(n)):
                seq[level] += 1
                # Catalog numbers step by 10 with jitter, e.g. CS 2140, CS 2210
                number = level * 1000 + min(999, seq[level] * 10 + rng.choice([0, 1, 2, 5]))
                course_code = f"{code} {number}"
                if course_code in courses:
                    continue

                topic = rng.choice(dept_topics)
                spec = C.TOPICS[topic]
                sub = rng.choice(subtopics[topic])

                head = rng.choice(sub["heads"])
                title = _make_title(rng, head, level, spec)

                # Keywords: all anchors + most of the sub-topic slice
                pool = sub["slice"]
                k = min(len(pool), max(2, len(pool) - 1))
                kws = list(sub["anchors"]) + rng.sample(pool, k=k)

                description = rng.choice(C.DESCRIPTION_TEMPLATES).format(
                    kw1=kws[0], kw2=kws[1], kw3=kws[2],
                    kw4=kws[3] if len(kws) > 3 else kws[0],
                )

                # Content-distinctive courses carry a specialization qualifier that
                # separates them from their sub-topic siblings; the rest are the
                # near-duplicate population the redundancy analysis is meant to surface.
                specialization = None
                if rng.random() < C.DISTINCTIVE_SHARE:
                    specialization = rng.choice(C.SPECIALIZATIONS)
                    title = f"{specialization} {title}"
                    description = (f"{description} Emphasis on {specialization.lower()} "
                                   f"applications of {kws[0]}.")
                # Credits: 4 is the modal value; labs and capstones vary
                credits = 4 if rng.random() < 0.72 else rng.choice([3, 3, 4, 5])

                courses[course_code] = {
                    "course_code": course_code,
                    "department": code,
                    "number": str(number),
                    "title": title,
                    "description": description,
                    "credits": str(credits),
                    "level": level,
                    "topic": topic,
                    "subtopic": sub["key"],
                    "specialization": specialization,
                    "keywords": sorted(set(kws)),
                    "prerequisites": [],
                    "corequisites": [],
                    "prerequisite_text": "",
                    "corequisite_text": "",
                    "prereq_logic": "NONE",
                    "catalog_years": [],
                }
    return courses


def _make_title(rng: random.Random, head: str, level: int, spec: dict) -> str:
    """Give related courses sequenced titles so a catalog reads plausibly."""
    r = rng.random()
    if level <= 2 and r < 0.30:
        return f"Introduction to {head}"
    if r < 0.45:
        return f"{head} {rng.choice([1, 2])}"
    if r < 0.60 and level >= 3:
        return f"Advanced {head}"
    if r < 0.70:
        return f"{head}: {rng.choice(spec['keywords']).title()}"
    return head


# ============================================================
# 3. Prerequisite graph
# ============================================================

def generate_prerequisites(courses: dict, rng: random.Random) -> None:
    """Attach prerequisites and corequisites in place.

    Component structure is designed rather than purely random: each department has a
    'spine' of chained courses that produces the 6-8 deep chains the real graph had,
    while the remaining courses attach sparsely or not at all. That leaves a realistic
    population of isolated nodes and small components without fragmenting the graph
    so badly that it becomes unreadable (the real graph averaged 1.54 nodes per
    component, which would render as mostly dust).
    """
    by_dept_level = defaultdict(list)
    for code, c in courses.items():
        by_dept_level[(c["department"], c["level"])].append(code)
    for key in by_dept_level:
        by_dept_level[key].sort()

    dept_cfg = {d["code"]: d for d in C.DEPARTMENTS}
    service_depts = [d["code"] for d in C.DEPARTMENTS if d["service"] >= 0.5]

    # --- Gateway courses: 1000-level courses that many programs will require ---
    gateways = []
    for dept in C.DEPARTMENTS:
        pool = by_dept_level[(dept["code"], 1)]
        if pool:
            k = 2 if dept["service"] >= 0.5 else 1
            gateways.extend(pool[:k])

    # --- Department spines: guarantee deep chains ---
    for dept in C.DEPARTMENTS:
        code = dept["code"]
        depth_target = 3 + int(round(dept["depth"] * 5))     # 3..8
        spine = []
        for level in (1, 2, 2, 3, 3, 4, 4, 4):
            pool = [c for c in by_dept_level[(code, level)] if c not in spine]
            if pool:
                spine.append(pool[len(spine) % len(pool)])
        spine = spine[:depth_target]
        for prev, nxt in zip(spine, spine[1:]):
            _add_prereq(courses, nxt, prev)

    # --- Bulk attachment ---
    for code, c in sorted(courses.items()):
        level = c["level"]
        dept = c["department"]
        cfg = dept_cfg[dept]
        if rng.random() > C.PREREQ_PROB_BY_LEVEL[level]:
            continue

        n_prereqs = rng.choices([1, 2, 3], weights=[0.35, 0.40, 0.25], k=1)[0]
        for _ in range(n_prereqs):
            if rng.random() < cfg["cross"] * 0.5 and service_depts:
                # Cross-department dependency, usually on a service department
                src_dept = rng.choice([d for d in service_depts if d != dept] or [dept])
                src_level = rng.choice([1, 1, 2])
            else:
                src_dept = dept
                src_level = rng.choice([l for l in range(1, level)] or [1])

            pool = by_dept_level[(src_dept, src_level)]
            if not pool:
                continue
            # Bias toward gateway courses so they accumulate high in-degree fan-out
            candidates = [p for p in pool if p in gateways] or pool
            if rng.random() < 0.45 and any(p in gateways for p in pool):
                pick = rng.choice([p for p in pool if p in gateways])
            else:
                pick = rng.choice(candidates if rng.random() < 0.3 else pool)
            _add_prereq(courses, code, pick)

    # --- Corequisite labs ---
    for dept in C.DEPARTMENTS:
        if not dept["labs"]:
            continue
        for level in (1, 2, 3):
            pool = by_dept_level[(dept["code"], level)]
            for parent in pool[: max(1, len(pool) // 6)]:
                lab_pool = [c for c in pool if c != parent and not courses[c]["corequisites"]]
                if lab_pool:
                    lab = rng.choice(lab_pool)
                    if lab not in courses[parent]["corequisites"]:
                        courses[parent]["corequisites"].append(lab)

    # --- Documented data-quality artifacts, mirroring the real catalog ---
    # The real courses.json contained self-loops (CS 2500 requires CS 2500) and cycles
    # that the pipeline had to break. Reproducing a handful keeps the "cleaned N
    # self-loops / M cycles" story in the dashboard honest.
    artifacts = {"self_loops": [], "cycles": []}
    deep = [c for c, d in courses.items() if d["prerequisites"] and d["level"] >= 3]
    for code in sorted(deep)[:6]:
        courses[code]["prerequisites"].append(code)
        artifacts["self_loops"].append(code)
    for code in sorted(deep)[10:16]:
        # The back-edge target must be 2000-level or above: a cycle onto a 1000-level
        # course would give it a prerequisite, breaking the rule that intro courses have
        # none. Real catalogues do contain such cases, but the blueprint states the rule
        # explicitly, so cycles are confined to courses where it does not apply.
        prereqs = [p for p in courses[code]["prerequisites"]
                   if p != code and courses[p]["level"] >= 2]
        if prereqs:
            back = prereqs[0]
            if code not in courses[back]["prerequisites"]:
                courses[back]["prerequisites"].append(code)
                artifacts["cycles"].append([code, back])

    # --- Finalize prereq text + logic ---
    for code, c in courses.items():
        c["prerequisites"] = sorted(set(c["prerequisites"]))
        c["corequisites"] = sorted(set(c["corequisites"]))
        real = [p for p in c["prerequisites"] if p != code]
        if not c["prerequisites"]:
            c["prereq_logic"] = "NONE"
        elif len(c["prerequisites"]) == 1:
            c["prereq_logic"] = "SINGLE"
        elif len(real) >= 3 and rng.random() < 0.35:
            c["prereq_logic"] = "COMPLEX"
        else:
            c["prereq_logic"] = rng.choice(["AND", "AND", "OR"])

        if c["prereq_logic"] == "NONE":
            c["prerequisite_text"] = ""
        elif c["prereq_logic"] == "OR":
            c["prerequisite_text"] = " or ".join(c["prerequisites"])
        elif c["prereq_logic"] == "COMPLEX":
            half = max(1, len(c["prerequisites"]) // 2)
            c["prerequisite_text"] = "; ".join([
                " or ".join(c["prerequisites"][:half]),
                " or ".join(c["prerequisites"][half:]),
            ])
        else:
            c["prerequisite_text"] = "; ".join(
                f"{p} with a minimum grade of C-" for p in c["prerequisites"])
        c["corequisite_text"] = "; ".join(c["corequisites"])

    return artifacts, gateways


def _add_prereq(courses: dict, code: str, prereq: str) -> None:
    if prereq == code:
        return
    if prereq not in courses[code]["prerequisites"]:
        courses[code]["prerequisites"].append(prereq)


def parse_prerequisite_groups(course: dict) -> list[set]:
    """Copied from the original utils/course_utils.py.

    Returns AND-groups of OR-alternatives. A student must satisfy at least one course
    from every group.
    """
    logic = course.get("prereq_logic", "NONE")
    prereqs = course.get("prerequisites", [])
    if logic == "NONE" or not prereqs:
        return []
    code = course.get("course_code", "")
    prereqs = [p for p in prereqs if p != code]     # drop self-references
    if not prereqs:
        return []
    if logic in ("SINGLE", "OR"):
        return [set(prereqs)]
    if logic == "AND":
        return [{p} for p in prereqs]
    if logic == "COMPLEX":
        groups = []
        for part in course.get("prerequisite_text", "").split(";"):
            codes = {p.strip() for p in part.split(" or ") if p.strip() in set(prereqs)}
            if codes:
                groups.append(codes)
        accounted = set().union(*groups) if groups else set()
        for missing in set(prereqs) - accounted:
            groups.append({missing})
        return groups or [{p} for p in prereqs]
    return []


def build_prereq_graph(courses: dict) -> tuple[nx.DiGraph, dict]:
    """Copied from the original bottleneck_pipeline.build_prereq_graph, including
    the heuristic cycle-breaking."""
    G = nx.DiGraph()
    G.add_nodes_from(courses)
    for code, c in courses.items():
        for prereq in c["prerequisites"]:
            if prereq in courses and prereq != code:
                G.add_edge(prereq, code)

    cleaning = {"self_loops_removed": 0, "cycles_broken": 0}
    cleaning["self_loops_removed"] = sum(
        1 for code, c in courses.items() if code in c["prerequisites"])

    # nx.simple_cycles returns cycles in an order that depends on string hashing, so it
    # varies between processes. Since each cycle is broken by removing its last->first
    # edge, that ordering decides *which* edges disappear — the resulting graph, and every
    # metric downstream of it, is otherwise not reproducible. (The original has the same
    # latent issue; see ORIGINAL_APP_MAP §8.3.) Each cycle is rotated to start at its
    # smallest node, then the list is sorted, before any edge is removed.
    def canonical(cycle: list) -> list:
        i = cycle.index(min(cycle))
        return cycle[i:] + cycle[:i]

    cycles = sorted((canonical(c) for c in nx.simple_cycles(G)),
                    key=lambda c: (len(c), c))
    for cycle in cycles:
        if len(cycle) >= 2 and G.has_edge(cycle[-1], cycle[0]):
            G.remove_edge(cycle[-1], cycle[0])
            cleaning["cycles_broken"] += 1
    cleaning["is_dag"] = nx.is_directed_acyclic_graph(G)
    return G, cleaning


# ============================================================
# 4. Programs
# ============================================================

def generate_programs(courses: dict, G: nx.DiGraph, gateways: list,
                      rng: random.Random) -> dict:
    """Build versioned program definitions using the original's section vocabulary."""
    by_dept = defaultdict(list)
    for code, c in courses.items():
        by_dept[c["department"]].append(code)
    for d in by_dept:
        by_dept[d].sort()

    dept_cfg = {d["code"]: d for d in C.DEPARTMENTS}
    degree_types, degree_p = zip(*C.DEGREE_MIX)

    # Allocate programs across departments proportional to catalog size
    weights = np.array([d["n_courses"] for d in C.DEPARTMENTS], dtype=float)
    weights /= weights.sum()
    alloc = np.maximum(1, np.round(weights * C.N_PROGRAMS).astype(int))
    while alloc.sum() > C.N_PROGRAMS:
        alloc[int(np.argmax(alloc))] -= 1
    while alloc.sum() < C.N_PROGRAMS:
        alloc[int(np.argmin(alloc))] += 1

    programs: dict[str, dict] = {}
    conc_quota = C.N_PROGRAMS_WITH_CONCENTRATIONS

    for dept, n_progs in zip(C.DEPARTMENTS, alloc):
        dcode = dept["code"]
        used_titles = set()
        for i in range(int(n_progs)):
            degree = rng.choices(degree_types, weights=degree_p, k=1)[0]
            focus = rng.choice(sorted({courses[c]["topic"] for c in by_dept[dcode]}))
            focus_label = focus.replace("_", " ").title()
            title_base = f"{dept['name']}"
            if i > 0:
                title_base = f"{dept['name']} — {focus_label}"
            if title_base in used_titles:
                title_base = f"{dept['name']} — {focus_label} {i}"
            used_titles.add(title_base)

            prog_code = f"{degree.upper()}-{dcode}{i + 1:02d}"
            title = f"{title_base}, {degree}"
            total_credits = {"BS": 128, "BA": 120, "MS": 32, "Minor": 20}[degree]

            give_conc = conc_quota > 0 and degree in ("BS", "MS") and i == 0
            if give_conc:
                conc_quota -= 1

            n_versions = rng.randint(*C.VERSIONS_PER_PROGRAM)
            versions = []
            for v in range(n_versions):
                start_year = 2019 + v
                end_year = start_year + 1
                version = {
                    "effective_period": {
                        "start_date": f"6/24/{start_year}",
                        "end_date": f"5/24/{end_year}" if v < n_versions - 1 else "5/24/2027",
                    },
                    "program_metadata": {
                        "code": prog_code,
                        "title": f"{prog_code}: {title}",
                        "degree_type": degree,
                        "transcript_title": title,
                        "total_credits": total_credits,
                        "colleges": {
                            "primary": dept["name"],
                            "departments": [dcode],
                        },
                    },
                    "base_requirements": {"sections": _build_sections(
                        dcode, degree, by_dept, dept_cfg, gateways, courses, rng, v,
                        prog_idx=i, focus=focus)},
                    "concentrations": _build_concentrations(
                        dcode, by_dept, courses, rng) if give_conc else {},
                }
                versions.append(version)

            programs[prog_code] = {
                "program_code": prog_code,
                "program_title": title,
                "department": dcode,
                "degree_type": degree,
                "version_count": n_versions,
                "versions": versions,
            }
    return programs


def _build_sections(dcode, degree, by_dept, dept_cfg, gateways, courses, rng,
                    version_idx, prog_idx=0, focus=None):
    """Sections use the original's type vocabulary: required / choice / credits /
    advisor / pathway / info."""
    home = by_dept[dcode]
    lvl = lambda pool, l: [c for c in pool if courses[c]["level"] == l]

    if degree == "MS":
        core_pool = lvl(home, 4) + lvl(home, 3)
        n_core = min(len(core_pool), rng.randint(5, 8))
    elif degree == "Minor":
        core_pool = lvl(home, 1) + lvl(home, 2)
        n_core = min(len(core_pool), rng.randint(3, 5))
    else:
        core_pool = lvl(home, 1) + lvl(home, 2) + lvl(home, 3)
        n_core = min(len(core_pool), rng.randint(10, 16))

    core_pool = sorted(core_pool)

    # Each program is built around its own curricular focus, so sibling programs in the
    # same department overlap partially rather than sharing an identical core. Without
    # this, every program in a department requires the same courses and program_count
    # inflates until "required by 5+ programs" stops meaning anything.
    focused = [c for c in core_pool if focus and courses[c]["topic"] == focus]
    shared_spine = core_pool[: max(2, n_core // 3)]      # genuine departmental core
    remainder = [c for c in core_pool if c not in shared_spine and c not in focused]

    core = list(dict.fromkeys(shared_spine + focused))
    if len(core) < n_core and remainder:
        # Rotate the fill window by program index so siblings draw different courses
        start = (prog_idx * 5 + version_idx * 2) % len(remainder)
        rotated = remainder[start:] + remainder[:start]
        core.extend(rotated[: n_core - len(core)])
    core = sorted(dict.fromkeys(core))[:n_core]

    # Pull in the in-department prerequisite ancestors of the chosen core. A program that
    # requires a 3000-level course requires its prerequisites too, and without this the
    # program subgraph contains disconnected courses whose prerequisites all sit outside
    # it — so max_depth (longest internal chain) collapses to 0-2 for every program and
    # the Program Metrics sort by depth carries no information.
    closure, frontier = set(core), list(core)
    while frontier:
        node = frontier.pop()
        for prereq in courses[node]["prerequisites"]:
            if (prereq != node and prereq not in closure
                    and courses.get(prereq, {}).get("department") == dcode):
                closure.add(prereq)
                frontier.append(prereq)
    core = sorted(closure)

    sections = [
        {"name": f"{dcode} Program Overview", "type": "info"},
        {"name": f"{dcode} Core Requirements", "type": "required",
         "courses": [_course_ref(courses, c) for c in core]},
    ]

    # Service-department requirements (cross-department dependency)
    if degree in ("BS", "BA") and dept_cfg[dcode]["cross"] > 0.15:
        svc = [d["code"] for d in C.DEPARTMENTS if d["service"] >= 0.5 and d["code"] != dcode]
        svc_courses = []
        for s in svc[:2]:
            pool = lvl(by_dept[s], 1) + lvl(by_dept[s], 2)
            gw = [c for c in pool if c in gateways] or pool[:2]
            svc_courses.extend(sorted(gw)[:2])
        if svc_courses:
            sections.append({
                "name": "Foundation Requirements (other departments)",
                "type": "required",
                "courses": [_course_ref(courses, c) for c in svc_courses],
            })

    # Choice section
    upper = lvl(home, 3) + lvl(home, 4)
    opts = sorted(set(upper) - set(core))
    if opts:
        picks = rng.sample(opts, k=min(len(opts), rng.randint(4, 8)))
        sections.append({
            "name": f"{dcode} Electives",
            "type": "choice",
            "selection_count": min(3, len(picks)),
            "options": [_course_ref(courses, c) for c in picks],
        })

    # Credits section
    if opts and rng.random() < 0.6:
        picks = rng.sample(opts, k=min(len(opts), rng.randint(3, 6)))
        sections.append({
            "name": f"{dcode} Advanced Coursework",
            "type": "credits",
            "credits_required": str(rng.choice([8, 12, 16])),
            "options": [_course_ref(courses, c) for c in picks],
        })

    # Open range elective (exercises _resolve_range in the original). Deliberately rare
    # and narrow: a wide open pool tags hundreds of courses with the program, which
    # inflates program_count and makes "gateway course" meaningless.
    if rng.random() < C.RANGE_SECTION_PROB:
        sections.append({
            "name": "Open Upper-Level Elective",
            "type": "choice",
            "credits_total": "8",
            "options": [{
                "type": "range", "department": dcode,
                "level_min": str(C.RANGE_LEVEL_MIN), "level_max": "4999",
            }],
        })

    if degree in ("BS", "MS") and rng.random() < 0.4:
        sections.append({
            "name": "Advisor-Approved Coursework",
            "type": "advisor",
            "options": [_course_ref(courses, c) for c in sorted(opts)[:3]],
        })
    return sections


def _build_concentrations(dcode, by_dept, courses, rng):
    """Give a program 3-4 concentrations drawn from distinct topics."""
    home = by_dept[dcode]
    upper = [c for c in home if courses[c]["level"] >= 3]
    by_topic = defaultdict(list)
    for c in upper:
        by_topic[courses[c]["topic"]].append(c)
    topics = sorted(t for t, v in by_topic.items() if len(v) >= 3)[:4]

    concs = {}
    for t in topics:
        key = t[:4].upper()
        picks = sorted(by_topic[t])[:5]
        concs[key] = {
            "name": t.replace("_", " ").title(),
            "title": f"{t.replace('_', ' ').title()} Concentration",
            "sections": [{
                "name": f"{t.replace('_', ' ').title()} Requirements",
                "type": "required",
                "courses": [_course_ref(courses, c) for c in picks],
            }],
        }
    return concs


def _course_ref(courses, code):
    return {"code": code, "title": courses[code]["title"],
            "credits": courses[code]["credits"]}


def extract_program_courses(program: dict, mode: str = "required",
                            version: dict | None = None) -> dict:
    """Replicates utils/program_utils.extract_program_courses.

    Returns {course_code: requirement_type}. Ranges are not resolved here (the
    original resolves them at graph-build time against the catalog).
    """
    if version is None:
        version = program["versions"][-1]
    out: dict[str, str] = {}

    def add(section, req_type):
        for c in section.get("courses", []) or []:
            out.setdefault(c["code"], req_type)
        for o in section.get("options", []) or []:
            if o.get("type") == "range":
                continue
            if "code" in o:
                out.setdefault(o["code"], req_type)

    for sec in version.get("base_requirements", {}).get("sections", []):
        t = sec.get("type", "")
        if t in ("info", "experiential"):
            continue
        if t == "required":
            add(sec, "core")
        elif t in ("choice", "credits", "advisor"):
            if mode == "all":
                add(sec, "elective")
        elif t == "pathway":
            if mode in ("all", "pathways"):
                add(sec, "pathway")

    if mode in ("all", "concentrations"):
        for conc in version.get("concentrations", {}).values():
            for sec in conc.get("sections", []):
                add(sec, "concentration")
    return out


def build_choice_label(section: dict, n_options: int) -> str:
    """Copied from the original load_data._build_choice_label."""
    t = section.get("type", "")
    name = section.get("name", "this section")
    sel = section.get("selection_count")
    cred_req = section.get("credits_required")
    cred_tot = section.get("credits_total")

    if t == "advisor":
        return f'Advisor-approved — select with your advisor from "{name}"'
    if sel is not None:
        of_part = f" of {n_options}" if n_options else ""
        return f'Pick {sel}{of_part} courses from "{name}"'
    if cred_req:
        return f'Earn {cred_req} credits from "{name}"'
    if cred_tot:
        return f'Pick courses totalling {cred_tot} credits from "{name}"'
    return f'Choose from "{name}"'


def build_elective_context(programs: dict, courses: dict) -> dict:
    """Per-course elective context, replicating load_data._process_version.

    The original tags every course reached through a choice / credits / advisor section
    with the section it came from and a human-readable selection rule, then renders that
    block in the Graph View node hover. Range options get the same treatment via
    _build_range_elective_context. Without this the elective portion of the hover cannot
    be reproduced.

    Returns {course_code: {section_name, choice_label, elective_type, is_range,
                           range_description, programs: [...]}}.
    """
    CHOICE_TYPES = {"choice", "credits", "advisor"}
    out: dict[str, dict] = {}

    def tag(code: str, ctx: dict, prog_code: str) -> None:
        if code not in courses:
            return
        entry = out.setdefault(code, {**ctx, "programs": []})
        if prog_code not in entry["programs"]:
            entry["programs"].append(prog_code)

    for prog_code, prog in programs.items():
        for version in prog["versions"]:
            for sec in version.get("base_requirements", {}).get("sections", []):
                if sec.get("type") not in CHOICE_TYPES:
                    continue
                options = sec.get("options", []) or []
                concrete = [o for o in options
                            if isinstance(o, dict) and "code" in o
                            and o.get("type") != "range"]
                label = build_choice_label(sec, len(concrete))
                base = {
                    "section_name": sec.get("name", ""),
                    "choice_label": label,
                    "elective_type": sec.get("type", ""),
                    "is_range": False,
                    "range_description": "",
                }
                for o in concrete:
                    tag(o["code"], base, prog_code)
                for o in options:
                    if not isinstance(o, dict) or o.get("type") != "range":
                        continue
                    dept = o.get("department", "")
                    lo = int(o.get("level_min", 0))
                    hi = int(o["level_max"]) if o.get("level_max") else None
                    desc = f"{dept} {o.get('level_min', '?')}–{o.get('level_max', 'higher')}"
                    rng_ctx = {
                        "section_name": sec.get("name", ""),
                        "choice_label": desc,
                        "elective_type": "range",
                        "is_range": True,
                        "range_description": desc,
                    }
                    for code, c in courses.items():
                        if c["department"] != dept:
                            continue
                        n = int(c["number"])
                        if n < lo or (hi is not None and n > hi):
                            continue
                        tag(code, rng_ctx, prog_code)
    return out


def resolve_ranges(program: dict, courses: dict, version: dict | None = None) -> dict:
    """Resolve range-based electives against the catalog (the original's _resolve_range)."""
    if version is None:
        version = program["versions"][-1]
    out = {}
    for sec in version.get("base_requirements", {}).get("sections", []):
        for o in sec.get("options", []) or []:
            if o.get("type") != "range":
                continue
            dept = o["department"]
            lo = int(o.get("level_min", 0))
            hi = int(o["level_max"]) if o.get("level_max") else None
            for code, c in courses.items():
                if c["department"] != dept:
                    continue
                n = int(c["number"])
                if n < lo or (hi is not None and n > hi):
                    continue
                out.setdefault(code, "elective")
    return out


# ============================================================
# 5. Sections and enrollment
# ============================================================

def select_severe_bottlenecks(courses: dict, G: nx.DiGraph,
                             program_counts: dict) -> set:
    """Pick the notorious gateway courses, from graph structure only.

    Chosen before enrollment is generated so that these courses can be made extreme in
    the observable data as well as in student friction. If severity exists only in
    friction, the labels become extreme while avg_fill_rate and behavioral_score stay
    ordinary, and the model has nothing to key on — Precision@20 stays at chance-plus.

    Candidates must have at least one prerequisite: delay is measured from the term a
    student completes a course's prerequisites, so compute_ground_truth never labels a
    prerequisite-free course however oversubscribed it is.
    """
    betw = nx.betweenness_centrality(G)
    in_deg, out_deg = dict(G.in_degree()), dict(G.out_degree())

    def rank_signal(code):
        return (12.0 * betw.get(code, 0.0)
                + 0.30 * min(program_counts.get(code, 0), 12)
                + 0.25 * min(out_deg.get(code, 0), 12)
                + 0.15 * min(in_deg.get(code, 0), 6))

    candidates = [c for c in courses
                  if in_deg.get(c, 0) > 0 and courses[c]["level"] in (2, 3)]
    return set(sorted(candidates, key=lambda c: -rank_signal(c))[:C.N_SEVERE_BOTTLENECKS])


def generate_enrollment(courses: dict, programs: dict, published_terms: list,
                        program_counts: dict, rng: random.Random,
                        np_rng: np.random.Generator,
                        severe: set | None = None) -> tuple[list, dict]:
    """Generate section-level rows, then aggregate exactly as the original's
    aggregate_by_course() does.

    Fill pressure is calibrated by bisection on a global offset so that the share of
    sections at/over capacity and the share carrying a waitlist match the real
    system's published findings (36% / 31.9%).
    """
    dept_cfg = {d["code"]: d for d in C.DEPARTMENTS}
    instructors = _instructor_pool(rng)

    # Per-course latent demand pressure, before global calibration
    pressure = {}
    for code, c in courses.items():
        cfg = dept_cfg[c["department"]]
        base = cfg["demand"]
        level_factor = {1: 1.15, 2: 1.0, 3: 0.85, 4: 0.7}[c["level"]]
        prog_factor = 1.0 + 0.06 * min(program_counts.get(code, 0), 8)
        noise = np_rng.normal(0, 0.22)
        pressure[code] = base * level_factor * prog_factor + noise
        if severe and code in severe:
            # Visibly oversubscribed: consistently over capacity, waitlisted every term.
            pressure[code] = pressure[code] * 1.25 + 0.45

    # Which courses are offered in which terms (offering_frequency varies)
    offerings = {}
    for code, c in courses.items():
        cfg = dept_cfg[c["department"]]
        season_pref = cfg["seasonal"]
        terms = []
        for t in published_terms:
            season = term_season(t)
            if season in C.SUMMER_SEASONS:
                # Summer Full carries more volume than the split sessions
                base = 0.30 if season == "Summer Full" else 0.16
                p = base if c["level"] <= 2 else base * 0.45
            elif season == season_pref:
                p = 0.92 if c["level"] <= 2 else 0.72
            else:
                p = 0.62 if c["level"] <= 2 else 0.45
            if rng.random() < p:
                terms.append(t)
        if not terms:
            terms = [rng.choice([t for t in published_terms if not is_summer(t)])]
        offerings[code] = terms

    # Fixed per-course base capacity, drawn once so it is stable across calibration passes
    base_caps = {}
    for code, c in sorted(courses.items()):
        cap_pool = C.SECTION_CAPACITIES
        if c["level"] == 1:
            cap_choices = cap_pool[3:]
        elif c["level"] == 2:
            cap_choices = cap_pool[2:8]
        else:
            cap_choices = cap_pool[:6]
        base_caps[code] = rng.choice(cap_choices)

    # Standing section count per course, fixed across terms (see note in build_rows)
    base_sections = {}
    for code, c in sorted(courses.items()):
        if c["level"] <= 2 and pressure[code] > 0.9:
            base_sections[code] = rng.choice([1, 2, 2, 3])
        elif c["level"] <= 2:
            base_sections[code] = rng.choice([1, 1, 2])
        else:
            base_sections[code] = 1
        if severe and code in severe:
            # Constrained supply is part of what makes these courses chokepoints
            base_sections[code] = 1

    years = sorted({t[:4] for t in published_terms})

    def build_rows(offset: float, wl_prob: float) -> list:
        """Walk terms in chronological order so next-year capacity can respond to
        last-year demand. That feedback loop is the signal Tab 8 measures — without it,
        capacity correlates with enrollment purely through course size and every
        department scores identically."""
        rows = []
        # last_year[(course)] = (mean enrolment per section, mean unmet demand per section)
        last_year: dict[str, tuple[float, float]] = {}
        pending: dict[str, list[tuple[int, float]]] = defaultdict(list)
        current_year = years[0]

        for term in published_terms:
            year = term[:4]
            if year != current_year:
                # Roll the previous year's observations forward
                for code, obs in pending.items():
                    enr = float(np.mean([o[0] for o in obs]))
                    unmet = float(np.mean([o[1] for o in obs]))
                    last_year[code] = (enr, unmet)
                pending = defaultdict(list)
                current_year = year

            season = term_season(term)
            for code, c in sorted(courses.items()):
                if term not in offerings[code]:
                    continue
                cfg = dept_cfg[c["department"]]
                base_cap = base_caps[code]

                # Capacity response: blend the standing base capacity toward the total
                # demand last year revealed (seats filled plus seats short), weighted by
                # the department's `respond` value. A department with respond=0 keeps its
                # base capacity forever no matter how large the waitlist grows.
                if code in last_year:
                    observed_need = last_year[code][0] + last_year[code][1]
                    cap = base_cap * (1 - cfg["respond"]) + observed_need * cfg["respond"]
                    cap = int(round(max(base_cap * 0.85, min(cap, base_cap * 2.2))))
                else:
                    cap = base_cap

                # Section count is a standing property of the course that departments
                # adjust alongside capacity — not per-term noise. Re-rolling it every
                # term would make year-over-year course totals jump erratically, which
                # would cripple the same-season-last-year baseline the demand model is
                # measured against and hand the model an unearned improvement.
                n_sections = base_sections[code]
                if code in last_year and cfg["respond"] > 0.5:
                    need_ratio = (last_year[code][0] + last_year[code][1]) / max(cap, 1)
                    if need_ratio > 1.25:
                        n_sections += 1
                if is_summer(term):
                    n_sections = 1

                for s in range(n_sections):
                    seasonal_mult = 1.0 if season == cfg["seasonal"] else (
                        0.45 if is_summer(term) else 0.88)
                    # Demand is anchored to the course's standing size (base_cap), NOT to
                    # the current capacity. Deriving demand from capacity would mean every
                    # seat a department adds also adds proportional demand, so no
                    # department could ever close its gap and the responsiveness metric
                    # would be measuring nothing.
                    demand = base_cap * (pressure[code] + offset) * seasonal_mult
                    # Department enrollment trend, compounded from the first published
                    # year. This is what the naive same-season-last-year baseline cannot
                    # capture and the forecaster can.
                    year_offset = years.index(year)
                    demand *= (1.0 + cfg["growth"] * C.GROWTH_SCALE) ** year_offset
                    demand *= max(0.15, float(np_rng.normal(1.0, C.DEMAND_TERM_NOISE_SD)))
                    # Registration admits over capacity only where overrides are granted;
                    # the rest of the excess demand shows up as waitlist.
                    enrolled = max(1, min(int(round(demand)), int(cap * 1.06)))

                    overflow = demand - cap
                    waitlist = 0
                    if overflow > 0:
                        # Not every over-subscribed section records a waitlist — some
                        # departments never enable one. wl_prob tunes that share, which
                        # is what makes the 31.9% target reachable at all: if every
                        # over-capacity section carried a waitlist, the waitlist rate
                        # would be pinned above the at-capacity rate.
                        if rng.random() < wl_prob:
                            waitlist = max(1, int(round(overflow * rng.uniform(0.5, 1.4))))
                    elif enrolled >= cap * 0.94 and rng.random() < wl_prob * 0.35:
                        waitlist = rng.randint(1, 6)

                    pending[code].append((enrolled, max(0.0, overflow)))
                    rows.append({
                        "course": code,
                        "department": c["department"],
                        "term_code": term,
                        "term": term_display(term),
                        "season": season,
                        "section": f"{s + 1:02d}",
                        "instructor": rng.choice(instructors),
                        "enrollment": enrolled,
                        "max_enrollment": cap,
                        "waitlist": waitlist,
                    })
        return rows

    def bisect(fn, lo, hi, target, iters=20):
        """Shared bisection helper. The RNG state is restored on every probe so each
        candidate is evaluated against identical randomness."""
        mid = (lo + hi) / 2
        rows = []
        for _ in range(iters):
            mid = (lo + hi) / 2
            state, np_state = rng.getstate(), np_rng.bit_generator.state
            rows = fn(mid)
            rng.setstate(state)
            np_rng.bit_generator.state = np_state
            if _measure(rows, target[0]) < target[1]:
                lo = mid
            else:
                hi = mid
        return mid, rows

    def _measure(rows, kind):
        if kind == "at_cap":
            return float(np.mean([r["enrollment"] >= r["max_enrollment"] for r in rows]))
        return float(np.mean([r["waitlist"] > 0 for r in rows]))

    # --- Pass 1: global fill offset -> at-capacity rate ---
    offset, rows = bisect(lambda m: build_rows(m, C.WAITLIST_NEAR_CAP_PROB),
                          -0.60, 0.90, ("at_cap", C.TARGET_AT_CAPACITY_RATE))
    # --- Pass 2: near-capacity waitlist probability -> waitlist rate ---
    # Sections already over capacity always carry a waitlist, so this only tunes the
    # near-full tail. If the over-capacity population alone already exceeds the target,
    # the floor is reported rather than silently missed.
    wl_prob, rows = bisect(lambda m: build_rows(offset, m),
                           0.0, 1.0, ("waitlist", C.TARGET_WAITLIST_RATE))
    log(f"    calibrated fill offset={offset:+.4f}, waitlist prob={wl_prob:.3f} "
        f"-> at-capacity {_measure(rows, 'at_cap'):.1%}, "
        f"waitlist {_measure(rows, 'waitlist'):.1%}")

    behavioral = aggregate_by_course(rows, published_terms)
    return rows, behavioral


def _instructor_pool(rng: random.Random) -> list:
    """Instructor strings in the original's CourseLeaf format so the parser matches."""
    pool = []
    for i in range(220):
        first = C.INSTRUCTOR_FIRST[i % len(C.INSTRUCTOR_FIRST)]
        last = C.INSTRUCTOR_LAST[(i * 7) % len(C.INSTRUCTOR_LAST)]
        pid = 900000000 + i * 137
        pool.append(f"{last}, {first} ({pid}) [Primary, 100%, Yes]")
    pool.append("TBD")
    return pool


def aggregate_by_course(rows: list, published_terms: list) -> dict:
    """Replicates load_courseleaf_enrollment.aggregate_by_course exactly, including
    the derived metrics and the enrollment_series payload the trend chart reads."""
    by_course = defaultdict(list)
    for r in rows:
        by_course[r["course"]].append(r)
    total_terms = len({r["term_code"] for r in rows})

    out = {}
    for course, recs in by_course.items():
        recs = sorted(recs, key=lambda r: (r["term_code"], r["section"]))
        fill = [r["enrollment"] / r["max_enrollment"] if r["max_enrollment"] > 0 else 0.0
                for r in recs]
        wl = [r["waitlist"] for r in recs]
        terms_offered = len({r["term_code"] for r in recs})

        # Series is per-term (sections summed), which is what a trend line should show
        per_term = defaultdict(lambda: {"enr": 0, "cap": 0, "prof": []})
        for r in recs:
            pt = per_term[r["term_code"]]
            pt["enr"] += r["enrollment"]
            pt["cap"] += r["max_enrollment"]
            pt["prof"].append(r["instructor"])
        ordered = sorted(per_term)
        series = {
            "terms": ordered,
            "term_labels": [term_display(t) for t in ordered],
            "enrollment": [per_term[t]["enr"] for t in ordered],
            "fill_rate": [round(per_term[t]["enr"] / per_term[t]["cap"], 4)
                          if per_term[t]["cap"] else 0.0 for t in ordered],
            "professor": [per_term[t]["prof"][0] for t in ordered],
        }

        enr_series = series["enrollment"]
        if len(enr_series) >= 2:
            slope = float(np.polyfit(np.arange(len(enr_series)), np.array(enr_series), 1)[0])
        else:
            slope = 0.0

        caps = [r["max_enrollment"] for r in recs]
        out[course] = {
            "course_code": course,
            "avg_enrollment": round(float(np.mean([r["enrollment"] for r in recs])), 3),
            "max_enrollment_capacity": round(float(np.mean(caps)), 3),
            "avg_fill_rate": round(float(np.mean(fill)), 4),
            "max_fill_rate": round(float(np.max(fill)), 4),
            "avg_waitlist": round(float(np.mean(wl)), 3),
            "max_waitlist": int(np.max(wl)),
            "waitlist_frequency": round(float(np.mean([w > 0 for w in wl])), 4),
            "total_waitlist_semesters": int(sum(1 for w in wl if w > 0)),
            "total_sections": len(recs),
            "terms_offered": terms_offered,
            "capacity_variance": round(float(np.std(caps, ddof=1)), 3) if len(caps) > 1 else 0.0,
            "avg_crosslist_enrollment": 0.0,
            "has_crosslist": False,
            "sections_per_semester": round(len(recs) / terms_offered, 4),
            "offering_frequency": round(terms_offered / total_terms, 4),
            "enrollment_trend": round(slope, 4),
            "enrollment_series": series,
        }
    return out


def behavioral_score(feat: dict) -> float:
    """Copied from the original load_behavioral_features()."""
    score = 0.0
    if feat.get("avg_fill_rate", 0) > 0.95:
        score += 1
    if feat.get("waitlist_frequency", 0) > 0.3:
        score += 2
    if feat.get("sections_per_semester", 0) < 1.5:
        score += 1
    return score


# ============================================================
# 6. Student pathways
# ============================================================

def compute_friction(courses: dict, G: nx.DiGraph, behavioral: dict,
                     program_counts: dict, np_rng: np.random.Generator,
                     severe: set | None = None) -> dict:
    """Latent per-course 'friction' — how hard it is for an eligible student to
    actually get into the course.

    This is the generative mechanism behind the ML labels. It is deliberately a
    *partially* observable function of the same structural and capacity properties
    that FEATURE_COLS captures, plus idiosyncratic noise weighted by
    C.FRICTION_NOISE. That noise weight is the single knob controlling achievable
    AUC: without it the features would be perfectly predictive and the reported
    metric would be meaningless.
    """
    betw = nx.betweenness_centrality(G)
    in_deg = dict(G.in_degree())
    out_deg = dict(G.out_degree())

    raw = {}
    for code, c in courses.items():
        b = behavioral.get(code, {})
        signal = (
            2.2 * min(b.get("avg_fill_rate", 0.7), 1.3)
            + 1.6 * b.get("waitlist_frequency", 0.0)
            + 0.9 * (1.0 if b.get("sections_per_semester", 1) < 1.5 else 0.0)
            + 0.05 * min(in_deg.get(code, 0), 8)
            + 0.04 * min(out_deg.get(code, 0), 12)
            + 14.0 * betw.get(code, 0.0)
            + 0.06 * min(program_counts.get(code, 0), 10)
            + 0.18 * (1.0 if c["level"] <= 2 else 0.0)
        )
        raw[code] = signal

    vals = np.array([raw[c] for c in sorted(raw)])
    mu, sd = float(vals.mean()), float(vals.std() or 1.0)

    # Designate the most structurally prominent courses as severe bottlenecks: high
    # fill, waitlisted, chokepoints in the graph, required by many programs. Their
    # friction is set near the ceiling with no noise, so they are unambiguous.
    #
    # Candidates must have at least one prerequisite. Delay is measured from the term a
    # student finishes a course's prerequisites, so compute_ground_truth only ever
    # labels courses that have them — a prerequisite-free gateway course can never
    # carry a bottleneck label no matter how oversubscribed it is. Selecting severe
    # courses without this filter puts them all outside the labelled set.
    severe = severe or set()

    friction = {}
    for code in sorted(raw):
        if code in severe:
            lo, hi = C.SEVERE_FRICTION_RANGE
            friction[code] = float(np_rng.uniform(lo, hi))
            continue
        z = (raw[code] - mu) / sd
        eps = float(np_rng.normal(0, 1))
        # Noise is attenuated for courses at the extremes of the structural signal.
        # A course that is unambiguously a chokepoint on every dimension behaves like
        # one; the ambiguity is concentrated in the middle of the distribution. This is
        # what lets the model reach high precision on its top-ranked courses while
        # staying middling overall — the real system's AUC 0.772 / P@20 0.85 profile.
        # A single flat noise term cannot produce that combination.
        noise = C.FRICTION_NOISE * (1.0 - C.FRICTION_TAIL_CERTAINTY *
                                    min(1.0, abs(z) / 1.8))
        blended = math.sqrt(1 - noise) * z + math.sqrt(noise) * eps
        friction[code] = 1.0 / (1.0 + math.exp(-1.15 * blended))
    return friction


def simulate_students(courses: dict, programs: dict, pathway_terms: list,
                      friction: dict, rng: random.Random,
                      n_students: int) -> list:
    """Simulate student course-taking pathways over the deep term window.

    Each student is assigned a program, an entry term, and a per-term course load.
    They may only enroll in a course once its prerequisite groups are satisfied
    (AND across groups, OR within a group) — the same rule the ground-truth
    computation later uses. Friction makes them postpone or never enroll.
    """
    prog_codes = sorted(programs)
    prog_course_lists = {}
    for pc in prog_codes:
        prog = programs[pc]
        req = extract_program_courses(prog, mode="required")
        allc = extract_program_courses(prog, mode="all")
        prog_course_lists[pc] = (sorted(req), sorted(set(allc) - set(req)))

    prereq_groups = {code: parse_prerequisite_groups(c) for code, c in courses.items()}
    all_course_codes = sorted(courses)

    # Entry cohorts: most students enter in Fall, some in Spring. Entry is restricted to
    # terms that leave at least four terms of runway, so every simulated student has a
    # pathway long enough to contribute delay/stalling evidence.
    latest_entry = pathway_terms[-4] if len(pathway_terms) > 4 else pathway_terms[0]
    fall_terms = [t for t in pathway_terms
                  if term_season(t) == "Fall" and t <= latest_entry]
    spring_terms = [t for t in pathway_terms
                    if term_season(t) == "Spring" and t <= latest_entry]
    entry_pool = [t for t in fall_terms for _ in range(4)] + spring_terms

    students = []
    for sid in range(n_students):
        pc = rng.choice(prog_codes)
        req, elec = prog_course_lists[pc]
        entry = rng.choice(entry_pool)
        entry_i = pathway_terms.index(entry)
        # Students take a plan of required courses plus some electives
        plan = list(req) + rng.sample(elec, k=min(len(elec), rng.randint(2, 6)))
        rng.shuffle(plan)

        # Graduate plans are drawn entirely from 3000/4000-level courses, so a student
        # starting from nothing would never satisfy a single prerequisite and would
        # produce an empty pathway. Their undergraduate foundation is treated as already
        # complete: any prerequisite that lies outside the graduate plan is seeded as
        # taken. Undergraduate plans include 1000-level courses and need no seeding.
        taken: set[str] = set()
        if programs[pc]["degree_type"] in ("MS", "MA", "MBA"):
            plan_set = set(plan)
            for code in plan:
                for group in prereq_groups.get(code, []):
                    if not (group & plan_set):
                        taken.update(group)

        terms_out = []
        load_base = rng.randint(*C.COURSES_PER_TERM)
        part_time = rng.random() < C.PART_TIME_SHARE

        # `passed` drives prerequisite eligibility; `attempted` is what appears on the
        # transcript. They diverge when a student withdraws or fails, which is the main
        # source of delay that no structural feature can explain.
        passed = set(taken)
        attempted_any = False

        for ti in range(entry_i, len(pathway_terms)):
            term = pathway_terms[ti]
            season = term_season(term)

            # Stop-out: students take terms off, transfer away and back, or go on co-op.
            if attempted_any and rng.random() < C.STOPOUT_PROB:
                continue

            if season in C.SUMMER_SEASONS:
                # Summer 1 and Summer 2 are half-terms; students rarely take a full load
                if rng.random() > (0.22 if season == "Summer Full" else 0.12):
                    continue
                load = rng.randint(1, 2)
            else:
                load = max(1, load_base + rng.choice([-1, 0, 0, 1]))
                if part_time:
                    load = max(1, load // 2)

            # Program switch: the student's remaining plan is replaced partway through.
            if attempted_any and rng.random() < C.PROGRAM_SWITCH_PROB:
                new_pc = rng.choice(prog_codes)
                n_req, n_elec = prog_course_lists[new_pc]
                plan = list(dict.fromkeys(
                    [c for c in plan if c in passed] + list(n_req)
                    + rng.sample(n_elec, k=min(len(n_elec), rng.randint(1, 4)))))
                pc = new_pc

            # Eligible = every prereq group satisfied by courses already PASSED
            eligible = [
                code for code in plan
                if code not in passed
                and all(g & passed for g in prereq_groups.get(code, []))
            ]

            # Off-plan coursework: general electives, exploration, courses taken for
            # interest. Real transcripts are not confined to the degree audit.
            if rng.random() < C.OFF_PLAN_PROB:
                off = rng.sample(all_course_codes, k=min(len(all_course_codes), 6))
                eligible += [
                    c for c in off
                    if c not in passed
                    and all(g & passed for g in prereq_groups.get(c, []))
                ]
            if not eligible:
                continue

            # Friction gates enrollment: a high-friction course gets deferred
            picks = []
            for code in eligible:
                if len(picks) >= load:
                    break
                f = friction.get(code, 0.5)
                if rng.random() < (1.0 - 0.85 * f):
                    picks.append(code)
            # Fill remaining slots with whatever is left, lowest friction first
            if len(picks) < load:
                leftover = sorted((c for c in eligible if c not in picks),
                                  key=lambda c: friction.get(c, 0.5))
                picks.extend(leftover[: load - len(picks)])

            if not picks:
                continue

            # Withdrawal / non-passing grade: the attempt is on the transcript but does
            # not unlock anything downstream, so the student must retake it later.
            for code in picks:
                if rng.random() >= C.WITHDRAWAL_PROB:
                    passed.add(code)

            attempted_any = True
            terms_out.append({"term": int(term), "courses": picks})

            if len({c for t in terms_out for c in t["courses"]}) >= len(plan):
                break

        if terms_out:
            enrolled_here = sorted({c for t in terms_out for c in t["courses"]})
            students.append({
                "student_id": f"PRU{sid:06d}",
                "program": pc,
                "entry_term": int(entry),
                "terms": terms_out,
                # Only courses actually taken in a simulated term. Seeded graduate
                # prerequisites are prior credit, not enrollments here.
                "flat_sequence": enrolled_here,
                "prior_credit": sorted(taken - set(enrolled_here)),
            })
    return students


# ============================================================
# 7. Ground truth — exact replication of compute_ground_truth
# ============================================================

def build_student_indexes(students: list) -> tuple[dict, dict]:
    student_data, course_to_students = {}, defaultdict(set)
    for s in students:
        sid = s["student_id"]
        terms = sorted(s["terms"], key=lambda t: t["term"])
        all_courses = set(s["flat_sequence"])
        student_data[sid] = {
            "terms": [(t["term"], set(t["courses"])) for t in terms],
            "first_term": terms[0]["term"] if terms else None,
            "all_courses": all_courses,
        }
        for c in all_courses:
            course_to_students[c].add(sid)
    return student_data, course_to_students


def compute_ground_truth(courses: dict, student_data: dict,
                         course_to_students: dict, cohort_filter=None) -> dict:
    """Copied from the original bottleneck_pipeline.compute_ground_truth."""
    prereq_map = {}
    for code, c in courses.items():
        groups = parse_prerequisite_groups(c)
        if groups:
            prereq_map[code] = groups

    if cohort_filter:
        valid_sids = {sid for sid, sd in student_data.items() if cohort_filter(sd)}
    else:
        valid_sids = set(student_data)

    ground_truth, skipped_small = {}, 0

    for course_code, prereq_groups in prereq_map.items():
        candidate_sids = None
        for group in prereq_groups:
            group_students = set()
            for c in group:
                group_students |= (course_to_students.get(c, set()) & valid_sids)
            candidate_sids = group_students if candidate_sids is None else (
                candidate_sids & group_students)
        if not candidate_sids:
            continue

        delays, n_eligible, n_stalled = [], 0, 0
        for sid in candidate_sids:
            terms = student_data[sid]["terms"]
            cumulative, completion_term = set(), None
            for term_code, term_courses in terms:
                cumulative |= term_courses
                if completion_term is None and all(g & cumulative for g in prereq_groups):
                    completion_term = term_code
            if completion_term is None:
                continue
            n_eligible += 1

            enrolled_term = None
            for term_code, term_courses in terms:
                if course_code in term_courses and term_code >= completion_term:
                    enrolled_term = term_code
                    break
            if enrolled_term is not None:
                delays.append(term_delay(completion_term, enrolled_term))
            else:
                last_term = terms[-1][0] if terms else 0
                if term_delay(completion_term, last_term) >= C.STALLING_WINDOW:
                    n_stalled += 1

        if n_eligible < C.MIN_ELIGIBLE_STUDENTS:
            skipped_small += 1
            continue

        ground_truth[course_code] = {
            "median_delay": float(np.median(delays)) if delays else float(C.STALLING_WINDOW),
            "stalling_rate": n_stalled / n_eligible,
            "n_eligible": n_eligible,
            "n_enrolled": len(delays),
            "n_stalled": n_stalled,
        }

    if not ground_truth:
        return ground_truth

    delays_arr = np.array([v["median_delay"] for v in ground_truth.values()])
    rates_arr = np.array([v["stalling_rate"] for v in ground_truth.values()])
    d_min, d_max = delays_arr.min(), delays_arr.max()
    r_min, r_max = rates_arr.min(), rates_arr.max()

    for v in ground_truth.values():
        v["delay_norm"] = ((v["median_delay"] - d_min) / (d_max - d_min)) if d_max > d_min else 0
        v["stalling_norm"] = ((v["stalling_rate"] - r_min) / (r_max - r_min)) if r_max > r_min else 0
        v["composite"] = 0.5 * v["delay_norm"] + 0.5 * v["stalling_norm"]

    composites = [v["composite"] for v in ground_truth.values()]
    threshold = float(np.percentile(composites, C.BOTTLENECK_PERCENTILE))
    for v in ground_truth.values():
        v["label"] = 1 if v["composite"] >= threshold else 0

    ground_truth["__meta__"] = {
        "threshold": threshold,
        "skipped_too_few_students": skipped_small,
        "n_courses": len(ground_truth) - 1,
    }
    return ground_truth


# ============================================================
# 8. Features — the original's exact FEATURE_COLS
# ============================================================

def compute_features(courses: dict, G: nx.DiGraph, behavioral: dict,
                     program_counts: dict) -> dict:
    """Copied from the original bottleneck_pipeline.compute_features."""
    betweenness = nx.betweenness_centrality(G)
    cascade_impact, prereq_chain_depth = {}, {}

    if nx.is_directed_acyclic_graph(G):
        depth = {}
        for node in nx.topological_sort(G):
            preds = list(G.predecessors(node))
            depth[node] = max((depth[p] + 1 for p in preds), default=0)
        prereq_chain_depth = depth
        for node in G.nodes():
            cascade_impact[node] = len(nx.descendants(G, node))
    else:
        for node in G.nodes():
            cascade_impact[node] = len(nx.descendants(G, node))
            prereq_chain_depth[node] = 0

    feats = {}
    for code in G.nodes():
        b = behavioral.get(code, {})
        feats[code] = {
            "behavioral_score": behavioral_score(b),
            "in_degree": G.in_degree(code),
            "out_degree": G.out_degree(code),
            "betweenness": round(betweenness.get(code, 0.0), 8),
            "program_count": program_counts.get(code, 0),
            "level": courses[code]["level"],
            "cascade_impact": cascade_impact.get(code, 0),
            "prereq_chain_depth": prereq_chain_depth.get(code, 0),
            "avg_fill_rate": round(b.get("avg_fill_rate", 0.0), 4),
        }
    return feats


# ============================================================
# 9. RandomForest — real training, measured metrics
# ============================================================

def train_bottleneck_models(features: dict, gt_train: dict, gt_test: dict,
                            gt_full: dict) -> tuple[dict, dict]:
    """Train the three models the original trained and report measured metrics."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score

    def matrix(gt):
        codes = [c for c in gt if c != "__meta__" and c in features]
        X = np.array([[features[c][f] for f in C.FEATURE_COLS] for c in codes], dtype=float)
        y = np.array([gt[c]["label"] for c in codes])
        return codes, X, y

    c_tr, X_tr, y_tr = matrix(gt_train)
    c_te, X_te, y_te = matrix(gt_test)
    log(f"    train n={len(c_tr)} (pos {y_tr.sum()}), test n={len(c_te)} (pos {y_te.sum()})")

    results = {}

    def evaluate(name, y_true, y_score, y_pred):
        m = {
            "auc": float(roc_auc_score(y_true, y_score)) if len(set(y_true)) > 1 else None,
            "precision": float(precision_score(y_true, y_pred, zero_division=0)),
            "recall": float(recall_score(y_true, y_pred, zero_division=0)),
            "f1": float(f1_score(y_true, y_pred, zero_division=0)),
            "n_test": int(len(y_true)),
            "base_rate": round(float(np.mean(y_true)), 4),
        }
        order = np.argsort(-y_score)
        for k in (10, 20, 50):
            if len(order) >= k:
                m[f"precision_at_{k}"] = round(float(np.mean(y_true[order[:k]])), 4)
        results[name] = m
        return m

    # --- Model 1: threshold rule (the original's compute_rule_based_score) ---
    rule_scores = np.array([_rule_score(features[c]) for c in c_te])
    rule_cut = float(np.percentile(rule_scores, C.BOTTLENECK_PERCENTILE))
    evaluate("threshold_rule", y_te, rule_scores, (rule_scores >= rule_cut).astype(int))

    # --- Model 2: logistic regression ---
    scaler = StandardScaler().fit(X_tr)
    lr = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=C.SEED)
    lr.fit(scaler.transform(X_tr), y_tr)
    lr_prob = lr.predict_proba(scaler.transform(X_te))[:, 1]
    evaluate("logistic_regression", y_te, lr_prob, (lr_prob >= 0.5).astype(int))

    # --- Model 3: random forest (the model the dashboard actually consumes) ---
    rf = RandomForestClassifier(
        n_estimators=300, max_depth=8, min_samples_leaf=4,
        class_weight="balanced", random_state=C.SEED, n_jobs=-1)
    rf.fit(X_tr, y_tr)
    rf_prob = rf.predict_proba(X_te)[:, 1]
    rf_metrics = evaluate("random_forest", y_te, rf_prob,
                          (rf_prob >= C.BOTTLENECK_SCORE_THRESHOLD).astype(int))
    results["random_forest"]["feature_importance"] = {
        f: round(float(w), 5) for f, w in zip(C.FEATURE_COLS, rf.feature_importances_)
    }

    # --- Score every course in the catalog (the original's _save_rf_scores) ---
    all_codes = sorted(features)
    X_all = np.array([[features[c][f] for f in C.FEATURE_COLS] for c in all_codes],
                     dtype=float)
    probs = rf.predict_proba(X_all)[:, 1]
    scores = {c: round(float(p), 6) for c, p in zip(all_codes, probs)}

    # Precision@k is also reported against the full-sample labels, not just the held-out
    # cohort. The test cohort is students entering Fall 2023 or later, who have only a
    # few terms of history, so their delay and stalling estimates — and therefore the
    # top-quartile labels derived from them — are considerably noisier than the
    # full-sample ones. Both are reported rather than picking the flattering one.
    full_labels = {c: v["label"] for c, v in gt_full.items() if c != "__meta__"}
    ranked_all = [c for c in sorted(scores, key=lambda x: -scores[x]) if c in full_labels]
    full_prec = {}
    for k in (10, 20, 50):
        if len(ranked_all) >= k:
            full_prec[f"precision_at_{k}"] = round(
                float(np.mean([full_labels[c] for c in ranked_all[:k]])), 4)
    results["random_forest"]["full_sample"] = {
        **full_prec,
        "n_labelled": len(full_labels),
        "base_rate": round(float(np.mean(list(full_labels.values()))), 4),
        "note": ("Ranking scored against full-sample labels; the metrics above the "
                 "`full_sample` key use the held-out Fall-2023+ cohort, as the original "
                 "pipeline did."),
    }

    log(f"    RF  AUC={rf_metrics['auc']:.4f}  "
        f"P@20(test cohort)={rf_metrics.get('precision_at_20')}  "
        f"P@20(full sample)={full_prec.get('precision_at_20')}  "
        f"base_rate={rf_metrics['base_rate']:.3f}")
    return scores, results


def _rule_score(row: dict) -> float:
    """Copied from the original compute_rule_based_score."""
    score = row["behavioral_score"]
    if row["out_degree"] > 0:
        score += 0.5
    if row["in_degree"] > 3:
        score += 0.5
    if row["betweenness"] > 0.1:
        score += 1.0
    if row["program_count"] > 1:
        score += 0.5
    if row["level"] <= 2:
        score += 0.25
    return score


# ============================================================
# 10. Similarity — real TF-IDF cosine
# ============================================================

def compute_similarity(courses: dict) -> tuple[list, dict]:
    """Real TF-IDF cosine similarity over generated titles + descriptions.

    The original used sentence-transformer embeddings; TF-IDF is used here because it
    is a genuine text-similarity computation with no model download, and because the
    descriptions are themselves generated from topic keyword pools — the cluster
    structure being measured is real structure in the text.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    codes = sorted(courses)
    docs = []
    for c in codes:
        cd = courses[c]
        topic_phrase = cd["topic"].replace("_", " ")
        sub_phrase = cd["subtopic"].replace("#", " strand ").replace("_", " ")
        kw = " ".join(cd["keywords"])
        # Title and keywords are weighted by repetition — they carry the content signal.
        # The topic/sub-topic phrases act as the shared vocabulary a real course
        # catalogue supplies through its subject-area language. Repeat counts are swept
        # against the pair-count and cluster-count targets rather than guessed.
        spec = cd.get("specialization")
        docs.append(" ".join([
            cd["title"], cd["title"], cd["description"],
            *([kw] * C.SIM_KEYWORD_REPEAT),
            *([topic_phrase] * C.SIM_TOPIC_REPEAT),
            *([sub_phrase] * C.SIM_SUBTOPIC_REPEAT),
            *([spec] * C.SPECIALIZATION_REPEAT if spec else []),
        ]))
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2),
                          sublinear_tf=True, min_df=1)
    X = vec.fit_transform(docs)
    S = cosine_similarity(X)
    np.fill_diagonal(S, 0.0)

    pairs = []
    idx = np.argwhere(S >= C.SIMILARITY_STORE_THRESHOLD)
    for i, j in idx:
        if i >= j:
            continue
        a, b = codes[i], codes[j]
        ka, kb = set(courses[a]["keywords"]), set(courses[b]["keywords"])
        shared = sorted(ka & kb)
        score = round(float(S[i, j]), 4)
        pairs.append({
            "course_1": a, "course_1_title": courses[a]["title"],
            "course_1_dept": courses[a]["department"],
            "course_2": b, "course_2_title": courses[b]["title"],
            "course_2_dept": courses[b]["department"],
            "similarity_score": score,
            "same_department": courses[a]["department"] == courses[b]["department"],
            "potential_redundancy": bool(score >= 0.90 and shared),
            "shared_keywords": shared,
        })
    pairs.sort(key=lambda p: -p["similarity_score"])

    # Bidirectional map, matching load_similarity_data()
    sim_map = defaultdict(dict)
    for p in pairs:
        info = {"similarity_score": p["similarity_score"],
                "same_department": p["same_department"],
                "shared_keywords": p["shared_keywords"]}
        sim_map[p["course_1"]][p["course_2"]] = {**info, "title": p["course_2_title"]}
        sim_map[p["course_2"]][p["course_1"]] = {**info, "title": p["course_1_title"]}
    return pairs, dict(sim_map)


def find_redundant_clusters(sim_map: dict, G: nx.DiGraph,
                            min_similarity: float) -> list:
    """Copied from the original analysis/redundancy_analysis.find_redundant_course_clusters."""
    visited, clusters = set(), []
    for course in sorted(G.nodes()):
        if course in visited or course not in sim_map:
            continue
        cluster, stack = {course}, [course]
        while stack:
            current = stack.pop()
            visited.add(current)
            for sim, info in sim_map.get(current, {}).items():
                if (info["similarity_score"] >= min_similarity
                        and sim in G.nodes() and sim not in visited):
                    cluster.add(sim)
                    stack.append(sim)
        if len(cluster) > 1:
            sims = [sim_map[c1][c2]["similarity_score"]
                    for c1 in cluster for c2 in cluster
                    if c1 < c2 and c2 in sim_map.get(c1, {})]
            depts = {c.split()[0] for c in cluster}
            clusters.append({
                "courses": sorted(cluster),
                "size": len(cluster),
                "avg_similarity": round(float(np.mean(sims)) if sims else 0.0, 4),
                "total_prereqs": sum(G.in_degree(c) for c in cluster),
                "total_unlocks": sum(G.out_degree(c) for c in cluster),
                "same_dept": len(depts) == 1,
            })
    return sorted(clusters, key=lambda c: -c["avg_similarity"])


def build_bottleneck_substitutes(G: nx.DiGraph, sim_map: dict, scores: dict,
                                 min_similarity: float) -> dict:
    """Copied from the original identify_bottleneck_substitutes, including the
    mutual-bottleneck deduplication rule."""
    course_scores = {c: s for c, s in scores.items() if c in G.nodes()}
    if not course_scores:
        return {}
    sorted_scores = sorted(course_scores.items(), key=lambda x: -x[1])
    bottlenecks = {c for c, s in sorted_scores if s >= C.BOTTLENECK_SCORE_THRESHOLD}
    lookup = dict(sorted_scores)

    out, seen_pairs = {}, set()
    for course, cscore in sorted_scores:
        if course not in bottlenecks or cscore == 0 or course not in sim_map:
            continue
        subs = []
        for sim, info in sim_map[course].items():
            if info["similarity_score"] < min_similarity or sim not in G.nodes():
                continue
            sscore = lookup.get(sim, 0)
            is_sub_bn = sim in bottlenecks
            pair = tuple(sorted([course, sim]))
            if is_sub_bn:
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                if sscore > cscore or (sscore == cscore and sim < course):
                    continue
            b_un, s_un = G.out_degree(course), G.out_degree(sim)
            b_pr, s_pr = G.in_degree(course), G.in_degree(sim)
            subs.append({
                "course": sim,
                "title": info.get("title", ""),
                "similarity": info["similarity_score"],
                "same_dept": info["same_department"],
                "shared_keywords": info.get("shared_keywords", []),
                "bottleneck_centrality": round(cscore, 6),
                "substitute_centrality": round(sscore, 6),
                "bottleneck_unlocks": b_un, "substitute_unlocks": s_un,
                "bottleneck_prereqs": b_pr, "substitute_prereqs": s_pr,
                "is_better_access": bool(s_pr <= b_pr and s_un >= b_un * 0.5),
                "is_mutual_bottleneck": is_sub_bn,
            })
        if subs:
            out[course] = sorted(subs, key=lambda s: -s["similarity"])
    return out


# ============================================================
# 11. Program metrics — exact replication of calculate_program_metrics
# ============================================================

def compute_program_metrics(programs: dict, courses: dict, G: nx.DiGraph,
                            scores: dict, program_tags: dict,
                            course_mode: str = "required") -> dict:
    """Copied from the original graphs.calculate_program_metrics, including its
    density convention (directed edge count over undirected max pairs)."""
    metrics = {}
    for prog_code, prog in programs.items():
        version = prog["versions"][-1]
        extracted = extract_program_courses(prog, mode=course_mode, version=version)
        courses_set = set(extracted)
        if course_mode == "all":
            courses_set |= set(resolve_ranges(prog, courses, version))

        valid = [c for c in sorted(courses_set) if c in G.nodes()]
        if not valid:
            continue
        sub = G.subgraph(valid)
        n = sub.number_of_nodes()
        num_edges = sub.number_of_edges()
        in_deg = [d for _, d in sub.in_degree()]
        out_deg = [d for _, d in sub.out_degree()]
        max_edges = n * (n - 1) / 2

        try:
            depth = nx.dag_longest_path_length(sub) if nx.is_directed_acyclic_graph(sub) else 0
        except Exception:
            depth = 0

        prog_scores = {c: scores[c] for c in valid if scores.get(c, 0) > 0}
        bottleneck_courses = [c for c, _ in sorted(prog_scores.items(),
                                                   key=lambda x: -x[1])[:3]]

        shared = [c for c in valid if len(program_tags.get(c, [])) > 1]
        lower = sum(1 for c in valid if courses[c]["level"] <= 3)
        level_counts = Counter(courses[c]["level"] for c in valid)

        cross_dept = sum(1 for c in valid if courses[c]["department"] != prog["department"])

        metrics[prog_code] = {
            "program_code": prog_code,
            "program_title": prog["program_title"],
            "department": prog["department"],
            "degree_type": prog["degree_type"],
            "total_credits": version["program_metadata"]["total_credits"],
            "total_courses": n,
            "num_connections": num_edges,
            "avg_prereqs": round(sum(in_deg) / n, 4),
            "max_prereqs": max(in_deg, default=0),
            "density": round(num_edges / max_edges, 6) if max_edges > 0 else 0.0,
            "max_depth": depth,
            "cross_program_share": round(len(shared) / n, 4),
            "avg_unlocks": round(sum(out_deg) / n, 4),
            "foundational_ratio": round(lower / n, 4),
            "level_ratios": {str(l): round(cnt / n * 100, 1)
                             for l, cnt in sorted(level_counts.items())},
            "modularity_proxy": nx.number_connected_components(sub.to_undirected()),
            "bottleneck_courses": bottleneck_courses,
            # Additional metric the blueprint asks for that the original computed
            # only implicitly via cross_program_share
            "cross_dept_pct": round(cross_dept / n * 100, 2),
            "gateway_count": sum(1 for c in valid if len(program_tags.get(c, [])) >= 5),
        }
    return metrics


# ============================================================
# 12. Demand forecast — exact DemandAggregator formulas
# ============================================================

def generate_demand(courses: dict, programs: dict, behavioral: dict, scores: dict,
                    published_terms: list, rng: random.Random) -> dict:
    """Synthesise the student preference submissions the original tab was waiting on,
    run the exact aggregator formulas, and pre-compute every growth scenario.

    The original Demand Forecast tab was disabled precisely because no preference feed
    existed. The blueprint reinterprets the tab as a department growth-% slider. Both
    are produced: the table schema is the original's, and each growth scenario is a
    separate pre-computed block the slider selects between.
    """
    forecast_term = published_terms[-1]
    prog_codes = sorted(programs)

    # --- Synthetic preference submissions ---
    prefs = []
    n_planners = 2400
    for i in range(n_planners):
        pc = rng.choice(prog_codes)
        allc = sorted(extract_program_courses(programs[pc], mode="all"))
        if len(allc) < 6:
            continue
        n_slots = rng.randint(*C.PREFERENCE_SLOTS)
        slots = {}
        pool = rng.sample(allc, k=min(len(allc), n_slots * C.PREFS_PER_SLOT))
        for s in range(n_slots):
            chunk = pool[s * C.PREFS_PER_SLOT:(s + 1) * C.PREFS_PER_SLOT]
            if chunk:
                slots[f"slot_{s + 1}"] = chunk
        if slots:
            prefs.append({"student_id": f"PLAN{i:05d}", "program": pc,
                          "preferences": slots, "term": forecast_term})

    unique_plans = len({(p["student_id"], p["term"]) for p in prefs})

    # --- Aggregate (slot-aware, ranks beyond 3 discarded) ---
    demand = defaultdict(lambda: {"total_requests": 0, "rank_1": 0, "rank_2": 0,
                                  "rank_3": 0, "students": set()})
    for p in prefs:
        for _slot, clist in p["preferences"].items():
            for rank, course in enumerate(clist, start=1):
                if rank > 3:
                    continue
                d = demand[course]
                d["total_requests"] += 1
                d[f"rank_{rank}"] += 1
                d["students"].add(p["student_id"])

    def build(growth: float, dept_filter: str | None = None) -> list:
        rows = []
        for course, d in demand.items():
            if course not in courses:
                continue
            if dept_filter and courses[course]["department"] != dept_filter:
                continue
            b = behavioral.get(course, {})
            g = 1.0 + growth
            weighted = sum(d[f"rank_{r}"] * C.RANK_WEIGHTS[r] for r in C.RANK_WEIGHTS) * g
            max_enr = b.get("max_enrollment_capacity", 40)
            sections = b.get("sections_per_semester", 1)
            capacity = max_enr * sections
            ml_risk = scores.get(course, 0.5)
            shortage = max(0.0, weighted - capacity)
            sections_needed = int(math.ceil(shortage / C.DEFAULT_SECTION_SIZE)) if shortage > 0 else 0
            rows.append({
                "course": course,
                "title": courses[course]["title"],
                "department": courses[course]["department"],
                "total_requests": d["total_requests"],
                "rank_1_requests": d["rank_1"],
                "rank_2_requests": d["rank_2"],
                "rank_3_requests": d["rank_3"],
                "weighted_demand": round(weighted, 2),
                "current_capacity": round(capacity, 2),
                "shortage": round(shortage, 2),
                "sections_needed": sections_needed,
                "ml_risk": round(ml_risk, 4),
                "fill_rate": round(b.get("avg_fill_rate", 0.75), 4),
                "priority_score": round(
                    shortage * 0.4 + ml_risk * 100 * 0.3 + weighted * 0.3, 3),
                "capacity_exceeded": bool(shortage > 0),
            })
        return sorted(rows, key=lambda r: -r["shortage"])

    # Most columns in the table are scenario-invariant (title, department, request
    # counts, capacity, ML risk, fill rate). Only the four demand-derived figures move
    # with the growth percentage, so the invariant block ships once and each scenario
    # ships a delta keyed by course code. Repeating every row five times cost ~1 MB.
    base_rows = build(0.0)
    invariant_keys = ["course", "title", "department", "total_requests",
                      "rank_1_requests", "rank_2_requests", "rank_3_requests",
                      "current_capacity", "ml_risk", "fill_rate"]
    courses_block = [{k: r[k] for k in invariant_keys} for r in base_rows]
    delta_keys = ["weighted_demand", "shortage", "sections_needed", "priority_score"]

    scenarios = {}
    for growth in C.GROWTH_SCENARIOS:
        key = f"{int(growth * 100)}"
        rows = build(growth)
        scenarios[key] = {
            "growth_pct": int(growth * 100),
            "kpis": {
                "total_plans_submitted": unique_plans,
                "courses_with_shortages": sum(1 for r in rows if r["shortage"] > 0),
                "sections_needed": sum(r["sections_needed"] for r in rows),
                "courses_analyzed": len(rows),
                "total_shortage": round(sum(r["shortage"] for r in rows), 1),
            },
            # [weighted_demand, shortage, sections_needed, priority_score]
            "deltas": {r["course"]: [r[k] for k in delta_keys] for r in rows},
            "critical_courses": [r["course"] for r in sorted(
                [r for r in rows if r["ml_risk"] > 0.7 and r["weighted_demand"] > 30],
                key=lambda r: -r["priority_score"])[:10]],
            "recommendations": _recommendations(rows),
        }

    # Per-department scenario KPIs so the department filter does not require
    # recomputation in the browser
    by_dept = {}
    for dept in C.DEPARTMENTS:
        by_dept[dept["code"]] = {}
        for growth in C.GROWTH_SCENARIOS:
            rows = build(growth, dept_filter=dept["code"])
            by_dept[dept["code"]][f"{int(growth * 100)}"] = {
                "courses_with_shortages": sum(1 for r in rows if r["shortage"] > 0),
                "sections_needed": sum(r["sections_needed"] for r in rows),
                "courses_analyzed": len(rows),
                "total_shortage": round(sum(r["shortage"] for r in rows), 1),
            }

    return {
        "forecast_term": forecast_term,
        "forecast_term_label": term_display(forecast_term),
        "rank_weights": {str(k): v for k, v in C.RANK_WEIGHTS.items()},
        "section_size_assumption": C.DEFAULT_SECTION_SIZE,
        "growth_scenarios": [int(g * 100) for g in C.GROWTH_SCENARIOS],
        "invariant_keys": invariant_keys,
        "delta_keys": delta_keys,
        "courses": courses_block,
        "scenarios": scenarios,
        "by_department": by_dept,
        "enrollment_forecast_model": None,  # filled in by main()
        "formulas": {
            "weighted_demand": "sum(rank_r_count * rank_weight_r) * (1 + growth)",
            "current_capacity": "max_enrollment_capacity * sections_per_semester",
            "shortage": "max(0, weighted_demand - current_capacity)",
            "sections_needed": f"ceil(shortage / {C.DEFAULT_SECTION_SIZE})",
            "priority_score": "shortage*0.4 + ml_risk*100*0.3 + weighted_demand*0.3",
        },
        "note": ("The original Demand Forecast tab aggregated ranked student course "
                 "preferences but was disabled because no preference feed existed. "
                 "Preferences are synthesised here and run through the original's exact "
                 "formulas; the growth scenarios layer the blueprint's department-growth "
                 "slider on top of that same table."),
    }


def train_demand_model(rows: list, courses: dict, published_terms: list) -> dict:
    """Reproduce the original's RandomForest enrollment forecaster.

    This is the *second* demand path in the original system and the source of its
    "MAE 11.16 students, 28.7% over naive" figure. It lived in R
    (model_data/demand_model_rf.rds) and was never wired into the Shiny dashboard —
    separate from DemandAggregator, which does no statistical modelling at all.

    Panel and feature set are taken from the original's course_term_enrollment.csv
    header. Target is next-occurrence enrollment; the naive baseline is literally
    same_season_last_year_enrollment, which is what the 28.7% improvement is measured
    against.
    """
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error

    # --- Collapse sections into one course-term row ---
    panel: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r["course"], r["term_code"])
        p = panel.setdefault(key, {
            "course_code": r["course"], "term_code": r["term_code"],
            "season": r["season"], "department": r["department"],
            "enrollment": 0, "capacity": 0, "waitlist": 0, "num_sections": 0,
        })
        p["enrollment"] += r["enrollment"]
        p["capacity"] += r["max_enrollment"]
        p["waitlist"] += r["waitlist"]
        p["num_sections"] += 1

    for p in panel.values():
        c = courses[p["course_code"]]
        p["year"] = int(p["term_code"][:4]) - (1 if p["season"] == "Fall" else 0)
        p["course_level"] = c["level"] * 1000
        p["credits"] = int(c["credits"])
        p["num_prereqs"] = len([x for x in c["prerequisites"] if x != p["course_code"]])
        p["num_coreqs"] = len(c["corequisites"])
        p["prereq_logic"] = c["prereq_logic"]
        p["has_prereqs"] = bool(p["num_prereqs"])
        p["fill_rate"] = p["enrollment"] / p["capacity"] if p["capacity"] else 0.0
        p["has_waitlist"] = int(p["waitlist"] > 0)
        p["at_capacity"] = int(p["enrollment"] >= p["capacity"])

    # --- Same-season-last-year lags ---
    season_terms = defaultdict(list)
    for t in published_terms:
        season_terms[term_season(t)].append(t)
    prev_term = {}
    for season, ts in season_terms.items():
        for a, b in zip(ts, ts[1:]):
            prev_term[b] = a

    logic_codes = {"NONE": 0, "SINGLE": 1, "OR": 2, "AND": 3, "COMPLEX": 4}
    feature_names = [
        "same_season_last_year_enrollment", "same_season_last_year_capacity",
        "same_season_last_year_fill_rate", "same_season_last_year_waitlist",
        "yoy_enrollment_change", "yoy_enrollment_pct_change",
        "capacity", "num_sections", "course_level", "credits",
        "num_prereqs", "num_coreqs", "prereq_logic_code", "has_prereqs",
        "season_code", "year",
    ]

    samples = []
    for (course, term), p in panel.items():
        prev_t = prev_term.get(term)
        if prev_t is None:
            continue
        q = panel.get((course, prev_t))
        if q is None:
            continue
        # yoy features need the lag *before* the lag; absent for the first pair
        prev2 = prev_term.get(prev_t)
        r2 = panel.get((course, prev2)) if prev2 else None
        yoy_change = (q["enrollment"] - r2["enrollment"]) if r2 else 0.0
        yoy_pct = (yoy_change / r2["enrollment"]) if (r2 and r2["enrollment"]) else 0.0

        samples.append({
            "course": course, "term": term, "y": p["enrollment"],
            "naive": q["enrollment"],
            "x": [
                q["enrollment"], q["capacity"], q["fill_rate"], q["waitlist"],
                yoy_change, yoy_pct,
                p["capacity"], p["num_sections"], p["course_level"], p["credits"],
                p["num_prereqs"], p["num_coreqs"],
                logic_codes.get(p["prereq_logic"], 0), int(p["has_prereqs"]),
                C.SEASON_ORDER.index(p["season"]), p["year"],
            ],
        })

    if len(samples) < 80:
        return {"error": "insufficient lagged course-term pairs", "n_samples": len(samples)}

    # --- Temporal split: hold out the most recent academic year ---
    # Splitting on a single term would put the whole test set in one season; the summer
    # sessions carry far smaller enrollments than Fall/Spring, so a summer-only test set
    # makes the naive lag baseline look artificially strong. Holding out a full academic
    # year keeps the season mix comparable between train and test.
    test_ay = max(s["term"][:4] for s in samples)
    train = [s for s in samples if s["term"][:4] != test_ay]
    test = [s for s in samples if s["term"][:4] == test_ay]
    if len(test) < 20 or len(train) < 40:
        cut = int(len(samples) * 0.75)
        ordered = sorted(samples, key=lambda s: s["term"])
        train, test = ordered[:cut], ordered[cut:]
        test_ay = "split-75/25"

    X_tr = np.array([s["x"] for s in train], dtype=float)
    y_tr = np.array([s["y"] for s in train], dtype=float)
    X_te = np.array([s["x"] for s in test], dtype=float)
    y_te = np.array([s["y"] for s in test], dtype=float)
    naive_te = np.array([s["naive"] for s in test], dtype=float)

    naive_mae = float(mean_absolute_error(y_te, naive_te))

    lr = LinearRegression().fit(X_tr, y_tr)
    lr_mae = float(mean_absolute_error(y_te, lr.predict(X_te)))

    rf = RandomForestRegressor(n_estimators=300, max_depth=12, min_samples_leaf=3,
                               random_state=C.SEED, n_jobs=-1).fit(X_tr, y_tr)
    rf_pred = rf.predict(X_te)
    rf_mae = float(mean_absolute_error(y_te, rf_pred))

    def improvement(mae):
        return round((naive_mae - mae) / naive_mae * 100, 1) if naive_mae else 0.0

    return {
        "target": "course-term total enrollment",
        "naive_baseline": "same_season_last_year_enrollment",
        "test_academic_year": test_ay,
        "test_split": f"held out academic year {test_ay}",
        "n_train": len(train),
        "n_test": len(test),
        "features": feature_names,
        "models": {
            "Naive": {"test_mae": round(naive_mae, 3), "improvement_pct": 0.0},
            "Linear Regression": {"test_mae": round(lr_mae, 3),
                                  "improvement_pct": improvement(lr_mae)},
            "Random Forest": {"test_mae": round(rf_mae, 3),
                              "improvement_pct": improvement(rf_mae)},
        },
        "feature_importance": {
            f: round(float(w), 5)
            for f, w in sorted(zip(feature_names, rf.feature_importances_),
                               key=lambda x: -x[1])
        },
        "predictions": [
            {"course": s["course"], "actual": int(s["y"]),
             "predicted": round(float(pred), 1), "naive": int(s["naive"])}
            for s, pred in zip(test, rf_pred)
        ][:400],
        "note": ("Separate from the preference aggregator: this is the enrollment "
                 "forecaster the original trained in R and never wired into the "
                 "dashboard. MAE figures here are measured on synthetic data, not "
                 "copied from the real model."),
    }


def _recommendations(rows: list) -> list:
    """Mirrors the recommendations.txt export from the original tab."""
    out = []
    for r in sorted(rows, key=lambda r: -r["priority_score"])[:15]:
        if r["sections_needed"] >= 3:
            action, urgency = f"Add {r['sections_needed']} sections", "HIGH"
        elif r["sections_needed"] >= 1:
            action, urgency = f"Add {r['sections_needed']} section", "MODERATE"
        elif r["ml_risk"] > 0.7:
            action, urgency = "Monitor — high bottleneck risk", "MODERATE"
        else:
            action, urgency = "No action needed", "LOW"
        out.append({
            "course": r["course"], "action": action, "urgency": urgency,
            "impact": f"{int(r['shortage'])} students currently unserved",
            "reason": (f"Weighted demand {r['weighted_demand']:.0f} vs capacity "
                       f"{r['current_capacity']:.0f}; ML risk {r['ml_risk']:.0%}"),
        })
    return out


# ============================================================
# 13. Department responsiveness — Tab 8
# ============================================================

def compute_responsiveness(rows: list, published_terms: list) -> dict:
    """Pearson correlation between Year N enrollment and Year N+1 capacity, plus the
    blueprint's 40% utilization / 30% over-capacity / 30% waitlist weighted score.

    Rebuilt from the blueprint's written spec — the Dash dashboard that originally
    contained this tab is not present in the codebase.
    """
    from scipy.stats import pearsonr

    # Group published terms into academic years
    years = sorted({t[:4] for t in published_terms})
    by_dept_year = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_dept_year[r["department"]][r["term_code"][:4]].append(r)

    def corr(xs, ys):
        if len(xs) < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
            return 0.0, 1.0
        try:
            r, p = pearsonr(xs, ys)
        except Exception:
            return 0.0, 1.0
        return (0.0 if math.isnan(r) else float(r),
                1.0 if math.isnan(p) else float(p))

    raw = {}
    for dept in C.DEPARTMENTS:
        d = dept["code"]
        year_rows = by_dept_year.get(d, {})
        pairs_n, pairs_n1, per_pair = [], [], []
        unmet_all, capdelta_all = [], []

        for y_n, y_n1 in zip(years, years[1:]):
            a, b = year_rows.get(y_n, []), year_rows.get(y_n1, [])
            if not a or not b:
                continue
            # Match like-for-like: courses present in both years
            enr_n, cap_n, wl_n, cap_n1 = (defaultdict(int) for _ in range(4))
            for r in a:
                enr_n[r["course"]] += r["enrollment"]
                cap_n[r["course"]] += r["max_enrollment"]
                wl_n[r["course"]] += r["waitlist"]
            for r in b:
                cap_n1[r["course"]] += r["max_enrollment"]
            common = sorted(set(enr_n) & set(cap_n1))
            if len(common) < 3:
                continue

            xs = [enr_n[c] for c in common]
            ys = [cap_n1[c] for c in common]
            pairs_n.extend(xs)
            pairs_n1.extend(ys)

            # Unmet demand in year N vs. the capacity change the department made
            # going into year N+1. This is the discriminating signal.
            unmet = [wl_n[c] + max(0, enr_n[c] - cap_n[c]) for c in common]
            capdelta = [cap_n1[c] - cap_n[c] for c in common]
            unmet_all.extend(unmet)
            capdelta_all.extend(capdelta)

            r_val, p_val = corr(xs, ys)
            dr_val, _ = corr(unmet, capdelta)
            per_pair.append({
                "year_n": y_n, "year_n_label": f"AY{y_n}",
                "year_n_plus_1": y_n1, "year_n_plus_1_label": f"AY{y_n1}",
                "n_courses": len(common),
                "correlation": round(r_val, 4),
                "p_value": round(p_val, 5),
                "demand_response_correlation": round(dr_val, 4),
                "total_enrollment_year_n": sum(xs),
                "total_capacity_year_n_plus_1": sum(ys),
                "total_unmet_demand_year_n": sum(unmet),
                "total_capacity_added": sum(capdelta),
            })

        overall_r, overall_p = corr(pairs_n, pairs_n1)
        dr_r, dr_p = corr(unmet_all, capdelta_all)

        dept_rows = [r for r in rows if r["department"] == d]

        # Unmet-demand trend: mean unserved students per section in the first published
        # academic year vs the last. Positive means the department closed the gap.
        first_y, last_y = years[0], years[-1]
        def unmet_per_section(y):
            rs = year_rows.get(y, [])
            if not rs:
                return 0.0
            return float(np.mean([r["waitlist"] + max(0, r["enrollment"] - r["max_enrollment"])
                                  for r in rs]))
        u_first, u_last = unmet_per_section(first_y), unmet_per_section(last_y)
        # Symmetric and bounded to (-1, 1). A plain (first-last)/first ratio explodes
        # when the department started from a small base.
        unmet_trend = (u_first - u_last) / (u_first + u_last + 1.0)

        # Served rate: of everyone who wanted a seat, what share got one. Unlike raw
        # utilization this is penalised by unmet demand, so a department cannot score
        # well simply by running full sections with a long waitlist behind them.
        served = sum(r["enrollment"] for r in dept_rows)
        unserved = sum(r["waitlist"] + max(0, r["enrollment"] - r["max_enrollment"])
                       for r in dept_rows)
        served_rate = served / (served + unserved) if (served + unserved) else 0.0

        raw[d] = {
            "dept": dept,
            "correlation": overall_r,
            "p_value": overall_p,
            "demand_response_correlation": dr_r,
            "demand_response_p": dr_p,
            "unmet_trend": unmet_trend,
            "unmet_first_year": u_first,
            "unmet_last_year": u_last,
            "served_rate": served_rate,
            "utilization": float(np.mean([min(r["enrollment"] / r["max_enrollment"], 1.5)
                                         for r in dept_rows])) if dept_rows else 0.0,
            "over_capacity_rate": float(np.mean([r["enrollment"] >= r["max_enrollment"]
                                                 for r in dept_rows])) if dept_rows else 0.0,
            "waitlist_rate": float(np.mean([r["waitlist"] > 0
                                            for r in dept_rows])) if dept_rows else 0.0,
            "n_sections": len(dept_rows),
            "n_courses": len({r["course"] for r in dept_rows}),
            "term_pairs": per_pair,
        }

    # --- Peer-relative scoring ---
    # Components live on incomparable absolute scales (utilization sits near 0.9 for
    # everyone, waitlist rate near 0.3), so a raw weighted sum lands every department in
    # the same band and the classification carries no information. Each component is
    # min-max normalised across departments first, so scores answer "how does this
    # department compare to its peers" — the question the ranking chart actually poses.
    def normalize(key, invert=False):
        vals = {d: raw[d][key] for d in raw}
        lo, hi = min(vals.values()), max(vals.values())
        span = hi - lo
        out = {}
        for d, v in vals.items():
            n = 0.5 if span == 0 else (v - lo) / span
            out[d] = (1.0 - n) if invert else n
        return out

    util_n = normalize("utilization")
    over_n = normalize("over_capacity_rate", invert=True)
    wl_n = normalize("waitlist_rate", invert=True)
    dr_n = normalize("demand_response_correlation")
    trend_n = normalize("unmet_trend")
    served_n = normalize("served_rate")

    w = C.RESPONSIVENESS_WEIGHTS
    scored = {}
    for d, r in raw.items():
        # The specified formula, applied literally to raw component values:
        # 40% utilization, 30% over-capacity, 30% waitlist. Utilization counts
        # positively (seats used); over-capacity and waitlist count negatively
        # (unserved demand), so both are inverted.
        scored[d] = (w["utilization"] * min(r["utilization"], 1.0)
                     + w["over_capacity"] * (1.0 - r["over_capacity_rate"])
                     + w["waitlist"] * (1.0 - r["waitlist_rate"]))

    # Classification thresholds are not given anywhere in the original or the blueprint,
    # so terciles of the observed distribution are used rather than invented cut-points.
    ordered = sorted(scored, key=lambda d: scored[d])
    n_dept = len(ordered)
    class_of = {}
    for i, d in enumerate(ordered):
        idx = min(2, int(i * len(C.RESPONSIVENESS_CLASSES) / max(1, n_dept)))
        class_of[d] = C.RESPONSIVENESS_CLASSES[idx]
    tercile_cuts = [round(scored[ordered[int(n_dept * f)]], 4) for f in (1 / 3, 2 / 3)]

    out = {}
    for d, r in raw.items():
        score = scored[d]
        classification = class_of[d]
        out[d] = {
            "department": d,
            "department_name": r["dept"]["name"],
            "color": r["dept"]["color"],
            "correlation": round(r["correlation"], 4),
            "p_value": round(r["p_value"], 5),
            "demand_response_correlation": round(r["demand_response_correlation"], 4),
            "demand_response_p_value": round(r["demand_response_p"], 5),
            "responsiveness_score": round(score, 4),
            "classification": classification,
            # The three components the specified formula weights, as raw values.
            "components": {
                "utilization": round(r["utilization"], 4),
                "over_capacity_rate": round(r["over_capacity_rate"], 4),
                "waitlist_rate": round(r["waitlist_rate"], 4),
            },
            "component_contributions": {
                "utilization": round(w["utilization"] * min(r["utilization"], 1.0), 4),
                "over_capacity": round(w["over_capacity"] * (1 - r["over_capacity_rate"]), 4),
                "waitlist": round(w["waitlist"] * (1 - r["waitlist_rate"]), 4),
            },
            # Supplementary diagnostics, reported alongside but NOT part of the score.
            "diagnostics": {
                "demand_response_correlation": round(r["demand_response_correlation"], 4),
                "unmet_trend": round(r["unmet_trend"], 4),
                "unmet_per_section_first_year": round(r["unmet_first_year"], 2),
                "unmet_per_section_last_year": round(r["unmet_last_year"], 2),
                "served_rate": round(r["served_rate"], 4),
                "utilization_peer_normalized": round(util_n[d], 4),
                "demand_response_peer_normalized": round(dr_n[d], 4),
                "unmet_trend_peer_normalized": round(trend_n[d], 4),
                "served_rate_peer_normalized": round(served_n[d], 4),
            },
            "n_sections": r["n_sections"],
            "n_courses": r["n_courses"],
            "term_pairs": r["term_pairs"],
        }

    ranked = sorted(out.values(), key=lambda x: -x["responsiveness_score"])
    return {
        "weights": C.RESPONSIVENESS_WEIGHTS,
        "classes": C.RESPONSIVENESS_CLASSES,
        "tercile_cuts": tercile_cuts,
        "formula": ("0.40 * min(utilization, 1) + 0.30 * (1 - over_capacity_rate) "
                    "+ 0.30 * (1 - waitlist_rate)"),
        "scoring_note": (
            "The 40% utilization / 30% over-capacity / 30% waitlist weighting is applied "
            "literally to raw component values. Utilization counts positively (seats "
            "used); over-capacity and waitlist count negatively (unserved demand) and are "
            "inverted. Classification thresholds are not specified in the original or the "
            "blueprint — the Dash dashboard that produced this tab is not in the "
            "codebase — so terciles of the observed distribution are used rather than "
            "invented cut-points."),
        "diagnostics_note": (
            "One caveat worth surfacing in the UI: all three weighted components are "
            "demand indicators, so a department under little demand scores well without "
            "having adjusted anything. The `diagnostics` block on each department carries "
            "measures that isolate response rather than demand — chiefly "
            "`demand_response_correlation` (Pearson r between unmet demand in year N and "
            "the capacity change into year N+1) and `unmet_trend`. These are reported "
            "only; they do not enter responsiveness_score."),
        "correlation_note": (
            "`correlation` is the blueprint's literal metric: Pearson r between Year N "
            "enrollment and Year N+1 capacity, across courses offered in both years. It "
            "runs high for every department because both quantities scale with course "
            "size. `demand_response_correlation` is the discriminating measure: Pearson r "
            "between unmet demand in Year N (waitlist + over-capacity enrollment) and the "
            "capacity change into Year N+1. That is what 'how well do departments learn' "
            "actually asks."),
        "departments": out,
        "ranking": [d["department"] for d in ranked],
        "summary": {
            "most_responsive": ranked[0]["department"] if ranked else None,
            "least_responsive": ranked[-1]["department"] if ranked else None,
            "mean_correlation": round(float(np.mean(
                [d["correlation"] for d in out.values()])), 4) if out else 0.0,
            "mean_demand_response_correlation": round(float(np.mean(
                [d["diagnostics"]["demand_response_correlation"]
                 for d in out.values()])), 4) if out else 0.0,
            "n_responsive": sum(1 for d in out.values()
                                if d["classification"] == "responsive"),
            "n_moderate": sum(1 for d in out.values()
                              if d["classification"] == "moderate"),
            "n_unresponsive": sum(1 for d in out.values()
                                  if d["classification"] == "unresponsive"),
        },
    }


# ============================================================
# 14. Temporal patterns — Tab 7
# ============================================================

def compute_temporal(rows: list, published_terms: list) -> dict:
    """Department x term matrices for the seasonal heatmap, plus season aggregates."""
    depts = [d["code"] for d in C.DEPARTMENTS]
    idx = {(r_d, r_t): {"enr": 0, "cap": 0, "wl": 0, "sections": 0}
           for r_d in depts for r_t in published_terms}
    for r in rows:
        cell = idx[(r["department"], r["term_code"])]
        cell["enr"] += r["enrollment"]
        cell["cap"] += r["max_enrollment"]
        cell["wl"] += r["waitlist"]
        cell["sections"] += 1

    def matrix(metric):
        out = []
        for d in depts:
            row = []
            for t in published_terms:
                c = idx[(d, t)]
                if metric == "enrollment":
                    row.append(c["enr"])
                elif metric == "fill_rate":
                    row.append(round(c["enr"] / c["cap"], 4) if c["cap"] else 0.0)
                elif metric == "waitlist":
                    row.append(c["wl"])
                else:
                    row.append(c["sections"])
            out.append(row)
        return out

    seasons = {}
    for season in C.SEASON_ORDER:
        s_rows = [r for r in rows if r["season"] == season]
        if not s_rows:
            continue
        seasons[season] = {
            "sections": len(s_rows),
            "total_enrollment": sum(r["enrollment"] for r in s_rows),
            "mean_fill_rate": round(float(np.mean(
                [r["enrollment"] / r["max_enrollment"] for r in s_rows])), 4),
            "at_capacity_rate": round(float(np.mean(
                [r["enrollment"] >= r["max_enrollment"] for r in s_rows])), 4),
            "waitlist_rate": round(float(np.mean([r["waitlist"] > 0 for r in s_rows])), 4),
            "mean_section_size": round(float(np.mean([r["enrollment"] for r in s_rows])), 2),
        }

    # Like-for-like term comparison: same season, consecutive years
    like_for_like = []
    for season in C.SEASON_ORDER:
        s_terms = [t for t in published_terms if term_season(t) == season]
        for t_a, t_b in zip(s_terms, s_terms[1:]):
            a = [r for r in rows if r["term_code"] == t_a]
            b = [r for r in rows if r["term_code"] == t_b]
            if not a or not b:
                continue
            ea, eb = sum(r["enrollment"] for r in a), sum(r["enrollment"] for r in b)
            like_for_like.append({
                "season": season,
                "term_a": t_a, "term_a_label": term_display(t_a),
                "term_b": t_b, "term_b_label": term_display(t_b),
                "enrollment_a": ea, "enrollment_b": eb,
                "pct_change": round((eb - ea) / ea * 100, 2) if ea else 0.0,
                "fill_rate_a": round(float(np.mean(
                    [r["enrollment"] / r["max_enrollment"] for r in a])), 4),
                "fill_rate_b": round(float(np.mean(
                    [r["enrollment"] / r["max_enrollment"] for r in b])), 4),
            })

    return {
        "departments": depts,
        "department_names": {d["code"]: d["name"] for d in C.DEPARTMENTS},
        "terms": published_terms,
        "term_labels": [term_display(t) for t in published_terms],
        "term_seasons": [term_season(t) for t in published_terms],
        "matrices": {m: matrix(m) for m in
                     ("enrollment", "fill_rate", "waitlist", "sections")},
        "seasons": seasons,
        "like_for_like": like_for_like,
    }


# ============================================================
# 15. Summary stats — Tab 6
# ============================================================

def compute_summary(rows: list, courses: dict, programs: dict, G: nx.DiGraph,
                    behavioral: dict, scores: dict, published_terms: list,
                    cleaning: dict, model_results: dict, pairs: list,
                    clusters: list) -> dict:
    fills = [r["enrollment"] / r["max_enrollment"] for r in rows]
    at_cap = [r["enrollment"] >= r["max_enrollment"] for r in rows]
    has_wl = [r["waitlist"] > 0 for r in rows]

    per_term = []
    for t in published_terms:
        t_rows = [r for r in rows if r["term_code"] == t]
        per_term.append({
            "term": t, "label": term_display(t), "season": term_season(t),
            "sections": len(t_rows),
            "total_enrollment": sum(r["enrollment"] for r in t_rows),
            "total_capacity": sum(r["max_enrollment"] for r in t_rows),
            "mean_fill_rate": round(float(np.mean(
                [r["enrollment"] / r["max_enrollment"] for r in t_rows])), 4),
            "at_capacity_rate": round(float(np.mean(
                [r["enrollment"] >= r["max_enrollment"] for r in t_rows])), 4),
            "waitlist_rate": round(float(np.mean([r["waitlist"] > 0 for r in t_rows])), 4),
        })

    # Capacity utilization histogram (20 bins, 0 to 1.5)
    hist, edges = np.histogram(np.clip(fills, 0, 1.5), bins=20, range=(0, 1.5))

    undirected = G.to_undirected()
    components = list(nx.connected_components(undirected))
    comp_sizes = sorted((len(c) for c in components), reverse=True)
    bn = [c for c, s in scores.items() if s >= C.BOTTLENECK_SCORE_THRESHOLD]

    dag = nx.DiGraph(G)
    try:
        longest = nx.dag_longest_path(dag) if nx.is_directed_acyclic_graph(dag) else []
    except Exception:
        longest = []

    return {
        "university": C.UNIVERSITY_NAME,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "kpis": {
            "total_courses": len(courses),
            "total_programs": len(programs),
            "total_departments": len(C.DEPARTMENTS),
            "total_sections": len(rows),
            "total_terms": len(published_terms),
            "total_enrollment": int(sum(r["enrollment"] for r in rows)),
            "total_capacity": int(sum(r["max_enrollment"] for r in rows)),
            "pct_at_capacity": round(float(np.mean(at_cap)) * 100, 1),
            "pct_with_waitlist": round(float(np.mean(has_wl)) * 100, 1),
            "mean_fill_rate": round(float(np.mean(fills)), 4),
            "median_fill_rate": round(float(np.median(fills)), 4),
            "mean_section_size": round(float(np.mean([r["enrollment"] for r in rows])), 1),
            "total_waitlisted_students": int(sum(r["waitlist"] for r in rows)),
            "bottleneck_courses": len(bn),
            "pct_bottleneck": round(len(bn) / len(scores) * 100, 1) if scores else 0.0,
        },
        "graph": {
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "prerequisite_edges": G.number_of_edges(),
            "corequisite_edges": sum(len(c["corequisites"]) for c in courses.values()),
            "components": len(components),
            "largest_component": comp_sizes[0] if comp_sizes else 0,
            "isolated_nodes": sum(1 for s in comp_sizes if s == 1),
            "mean_component_size": round(float(np.mean(comp_sizes)), 2) if comp_sizes else 0,
            "longest_chain_depth": max(0, len(longest) - 1),
            "longest_chain": longest,
            "mean_in_degree": round(
                sum(d for _, d in G.in_degree()) / G.number_of_nodes(), 3),
            "max_in_degree": max((d for _, d in G.in_degree()), default=0),
            "max_out_degree": max((d for _, d in G.out_degree()), default=0),
            "is_dag": cleaning["is_dag"],
            "self_loops_removed": cleaning["self_loops_removed"],
            "cycles_broken": cleaning["cycles_broken"],
        },
        "enrollment_by_term": per_term,
        "fill_rate_histogram": {
            "bin_edges": [round(float(e), 3) for e in edges],
            "counts": [int(c) for c in hist],
        },
        "capacity_donut": {
            "under_75": int(sum(1 for f in fills if f < 0.75)),
            "between_75_95": int(sum(1 for f in fills if 0.75 <= f < 0.95)),
            "between_95_100": int(sum(1 for f in fills if 0.95 <= f < 1.0)),
            "at_or_over": int(sum(1 for f in fills if f >= 1.0)),
        },
        "models": model_results,
        "nlp": {
            "pairs_stored": len(pairs),
            "pairs_at_080": sum(1 for p in pairs if p["similarity_score"] >= 0.80),
            "pairs_at_085": sum(1 for p in pairs if p["similarity_score"] >= 0.85),
            "pairs_at_090": sum(1 for p in pairs if p["similarity_score"] >= 0.90),
            "clusters": len(clusters),
            "method": "TF-IDF (1-2 grams, sublinear tf) + cosine similarity",
        },
        "real_system_context": {
            "note": ("The production system operates on protected institutional data at "
                     "roughly 10x this scale. Figures below are the real system's, "
                     "recorded for context; every number elsewhere in this dashboard "
                     "is synthetic."),
            "courses": 8587, "programs": 1017, "graph_nodes": 8579,
            "graph_edges": 8072, "graph_components": 5575,
            "similarity_pairs_at_080": 25431, "similarity_clusters": 334,
            "rf_auc": 0.772, "rf_precision_at_20": 0.85,
            "markov_recall_at_10": 0.503, "rf_demand_mae": 11.16,
            "pct_at_capacity": 36.0, "pct_with_waitlist": 31.9,
        },
    }


# ============================================================
# 16. Layout — precomputed hierarchical positions
# ============================================================

def layered_dag_layout(G: nx.DiGraph, courses: dict) -> tuple[dict, dict]:
    """Sugiyama-style layered layout: same tiers as the original, better ordering.

    The original assigns x within a tier alphabetically, which ignores the edges
    entirely — two courses joined by a prerequisite routinely land at opposite ends of a
    row for no reason. This keeps the tier assignment (course level, so vertical distance
    still reads as prerequisite depth) and replaces the ordering with a barycentre
    heuristic: each node is placed near the average position of its neighbours in the
    adjacent tier, sweeping down and up until the crossing count stops improving.

    Spacing is adaptive. Crossing minimisation alone does not narrow anything — the node
    count per tier is fixed, so the row stays as wide as before. Because node radius
    already shrinks with graph size in the original (`max(15, min(35, 500/n))`, i.e. 15px
    at this scale), tight spacing is visually appropriate, and bounding total width is
    what actually makes the unfiltered view usable.

    Returns (positions, stats).
    """
    tiers: dict[int, list[str]] = defaultdict(list)
    for node in G.nodes():
        tiers[courses[node]["level"]].append(node)
    levels = sorted(tiers)
    for lvl in levels:
        tiers[lvl].sort()          # deterministic starting order

    order = {lvl: list(tiers[lvl]) for lvl in levels}

    def count_crossings(order: dict) -> int:
        """Total edge crossings between every pair of adjacent tiers."""
        total = 0
        for upper, lower in zip(levels, levels[1:]):
            pos_u = {n: i for i, n in enumerate(order[upper])}
            pos_l = {n: i for i, n in enumerate(order[lower])}
            edges = [(pos_u[u], pos_l[v]) for u in order[upper]
                     for v in G.successors(u) if v in pos_l]
            edges.sort()
            # Count inversions in the lower endpoints — each is one crossing
            for i in range(len(edges)):
                for j in range(i + 1, len(edges)):
                    if edges[i][1] > edges[j][1]:
                        total += 1
        return total

    def barycentre(order: dict, lvl: int, ref_lvl: int, downward: bool) -> list:
        ref_pos = {n: i for i, n in enumerate(order[ref_lvl])}
        scored = []
        for i, node in enumerate(order[lvl]):
            neighbours = (G.predecessors(node) if downward else G.successors(node))
            idx = [ref_pos[n] for n in neighbours if n in ref_pos]
            # Nodes with no edge into the reference tier keep their current position,
            # which stops isolated courses from all collapsing to one end
            key = (sum(idx) / len(idx)) if idx else (i * len(ref_pos) / max(1, len(order[lvl])))
            scored.append((key, node))
        scored.sort(key=lambda t: (t[0], t[1]))
        return [n for _, n in scored]

    best = {lvl: list(order[lvl]) for lvl in levels}
    best_crossings = count_crossings(best)
    initial_crossings = best_crossings

    for sweep in range(8):
        downward = sweep % 2 == 0
        seq = levels[1:] if downward else levels[-2::-1]
        for lvl in seq:
            ref = lvl - 1 if downward else lvl + 1
            if ref not in order:
                continue
            order[lvl] = barycentre(order, lvl, ref, downward)
        c = count_crossings(order)
        if c < best_crossings:
            best_crossings, best = c, {l: list(order[l]) for l in levels}

    # Adaptive spacing: bound total width so the unfiltered graph fits a sane canvas
    widest = max(len(best[lvl]) for lvl in levels)
    x_spacing = max(40.0, min(150.0, 12000.0 / widest))
    y_spacing = 100

    xpos = {}
    for i, lvl in enumerate(levels):
        nodes = best[lvl]
        start_x = -(len(nodes) - 1) * x_spacing / 2
        for j, node in enumerate(nodes):
            xpos[node] = start_x + j * x_spacing

    def mean_edge_dx() -> float:
        d = [abs(xpos[u] - xpos[v]) for u, v in G.edges()
             if u in xpos and v in xpos]
        return float(np.mean(d)) if d else 0.0

    dx_uniform = mean_edge_dx()

    # ---- Coordinate assignment (Sugiyama step 4) ----
    # Ordering alone minimises *crossings*, which is not the same as making a chain look
    # like a chain: with uniform spacing, prerequisite-linked courses still sit far apart
    # on average. This pass slides each node toward the mean x of its neighbours in the
    # adjacent tiers, processing higher-degree nodes first and clamping each to its
    # in-tier neighbours so the ordering (and therefore the crossing count) is preserved.
    # Because nodes can only move within bounds set by their neighbours, total width
    # cannot grow.
    # Minimum separation is deliberately *below* the initial spacing. With min_sep equal
    # to the spacing, every node's lower and upper bound collapse onto its current
    # position and nothing can move at all. Allowing nodes to compress toward each other
    # creates the slack the pass needs; the hard extent clamp keeps total width from
    # growing in exchange.
    min_sep = x_spacing * 0.34
    half_extent = (widest - 1) * x_spacing / 2

    for _ in range(12):
        for lvl in levels:
            nodes = best[lvl]
            index = {n: j for j, n in enumerate(nodes)}
            priority = sorted(
                nodes,
                key=lambda n: -(G.in_degree(n) + G.out_degree(n)))
            for node in priority:
                neighbours = [n for n in
                              list(G.predecessors(node)) + list(G.successors(node))
                              if n in xpos and courses[n]["level"] != lvl]
                if not neighbours:
                    continue
                target = float(np.mean([xpos[n] for n in neighbours]))
                j = index[node]
                lo = xpos[nodes[j - 1]] + min_sep if j > 0 else -half_extent
                hi = xpos[nodes[j + 1]] - min_sep if j < len(nodes) - 1 else half_extent
                lo, hi = max(lo, -half_extent), min(hi, half_extent)
                if lo <= hi:
                    xpos[node] = min(max(target, lo), hi)

    dx_refined = mean_edge_dx()

    pos = {node: [round(xpos[node], 2), -levels.index(courses[node]["level"]) * y_spacing]
           for node in xpos}

    xs = [p[0] for p in pos.values()]
    width = max(xs) - min(xs)
    stats = {
        "algorithm": ("layered (tier = course level), barycentre ordering over 8 sweeps, "
                      "then priority-based coordinate assignment over 6 passes"),
        "crossings_alphabetical": initial_crossings,
        "crossings_after": best_crossings,
        "crossing_reduction_pct": round(
            (initial_crossings - best_crossings) / initial_crossings * 100, 1)
        if initial_crossings else 0.0,
        "mean_edge_dx_uniform": round(dx_uniform, 1),
        "mean_edge_dx_refined": round(dx_refined, 1),
        "edge_length_reduction_pct": round(
            (dx_uniform - dx_refined) / dx_uniform * 100, 1) if dx_uniform else 0.0,
        "x_spacing": x_spacing,
        "y_spacing": y_spacing,
        "width": round(width, 1),
        "height": (len(levels) - 1) * y_spacing,
        "widest_tier": widest,
        "tier_sizes": {str(lvl): len(best[lvl]) for lvl in levels},
    }
    return pos, stats


def hierarchical_layout(G: nx.DiGraph, courses: dict) -> dict:
    """Replicates graphs.create_hierarchical_layout exactly: group by level, sort
    alphabetically within level, centre horizontally at x_spacing=150, stack levels
    downward at y_spacing=100."""
    levels = defaultdict(list)
    for node in G.nodes():
        levels[courses[node]["level"]].append(node)

    pos = {}
    x_spacing, y_spacing = 150, 100
    for level_idx, lvl in enumerate(sorted(levels)):
        nodes = sorted(levels[lvl])
        n = len(nodes)
        start_x = -(n - 1) * x_spacing / 2
        for i, node in enumerate(nodes):
            pos[node] = [start_x + i * x_spacing, -level_idx * y_spacing]
    return pos


# ============================================================
# Emit
# ============================================================

def write_json(name: str, payload, out_dir: Path = DATA_OUT) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"), ensure_ascii=False)
    size = path.stat().st_size
    log(f"    wrote {name:34s} {size / 1024:9.1f} KB")
    return size


# ============================================================
# Main
# ============================================================

def main() -> int:
    # Belt and braces on reproducibility. Python randomises string hashes per process, so
    # any set or dict iteration that leaks into output makes the run irreproducible even
    # with a fixed seed. The known offender (nx.simple_cycles ordering) is handled
    # directly in build_prereq_graph, but this guarantees the property rather than relying
    # on having found every such site.
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.execve(sys.executable, [sys.executable, *sys.argv],
                  {**os.environ, "PYTHONHASHSEED": "0"})

    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="fewer students for a fast iteration loop")
    ap.add_argument("--students", type=int, default=None)
    args = ap.parse_args()

    n_students = args.students or (1500 if args.quick else C.N_STUDENTS)

    rng = random.Random(C.SEED)
    np_rng = np.random.default_rng(C.SEED)

    log(f"Pacific Ridge University mock data generator (seed={C.SEED})")

    # --- 1. Terms ---
    pathway_terms, published_terms = build_terms()
    log(f"  1. terms: {len(pathway_terms)} pathway, {len(published_terms)} published "
        f"({term_display(published_terms[0])} - {term_display(published_terms[-1])})")

    # --- 2. Courses ---
    subtopics = build_subtopics()
    courses = generate_courses(rng, np_rng, subtopics)
    log(f"  2. courses: {len(courses)} across "
        f"{len({c['subtopic'] for c in courses.values()})} content sub-topics")

    # --- 3. Prerequisite graph ---
    artifacts, gateways = generate_prerequisites(courses, rng)
    G, cleaning = build_prereq_graph(courses)
    log(f"  3. graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, "
        f"{cleaning['self_loops_removed']} self-loops, "
        f"{cleaning['cycles_broken']} cycles broken, DAG={cleaning['is_dag']}")

    # --- 4. Programs ---
    programs = generate_programs(courses, G, gateways, rng)
    program_tags = defaultdict(list)
    for pc, prog in programs.items():
        tagged = set(extract_program_courses(prog, mode="all"))
        tagged |= set(resolve_ranges(prog, courses))
        for c in tagged:
            if c in courses:
                program_tags[c].append(pc)
    program_counts = {c: len(v) for c, v in program_tags.items()}
    elective_ctx = build_elective_context(programs, courses)
    log(f"  4. programs: {len(programs)}, "
        f"mean {np.mean([p['version_count'] for p in programs.values()]):.2f} versions; "
        f"{sum(1 for v in program_counts.values() if v >= 5)} gateway courses (5+ programs); "
        f"{len(elective_ctx)} courses with elective context")

    # --- 5. Enrollment ---
    severe = select_severe_bottlenecks(courses, G, program_counts)
    rows, behavioral = generate_enrollment(courses, programs, published_terms,
                                          program_counts, rng, np_rng, severe=severe)
    log(f"  5. sections: {len(rows)}, "
        f"at-capacity {np.mean([r['enrollment'] >= r['max_enrollment'] for r in rows]):.1%}, "
        f"waitlist {np.mean([r['waitlist'] > 0 for r in rows]):.1%}; "
        f"{len(severe)} severe bottlenecks seeded")

    # --- 6. Students ---
    friction = compute_friction(courses, G, behavioral, program_counts, np_rng,
                                severe=severe)
    students = simulate_students(courses, programs, pathway_terms, friction,
                                 rng, n_students)
    total_enr = sum(len(t["courses"]) for s in students for t in s["terms"])
    log(f"  6. students: {len(students)}, {total_enr} course enrollments, "
        f"mean {total_enr / len(students):.1f} each")

    # --- 7. Ground truth ---
    student_data, course_to_students = build_student_indexes(students)
    gt_full = compute_ground_truth(courses, student_data, course_to_students)
    gt_train = compute_ground_truth(
        courses, student_data, course_to_students,
        cohort_filter=lambda sd: sd["first_term"] is not None
        and sd["first_term"] < C.FALL_2023_TERM)
    gt_test = compute_ground_truth(
        courses, student_data, course_to_students,
        cohort_filter=lambda sd: sd["first_term"] is not None
        and sd["first_term"] >= C.FALL_2023_TERM)
    log(f"  7. ground truth: full={gt_full['__meta__']['n_courses']}, "
        f"train={gt_train.get('__meta__', {}).get('n_courses', 0)}, "
        f"test={gt_test.get('__meta__', {}).get('n_courses', 0)}")

    # --- 8. Features ---
    features = compute_features(courses, G, behavioral, program_counts)
    log(f"  8. features: {len(features)} courses x {len(C.FEATURE_COLS)} features")

    # --- 9. Models ---
    scores, model_results = train_bottleneck_models(features, gt_train, gt_test, gt_full)
    log(f"  9. models trained; {sum(1 for s in scores.values() if s >= 0.5)} courses "
        f"flagged at threshold {C.BOTTLENECK_SCORE_THRESHOLD}")

    # --- 10. Similarity ---
    pairs, sim_map = compute_similarity(courses)
    clusters = find_redundant_clusters(sim_map, G, C.REDUNDANCY_CLUSTER_THRESHOLD)
    substitutes = build_bottleneck_substitutes(G, sim_map, scores,
                                              C.SIMILARITY_FLAG_THRESHOLD)
    n080 = sum(1 for p in pairs if p["similarity_score"] >= 0.80)
    log(f" 10. similarity: {len(pairs)} pairs stored (>={C.SIMILARITY_STORE_THRESHOLD}), "
        f"{n080} at >=0.80, {len(clusters)} clusters, "
        f"{len(substitutes)} bottlenecks with substitutes")

    # --- 11. Program metrics ---
    pm_required = compute_program_metrics(programs, courses, G, scores,
                                         program_tags, "required")
    pm_all = compute_program_metrics(programs, courses, G, scores, program_tags, "all")
    log(f" 11. program metrics: {len(pm_required)} required-mode, {len(pm_all)} all-mode")

    # --- 12. Demand ---
    demand = generate_demand(courses, programs, behavioral, scores,
                             published_terms, rng)
    log(f" 12. demand: {len(C.GROWTH_SCENARIOS)} scenarios, "
        f"{demand['scenarios']['0']['kpis']['courses_analyzed']} courses; "
        f"shortages 0%={demand['scenarios']['0']['kpis']['courses_with_shortages']} "
        f"-> 20%={demand['scenarios']['20']['kpis']['courses_with_shortages']}")

    # --- 13. Responsiveness ---
    demand_model = train_demand_model(rows, courses, published_terms)
    if "error" not in demand_model:
        dm = demand_model["models"]
        log(f"      demand RF: naive MAE={dm['Naive']['test_mae']:.2f}, "
            f"RF MAE={dm['Random Forest']['test_mae']:.2f} "
            f"({dm['Random Forest']['improvement_pct']:+.1f}% vs naive)")
    else:
        log(f"      demand RF skipped: {demand_model['error']}")

    responsiveness = compute_responsiveness(rows, published_terms)
    log(f" 13. responsiveness: {responsiveness['summary']['n_responsive']} responsive, "
        f"{responsiveness['summary']['n_moderate']} moderate, "
        f"{responsiveness['summary']['n_unresponsive']} unresponsive")

    # --- 14. Temporal ---
    temporal = compute_temporal(rows, published_terms)
    log(f" 14. temporal: {len(temporal['departments'])}x{len(temporal['terms'])} matrices, "
        f"{len(temporal['like_for_like'])} like-for-like comparisons")

    # --- 15. Summary ---
    summary = compute_summary(rows, courses, programs, G, behavioral, scores,
                              published_terms, cleaning, model_results, pairs, clusters)
    log(f" 15. summary: {summary['kpis']['pct_at_capacity']}% at capacity, "
        f"{summary['kpis']['pct_with_waitlist']}% with waitlist")

    # --- 16. Layout ---
    layout = hierarchical_layout(G, courses)
    layout_dag, layout_stats = layered_dag_layout(G, courses)
    log(f" 16. layout: {len(layout)} nodes; "
        f"hierarchical (original) + DAG-layered "
        f"(crossings {layout_stats['crossings_alphabetical']:,} -> "
        f"{layout_stats['crossings_after']:,}, -{layout_stats['crossing_reduction_pct']}%; "
        f"mean edge dx {layout_stats['mean_edge_dx_uniform']:,.0f} -> "
        f"{layout_stats['mean_edge_dx_refined']:,.0f}px, "
        f"-{layout_stats['edge_length_reduction_pct']}%; "
        f"width {layout_stats['width']:,.0f}px)")

    # --- 17. Emit ---
    log(" 17. writing output")
    demand["enrollment_forecast_model"] = demand_model
    summary["models"]["demand_forecast"] = {
        k: v for k, v in demand_model.items()
        if k in ("models", "naive_baseline", "test_split", "n_train", "n_test")
    }

    emit(courses, programs, G, layout, layout_dag, layout_stats, elective_ctx,
         behavioral, rows, features, scores,
         gt_full, model_results, pairs, sim_map, clusters, substitutes,
         pm_required, pm_all, demand, responsiveness, temporal, summary,
         students, published_terms, pathway_terms, program_tags, artifacts)

    log("done")
    return 0


def emit(courses, programs, G, layout, layout_dag, layout_stats, elective_ctx,
         behavioral, rows, features, scores,
         gt_full, model_results, pairs, sim_map, clusters, substitutes,
         pm_required, pm_all, demand, responsiveness, temporal, summary,
         students, published_terms, pathway_terms, program_tags, artifacts):
    total = 0

    # --- courses.json: catalog + graph attributes the Graph View needs per node ---
    course_out = {}
    for code, c in courses.items():
        f = features.get(code, {})
        course_out[code] = {
            "course_code": code,
            "department": c["department"],
            "number": c["number"],
            "title": c["title"],
            "description": c["description"],
            "credits": c["credits"],
            "level": c["level"],
            "topic": c["topic"],
            "keywords": c["keywords"],
            "prerequisites": [p for p in c["prerequisites"] if p != code],
            "corequisites": c["corequisites"],
            "prerequisite_text": c["prerequisite_text"],
            "corequisite_text": c["corequisite_text"],
            "prereq_logic": c["prereq_logic"],
            "programs": sorted(program_tags.get(code, [])),
            "program_count": len(program_tags.get(code, [])),
            "in_degree": f.get("in_degree", 0),
            "out_degree": f.get("out_degree", 0),
            "prereq_chain_depth": f.get("prereq_chain_depth", 0),
            "cascade_impact": f.get("cascade_impact", 0),
            "betweenness": f.get("betweenness", 0.0),
            "bottleneck_score": scores.get(code, 0.0),
            "is_bottleneck": bool(scores.get(code, 0.0) >= C.BOTTLENECK_SCORE_THRESHOLD),
            # Default render: DAG-layered coordinates (tiers preserved, ordering
            # crossing-minimised). x_hier/y_hier are the original's exact
            # create_hierarchical_layout output, kept for parity comparison.
            "x": layout_dag.get(code, [0, 0])[0],
            "y": layout_dag.get(code, [0, 0])[1],
            "x_hier": layout.get(code, [0, 0])[0],
            "y_hier": layout.get(code, [0, 0])[1],
            # Elective context, from load_data._process_version. Drives the elective block
            # in the Graph View node hover. None for courses only ever reached through a
            # `required` section.
            "is_elective": code in elective_ctx,
            "elective_context": elective_ctx.get(code),
        }
    total += write_json("courses.json", course_out)

    # --- prerequisites.json: edge list ---
    edges = [{"source": u, "target": v, "type": "prerequisite"}
             for u, v in sorted(G.edges())]
    edges += [{"source": code, "target": co, "type": "corequisite"}
              for code, c in sorted(courses.items()) for co in c["corequisites"]
              if co in courses]
    total += write_json("prerequisites.json", {
        "layout": layout_stats,
        "edges": edges,
        "edge_counts": dict(Counter(e["type"] for e in edges)),
        "cleaning": {
            "self_loops_removed": summary["graph"]["self_loops_removed"],
            "cycles_broken": summary["graph"]["cycles_broken"],
            "self_loop_courses": artifacts["self_loops"],
            "cycle_pairs": artifacts["cycles"],
            "note": ("Mirrors the real catalog, which contained self-referencing "
                     "prerequisites and cycles. Both are removed before analysis, "
                     "exactly as the production pipeline does."),
        },
    })

    # --- programs.json ---
    total += write_json("programs.json", {
        "programs": programs,
        "index": sorted(
            [{"code": pc, "title": p["program_title"], "department": p["department"],
              "degree_type": p["degree_type"], "version_count": p["version_count"],
              "total_credits": p["versions"][-1]["program_metadata"]["total_credits"],
              "has_concentrations": bool(p["versions"][-1]["concentrations"]),
              "required_courses": len(extract_program_courses(p, "required")),
              "all_courses": len(extract_program_courses(p, "all"))}
             for pc, p in programs.items()],
            key=lambda x: x["title"]),
        "degree_groups": {
            "Undergraduate": sorted(pc for pc, p in programs.items()
                                    if p["degree_type"] in ("BS", "BA", "BFA")),
            "Graduate": sorted(pc for pc, p in programs.items()
                               if p["degree_type"] in ("MS", "MA", "MBA")),
            "Other": sorted(pc for pc, p in programs.items()
                            if p["degree_type"] not in
                            ("BS", "BA", "BFA", "MS", "MA", "MBA")),
        },
    })

    # --- program_structures.json ---
    total += write_json("program_structures.json", {
        "required_mode": pm_required,
        "all_mode": pm_all,
        "metric_definitions": {
            "total_courses": "Courses in the program subgraph",
            "num_connections": "Prerequisite edges within the program subgraph",
            "density": ("Edges / (n(n-1)/2). Reproduces the original's convention of a "
                        "directed numerator over an undirected maximum, so values can "
                        "exceed 0.5."),
            "max_depth": "nx.dag_longest_path_length of the program subgraph",
            "cross_program_share": "Share of courses also required by another program",
            "avg_unlocks": "Mean out-degree within the program subgraph",
            "modularity_proxy": "Connected components of the undirected subgraph",
            "foundational_ratio": "Share of courses at level <= 3",
            "avg_prereqs": "Mean in-degree within the program subgraph",
            "cross_dept_pct": "Share of courses owned by another department",
            "gateway_count": "Courses required by 5 or more programs",
        },
    })

    # --- department_metrics.json ---
    dept_metrics = {}
    for dept in C.DEPARTMENTS:
        d = dept["code"]
        d_courses = [c for c, v in courses.items() if v["department"] == d]
        d_rows = [r for r in rows if r["department"] == d]
        d_scores = [scores.get(c, 0) for c in d_courses]
        dept_metrics[d] = {
            "code": d, "name": dept["name"], "color": dept["color"],
            "n_courses": len(d_courses),
            "n_programs": sum(1 for p in programs.values() if p["department"] == d),
            "n_sections": len(d_rows),
            "total_enrollment": sum(r["enrollment"] for r in d_rows),
            "total_capacity": sum(r["max_enrollment"] for r in d_rows),
            "mean_fill_rate": round(float(np.mean(
                [r["enrollment"] / r["max_enrollment"] for r in d_rows])), 4) if d_rows else 0,
            "at_capacity_rate": round(float(np.mean(
                [r["enrollment"] >= r["max_enrollment"] for r in d_rows])), 4) if d_rows else 0,
            "waitlist_rate": round(float(np.mean(
                [r["waitlist"] > 0 for r in d_rows])), 4) if d_rows else 0,
            "mean_bottleneck_score": round(float(np.mean(d_scores)), 4) if d_scores else 0,
            "n_bottlenecks": sum(1 for s in d_scores if s >= C.BOTTLENECK_SCORE_THRESHOLD),
            "mean_prereqs": round(float(np.mean(
                [features[c]["in_degree"] for c in d_courses])), 3),
            "max_chain_depth": max((features[c]["prereq_chain_depth"]
                                    for c in d_courses), default=0),
            "level_distribution": dict(Counter(
                courses[c]["level"] for c in d_courses)),
            "seasonal_preference": dept["seasonal"],
        }
    total += write_json("department_metrics.json", dept_metrics)

    # --- enrollment_by_course.json ---
    total += write_json("enrollment_by_course.json", behavioral)

    # --- bottleneck_scores.json ---
    total += write_json("bottleneck_scores.json", {
        "threshold": C.BOTTLENECK_SCORE_THRESHOLD,
        "scores": scores,
        "features": features,
        "feature_cols": C.FEATURE_COLS,
        "ground_truth": {k: v for k, v in gt_full.items() if k != "__meta__"},
        "ground_truth_meta": gt_full.get("__meta__", {}),
        "models": model_results,
        "methodology": {
            "label": ("median enrollment delay and stalling rate measured from simulated "
                      "student pathways, min-max normalised, combined 50/50 into a "
                      "composite; top quartile labelled bottleneck"),
            "split": "temporal — students entering before Fall 2023 train, Fall 2023+ test",
            "model": "RandomForestClassifier(n_estimators=300, max_depth=8, "
                     "min_samples_leaf=4, class_weight='balanced')",
            "min_eligible_students": C.MIN_ELIGIBLE_STUDENTS,
            "bottleneck_percentile": C.BOTTLENECK_PERCENTILE,
            "stalling_window": C.STALLING_WINDOW,
        },
        "top_20": [{"course": c, "score": scores[c],
                    "title": courses[c]["title"],
                    "department": courses[c]["department"]}
                   for c in sorted(scores, key=lambda x: -scores[x])[:20]],
    })

    # --- similarity_pairs.json ---
    # Pairs ship as fixed-order tuples rather than objects, and without titles or
    # keyword lists: titles live in courses.json and shared keywords are recoverable by
    # intersecting them. That is a ~5x payload reduction on the single largest file.
    #
    # The similarity threshold is a live slider (0.60-0.95), so substitutes and clusters
    # cannot be fully precomputed — the browser recomputes them per threshold from
    # `pairs`, exactly as the original filtered its similarity_map then re-ran the
    # analysis. The precomputed blocks below are the default-0.80 view, shipped so the
    # tab has something to paint before any interaction.
    compact_pairs = [[p["course_1"], p["course_2"], p["similarity_score"]]
                     for p in pairs]
    total += write_json("similarity_pairs.json", {
        "store_threshold": C.SIMILARITY_STORE_THRESHOLD,
        "flag_threshold": C.SIMILARITY_FLAG_THRESHOLD,
        "cluster_threshold": C.REDUNDANCY_CLUSTER_THRESHOLD,
        "method": "TF-IDF (1-2 grams, sublinear tf, min_df=1) + cosine similarity",
        "pair_format": ["course_1", "course_2", "similarity_score"],
        "counts": {
            "stored": len(pairs),
            "at_060": sum(1 for p in pairs if p["similarity_score"] >= 0.60),
            "at_070": sum(1 for p in pairs if p["similarity_score"] >= 0.70),
            "at_080": sum(1 for p in pairs if p["similarity_score"] >= 0.80),
            "at_085": sum(1 for p in pairs if p["similarity_score"] >= 0.85),
            "at_090": sum(1 for p in pairs if p["similarity_score"] >= 0.90),
        },
        "pairs": compact_pairs,
        "clusters_at_default": clusters[:60],
        "cluster_count_at_default": len(clusters),
        "bottleneck_substitutes_at_default": {
            # The chart draws the top 15 bottlenecks with 3 substitutes each; 6 gives the
            # UI headroom without shipping the full fan-out for all 246.
            b: subs[:6] for b, subs in sorted(
                substitutes.items(),
                key=lambda kv: -kv[1][0]["bottleneck_centrality"])[:40]
        },
        "bottleneck_substitute_count_at_default": len(substitutes),
    })

    # --- forecast_scenarios.json ---
    total += write_json("forecast_scenarios.json", demand)

    # --- department_responsiveness.json ---
    total += write_json("department_responsiveness.json", responsiveness)

    # --- temporal_patterns.json ---
    total += write_json("temporal_patterns.json", temporal)

    # --- summary_stats.json ---
    total += write_json("summary_stats.json", summary)

    # --- course_terms.json ---
    # Compact course -> offered-term index. The sidebar term filter and the Graph View's
    # node-set filter both need this (the original called get_courses_by_terms), but the
    # only other place it lives is enrollment_by_course.json, which is 1 MB. Term codes are
    # replaced by their index into `terms` to keep it small.
    term_index = {t: i for i, t in enumerate(published_terms)}
    offered = {
        code: sorted(term_index[t] for t in v["enrollment_series"]["terms"])
        for code, v in behavioral.items()
    }
    total += write_json("course_terms.json", {
        "terms": published_terms,
        "term_labels": [term_display(t) for t in published_terms],
        "offered": offered,
        "note": ("Term codes are indices into `terms`. Departments and programs are "
                 "filtered by term through this index rather than by loading the full "
                 "enrollment file."),
    })

    # --- terms.json ---
    total += write_json("terms.json", {
        "published": [{"code": t, "display": term_display(t), "season": term_season(t),
                       "academic_year": f"AY{t[:4]}"} for t in published_terms],
        "pathway_window": [{"code": t, "display": term_display(t)} for t in pathway_terms],
        "season_codes": C.SEASON_CODE,
        "note": ("Academic-year Banner coding (Fall 2022 -> 202310). Chosen because it is "
                 "the only scheme consistent with the original's semester_index(), which "
                 "the ML delay arithmetic depends on."),
    })

    # --- students_sample.json: 200 pathways so the claim is inspectable ---
    total += write_json("students_sample.json", {
        "note": (f"{len(students)} student pathways were simulated to derive the "
                 "bottleneck ground truth. Only aggregates ship to the browser; this is "
                 "a 200-student sample for inspection."),
        "n_simulated": len(students),
        "sample": students[:200],
    })

    # --- Full student pathways stay out of the browser payload ---
    INTERMEDIATE.mkdir(parents=True, exist_ok=True)
    with open(INTERMEDIATE / "students_full.json", "w") as f:
        json.dump(students, f, separators=(",", ":"))
    with open(INTERMEDIATE / "sections_full.json", "w") as f:
        json.dump(rows, f, separators=(",", ":"))
    log(f"    wrote intermediate/students_full.json + sections_full.json "
        f"(not shipped)")

    log(f"    total shipped payload: {total / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    sys.exit(main())
