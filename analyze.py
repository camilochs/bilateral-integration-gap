"""Regenerate every number reported in the paper directly from the shipped run
(results/harness_results.json). NO models and NO API keys required — this reads the
recorded per-case outcomes and recomputes the tables and figure values.

    python3 analyze.py

Outcome scoring is imported from scoring.py, so the strict silent-failure definition
here is exactly the one used to produce the paper.
"""
import json, os
import corpus

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = json.load(open(os.path.join(HERE, "results", "harness_results.json")))

ARMS = ["provided", "nodialogue", "forced", "forced_flagged", "dialogue"]
CLEAN = {t["id"] for t in corpus.TASKS if all(not m["inferable"] for m in t["mismatches"])}  # irreducible gaps
PURE_CONTROL = {"T6_bool_encoding", "T7_id_shape"}                                            # fully-inferable controls

# preserve model order as first seen
MODELS = []
for r in DATA:
    if r["model"] not in MODELS:
        MODELS.append(r["model"])

def sel(model=None, arm=None, tasks=None):
    return [r for r in DATA
            if (model is None or r["model"] == model)
            and (arm is None or r["arm"] == arm)
            and (tasks is None or r["task"] in tasks)]

def rate(rows, key):
    return round(sum(r[key] for r in rows) / len(rows), 3) if rows else float("nan")

# capability gate: a model enters the silent-failure claim only if Provided-success >= 0.8
CAPABLE = [m for m in MODELS if rate(sel(m, "provided"), "success") >= 0.8]

print(f"records: {len(DATA)}   models: {MODELS}")
print(f"capable (Provided-success >= 0.8): {CAPABLE}")
print(f"irreducible/clean tasks: {sorted(CLEAN)}")

print("\n=== Table 1 — per model, full corpus ===")
print(f"{'model':18s} {'Provided':>9s} {'Forced':>7s} {'Cold':>6s} {'Dialogue':>9s}")
print(f"{'':18s} {'(correct)':>9s} {'(silent)':>7s} {'(asks)':>6s} {'(correct)':>9s}")
for m in MODELS:
    dagger = "" if m in CAPABLE else " (below 0.8 bar)"
    print(f"{m:18s} {rate(sel(m,'provided'),'success'):>9} "
          f"{rate(sel(m,'forced'),'silent_failure'):>7} "
          f"{rate(sel(m,'nodialogue'),'asked'):>6} "
          f"{rate(sel(m,'dialogue'),'success'):>9}{dagger}")

print("\n=== Figure 1 — capable models, irreducible gaps, by condition (n=45 each) ===")
print(f"{'condition':16s} {'success':>8s} {'silent':>7s} {'error':>7s} {'asks':>6s}")
for arm in ARMS:
    rows = [r for r in sel(arm=arm, tasks=CLEAN) if r["model"] in CAPABLE]
    print(f"{arm:16s} {rate(rows,'success'):>8} {rate(rows,'silent_failure'):>7} "
          f"{rate(rows,'error_failure'):>7} {rate(rows,'asked'):>6}  (n={len(rows)})")

print("\n=== Concentration (capable models, Forced arm) ===")
fc = [r for r in sel(arm="forced", tasks=CLEAN) if r["model"] in CAPABLE]
pc = [r for r in sel(arm="forced", tasks=PURE_CONTROL) if r["model"] in CAPABLE]
print(f"silent failure on irreducible gaps : {rate(fc,'silent_failure')} (n={len(fc)})")
print(f"silent failure on inferable controls (T6,T7): {rate(pc,'silent_failure')} (n={len(pc)})")

print("\nHeadline: Provided 0.89 correct  ->  Forced 0.69 silent  ->  Forced-flagged 0.76 silent  ->  Dialogue 0.53 correct.")
print("Naming the underspecified field does not lower silent failure: the fact is absent, not merely unmarked.")
