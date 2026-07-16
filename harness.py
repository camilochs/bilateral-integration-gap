"""Bilateral-integration harness: measure whether SURFACING the hidden knowledge gap predicts
a correct integration, on local Ollama models, with a deterministic oracle (no LLM judge).

Two roles per task (asymmetric partial knowledge of the environment):
  - Agent A = PROVIDER of System A. Given ONLY a_context (A's output semantics). Cannot see B's needs.
  - Agent B = INTEGRATOR. Given ONLY b_context + a sample A-payload (keys visible, semantics NOT).
    Must write adapt(a_payload) -> b_payload. Cannot see A's semantics unless it is surfaced.

The correctness fact lives split across the two contexts. Neither can write a correct adapter alone;
the mismatch is closed only if SOMEONE asks/says the thing that surfaces it.

Three arms (within-task, matched sample + temperature):
  - NO-DIALOGUE (baseline): B writes the adapter cold, from b_context + sample only. Measures the
    silent-failure base rate when the boundary of one's own knowledge is never probed.
  - DIALOGUE: A and B exchange up to R rounds first (B drives, both may ask/volunteer), THEN B writes
    the adapter using the transcript.
  - PROVIDED (capability control): B is GIVEN the hidden facts directly, then writes the adapter. This
    KILLS the coding-incompetence confound: if PROVIDED success is high, the substrate can write the
    adapter once the gap is closed, so a NO-DIALOGUE failure is genuine non-detection, not incompetence.
    PROVIDED is the ceiling; NO-DIALOGUE the floor; DIALOGUE the empirical question (do they ask?).

Per (task, model, arm, run) we record:
  - surfaced[mismatch]  : did the transcript raise this mismatch? (probe_keywords substring, transcript-only,
                          independent of the adapter — this is the *detection* measure, PROXY, see NOTE)
  - success             : adapter passes ALL oracle cases
  - silent_failure      : adapter passes every BENIGN case but fails >=1 DISCRIMINATING case (looks done, broken)
  - invalid             : no runnable adapter produced

Star question: does #mismatches-surfaced predict success? And does DIALOGUE reduce silent failure vs NO-DIALOGUE?

NOTE (limitation, stated not hidden): surfaced[] is a keyword proxy on the transcript. It can miss a
paraphrase (false negative) or fire on an incidental mention (false positive). It is deliberately measured
independently of the adapter so detection is not defined by success. Refinement (stricter matcher) is future work.
"""
import re, os, json, sys, subprocess, tempfile, threading, concurrent.futures as cf
from collections import defaultdict
from openai import OpenAI
import corpus
from scoring import outcome, is_balk   # unit-tested scoring (see test_scoring.py)

OLL = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
_CLIENTS = {}
def client_for(model):
    """Route by model name: claude-* -> Anthropic (OpenAI-compat), deepseek* -> DeepSeek, else local Ollama.
    API keys are read from the environment only; never hardcoded."""
    if model.startswith("claude"):
        if "anthropic" not in _CLIENTS:
            _CLIENTS["anthropic"] = OpenAI(base_url="https://api.anthropic.com/v1/",
                                           api_key=os.environ["ANTHROPIC_API_KEY"])
        return _CLIENTS["anthropic"]
    if model.startswith("deepseek"):
        if "deepseek" not in _CLIENTS:
            _CLIENTS["deepseek"] = OpenAI(base_url="https://api.deepseek.com",
                                          api_key=os.environ["DEEPSEEK_API_KEY"])
        return _CLIENTS["deepseek"]
    return OLL

MODELS = os.environ.get("MODELS", "qwen2.5:7b,llama3.2:3b").split(",")
N_RUNS = int(os.environ.get("N_RUNS", "2"))
ROUNDS = int(os.environ.get("ROUNDS", "3"))     # dialogue rounds (each = B turn + A turn)
T = 0.7
DANGER = re.compile(r"\b(os\.|sys\.|subprocess|shutil|socket|urllib|requests|open\s*\(|eval\s*\(|exec\s*\(|__import__|input\s*\()")

def gen(model, messages, max_tokens=400):
    cl = client_for(model)
    kwargs = dict(model=model, timeout=180, max_tokens=max_tokens, messages=messages)
    if not model.startswith("claude"):     # Opus 4.8 deprecates temperature; locals use it for run variety
        kwargs["temperature"] = T
    last = None
    for _ in range(3):
        try:
            r = cl.chat.completions.create(**kwargs)
            return r.choices[0].message.content or ""
        except Exception as e:
            last = e
            import time; time.sleep(2)
    sys.stderr.write(f"[gen FAILED model={model}] {type(last).__name__}: {last}\n"); sys.stderr.flush()
    return ""

def extract_code(text):
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.S)
    code = m.group(1).strip() if m else text
    if "def adapt" not in code:                 # last resort: grab from a bare def adapt
        i = text.find("def adapt")
        code = text[i:].strip() if i >= 0 else code
    return code

def sample_payload(task):
    for c in task["oracle"]:
        if not c["discriminating"]:
            return c["a"]
    return task["oracle"][0]["a"]               # no benign case: a discriminating value still hides the semantics

# ─────────────────────────── deterministic oracle on a model-written adapter ───────────────────────────
_DRIVER = r'''
import json
_CASES = json.loads({cases_json!r})
def _eq(x, y):
    if isinstance(x, float) or isinstance(y, float):
        try: return abs(float(x) - float(y)) < 1e-9
        except Exception: return False
    if isinstance(x, dict) and isinstance(y, dict):
        return x.keys() == y.keys() and all(_eq(x[k], y[k]) for k in x)
    if isinstance(x, list) and isinstance(y, list):
        return len(x) == len(y) and all(_eq(a, b) for a, b in zip(x, y))
    return x == y
_out = []
for _a, _exp in _CASES:
    try:
        _got = adapt(_a)
        _out.append("pass" if _eq(_got, _exp) else "wrong")   # ran, correct vs ran, WRONG value (silent)
    except Exception:
        _out.append("error")                                  # raised — a loud/detectable failure
print("RESULT" + json.dumps(_out))
'''

def run_adapter(code, task):
    """Return per-oracle-case pass list, or None if the adapter is invalid/dangerous/non-runnable."""
    if not code or "def adapt" not in code or DANGER.search(code):
        return None
    cases = [[c["a"], task["ref"](c["a"])] for c in task["oracle"]]
    prog = code + "\n\n" + _DRIVER.format(cases_json=json.dumps(cases))
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, dir="/tmp") as f:
            f.write(prog); path = f.name
        r = subprocess.run(["python3", path], capture_output=True, timeout=12, cwd="/tmp",
                           env={"PATH": "/usr/bin:/bin"}, text=True)
        os.unlink(path)
        line = [l for l in r.stdout.splitlines() if l.startswith("RESULT")]
        return json.loads(line[-1][6:]) if line else None
    except Exception:
        return None

# outcome() and is_balk() live in scoring.py (unit-tested in test_scoring.py); imported at top.

# ─────────────────────────── dialogue + gap-surfacing ───────────────────────────
A_SYS = ("You represent the PROVIDER of System A at one company. You know ONLY the following about your "
         "own system, and nothing about the other company's system:\n\n{ctx}\n\n"
         "An engineer from ANOTHER company is building an integration that consumes your data. Answer their "
         "questions truthfully from the facts above, and proactively volunteer any detail of your format or "
         "semantics that an outsider could get wrong. Do not invent facts beyond what you were told. Reply in "
         "1-3 sentences. If nothing remains to clarify, reply exactly DONE.")
B_SYS = ("You are the INTEGRATOR at your company. You must write a Python function adapt(a_payload) that "
         "converts a payload from System A (another company) into the shape YOUR system requires. You know "
         "ONLY your own requirements, and a sample payload; you do NOT know System A's conventions:\n\n"
         "YOUR REQUIREMENTS:\n{ctx}\n\nSAMPLE a_payload (keys are real; the VALUES may hide conventions you "
         "must not assume): {sample}\n\n"
         "You can talk to System A's provider to learn what you need. Ask precise questions about anything in "
         "the payload whose meaning, format, units, encoding, or optionality is not certain. Reply in 1-3 "
         "sentences with your question(s). When you are confident you have every fact needed, reply exactly READY.")

def dialogue(model, task):
    ctxA = A_SYS.format(ctx=task["a_context"])
    ctxB = B_SYS.format(ctx=task["b_context"], sample=json.dumps(sample_payload(task)))
    transcript = []                              # list of (speaker, text)
    def render(for_side):
        me, other = ("B", "A") if for_side == "B" else ("A", "B")
        lines = [f"{'YOU' if s==me else 'THEM'}: {t}" for s, t in transcript]
        return "\n".join(lines) if lines else "(no messages yet)"
    for _ in range(ROUNDS):
        bmsg = gen(model, [{"role": "system", "content": ctxB},
                           {"role": "user", "content": "Conversation so far:\n" + render("B") +
                            "\n\nYour next message to System A's provider (a question, or READY):"}], 200)
        transcript.append(("B", bmsg.strip()))
        if bmsg.strip().upper().startswith("READY"):
            break
        amsg = gen(model, [{"role": "system", "content": ctxA},
                           {"role": "user", "content": "Conversation so far:\n" + render("A") +
                            "\n\nYour next reply to the integrator (or DONE):"}], 200)
        transcript.append(("A", amsg.strip()))
    return transcript

FORCED_SYS = ("You are the INTEGRATOR at your company. Write a Python function adapt(a_payload) that converts a "
              "payload from System A (another company) into the shape YOUR system requires. You know ONLY your "
              "own requirements and a sample payload; you do NOT know System A's conventions:\n\n"
              "YOUR REQUIREMENTS:\n{ctx}\n\nSAMPLE a_payload (keys are real; the VALUES may hide conventions you "
              "must not assume): {sample}\n\n"
              "You will receive NO further information and you CANNOT ask questions. Commit to your best "
              "implementation now.")

def write_adapter(model, task, transcript, forced=False, flagged=False):
    sys_p = (FORCED_SYS if (forced or flagged) else B_SYS).format(
        ctx=task["b_context"], sample=json.dumps(sample_payload(task)))
    convo = "\n".join(f"{'System-A provider' if s=='A' else 'You'}: {t}" for s, t in transcript)
    convo_block = ("\n\nWhat you learned from talking to System A's provider:\n" + convo) if transcript else ""
    instr = ("Now write the adapter." + convo_block +
             "\n\nReturn ONLY a Python function `def adapt(a_payload):` that takes one System-A payload dict and "
             "returns the dict your system requires. No explanation, no prints. Handle the conventions you "
             "learned. Use only the standard library.")
    if flagged:
        # NEUTRAL flag: name only the field(s) whose convention is undetermined — do NOT list the candidate
        # conventions or ask the surfacing question (that would leak the answer space). Removes the DETECTION
        # burden while withholding the fact.
        fields = ", ".join(mm["field"] for mm in task["mismatches"])
        instr += (f"\n\nNote: your requirements and the sample do NOT determine the convention for the "
                  f"following field(s): {fields}. You cannot ask about it. Make your best decision and commit.")
    if forced or flagged:
        instr += " Do NOT ask questions; commit to your best implementation."
    raw = gen(model, [{"role": "system", "content": sys_p}, {"role": "user", "content": instr}], 800)
    return raw, extract_code(raw)

def surfaced(transcript, task):
    """Keyword proxy: for each mismatch, did any transcript message raise it? (transcript-only, PROXY)."""
    blob = " ".join(t.lower() for _, t in transcript)
    return {mm["field"]: any(k.lower() in blob for k in mm["probe_keywords"]) for mm in task["mismatches"]}

def provided_facts(task):
    """Capability-control input: state each hidden fact plainly, as if the gap were perfectly surfaced."""
    lines = [f"- {mm['field']}: in System A, {mm['a_semantics']}." for mm in task["mismatches"]]
    return "System A's provider tells you the following about the payload:\n" + "\n".join(lines)

# ─────────────────────────── run matrix ───────────────────────────
def run_unit(task, model, arm, run_idx):
    forced = (arm == "forced")
    flagged = (arm == "forced_flagged")
    if arm == "dialogue":
        tr = dialogue(model, task)
        surf = surfaced(tr, task)
    elif arm == "provided":
        tr = [("A", provided_facts(task))]
        surf = {mm["field"]: True for mm in task["mismatches"]}   # given by construction
    else:  # nodialogue / forced / forced_flagged (all cold; forced+flagged forbid asking)
        tr = []
        surf = surfaced(tr, task)
    raw, code = write_adapter(model, task, tr, forced=forced, flagged=flagged)
    passes = run_adapter(code, task)                              # per-case list {pass,wrong,error} or None
    oc = outcome(passes, raw, task)
    return {"task": task["id"], "model": model, "arm": arm, "run": run_idx,
            "n_mismatches": len(task["mismatches"]),
            "n_surfaced": sum(surf.values()), "surfaced": surf,
            "turns": len(tr),
            # ── full raw record retained so any later question is a re-analysis, not a re-generation ──
            "per_case": passes, "code": code, "raw": raw,
            "temperature": (T if not model.startswith("claude") else None),
            **oc}

def main():
    units = [(t, m, arm, r) for t in corpus.TASKS for m in MODELS
             for arm in ("provided", "nodialogue", "forced", "forced_flagged", "dialogue") for r in range(N_RUNS)]
    print(f"units={len(units)}  models={MODELS}  runs={N_RUNS}  rounds={ROUNDS}", flush=True)
    recs = []; lock = threading.Lock(); done = [0]
    def work(u):
        rec = run_unit(*u)
        with lock:
            recs.append(rec); done[0] += 1
            if done[0] % 10 == 0: print(f"  {done[0]}/{len(units)}", flush=True)
        return rec
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(work, units))
    json.dump(recs, open("_harness_results.json", "w"), indent=1)

    # ── aggregate ──
    def rate(rows, key):
        return round(sum(r[key] for r in rows) / len(rows), 3) if rows else None
    print("\n=== ARM SUMMARY per model (success | silent=ran&wrong | error=crash | asked | garbage) ===")
    print(f"{'model':16s} {'arm':11s} {'n':>3s} {'succ':>6s} {'silent':>7s} {'error':>6s} {'asked':>6s} {'garbage':>8s}")
    for m in MODELS:
        for arm in ("provided", "nodialogue", "forced", "forced_flagged", "dialogue"):
            rows = [r for r in recs if r["arm"] == arm and r["model"] == m]
            print(f"{m:16s} {arm:11s} {len(rows):3d} {rate(rows,'success'):>6} {rate(rows,'silent_failure'):>7} "
                  f"{rate(rows,'error_failure'):>6} {rate(rows,'asked'):>6} {rate(rows,'garbage'):>8}")

    # ── localization: phenomenon should sit on NON-INFERABLE gaps, not the inferable control tasks ──
    clean_ids = {t["id"] for t in corpus.TASKS if all(not m["inferable"] for m in t["mismatches"])}
    print(f"\n=== INFERABILITY SPLIT (clean = gap not recoverable from schema/sample: {sorted(clean_ids)}) ===")
    print(f"{'arm':12s} {'group':8s} {'n':>4s} {'success':>8s} {'silent_fail':>12s}")
    for arm in ("provided", "nodialogue", "forced", "forced_flagged", "dialogue"):
        for grp, pred in (("clean", lambda r: r["task"] in clean_ids), ("control", lambda r: r["task"] not in clean_ids)):
            rows = [r for r in recs if r["arm"] == arm and pred(r)]
            if rows:
                print(f"{arm:12s} {grp:8s} {len(rows):4d} {rate(rows,'success'):>8} {rate(rows,'silent_failure'):>12}")

    # ── star relationship: does surfacing predict success? (fully-surfaced vs not, over valid adapters) ──
    print("\n=== DETECTION -> SUCCESS (valid adapters only) ===")
    valid = [r for r in recs if not r["invalid"]]
    full = [r for r in valid if r["n_surfaced"] == r["n_mismatches"]]
    part = [r for r in valid if r["n_surfaced"] < r["n_mismatches"]]
    print(f"all mismatches surfaced : n={len(full):3d}  success={rate(full,'success')}  silent_fail={rate(full,'silent_failure')}")
    print(f"gap left un-surfaced    : n={len(part):3d}  success={rate(part,'success')}  silent_fail={rate(part,'silent_failure')}")
    # point-biserial-ish: mean surfaced-fraction among successes vs failures
    succ = [r for r in valid if r["success"]]; fail = [r for r in valid if not r["success"]]
    def sf(rows): return round(sum(r["n_surfaced"]/r["n_mismatches"] for r in rows)/len(rows), 3) if rows else None
    print(f"mean surfaced-fraction  : successes={sf(succ)}  failures={sf(fail)}")

    print("\n=== PER-MODEL (success | silent_fail), nodialogue -> dialogue ===")
    for m in MODELS:
        nd = [r for r in recs if r["model"] == m and r["arm"] == "nodialogue"]
        dl = [r for r in recs if r["model"] == m and r["arm"] == "dialogue"]
        print(f"{m:14s} success {rate(nd,'success')} -> {rate(dl,'success')} | "
              f"silent {rate(nd,'silent_failure')} -> {rate(dl,'silent_failure')}")

if __name__ == "__main__":
    main()
