"""Deterministic unit tests for scoring.outcome() — code checking code (no model, no network).
Covers exactly the failure modes Codex flagged 2026-07-16:
 - an adapter that returns WRONG on one discriminating case but CRASHES on another must be LOUD, not silent;
 - no-benign tasks (all-discriminating) classify correctly;
 - a wrong value on a BENIGN/common case is loud, not silent.
"""
import sys
from scoring import outcome

def task(disc):                       # minimal task: only the discriminating flags are used
    return {"oracle": [{"discriminating": d} for d in disc]}

def label(oc):
    for k in ("success", "silent_failure", "error_failure", "asked", "garbage"):
        if oc[k]:
            return k
    return "none"

CASES = [
    # results,               disc,               raw,                       expected
    (["pass", "pass", "pass"], [False, True, True], "",                       "success"),
    (["pass", "wrong", "pass"], [False, True, True], "",                      "silent_failure"),  # benign ok, disc wrong, no error
    (["pass", "wrong", "error"], [False, True, True], "",                     "error_failure"),   # CODEX: wrong+crash -> loud
    (["pass", "error", "wrong"], [False, True, True], "",                     "error_failure"),   # crash anywhere -> loud
    (["wrong", "pass", "pass"], [False, True, True], "",                      "error_failure"),   # benign WRONG -> loud, not silent
    (["error", "pass", "pass"], [False, True, True], "",                      "error_failure"),   # benign crash -> loud
    (["wrong", "wrong"],        [True, True],        "",                      "silent_failure"),  # no-benign, all ran wrong -> silent
    (["wrong", "error"],        [True, True],        "",                      "error_failure"),   # no-benign, a crash -> loud
    (["error", "error"],        [True, True],        "",                      "error_failure"),
    (["pass", "pass"],          [False, True],       "",                      "success"),         # all pass => success
    (None,                      [False, True],       "Is amount cents or euros?", "asked"),
    (None,                      [False, True],       "def adapt(x): return x",    "garbage"),
]

fails = 0
for results, disc, raw, exp in CASES:
    got = label(outcome(results, raw, task(disc)))
    ok = (got == exp)
    print(f"{'OK  ' if ok else 'FAIL'} results={str(results):28s} disc={disc} -> {got:14s} (expected {exp})")
    if not ok:
        fails += 1

# the last CASE is actually all-pass -> success; fix its expectation inline by re-checking
print("\nExtra invariants:")
inv = [
    (outcome(["pass", "pass"], "", task([False, True]))["success"] is True, "all pass => success"),
    (outcome(["pass", "wrong", "error"], "", task([False, True, True]))["silent_failure"] is False, "wrong+error not silent"),
    (outcome(["wrong", "wrong"], "", task([True, True]))["silent_failure"] is True, "no-benign all-wrong is silent"),
    (sum(outcome(["pass", "wrong"], "", task([False, True]))[k] for k in
         ("success", "silent_failure", "error_failure", "asked", "garbage")) == 1, "flags mutually exclusive"),
]
for cond, name in inv:
    print(f"{'OK  ' if cond else 'FAIL'} {name}")
    if not cond:
        fails += 1

print(f"\n{'ALL TESTS PASS' if fails == 0 else f'{fails} FAILURES'}")
sys.exit(1 if fails else 0)
