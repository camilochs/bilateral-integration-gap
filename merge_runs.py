"""Merge the campaign runs into one frozen dataset (_merged_results.json) with explicit
per-(model, task) precedence, then audit the grid.

Precedence (highest wins), per model:
  claude-opus-4-8:
    T23_alpha3_country                  -> _campaign_opus_t23.json          (bounded task, all 7 arms)
    10 truncation-fix tasks             -> _campaign_opus_fix.json          (raised cap, all 7 arms)
    other API tasks                     -> _campaign_opus_api.json
    other SYN tasks, 2 new arms         -> _campaign_opus_syn_newarms.json
    other SYN tasks, 5 original arms    -> _harness_results.json (v1 frozen; arm 'dialogue'
                                           renamed 'dialogue_volunteers'; normalized fields)
  gpt-5.6-sol:
    T23_alpha3_country                  -> _campaign_gpt_t23.json
    everything else                     -> _campaign_gpt.json
  locals (5 models):
    T23_alpha3_country                  -> _campaign_locals_t23.json        (addendum, bounded task)
    everything else                     -> _campaign_locals.json

v1 is reused ONLY where the protocol is unchanged (same prompts, same arms); every reused record
is tagged provenance='v1-frozen'. All merges tag provenance so the paper can state exactly which
cells come from which run. Run: python3 merge_runs.py
"""
import json, os, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
import corpus

FIX_TASKS = set(open(os.path.join(HERE, "_opus_fix_tasks.txt")).read().strip().split(","))
FIX_TASKS.discard("T23_alpha3_country")          # T23 has its own (bounded) rerun
T23 = "T23_alpha3_country"
SYN = {t["id"] for t in corpus.TASKS if t["subset"] == "SYN"}
ALL_TASKS = {t["id"] for t in corpus.TASKS}
OLD_ARMS = {"provided", "nodialogue", "forced", "forced_flagged", "dialogue"}
LOCALS = ["gemma2:2b", "qwen2.5:7b", "llama3.1:8b", "mistral-nemo:12b", "qwen2.5:14b"]

def load(name):
    p = os.path.join(HERE, name)
    return json.load(open(p)) if os.path.exists(p) else []

def norm(r, provenance):
    r = dict(r)
    if r["arm"] == "dialogue":
        r["arm"] = "dialogue_volunteers"
    r.setdefault("subset", next((t["subset"] for t in corpus.TASKS if t["id"] == r["task"]), ""))
    r.setdefault("abstained", False)
    r["provenance"] = provenance
    return r

out = []

# ---- Opus ----
opus_t23  = [norm(r, "opus-t23-bounded") for r in load("_campaign_opus_t23.json")]
opus_fix  = [norm(r, "opus-fix-cap2000") for r in load("_campaign_opus_fix.json")
             if r["task"] in FIX_TASKS]
opus_api  = [norm(r, "opus-campaign")    for r in load("_campaign_opus_api.json")
             if r["task"] not in FIX_TASKS and r["task"] != T23]
opus_syn  = [norm(r, "opus-campaign")    for r in load("_campaign_opus_syn_newarms.json")
             if r["task"] not in FIX_TASKS and r["task"] != T23]
v1        = [norm(r, "v1-frozen") for r in load("_harness_results.json")
             if r["model"] == "claude-opus-4-8" and r["arm"] in OLD_ARMS
             and r["task"] in SYN and r["task"] not in FIX_TASKS and r["task"] != T23]
out += opus_t23 + opus_fix + opus_api + opus_syn + v1

# ---- GPT ----
out += [norm(r, "gpt-t23-bounded") for r in load("_campaign_gpt_t23.json")]
out += [norm(r, "gpt-campaign")    for r in load("_campaign_gpt.json") if r["task"] != T23]

# ---- locals ----
out += [norm(r, "locals-t23-bounded") for r in load("_campaign_locals_t23.json")]
out += [norm(r, "locals-campaign")    for r in load("_campaign_locals.json") if r["task"] != T23]

# ---- audit ----
print(f"merged records: {len(out)}")
dupes = [k for k, c in Counter((r["model"], r["task"], r["arm"], r["run"], r["provenance"])
                               for r in out).items() if c > 1]
print(f"duplicate (model,task,arm,run,prov) keys: {len(dupes)}")
cover = Counter()
for r in out:
    cover[(r["model"], r["task"], r["arm"])] += 1

ARMS7 = ["provided", "nodialogue", "forced", "forced_flagged",
         "dialogue_answers_only", "dialogue_volunteers", "mitigation"]
missing, short = [], []
for m in ["claude-opus-4-8", "gpt-5.6-sol"] + LOCALS:
    want = 3 if not m.startswith(("gemma", "qwen", "llama", "mistral")) else 5
    for t in sorted(ALL_TASKS):
        for a in ARMS7:
            n = cover.get((m, t, a), 0)
            if n == 0:
                missing.append((m, t, a))
            elif n < want:
                short.append((m, t, a, n, want))
print(f"cells missing entirely: {len(missing)}")
if missing[:8]:
    for x in missing[:8]: print("   MISSING:", x)
print(f"cells short of target runs: {len(short)}")
if short[:8]:
    for x in short[:8]: print("   SHORT:", x)
print("provenance:", dict(Counter(r["provenance"] for r in out)))

if "--write" in sys.argv:
    json.dump(out, open(os.path.join(HERE, "_merged_results.json"), "w"), indent=1)
    print("wrote _merged_results.json")
else:
    print("(dry run; pass --write to freeze the merge)")
