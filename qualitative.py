"""Qualitative failure-shape analysis over the frozen run (no model, no network, no LLM judge).

Classifies every silent failure and every abstention in the merged record with TRANSPARENT
heuristics (declared as such in the paper):

  silent-failure shapes (mutually exclusive priority: acknowledged > thorough > confident):
    acknowledged  the code/raw carries an assumption marker yet the unit still committed
                  (detected ambiguity, crossed it anyway)
    thorough      the adapter is elaborate: mapping table with >3 entries, or validation
                  scaffolding (try/except + checks), or long code (> 24 lines)
    confident     everything else: short idiomatic code built on the integrator's own convention

  abstentions:
    on-point      the ABSTAIN text raises the task's planted mismatch (probe-keyword match,
                  same proxy as dialogue surfacing)
    off-point     an abstention whose named question does not touch the planted mismatch
    over          any abstention on an inferable control (the interface held the answer)

Outputs _qualitative_report.json with counts + exemplar unit ids, and a console summary.

    python3 qualitative.py [merged.json]        # default: _merged_results.json
"""
import json, os, re, sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "_merged_results.json")
DATA = json.load(open(PATH))
import corpus

TASK = {t["id"]: t for t in corpus.TASKS}
CLEAN = {t["id"] for t in corpus.TASKS if all(not m["inferable"] for m in t["mismatches"])}
CTRL = {t["id"] for t in corpus.TASKS if all(m["inferable"] for m in t["mismatches"])}

ASSUME = re.compile(r"\b(assum\w*|guess\w*|presum\w*|unclear|ambiguous|uncertain|not\s+specified|"
                    r"no\s+way\s+to\s+know|convention\s+is\s+unknown|interpret\w*\s+as)\b", re.I)
MAP_ENTRY = re.compile(r"['\"][^'\"]{1,24}['\"]\s*:\s*")     # dict-literal entries
VALID_SCAFFOLD = re.compile(r"\b(try:|except\b|raise\b|isinstance\(|ValueError)\b")

def code_lines(code):
    return [l for l in (code or "").splitlines() if l.strip() and not l.strip().startswith("#")]

def classify_silent(rec):
    code, raw = rec.get("code") or "", rec.get("raw") or ""
    if ASSUME.search(code) or ASSUME.search(raw):
        return "acknowledged"
    n_map = len(MAP_ENTRY.findall(code))
    if n_map > 3 or VALID_SCAFFOLD.search(code) or len(code_lines(code)) > 24:
        return "thorough"
    return "confident"

def abstain_on_point(rec):
    blob = (rec.get("raw") or "").lower()
    kws = [k.lower() for mm in TASK[rec["task"]]["mismatches"] for k in mm["probe_keywords"]]
    return any(k in blob for k in kws)

silents = [r for r in DATA if r.get("silent_failure")]
abstains = [r for r in DATA if r.get("abstained")]

shape_counts = Counter()
shape_examples = defaultdict(list)
for r in silents:
    s = classify_silent(r)
    shape_counts[s] += 1
    shape_examples[s].append((r["model"], r["task"], r["arm"], r["run"], len(code_lines(r.get("code") or ""))))

ab_counts = Counter()
ab_examples = defaultdict(list)
for r in abstains:
    kind = "over" if r["task"] in CTRL else ("on-point" if abstain_on_point(r) else "off-point")
    # controls can still be on/off-point; track both axes
    ab_counts[kind] += 1
    if r["task"] in CTRL:
        ab_counts["ctrl-on-point" if abstain_on_point(r) else "ctrl-off-point"] += 1
    ab_examples[kind].append((r["model"], r["task"], r["arm"], r["run"]))

# on-point rate on irreducible abstentions (the construct check for RQ6)
irr_ab = [r for r in abstains if r["task"] in CLEAN]
irr_on = sum(1 for r in irr_ab if abstain_on_point(r))

report = {
    "n_records": len(DATA),
    "n_silent": len(silents),
    "silent_shapes": dict(shape_counts),
    "silent_shapes_by_model": {
        m: dict(Counter(classify_silent(r) for r in silents if r["model"] == m))
        for m in sorted({r["model"] for r in silents})},
    "n_abstentions": len(abstains),
    "abstentions": dict(ab_counts),
    "irreducible_abstentions_on_point": [irr_on, len(irr_ab)],
    "examples": {k: v[:8] for k, v in {**shape_examples, **ab_examples}.items()},
}
json.dump(report, open(os.path.join(HERE, "_qualitative_report.json"), "w"), indent=1)

print(f"records {len(DATA)}  silent {len(silents)}  abstentions {len(abstains)}")
print("\nsilent-failure shapes:")
for k in ("confident", "thorough", "acknowledged"):
    n = shape_counts.get(k, 0)
    print(f"  {k:13s} {n:3d}  ({n/len(silents):.0%})" if silents else "  none")
print("\nby model:")
for m, d in report["silent_shapes_by_model"].items():
    print(f"  {m:es20s}" if False else f"  {m:20s} {d}")
print(f"\nabstentions: {dict(ab_counts)}")
print(f"irreducible abstentions naming the planted mismatch: {irr_on}/{len(irr_ab)}"
      + (f" = {irr_on/len(irr_ab):.0%}" if irr_ab else ""))
print("\nexemplar units per shape (model, task, arm, run):")
for k, v in report["examples"].items():
    print(f"  {k}: {v[:3]}")
print("\nwrote _qualitative_report.json")
