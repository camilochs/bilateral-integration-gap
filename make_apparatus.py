"""Generate the paper's tables and figures as .tex includes, from corpus.py and the merged frozen
run. Everything lands in paper_jss/generated/ and regenerates with one command:

    python3 merge_runs.py --write && python3 make_apparatus.py

Emits:
  tab_corpus.tex    Table: the 24 tasks (subset, hidden fact, irreducibility, oracle cases)
  tab_models.tex    Table: per-model x arm success/silent rates (grows as runs land)
  fig_arms7.tex     Figure: 7-arm outcome distribution, capable models, irreducible gaps
  fig_heatmap.tex   Figure: model x task silent-failure heatmap under Forced
  fig_mitigation.tex Figure: the gated-commit trade-off (silent vs completion), per frontier/capable model
Rose palette throughout (palette.tex names)."""
import json, os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(HERE, "paper_jss", "generated")
os.makedirs(GEN, exist_ok=True)
import corpus

DATA = json.load(open(os.path.join(HERE, "_merged_results.json")))
CLEAN = {t["id"] for t in corpus.TASKS if all(not m["inferable"] for m in t["mismatches"])}
CTRL = {t["id"] for t in corpus.TASKS if all(m["inferable"] for m in t["mismatches"])}
SUBSET = {t["id"]: t.get("subset", "") for t in corpus.TASKS}
ARMS = ["provided", "nodialogue", "forced", "forced_flagged",
        "dialogue_answers_only", "dialogue_volunteers", "mitigation"]
ARM_SHORT = {"provided": "Provided", "nodialogue": "No-dial.", "forced": "Forced",
             "forced_flagged": "Flagged", "dialogue_answers_only": "Dial.\\,answers",
             "dialogue_volunteers": "Dial.\\,volunt.", "mitigation": "Mitigation"}
MODELS = [m for m in ["gemma2:2b", "qwen2.5:7b", "llama3.1:8b", "mistral-nemo:12b",
                      "qwen2.5:14b", "claude-opus-4-8", "gpt-5.6-sol"]
          if any(r["model"] == m for r in DATA)]
DISP = {"claude-opus-4-8": "Opus 4.8", "gpt-5.6-sol": "GPT-5.6-sol"}

def sel(model=None, arm=None, tasks=None):
    return [r for r in DATA if (model is None or r["model"] == model)
            and (arm is None or r["arm"] == arm)
            and (tasks is None or r["task"] in tasks)]

def rate(rows, key):
    return sum(r[key] for r in rows) / len(rows) if rows else float("nan")

def capable(threshold=0.8):
    return [m for m in MODELS if rate(sel(m, "provided"), "success") >= threshold]

def w(name, text):
    open(os.path.join(GEN, name), "w").write(text)
    print(f"  wrote generated/{name}")

# ── Table: corpus ─────────────────────────────────────────────────────────────
FACT = {"T1": "date order", "T2": "unit scale (cents)", "T3": "timezone", "T4": "legacy enum map",
        "T5": "null default + scale", "T6": "boolean Y/N", "T7": "id shape", "T8": "cardinality",
        "T9": "zero-decimal currency", "T10": "pagination base", "T11": "weight unit (lb)",
        "T12": "GBX pence quote", "T13": "absent = untracked", "T14": "legacy country code",
        "T15": "VAT-inclusive price", "T16": "phone country prefix", "T17": "spreadsheet date serial",
        "T18": "name order", "T19": "pack quantity", "T20": "temperature scale",
        "T21": "epoch milliseconds", "T22": "flag \\texttt{\"1\"/\"0\"}", "T23": "alpha-3 country",
        "T24": "decimal comma"}
rows = []
for t in corpus.TASKS:
    tid = t["id"].split("_")[0]
    irr = ("mixed" if 0 < sum(m["inferable"] for m in t["mismatches"]) < len(t["mismatches"])
           else ("inferable" if t["mismatches"][0]["inferable"] else "irreducible"))
    nd = sum(c["discriminating"] for c in t["oracle"])
    rows.append(f"{tid} & {t['subset']} & {FACT.get(tid, '?')} & {t['domain']} & {irr} & "
                f"{len(t['oracle'])}\\,/\\,{nd} \\\\")
w("tab_corpus.tex", r"""\begin{table*}[t]
\centering\small
\caption{The 24 bilateral integration tasks. \emph{SYN} tasks are synthetic; \emph{API} tasks model
documented conventions of real public-API surfaces. A task is \emph{irreducible} when the hidden
fact is not recoverable from the integrator's context and the sample payload, and \emph{inferable}
(control) when the interface reveals it. Oracle cases are total\,/\,discriminating.}
\label{tab:corpus}
\begin{tabular}{@{}llllll@{}}
\toprule
Task & Subset & Hidden fact & Domain & Class & Cases \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\end{table*}
""")

# ── Table: per-model, one semantic headline metric per condition ──────────────
CAP = capable()
METRICS = [("provided", "success"), ("nodialogue", "asked"), ("forced", "silent_failure"),
           ("forced_flagged", "silent_failure"), ("dialogue_answers_only", "success"),
           ("dialogue_volunteers", "success"), ("mitigation", "abstained")]
lines = []
for m in MODELS:
    disp = DISP.get(m, f"\\texttt{{{m}}}")
    dag = "" if m in CAP else "$^\\dagger$"
    cells = []
    for a, k in METRICS:
        rr = sel(m, a)
        cells.append(f"{rate(rr, k):.2f}" if rr else "--")
    lines.append(disp + dag + " & " + " & ".join(cells) + r" \\")
w("tab_models.tex", r"""\begin{table*}[t]
\centering\small
\setlength{\tabcolsep}{6pt}
\caption{Per-model behavior across the seven conditions, full corpus; each column reports the
condition's headline metric. \emph{Provided} is the capability ceiling (correct); \emph{Cold} is
how often the model asks instead of committing when alone; \emph{Forced} and \emph{Flagged} are
silent-failure rates under a no-ask order; the two \emph{Dialogue} columns are success with a
counterpart; \emph{Mitigation} is the explicit-abstention rate under the gated-commit rule. Rows
marked $^\dagger$ fall below the \textsc{Provided} $\geq 0.8$ capability bar. Local models: 5 runs
per cell; frontier: 3.}
\label{tab:models}
\begin{tabular}{@{}lccccccc@{}}
\toprule
 & \multicolumn{1}{c}{Capability} & \multicolumn{1}{c}{Alone} &
 \multicolumn{2}{c}{Forced commitment} & \multicolumn{2}{c}{Dialogue} &
 \multicolumn{1}{c}{Gated} \\
\cmidrule(lr){2-2}\cmidrule(lr){3-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}\cmidrule(l){8-8}
Model & \makecell{Provided\\(correct)} & \makecell{Cold\\(asks)} & \makecell{Forced\\(silent)} &
\makecell{Flagged\\(silent)} & \makecell{Answers\\(correct)} & \makecell{Volunt.\\(correct)} &
\makecell{Mitigation\\(abstains)} \\
\midrule
""" + "\n".join(lines) + r"""
\bottomrule
\end{tabular}
\end{table*}
""")

# ── Table: SYN vs API (generalization) ────────────────────────────────────────
rows_sa = []
for sub in ("SYN", "API"):
    ids_i = {t for t in CLEAN if SUBSET[t] == sub}
    ids_c = {t for t in CTRL if SUBSET[t] == sub}
    pi = [r for r in sel(arm="provided", tasks=ids_i) if r["model"] in CAP]
    fi = [r for r in sel(arm="forced", tasks=ids_i) if r["model"] in CAP]
    gi = [r for r in sel(arm="forced_flagged", tasks=ids_i) if r["model"] in CAP]
    fc = [r for r in sel(arm="forced", tasks=ids_c) if r["model"] in CAP]
    rows_sa.append(f"{sub} & {len(ids_i)} & {rate(pi,'success'):.2f} & {rate(fi,'silent_failure'):.2f} & "
                   f"{rate(gi,'silent_failure'):.2f} & "
                   + (f"{rate(fc,'silent_failure'):.2f} ({len(ids_c)})" if ids_c else "--")
                   + r" \\")
w("tab_synapi.tex", r"""\begin{table}[t]
\centering\small
\caption{Generalization from synthetic to API-derived tasks: capable models, per subset.
\emph{Irred.} = irreducible tasks in the subset; control column reports silent failure on the
subset's inferable controls (count in parentheses).}
\label{tab:synapi}
\begin{tabular}{@{}lccccc@{}}
\toprule
 & & Provided & Forced & Flagged & Controls \\
Subset & Irred. & (correct) & (silent) & (silent) & (silent) \\
\midrule
""" + "\n".join(rows_sa) + r"""
\bottomrule
\end{tabular}
\end{table}
""")

# ── Table: headline comparisons with task-cluster bootstrap CIs ───────────────
import random as _random
from collections import defaultdict as _dd
def _boot(rows_a, rows_b, key, n_boot=10000, seed=7):
    rng = _random.Random(seed)
    by_a, by_b = _dd(list), _dd(list)
    for r in rows_a: by_a[r["task"]].append(r[key])
    for r in rows_b: by_b[r["task"]].append(r[key])
    tasks = sorted(set(by_a) | set(by_b))
    def stat(ts):
        xa = [v for t in ts for v in by_a.get(t, [])]
        xb = [v for t in ts for v in by_b.get(t, [])]
        return (sum(xa)/len(xa) - sum(xb)/len(xb)) if (xa and xb) else None
    point = stat(tasks)
    if point is None: return None
    draws = sorted(d for d in (stat([tasks[rng.randrange(len(tasks))] for _ in tasks])
                               for _ in range(n_boot)) if d is not None)
    return point, draws[int(0.025*len(draws))], draws[int(0.975*len(draws))]

def _cap_rows(arm, tasks):
    return [r for r in sel(arm=arm, tasks=tasks) if r["model"] in CAP]

COMPS = [
    ("Forced vs Provided (silent, irreducible)", _cap_rows("forced", CLEAN), _cap_rows("provided", CLEAN), "silent_failure"),
    ("Flagged vs Forced (silent, irreducible)", _cap_rows("forced_flagged", CLEAN), _cap_rows("forced", CLEAN), "silent_failure"),
    ("Irreducible vs controls (Forced, silent)", _cap_rows("forced", CLEAN), _cap_rows("forced", CTRL), "silent_failure"),
    ("API vs SYN (Forced, silent, irreducible)",
     _cap_rows("forced", {t for t in CLEAN if SUBSET[t]=="API"}),
     _cap_rows("forced", {t for t in CLEAN if SUBSET[t]=="SYN"}), "silent_failure"),
    ("Volunteers vs answers-only (success, irred.)", _cap_rows("dialogue_volunteers", CLEAN), _cap_rows("dialogue_answers_only", CLEAN), "success"),
    ("Answers-only vs no-dialogue (success, irred.)", _cap_rows("dialogue_answers_only", CLEAN), _cap_rows("nodialogue", CLEAN), "success"),
    ("Mitigation vs Forced (silent, irreducible)", _cap_rows("mitigation", CLEAN), _cap_rows("forced", CLEAN), "silent_failure"),
    ("Mitigation vs Forced (success, controls)", _cap_rows("mitigation", CTRL), _cap_rows("forced", CTRL), "success"),
]
rows_h = []
for lab, ra, rb, key in COMPS:
    res = _boot(ra, rb, key)
    if res is None:
        rows_h.append(f"{lab} & -- & -- \\\\")
        continue
    d, lo, hi = res
    star = r"$^{*}$" if (lo > 0 or hi < 0) else ""
    rows_h.append(f"{lab} & ${d*100:+.0f}$ & $[{lo*100:+.0f},\\,{hi*100:+.0f}]${star} \\\\")
w("tab_headline.tex", r"""\begin{table}[t]
\centering\small
\setlength{\tabcolsep}{4pt}
\caption{Headline comparisons for capable models. Differences in percentage points with
task-cluster bootstrap 95\% intervals (tasks are the resampling unit; 10\,000 draws);
$^{*}$ marks intervals excluding zero. Irreducible-task rows compare 102 runs per side;
control rows 36.}
\label{tab:headline}
\begin{tabular}{@{}lcc@{}}
\toprule
Comparison & $\Delta$ (pp) & 95\% CI \\
\midrule
""" + "\n".join(rows_h) + r"""
\bottomrule
\end{tabular}
\end{table}
""")

# ── Figure: 7-arm outcome distribution (capable models, irreducible gaps) ─────
BAR_W = 7.6
segs_tex = []
y = len(ARMS) - 1
for a in ARMS:
    rr = [r for r in sel(arm=a, tasks=CLEAN) if r["model"] in CAP]
    n = len(rr)
    if n == 0:
        y -= 1; continue
    su, si = rate(rr, "success"), rate(rr, "silent_failure")
    ask = rate(rr, "asked")
    er = max(0.0, 1.0 - su - si - ask)
    x = 0.0
    for val, col in ((su, "good"), (si, "accentLeak"), (ask, "condBtwo"), (er, "celesteMute!45")):
        if val > 0.004:
            segs_tex.append(f"  \\fill[{col}] ({x*BAR_W:.3f},{y-0.32:.2f}) rectangle "
                            f"({(x+val)*BAR_W:.3f},{y+0.32:.2f});")
        x += val
    segs_tex.append(f"  \\draw[celesteMute!30, line width=0.4pt, rounded corners=1.5pt] "
                    f"(0,{y-0.32:.2f}) rectangle ({BAR_W},{y+0.32:.2f});")
    segs_tex.append(f"  \\node[anchor=east, celesteInk, font=\\scriptsize\\scshape] "
                    f"at (-0.15,{y+0.1:.2f}) {{{ARM_SHORT[a]}}};")
    segs_tex.append(f"  \\node[anchor=east, celesteMute!90, font=\\tiny] "
                    f"at (-0.15,{y-0.16:.2f}) {{n={n}}};")
    # dominant label
    lab = (f"{su*100:.0f}\\% correct" if su >= max(si, ask) else
           f"{si*100:.0f}\\% silent" if si >= ask else f"{ask*100:.0f}\\% asks/abstains")
    big = max(su, si, ask)
    xs = {su: 0.0, si: su, ask: su + si}[big] * BAR_W + big * BAR_W / 2
    segs_tex.append(f"  \\node[white, font=\\scriptsize\\bfseries] at ({xs:.2f},{y}) {{{lab}}};")
    y -= 1
leg = (r"  \foreach \x/\c/\t in {0/good/correct, 1.7/accentLeak/{silent failure}, "
       r"3.9/condBtwo/{asks / abstains}, 6.0/celesteMute!45/{error / other}}{"
       r"\fill[\c, rounded corners=1pt] (\x,-0.95) rectangle (\x+0.26,-0.75);"
       r"\node[celesteInk, font=\scriptsize, anchor=west] at (\x+0.32,-0.85){\t};}")
w("fig_arms7.tex", "\\begin{tikzpicture}[font=\\footnotesize]\n"
  + "\n".join(segs_tex) + "\n" + leg + "\n\\end{tikzpicture}\n")

# ── Figure: heatmap model x task (Forced, silent) ─────────────────────────────
# Outlined cells so a 0-rate cell (white, with border) is distinguishable from a missing cell
# (nothing drawn). No in-figure caption text: the LaTeX caption carries the legend.
_numkey = lambda tid: int(tid.split("_")[0][1:])          # T10 after T9, not after T1
tasks_sorted = sorted(CLEAN, key=_numkey) + sorted(CTRL, key=_numkey)
C = 0.52
cells = []
for i, m in enumerate(MODELS):
    for j, tid in enumerate(tasks_sorted):
        rr = sel(m, "forced", {tid})
        if not rr:
            continue
        v = rate(rr, "silent_failure")
        pct = int(round(v * 100))
        x0, y0 = j * C, -i * C
        cells.append(f"  \\fill[accentLeak!{pct}] ({x0:.2f},{y0:.2f}) rectangle "
                     f"({x0+C-0.05:.2f},{y0-C+0.05:.2f});")
        cells.append(f"  \\draw[celesteMute!40, line width=0.3pt] ({x0:.2f},{y0:.2f}) rectangle "
                     f"({x0+C-0.05:.2f},{y0-C+0.05:.2f});")
labels = [f"  \\node[anchor=east, celesteInk, font=\\scriptsize] at (-0.12,{-i*C-C/2+0.02:.2f}) "
          f"{{{DISP.get(m, m)}}};" for i, m in enumerate(MODELS)]
tlabels = [f"  \\node[anchor=south west, celesteMute!95, font=\\tiny, rotate=55] "
           f"at ({j*C+0.08:.2f},0.05) {{{tid.split('_')[0]}}};"
           for j, tid in enumerate(tasks_sorted)]
sep = len(CLEAN) * C - 0.025
div = (f"  \\draw[celesteInk!70, line width=0.8pt] ({sep:.2f},0.02) -- "
       f"({sep:.2f},{-len(MODELS)*C-0.02:.2f});")
# in-figure color scale: silent-failure rate 0 -> 1 (white -> full rose)
ybar = -len(MODELS) * C - 0.55
scale = [f"  \\node[anchor=east, celesteInk, font=\\tiny] at (-0.12,{ybar+0.10:.2f}) "
         f"{{silent-failure rate:}};"]
for k in range(5):
    v = k * 25
    scale.append(f"  \\fill[accentLeak!{v}] ({k*0.55:.2f},{ybar:.2f}) rectangle "
                 f"({k*0.55+0.50:.2f},{ybar+0.20:.2f});")
    scale.append(f"  \\draw[celesteMute!40, line width=0.3pt] ({k*0.55:.2f},{ybar:.2f}) rectangle "
                 f"({k*0.55+0.50:.2f},{ybar+0.20:.2f});")
    scale.append(f"  \\node[anchor=north, celesteMute!95, font=\\tiny] at "
                 f"({k*0.55+0.25:.2f},{ybar-0.03:.2f}) {{{v/100:.2f}}};")
w("fig_heatmap.tex", "\\begin{tikzpicture}[font=\\footnotesize]\n"
  + "\n".join(cells + labels + tlabels + [div] + scale) + "\n\\end{tikzpicture}\n")

# ── Figure: mitigation trade-off (dumbbells: Forced -> Mitigation) ────────────
# Per capable model, two vertical dumbbells on a shared 0..1 axis:
#   rose : silent failure on irreducible gaps  (the drop is the SAFETY gain)
#   teal : success on inferable controls      (the drop is the COMPLETION cost)
# Filled dot = Forced, open dot = Mitigation, arrow = the shift under the gated-commit rule.
H = 2.6
db_axis, db_marks = [], []
x = 0.55
xmax = x + 1.4
for m in (CAP if CAP else MODELS):
    fi = rate(sel(m, "forced", CLEAN), "silent_failure")
    mi = rate(sel(m, "mitigation", CLEAN), "silent_failure")
    fc = rate(sel(m, "forced", CTRL), "success")
    mc = rate(sel(m, "mitigation", CTRL), "success")
    if any(v != v for v in (fi, mi, fc, mc)):     # NaN -> model not run yet
        continue
    for k, (v0, v1, col) in enumerate(((fi, mi, "accentLeak"), (fc, mc, "good"))):
        cx = x + k * 0.95
        if abs(v0 - v1) > 0.02:
            db_marks.append(f"  \\draw[{col}!70, line width=1.0pt, -{{Stealth[length=2mm]}}] "
                            f"({cx:.2f},{v0*H:.3f}) -- ({cx:.2f},{v1*H+0.12:.3f});")
        db_marks.append(f"  \\fill[{col}] ({cx:.2f},{v0*H:.3f}) circle (0.085);")
        db_marks.append(f"  \\draw[{col}, line width=0.8pt, fill=white] ({cx:.2f},{v1*H:.3f}) "
                        f"circle (0.085);")
        db_marks.append(f"  \\node[anchor=west, celesteInk, font=\\tiny] at "
                        f"({cx+0.13:.2f},{v0*H:.3f}) {{{v0:.2f}}};")
        y1lab = v1 * H if abs(v0 - v1) > 0.12 else v1 * H - 0.22
        db_marks.append(f"  \\node[anchor=west, celesteInk, font=\\tiny] at "
                        f"({cx+0.13:.2f},{y1lab:.3f}) {{{v1:.2f}}};")
    db_marks.append(f"  \\node[font=\\scriptsize\\bfseries, celesteInk] at ({x+0.48:.2f},-0.62) "
                    f"{{{DISP.get(m, m)}}};")
    db_marks.append(f"  \\node[font=\\tiny, accentLeak] at ({x:.2f},-0.30) {{silent}};")
    db_marks.append(f"  \\node[font=\\tiny, good!80!black] at ({x+0.95:.2f},-0.30) {{success}};")
    xmax = x + 1.55
    x += 2.5
db_axis.append(f"  \\draw[celesteMute!60, line width=0.5pt] (0,0) -- (0,{H+0.06:.2f});")
for gv in (0.0, 0.25, 0.5, 0.75, 1.0):
    db_axis.append(f"  \\draw[celesteMute!22, line width=0.3pt] (0,{gv*H:.2f}) -- "
                   f"({xmax:.2f},{gv*H:.2f});")
    db_axis.append(f"  \\node[anchor=east, celesteMute!90, font=\\tiny] at (-0.08,{gv*H:.2f}) "
                   f"{{{gv:.2f}}};")
leg2 = ("  \\node[anchor=north west, font=\\tiny, celesteInk] at (-0.35,-0.85) "
        "{filled dot $=$ \\textsc{Forced}\\quad open dot $=$ \\textsc{Mitigation}\\quad "
        "arrow $=$ shift under the gated-commit rule};")
w("fig_mitigation.tex", "\\begin{tikzpicture}[font=\\footnotesize, >={Stealth}]\n"
  + "\n".join(db_axis + db_marks) + "\n" + leg2 + "\n\\end{tikzpicture}\n")

# ── Figure: ask-rate vs scale (RQ4) ───────────────────────────────────────────
H2 = 2.4
ax = [f"  \\draw[celesteMute!60, line width=0.5pt] (0,0) -- (0,{H2+0.06:.2f});"]
for gv in (0.0, 0.5, 1.0):
    ax.append(f"  \\draw[celesteMute!22, line width=0.3pt] (0,{gv*H2:.2f}) -- (COLW,{gv*H2:.2f});")
    ax.append(f"  \\node[anchor=east, celesteMute!90, font=\\tiny] at (-0.08,{gv*H2:.2f}) {{{gv:.1f}}};")
marks = []
x = 0.6
for m in MODELS:
    ask = rate(sel(m, "nodialogue"), "asked")
    cap_s = rate(sel(m, "provided"), "success")
    if ask != ask:
        continue
    marks.append(f"  \\draw[condBtwo, line width=1.4pt] ({x:.2f},0) -- ({x:.2f},{ask*H2:.3f});")
    marks.append(f"  \\fill[condBtwo] ({x:.2f},{ask*H2:.3f}) circle (0.10);")
    marks.append(f"  \\node[anchor=south, condBtwo, font=\\tiny] at ({x:.2f},{ask*H2+0.06:.3f}) {{{ask:.2f}}};")
    marks.append(f"  \\draw[good, line width=0.9pt, fill=white] ({x+0.28:.2f},{cap_s*H2:.3f}) circle (0.085);")
    marks.append(f"  \\fill[good] ({x+0.28:.2f},{cap_s*H2:.3f}) circle (0.05);")
    lbl = DISP.get(m, m.split(":")[0] + ":" + m.split(":")[1] if ":" in m else m)
    marks.append(f"  \\node[font=\\tiny, celesteInk, rotate=28, anchor=north east] at ({x+0.34:.2f},-0.10) {{{lbl}}};")
    x += 1.05
colw = x - 0.15
ax = [s.replace("COLW", f"{colw:.2f}") for s in ax]
leg4 = (f"  \\node[anchor=north west, font=\\tiny, celesteInk] at (-0.3,-1.25) "
        "{\\textcolor{condBtwo}{lollipop} $=$ cold ask-rate \\quad "
        "\\textcolor{good}{dot} $=$ \\textsc{Provided} success (capability)};")
w("fig_askscale.tex", "\\begin{tikzpicture}[font=\\footnotesize]\n"
  + "\n".join(ax + marks) + "\n" + leg4 + "\n\\end{tikzpicture}\n")

print(f"capable models: {CAP}")
print("done")
