"""
Pacific Ridge University — synthetic university definition.

All tuning constants for the mock data generator live here so the generator itself
stays readable. Every value is either (a) copied from the original Shiny dashboard's
ml_models/config.py, or (b) a calibration target taken from the blueprint's record of
the real system's findings.

Nothing here is derived from real institutional data.
"""

# ============================================================
# Determinism
# ============================================================
SEED = 20260812

UNIVERSITY_NAME = "Pacific Ridge University"
UNIVERSITY_SHORT = "PRU"

# ============================================================
# Terms
#
# Season sub-codes are copied verbatim from the original's
# utils/program_utils._TERM_CODE_SEASON, which load_data/load_courseleaf_enrollment.py
# agrees with (2 of the 3 maps in the original; utils/term_utils.TERM_CODE_MAP is the
# outlier and is not used for enrollment data). These are consistent with
# semester_index(): sub-code <20 = Fall, <40 = Spring, else Summer.
#
# The YEAR component is academic-year, not calendar-year: Fall 2022 -> 202310.
# Confirmed twice in the original — config.FALL_2023_TERM = 202410, and
# model_data/course_term_enrollment.csv rows read "AACE 6000, 202310.0, Fall, 2022".
# ============================================================
SEASON_CODE = {"Fall": "10", "Spring": "20", "Summer 1": "30",
               "Summer 2": "40", "Summer Full": "50"}
SEASON_MONTHS = {"Fall": (8, 12), "Spring": (1, 5), "Summer 1": (6, 6),
                 "Summer 2": (7, 7), "Summer Full": (6, 8)}
SEASON_ORDER = ["Fall", "Spring", "Summer 1", "Summer 2", "Summer Full"]
SUMMER_SEASONS = ["Summer 1", "Summer 2", "Summer Full"]

# Student pathways are simulated over a deeper window than the published
# enrollment window. The real system had multi-year Banner student history behind a
# 21-term CourseLeaf enrollment extract; the same asymmetry is required here so that
# ground-truth stalling (which needs >= STALLING_WINDOW post-completion semesters)
# is observable at all.
PATHWAY_ACADEMIC_YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]

# Academic years published to the dashboard, at all five seasons each. This matches the
# original's CourseLeaf extract, which covered Fall/Spring/Summer 1/Summer 2/Summer Full
# from Fall 2021 to Fall 2025 across 21 term files.
#
# The window length is not cosmetic: the demand forecaster's edge over the naive
# same-season-last-year baseline depends on how many same-season observations per course
# it can average over. At 3 academic years it reaches only +9.7% against the original's
# measured 28.7%; at 5 it reaches +18.8%. Extending past the original's window would
# improve the number further but would no longer be reproducing the original's setup.
PUBLISHED_ACADEMIC_YEARS = [2021, 2022, 2023, 2024, 2025]

# ============================================================
# Departments
#
# n_courses sums to 820 (blueprint target: ~800).
#   depth    - propensity for deep prerequisite chains (0-1)
#   cross    - propensity to draw prerequisites from other departments (0-1)
#   service  - how heavily other departments depend on this one (0-1)
#   demand   - baseline enrollment pressure (0-1); drives fill rates
#   respond  - how strongly the department adjusts next-year capacity to this year's
#              demand. Deliberately INDEPENDENT of `demand` so Tab 8 has real signal:
#              a department can be under heavy demand and still fail to respond, which
#              is exactly what the responsiveness metric is meant to expose.
#   growth   - year-over-year enrollment growth rate. Without a trend, last year's
#              same-season enrollment is an almost perfect predictor and the demand
#              forecaster cannot beat the naive baseline the way the real one did.
#   seasonal - which season this department skews toward
#   labs     - whether courses carry corequisite lab sections
# ============================================================
DEPARTMENTS = [
    dict(code="CS",   name="Computer Science",   n_courses=140, depth=0.95, cross=0.35,
         service=0.55, demand=0.95, respond=0.30, growth=+0.085, seasonal="Fall",   labs=False, color="#2563eb"),
    dict(code="DS",   name="Data Science",       n_courses=70,  depth=0.75, cross=0.65,
         service=0.20, demand=0.90, respond=0.88, growth=+0.140, seasonal="Fall",   labs=False, color="#0891b2"),
    dict(code="MATH", name="Mathematics",        n_courses=95,  depth=0.85, cross=0.10,
         service=0.95, demand=0.80, respond=0.72, growth=+0.020, seasonal="Spring", labs=False, color="#7c3aed"),
    dict(code="BA",   name="Business Analytics", n_courses=70,  depth=0.55, cross=0.50,
         service=0.15, demand=0.70, respond=0.55, growth=+0.045, seasonal="Spring", labs=False, color="#c026d3"),
    dict(code="ENGR", name="Engineering",        n_courses=105, depth=0.98, cross=0.45,
         service=0.25, demand=0.75, respond=0.42, growth=+0.010, seasonal="Fall",   labs=True,  color="#ea580c"),
    dict(code="ECON", name="Economics",          n_courses=70,  depth=0.50, cross=0.35,
         service=0.30, demand=0.60, respond=0.80, growth=-0.035, seasonal="Spring", labs=False, color="#65a30d"),
    dict(code="BIO",  name="Biology",            n_courses=85,  depth=0.70, cross=0.25,
         service=0.30, demand=0.70, respond=0.20, growth=+0.030, seasonal="Fall",   labs=True,  color="#059669"),
    dict(code="PSYC", name="Psychology",         n_courses=75,  depth=0.35, cross=0.20,
         service=0.20, demand=0.85, respond=0.12, growth=+0.065, seasonal="Spring", labs=False, color="#d97706"),
    dict(code="COMM", name="Communications",     n_courses=55,  depth=0.15, cross=0.10,
         service=0.10, demand=0.80, respond=0.65, growth=-0.055, seasonal="Spring", labs=False, color="#dc2626"),
    dict(code="PHYS", name="Physics",            n_courses=55,  depth=0.80, cross=0.35,
         service=0.75, demand=0.55, respond=0.50, growth=-0.020, seasonal="Fall",   labs=True,  color="#4f46e5"),
]

# Level mix across the catalog. 1000 = intro, 4000 = senior/graduate-adjacent.
LEVEL_WEIGHTS = {1: 0.18, 2: 0.30, 3: 0.31, 4: 0.21}

# Probability a course at each level has any prerequisites at all.
# 1000-level always 0 (blueprint: "1000-level has none").
PREREQ_PROB_BY_LEVEL = {1: 0.00, 2: 0.80, 3: 0.95, 4: 0.97}

# Target graph shape. Real: 8,579 nodes / 8,072 edges / 5,575 components.
# Scaled to catalog size while keeping the graph legible; see divergence #9.
TARGET_EDGES = 1200
TARGET_MAX_CHAIN_DEPTH = (6, 8)

# ============================================================
# Programs
# ============================================================
N_PROGRAMS = 80
DEGREE_MIX = [("BS", 0.40), ("BA", 0.22), ("MS", 0.30), ("Minor", 0.08)]
# Programs given concentration/pathway variants (blueprint: "3-4 programs")
N_PROGRAMS_WITH_CONCENTRATIONS = 4
# Program version history. Real mean was 3.74 versions per program (max 54).
VERSIONS_PER_PROGRAM = (1, 5)

# ============================================================
# Students & enrollment
# ============================================================
N_STUDENTS = 8000
COURSES_PER_TERM = (4, 6)

# Calibration targets from the real system (blueprint §Reference).
TARGET_AT_CAPACITY_RATE = 0.36     # share of sections with fill_rate >= 1.0
TARGET_WAITLIST_RATE = 0.319       # share of sections carrying a waitlist
SECTION_CAPACITIES = [24, 30, 35, 40, 45, 60, 80, 120, 150, 200]
# Multiplier on waitlist size, calibrated by bisection to hit TARGET_WAITLIST_RATE.
WAITLIST_NEAR_CAP_PROB = 0.28   # chance a near-full section carries a small waitlist

# ============================================================
# ML pipeline constants — copied verbatim from the original ml_models/config.py
# ============================================================
MIN_ELIGIBLE_STUDENTS = 10
BOTTLENECK_PERCENTILE = 75
STALLING_WINDOW = 3
FALL_2023_TERM = 202410
BOTTLENECK_SCORE_THRESHOLD = 0.5

FEATURE_COLS = [
    "behavioral_score", "in_degree", "out_degree", "betweenness",
    "program_count", "level", "cascade_impact", "prereq_chain_depth",
    "avg_fill_rate",
]

# RF calibration targets (real: AUC 0.772, Precision@20 0.85, base rate 25%).
# FRICTION_NOISE controls how much of a course's true student-facing friction is
# idiosyncratic rather than explained by FEATURE_COLS. It is the single knob that
# sets achievable AUC: 0 would make the features perfectly predictive (AUC ~1.0),
# 1 would make them useless (AUC ~0.5).
FRICTION_NOISE = 0.62

# Student-behaviour noise. The ground-truth label (median delay + stalling rate) is
# partly structural — a course deep in a prerequisite chain is taken late no matter
# what — so with perfectly orderly students the features predict the label almost
# exactly and AUC lands near 0.92. Real transcripts are not orderly, and this messiness
# is what held the real model to 0.772. Each of these is a documented real behaviour:
WITHDRAWAL_PROB = 0.10      # attempt appears on the transcript but unlocks nothing
STOPOUT_PROB = 0.10         # term taken off (co-op, transfer out, leave)
PROGRAM_SWITCH_PROB = 0.03  # per-term chance of changing programs
OFF_PLAN_PROB = 0.30        # chance of taking coursework outside the degree audit
PART_TIME_SHARE = 0.12      # students carrying roughly half a normal load

# A small set of unambiguously severe bottlenecks — the notorious gateway courses every
# large university has, where the constraint is obvious on every dimension at once.
# The blueprint calls for this directly: "Top 20 bottlenecks should have Precision@20
# story built in." Without them the friction distribution has no clear extreme, so the
# model's top-ranked courses are drawn from an ambiguous middle and Precision@20 sits
# near 0.60 regardless of hyperparameters.
N_SEVERE_BOTTLENECKS = 25
SEVERE_FRICTION_RANGE = (0.90, 0.99)
# How much the noise is attenuated for courses at the extremes of the structural
# signal. Raises precision on the top-ranked courses without inflating overall AUC,
# reproducing the real model's AUC 0.772 / Precision@20 0.85 profile (a flat noise
# term cannot produce that combination).
FRICTION_TAIL_CERTAINTY = 0.80
TARGET_AUC_BAND = (0.72, 0.82)
# Global multiplier on per-department growth rates. Swept so the demand forecaster's
# improvement over the naive same-season-last-year baseline lands near the original's
# measured 28.7%: larger trends give the naive lag more to miss.
GROWTH_SCALE = 1.0
# Standard deviation of per-section, per-term idiosyncratic demand noise. This is the
# dominant driver of the forecaster's edge over the naive baseline: the naive lag
# inherits last year's noise in full, while a model shrinks it toward the course's
# standing capacity. Swept against TARGET_DEMAND_IMPROVEMENT.
DEMAND_TERM_NOISE_SD = 0.16
TARGET_DEMAND_IMPROVEMENT = 28.7
TARGET_PRECISION_AT_20 = 0.85

# ============================================================
# NLP similarity — real: 25,431 pairs at 0.80, 334 clusters over 8,587 courses
# (2.96 pairs per course). Scaled to catalog size.
# ============================================================
SIMILARITY_STORE_THRESHOLD = 0.60   # matches the sidebar slider minimum
SIMILARITY_FLAG_THRESHOLD = 0.80    # the original's default
REDUNDANCY_CLUSTER_THRESHOLD = 0.85 # find_redundant_course_clusters, fixed in the original
TARGET_PAIRS_AT_080 = (2200, 3400)   # 2.96 pairs/course x 820, from the real ratio

# Cluster count is tracked but is NOT a hard target. The real figures (25,431 pairs at
# 0.80; 334 clusters) were measured at two different thresholds — clusters come from
# find_redundant_course_clusters, which is fixed at 0.85 — so they cannot be scaled to
# a single consistent expectation. Forcing the naive scaled value (~32 clusters) would
# require inflating the pair count past 5,000 to make the 0.85 DFS chain transitively,
# trading the metric that drives the Redundancy tab for one that does not affect it.
# Band below reflects what the calibrated corpus actually produces.
TARGET_CLUSTERS = (60, 110)

# Term-weighting used when building each course's pseudo-document for TF-IDF. These
# control how much vocabulary same-subtopic courses share, and therefore how many
# pairs clear 0.80 and how large the redundancy clusters get. Swept empirically
# against TARGET_PAIRS_AT_080 / TARGET_CLUSTERS.
SIM_KEYWORD_REPEAT = 4
SIM_TOPIC_REPEAT = 1
SIM_SUBTOPIC_REPEAT = 3

# Share of courses that are content-distinctive — they carry a specialization qualifier
# separating them from their sub-topic siblings. The remainder form the genuinely
# near-duplicate population that clusters.
#
# This split is what makes the pair count and the cluster count independently
# controllable. Without it every course has ~12 near-identical siblings and the whole
# catalogue collapses into clusters, which is not what the real corpus looked like:
# 334 clusters over 8,587 courses means redundancy was concentrated in a minority of
# the catalogue, not spread evenly across it.
DISTINCTIVE_SHARE = 0.24
SPECIALIZATION_REPEAT = 3

SPECIALIZATIONS = [
    "Quantum", "Urban", "Clinical", "Marine", "Computational", "Historical",
    "Comparative", "Applied", "Theoretical", "Environmental", "Global",
    "Behavioral", "Molecular", "Digital", "Industrial", "Cognitive",
    "Structural", "Tropical", "Forensic", "Developmental", "Geospatial",
    "Astronomical", "Agricultural", "Nonlinear", "Stochastic", "Semantic",
    "Cryptographic", "Ethnographic", "Legislative", "Biomechanical",
]

# Share of programs carrying an open-range elective section, and how narrow that
# range is. Kept low: a wide open pool tags hundreds of courses with the program,
# which inflates program_count and makes 'gateway course' meaningless.
RANGE_SECTION_PROB = 0.15
RANGE_LEVEL_MIN = 4000

# ============================================================
# Demand forecast — formulas from ml_models/demand_forecasting/demand_aggregator.py
# ============================================================
RANK_WEIGHTS = {1: 1.0, 2: 0.8, 3: 0.6}
DEFAULT_SECTION_SIZE = 40           # sections_needed = ceil(shortage / 40)
GROWTH_SCENARIOS = [0.0, 0.05, 0.10, 0.15, 0.20]
PREFERENCE_SLOTS = (3, 5)           # course slots a student ranks per term
PREFS_PER_SLOT = 3                  # ranked alternatives per slot

# ============================================================
# Department responsiveness (blueprint §Reference): 40% utilization,
# 30% over-capacity, 30% waitlist weighting.
# ============================================================
RESPONSIVENESS_WEIGHTS = dict(utilization=0.40, over_capacity=0.30, waitlist=0.30)
# Classification thresholds are NOT specified anywhere in the original or the blueprint
# (the blueprint gives the weights and the three class names only, and the Dash
# dashboard that produced this tab is absent from the codebase). Terciles of the
# observed score distribution are used, so the split is derived from the data rather
# than from invented cut-points.
RESPONSIVENESS_CLASSES = ["unresponsive", "moderate", "responsive"]

# ============================================================
# Topic vocabulary
#
# Course titles and descriptions are assembled from these pools. Topic membership is
# what creates genuine cluster structure in the TF-IDF similarity matrix, so that
# "content-equivalent alternatives" in Tab 4 are actually content-equivalent rather
# than randomly paired.
# ============================================================
TOPICS = {
    "programming": dict(
        depts=["CS", "DS"],
        title_heads=["Programming", "Program Design", "Software Construction",
                     "Object-Oriented Design", "Programming Paradigms"],
        keywords=["programming", "software", "code", "abstraction", "implementation",
                  "design", "testing", "modularity", "recursion", "data types"]),
    "algorithms": dict(
        depts=["CS", "DS", "MATH"],
        title_heads=["Algorithms", "Algorithms and Data", "Computational Complexity",
                     "Discrete Structures", "Analysis of Algorithms"],
        keywords=["algorithms", "complexity", "asymptotic", "graphs", "sorting",
                  "dynamic programming", "proofs", "data structures", "optimality"]),
    "systems": dict(
        depts=["CS", "ENGR"],
        title_heads=["Computer Systems", "Operating Systems", "Computer Architecture",
                     "Networks", "Distributed Systems"],
        keywords=["systems", "memory", "concurrency", "processes", "architecture",
                  "networks", "operating system", "hardware", "scheduling", "cache"]),
    "databases": dict(
        depts=["CS", "DS", "BA"],
        title_heads=["Databases", "Database Design", "Data Management",
                     "Information Systems", "Query Processing"],
        keywords=["databases", "relational", "query", "schema", "normalization",
                  "transactions", "indexing", "storage", "data management", "SQL"]),
    "machine_learning": dict(
        depts=["CS", "DS", "BA", "ECON"],
        title_heads=["Machine Learning", "Statistical Learning", "Predictive Modeling",
                     "Data Mining", "Applied Machine Learning"],
        keywords=["machine learning", "models", "prediction", "regression",
                  "classification", "training", "features", "supervised", "validation"]),
    "statistics": dict(
        depts=["MATH", "DS", "ECON", "PSYC", "BA"],
        title_heads=["Statistics", "Probability", "Statistical Inference",
                     "Regression Analysis", "Experimental Design"],
        keywords=["statistics", "probability", "inference", "distribution",
                  "hypothesis", "variance", "sampling", "estimation", "regression"]),
    "calculus": dict(
        depts=["MATH", "PHYS", "ENGR"],
        title_heads=["Calculus", "Multivariable Calculus", "Differential Equations",
                     "Real Analysis", "Vector Calculus"],
        keywords=["calculus", "derivative", "integral", "limits", "series",
                  "differential equations", "convergence", "vector fields"]),
    "linear_algebra": dict(
        depts=["MATH", "DS", "ENGR", "PHYS"],
        title_heads=["Linear Algebra", "Matrix Methods", "Applied Linear Algebra",
                     "Numerical Methods"],
        keywords=["linear algebra", "matrices", "eigenvalues", "vector spaces",
                  "transformations", "decomposition", "numerical", "systems of equations"]),
    "mechanics": dict(
        depts=["PHYS", "ENGR"],
        title_heads=["Mechanics", "Dynamics", "Statics", "Thermodynamics",
                     "Fluid Mechanics"],
        keywords=["mechanics", "forces", "motion", "energy", "momentum",
                  "equilibrium", "thermodynamics", "fluids", "laboratory"]),
    "electronics": dict(
        depts=["ENGR", "PHYS", "CS"],
        title_heads=["Circuits", "Electronics", "Signals and Systems",
                     "Embedded Systems", "Control Systems"],
        keywords=["circuits", "voltage", "signals", "electronics", "embedded",
                  "control", "feedback", "sensors", "laboratory"]),
    "microeconomics": dict(
        depts=["ECON", "BA"],
        title_heads=["Microeconomics", "Price Theory", "Market Structure",
                     "Industrial Organization"],
        keywords=["microeconomics", "markets", "demand", "supply", "elasticity",
                  "firms", "competition", "welfare", "pricing"]),
    "macroeconomics": dict(
        depts=["ECON", "BA"],
        title_heads=["Macroeconomics", "Monetary Policy", "Economic Growth",
                     "International Economics"],
        keywords=["macroeconomics", "inflation", "output", "policy", "monetary",
                  "fiscal", "growth", "trade", "aggregate"]),
    "finance": dict(
        depts=["BA", "ECON"],
        title_heads=["Finance", "Corporate Finance", "Investments",
                     "Financial Modeling", "Risk Management"],
        keywords=["finance", "valuation", "portfolio", "risk", "capital",
                  "investment", "returns", "discounting", "markets"]),
    "management": dict(
        depts=["BA", "COMM"],
        title_heads=["Management", "Organizational Behavior", "Operations Management",
                     "Strategy", "Project Management"],
        keywords=["management", "organizations", "strategy", "operations",
                  "leadership", "teams", "processes", "decision making"]),
    "cell_biology": dict(
        depts=["BIO"],
        title_heads=["Cell Biology", "Molecular Biology", "Biochemistry",
                     "Genetics", "Microbiology"],
        keywords=["cells", "molecular", "genetics", "proteins", "DNA",
                  "metabolism", "microbiology", "laboratory", "biochemistry"]),
    "organismal_biology": dict(
        depts=["BIO"],
        title_heads=["Physiology", "Anatomy", "Ecology", "Evolution",
                     "Neurobiology"],
        keywords=["physiology", "anatomy", "ecology", "evolution", "organisms",
                  "systems", "neural", "populations", "laboratory"]),
    "cognition": dict(
        depts=["PSYC", "CS", "BIO"],
        title_heads=["Cognitive Psychology", "Perception", "Learning and Memory",
                     "Cognitive Neuroscience"],
        keywords=["cognition", "memory", "perception", "attention", "learning",
                  "neuroscience", "behavior", "experiments", "processing"]),
    "social_psych": dict(
        depts=["PSYC", "COMM"],
        title_heads=["Social Psychology", "Developmental Psychology",
                     "Personality", "Abnormal Psychology"],
        keywords=["social", "development", "personality", "behavior", "clinical",
                  "groups", "attitudes", "assessment", "identity"]),
    "media": dict(
        depts=["COMM"],
        title_heads=["Media Studies", "Digital Media", "Journalism",
                     "Public Relations", "Rhetoric"],
        keywords=["media", "audiences", "journalism", "rhetoric", "digital",
                  "narrative", "public", "communication", "discourse"]),
    "research_methods": dict(
        depts=["PSYC", "COMM", "ECON", "BIO", "DS"],
        title_heads=["Research Methods", "Quantitative Methods",
                     "Qualitative Methods", "Field Research"],
        keywords=["research", "methods", "design", "measurement", "analysis",
                  "ethics", "data collection", "validity", "reporting"]),
    "capstone": dict(
        depts=["CS", "DS", "MATH", "BA", "ENGR", "ECON", "BIO", "PSYC", "COMM", "PHYS"],
        title_heads=["Capstone", "Senior Project", "Thesis Research", "Seminar"],
        keywords=["capstone", "project", "independent", "synthesis", "presentation",
                  "thesis", "seminar", "portfolio"]),
    "ethics": dict(
        depts=["CS", "BA", "COMM", "PSYC", "BIO"],
        title_heads=["Ethics", "Professional Practice", "Technology and Society",
                     "Policy and Regulation"],
        keywords=["ethics", "society", "policy", "professional", "responsibility",
                  "regulation", "impact", "governance", "fairness"]),
}

DESCRIPTION_TEMPLATES = [
    "Introduces {kw1} and {kw2}, with emphasis on {kw3} in applied settings.",
    "Covers {kw1}, {kw2}, and {kw3}. Students complete problem sets and a term project.",
    "Examines {kw1} through the lens of {kw2}. Topics include {kw3} and {kw4}.",
    "A survey of {kw1} and {kw2}, building toward independent work in {kw3}.",
    "Develops working knowledge of {kw1}, {kw2}, and {kw3} using case studies.",
    "Advanced treatment of {kw1}. Prior exposure to {kw2} and {kw3} is assumed.",
]

INSTRUCTOR_FIRST = [
    "Amara", "Devin", "Priya", "Rowan", "Yuki", "Mateo", "Noor", "Sasha", "Ines",
    "Kofi", "Lena", "Omar", "Tessa", "Rafael", "Anika", "Bo", "Camille", "Dmitri",
    "Esme", "Farid", "Greta", "Hana", "Idris", "Juno", "Kira", "Liam", "Maya",
    "Nikhil", "Oona", "Pablo", "Quinn", "Ravi", "Sena", "Theo", "Uma", "Viktor",
]
INSTRUCTOR_LAST = [
    "Okonkwo", "Halvorsen", "Raman", "Delacroix", "Tanaka", "Vasquez", "Haddad",
    "Petrov", "Moreau", "Mensah", "Bergstrom", "Nakamura", "Silva", "Adeyemi",
    "Kowalski", "Fitzgerald", "Marchetti", "Ibrahim", "Lindqvist", "Chaudhry",
    "Escobar", "Novak", "Whitfield", "Yamamoto", "Zamora", "Bhatt", "Castellano",
    "Duarte", "Ferrand", "Gustafsson",
]
