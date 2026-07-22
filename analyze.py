"""Analysis v2 for the expanded bilateral-integration run (24 tasks, 7 arms, SYN/API subsets).

Regenerates every number for the JSS manuscript from the frozen results JSON — no models, no keys.
Adds (over v1): task-cluster bootstrap CIs for the headline comparisons (runs cluster by task, the
GADMEC/IPM lesson), subset SYN vs API breakdown, the dialogue mechanism split (answers-only vs
volunteers), and the mitigation-arm tradeoff (silent-failure reduction vs completion collapse).

    python3 analyze.py [results.json]     # default: _harness_results.json
"""
import json, math, os, random, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "_harness_results.json")
DATA = json.load(open(PATH))
import corpus

ARMS = ["provided", "nodialogue", "forced", "forced_flagged",
        "dialogue_answers_only", "dialogue_volunteers", "mitigation"]
ARMS = [a for a in ARMS if any(r["arm"] == a for r in DATA)]          # tolerate partial runs
MODELS = list(dict.fromkeys(r["model"] for r in DATA))
TASK = {t["id"]: t for t in corpus.TASKS}
CLEAN = {t["id"] for t in corpus.TASKS if all(not m["inferable"] for m in t["mismatches"])}
CONTROL = {t["id"] for t in corpus.TASKS if all(m["inferable"] for m in t["mismatches"])}
SUBSET = {t["id"]: t.get("subset", "?") for t in corpus.TASKS}

def sel(model=None, arm=None, tasks=None, models=None):
    return [r for r in DATA
            if (model is None or r["model"] == model)
            and (models is None or r["model"] in models)
            and (arm is None or r["arm"] == arm)
            and (tasks is None or r["task"] in tasks)]

def rate(rows, key):
    return sum(r[key] for r in rows) / len(rows) if rows else float("nan")

def wilson(k, n, z=1.96):
    if n == 0: return (float("nan"), float("nan"))
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))

def fmt_rate(rows, key):
    k = sum(r[key] for r in rows); n = len(rows)
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k/n:.2f} [{lo:.2f}-{hi:.2f}]" if n else "n=0"

# ── capability gates ──────────────────────────────────────────────────────────
def pooled_capable(threshold=0.8):
    """Models whose pooled Provided-success clears the bar (the letter's gate)."""
    return [m for m in MODELS if rate(sel(m, "provided"), "success") >= threshold]

def cell_capable(m, t):
    """Per-cell gate: Provided success on EVERY run of that model-task cell (3/3 or 5/5)."""
    rows = sel(m, "provided", tasks={t})
    return bool(rows) and all(r["success"] for r in rows)

# ── task-cluster bootstrap (runs cluster by task; resample TASKS with replacement) ─────────────
def cluster_boot_diff(rows_a, rows_b, key, n_boot=10000, seed=7):
    """Bootstrap CI for rate(rows_a,key) - rate(rows_b,key), resampling task clusters.

    Cluster-aware: observations within a task are correlated (same hidden fact), so the resampling
    unit is the task, jointly for both arms (paired by task). Returns (diff, lo, hi)."""
    rng = random.Random(seed)
    by_a = defaultdict(list); by_b = defaultdict(list)
    for r in rows_a: by_a[r["task"]].append(r[key])
    for r in rows_b: by_b[r["task"]].append(r[key])
    tasks = sorted(set(by_a) | set(by_b))
    def stat(ts):
        xa = [v for t in ts for v in by_a.get(t, [])]
        xb = [v for t in ts for v in by_b.get(t, [])]
        if not xa or not xb: return None
        return sum(xa)/len(xa) - sum(xb)/len(xb)
    point = stat(tasks)
    draws = []
    for _ in range(n_boot):
        ts = [tasks[rng.randrange(len(tasks))] for _ in tasks]
        s = stat(ts)
        if s is not None: draws.append(s)
    draws.sort()
    lo = draws[int(0.025 * len(draws))]; hi = draws[int(0.975 * len(draws))]
    return point, lo, hi

def show_diff(label, rows_a, rows_b, key):
    d, lo, hi = cluster_boot_diff(rows_a, rows_b, key)
    star = " *" if (lo > 0 or hi < 0) else ""
    print(f"  {label}: {d:+.2f} pp[{lo:+.2f},{hi:+.2f}]{star}  "
          f"(A n={len(rows_a)}, B n={len(rows_b)}; cluster=task)")

# ══════════════════════════════════════════════════════════════════════════════
print(f"records: {len(DATA)}  models: {MODELS}")
print(f"arms present: {ARMS}")
print(f"tasks: {len(TASK)}  irreducible: {len(CLEAN)}  inferable controls: {len(CONTROL)}  "
      f"mixed: {len(TASK)-len(CLEAN)-len(CONTROL)}")
CAP = pooled_capable()
print(f"capable models (pooled Provided >= 0.8): {CAP}")

print("\n=== Table: per model x arm (full corpus) ===")
hdr = f"{'model':22s}" + "".join(f"{a[:12]:>13s}" for a in ARMS)
print(hdr + "   (cell: succ/silent)")
for m in MODELS:
    row = f"{m:22s}"
    for a in ARMS:
        rows = sel(m, a)
        row += f"  {rate(rows,'success'):.2f}/{rate(rows,'silent_failure'):.2f}"
    print(row)

print("\n=== RQ1: silent failure under Forced (capable models, irreducible gaps) ===")
f_rows = [r for r in sel(arm="forced", tasks=CLEAN) if r["model"] in CAP]
p_rows = [r for r in sel(arm="provided", tasks=CLEAN) if r["model"] in CAP]
print(f"  Provided correct : {fmt_rate(p_rows,'success')}")
print(f"  Forced silent    : {fmt_rate(f_rows,'silent_failure')}")
show_diff("Forced-silent minus Provided-silent", f_rows, p_rows, "silent_failure")
print("  per-cell gate (Provided all-runs on that task):")
q = [(m, t) for m in MODELS for t in CLEAN if cell_capable(m, t)]
fq = [r for (m, t) in q for r in sel(m, "forced", tasks={t})]
print(f"    qualifying cells: {len(q)}  Forced silent: {fmt_rate(fq,'silent_failure')}")

print("\n=== RQ2: absent information vs detection vs skill ===")
ff = [r for r in sel(arm="forced_flagged", tasks=CLEAN) if r["model"] in CAP]
print(f"  Forced-flagged silent (irreducible): {fmt_rate(ff,'silent_failure')}")
show_diff("Flagged minus Forced (silent)", ff, f_rows, "silent_failure")
fc = [r for r in sel(arm="forced", tasks=CONTROL) if r["model"] in CAP]
print(f"  Forced silent on inferable controls: {fmt_rate(fc,'silent_failure')}")
show_diff("Irreducible minus controls (Forced silent)", f_rows, fc, "silent_failure")

print("\n=== RQ2b: subset SYN (synthetic) vs API (API-derived), Forced silent, capable ===")
for sub in ("SYN", "API"):
    ids = {t for t in CLEAN if SUBSET[t] == sub}
    rows = [r for r in sel(arm="forced", tasks=ids) if r["model"] in CAP]
    print(f"  subset {sub} ({len(ids)} irreducible tasks): {fmt_rate(rows,'silent_failure')}")

print("\n=== RQ3: does asking track scale? (Cold ask-rate per model, full corpus) ===")
for m in MODELS:
    nd = sel(m, "nodialogue")
    print(f"  {m:22s} asks {rate(nd,'asked'):.2f}   provided-success {rate(sel(m,'provided'),'success'):.2f}")

print("\n=== RQ4: dialogue mechanism (capable, irreducible) ===")
ao = [r for r in sel(arm="dialogue_answers_only", tasks=CLEAN) if r["model"] in CAP]
vo = [r for r in sel(arm="dialogue_volunteers", tasks=CLEAN) if r["model"] in CAP]
nd = [r for r in sel(arm="nodialogue", tasks=CLEAN) if r["model"] in CAP]
for lab, rows in (("answers-only", ao), ("volunteers", vo), ("no-dialogue", nd)):
    if rows:
        print(f"  {lab:14s} success {fmt_rate(rows,'success')}   silent {fmt_rate(rows,'silent_failure')}")
if ao and vo:
    show_diff("volunteers minus answers-only (success)", vo, ao, "success")
    show_diff("answers-only minus no-dialogue (success)", ao, nd, "success")

print("\n=== RQ5: mitigation (gated commit), capable models ===")
mit_i = [r for r in sel(arm="mitigation", tasks=CLEAN) if r["model"] in CAP]
mit_c = [r for r in sel(arm="mitigation", tasks=CONTROL) if r["model"] in CAP]
for_c = [r for r in sel(arm="forced", tasks=CONTROL) if r["model"] in CAP]
if mit_i:
    print(f"  irreducible: silent {fmt_rate(mit_i,'silent_failure')}   "
          f"abstained {fmt_rate(mit_i,'abstained')}   success {fmt_rate(mit_i,'success')}")
    print(f"  controls   : success {fmt_rate(mit_c,'success')}   abstained {fmt_rate(mit_c,'abstained')}")
    show_diff("mitigation minus forced (silent, irreducible)", mit_i, f_rows, "silent_failure")
    if mit_c and for_c:
        show_diff("mitigation minus forced (success, controls)", mit_c, for_c, "success")
        print("  (completion collapse check: mitigation should NOT abstain on inferable controls)")

print("\nDone. Every number above regenerates from the frozen JSON; cluster CIs resample tasks.")

# ── --emit-numbers: machine-readable bridge for filling the manuscript and for verify-claims ──
if "--emit-numbers" in sys.argv:
    def kn(rows, key):
        k = sum(r[key] for r in rows); n = len(rows)
        lo, hi = wilson(k, n)
        return {"k": k, "n": n, "rate": round(k/n, 4) if n else None,
                "ci": [round(lo, 4), round(hi, 4)] if n else None}
    def diff(ra, rb, key):
        res = cluster_boot_diff(ra, rb, key)
        if res is None: return None
        d, lo, hi = res
        return {"diff_pp": round(d*100, 1), "ci_pp": [round(lo*100, 1), round(hi*100, 1)],
                "n": [len(ra), len(rb)]}
    def cap_rows(arm, tasks):
        return [r for r in sel(arm=arm, tasks=tasks) if r["model"] in CAP]
    SYN_I = {t for t in CLEAN if SUBSET[t] == "SYN"}
    API_I = {t for t in CLEAN if SUBSET[t] == "API"}
    q = [(m, t) for m in MODELS for t in CLEAN if cell_capable(m, t)]
    fq = [r for (m, t) in q for r in sel(m, "forced", tasks={t})]
    nums = {
        "n_models": len(MODELS), "models": MODELS, "capable": CAP,
        "n_tasks": len(TASK), "n_irreducible": len(CLEAN), "n_controls": len(CONTROL),
        "records": len(DATA),
        "provided_correct_irred": kn(cap_rows("provided", CLEAN), "success"),
        "forced_silent_irred": kn(cap_rows("forced", CLEAN), "silent_failure"),
        "flagged_silent_irred": kn(cap_rows("forced_flagged", CLEAN), "silent_failure"),
        "forced_silent_ctrl": kn(cap_rows("forced", CONTROL), "silent_failure"),
        "forced_success_ctrl": kn(cap_rows("forced", CONTROL), "success"),
        "percell_gate_forced_silent": kn(fq, "silent_failure"),
        "percell_qualifying_cells": len(q),
        "cold_ask_by_model": {m: kn(sel(m, "nodialogue"), "asked") for m in MODELS},
        "provided_success_by_model": {m: kn(sel(m, "provided"), "success") for m in MODELS},
        "dialogue_answers_success_irred": kn(cap_rows("dialogue_answers_only", CLEAN), "success"),
        "dialogue_volunteers_success_irred": kn(cap_rows("dialogue_volunteers", CLEAN), "success"),
        "nodialogue_success_irred": kn(cap_rows("nodialogue", CLEAN), "success"),
        "mitigation_silent_irred": kn(cap_rows("mitigation", CLEAN), "silent_failure"),
        "mitigation_abstain_irred": kn(cap_rows("mitigation", CLEAN), "abstained"),
        "mitigation_success_ctrl": kn(cap_rows("mitigation", CONTROL), "success"),
        "mitigation_abstain_ctrl": kn(cap_rows("mitigation", CONTROL), "abstained"),
        "syn_forced_silent": kn(cap_rows("forced", SYN_I), "silent_failure"),
        "api_forced_silent": kn(cap_rows("forced", API_I), "silent_failure"),
        "d_forced_vs_provided_silent": diff(cap_rows("forced", CLEAN), cap_rows("provided", CLEAN), "silent_failure"),
        "d_flagged_vs_forced_silent": diff(cap_rows("forced_flagged", CLEAN), cap_rows("forced", CLEAN), "silent_failure"),
        "d_irred_vs_ctrl_forced_silent": diff(cap_rows("forced", CLEAN), cap_rows("forced", CONTROL), "silent_failure"),
        "d_api_vs_syn_forced_silent": diff(cap_rows("forced", API_I), cap_rows("forced", SYN_I), "silent_failure"),
        "d_vol_vs_ans_success": diff(cap_rows("dialogue_volunteers", CLEAN), cap_rows("dialogue_answers_only", CLEAN), "success"),
        "d_ans_vs_cold_success": diff(cap_rows("dialogue_answers_only", CLEAN), cap_rows("nodialogue", CLEAN), "success"),
        "d_mitig_vs_forced_silent": diff(cap_rows("mitigation", CLEAN), cap_rows("forced", CLEAN), "silent_failure"),
        "d_mitig_vs_forced_success_ctrl": diff(cap_rows("mitigation", CONTROL), cap_rows("forced", CONTROL), "success"),
    }
    qual_path = os.path.join(HERE, "_qualitative_report.json")
    if os.path.exists(qual_path):
        nums["qualitative"] = json.load(open(qual_path))
    out_path = os.path.join(HERE, "_paper_numbers.json")
    json.dump(nums, open(out_path, "w"), indent=1)
    print(f"wrote {out_path} ({len(nums)} entries)")
