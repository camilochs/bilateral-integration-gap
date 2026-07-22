<div align="center">

# Code Agents under Split Specifications
### An Empirical Study of Silent Failure in Cross-Organizational Integration

Corpus, deterministic oracle, frozen runs, and reproduction harness for the paper
(Journal of Systems and Software submission).

[![License: MIT](https://img.shields.io/badge/License-MIT-C23E63.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-2E9C8E.svg)](https://www.python.org/)
[![Reproducible](https://img.shields.io/badge/numbers-reproducible%20offline-7E5AA6.svg)](#reproduce-the-paper-one-command-no-models-needed)

<img src="figures/fig1.png" width="800" alt="Two agents across an organizational boundary. Agent A holds the reconciling fact (dates are day-first) that Agent B needs and cannot see. If B asks and obtains it, the adapter is grounded and correct; if B commits without it, the adapter runs clean and returns the wrong value, a silent failure.">

</div>

---

## The result in one line

Two code agents from different organizations must build an integration, and the fact that makes it correct is held by the other side. **Given that fact, the capable models build the integration correctly 90% of the time. Forbidden to ask and forced to commit, the same models ship an adapter that runs clean and returns the wrong value (a _silent failure_) 61% of the time** (task-cluster 95% CI 55–67%). Naming the underspecified field does not lower that rate (it rises to 69%): the fact is *absent*, not merely unmarked. Capability does not close the gap; what closes it is surfacing the missing fact, and that behavior does not track model scale.

**What this contains.** The full study: **24 tasks** (8 synthetic + 16 modeled on documented public-API conventions), **7 conditions**, **7 models** (five local open-weight, 2B–14B, and two frontier systems from different providers: Opus 4.8 and GPT-5.6-sol), and task-cluster bootstrap confidence intervals. The two mechanism conditions (answers-only dialogue, gated-commit mitigation) decompose the recovery channel. Deterministic oracle, **no model-based evaluation**. Every number in the paper regenerates from the frozen run with no models and no API keys.

## Reproduce the paper (one command, no models needed)

```bash
./reproduce.sh
```

This runs offline from the frozen run in `results/`. The bootstrap is **seeded (seed=7)**, so the confidence intervals reproduce exactly. The script regenerates `_paper_numbers.json` and confirms it is **byte-identical** to the shipped `results/_paper_numbers.json` — every value in the paper is reproduced from the frozen record alone. No network, no API keys, standard library only.

To regenerate the paper's tables and figures (LaTeX includes) as well:

```bash
python3 make_apparatus.py            # writes paper_jss/generated/*.tex from the frozen run
```

## What this repository is

| File | What it is |
|---|---|
| **`corpus.py`** | The 24 bilateral integration tasks. Each gives System A's context and System B's context (asymmetric partial knowledge) and plants at least one hidden mismatch. `subset` marks SYN (synthetic) vs API (documented real-interface conventions: zero-decimal currencies, GBX pence quotes, spreadsheet date serials, legacy country codes, VAT-inclusive prices, E.164 telephony, …). **Self-validating**: `python3 corpus.py` proves each gap is solvable once surfaced, silent on benign inputs, breaking on the discriminating ones. |
| **`scoring.py`** | The strict outcome definition. A *silent failure* = the adapter ran on every case with **no exception**, passed every benign case, and returned a **wrong value** on a discriminating case. A crash anywhere is loud, never silent. |
| **`harness.py`** | The experiment: **7 conditions** × 7 models. `provided` (fact given = capability ceiling), `nodialogue` (asks but no one answers), `forced` (commit, cannot ask), `forced_flagged` (the ambiguous field is named, still cannot ask), `dialogue_answers_only` (provider answers only what is asked), `dialogue_volunteers` (provider may volunteer), `mitigation` (gated commit: build only if the fact is established, else abstain). Checkpoints every 25 units and resumes. |
| **`test_scoring.py`** | Unit tests for the scoring, including the edge cases (a wrong value on one case plus a crash on another is *loud*, not silent). |
| **`analyze.py`** | Regenerates every reported number from the frozen run, with per-model + per-cell capability gating, Wilson intervals, and task-cluster bootstrap CIs. `--emit-numbers` writes the machine-readable `_paper_numbers.json`. **No models, no keys.** |
| **`qualitative.py`** | Transparent (non-LLM) classification of every silent failure into *confident default* / *thorough wrong adapter* / *acknowledged guess*, and of every abstention against each task's surfacing question. |
| **`merge_runs.py`** | Merges the per-campaign runs into the frozen `results/_merged_results.json` with explicit per-cell provenance, and audits the 5,208-cell grid (no duplicates, no missing/short cells). |
| **`make_apparatus.py`** | Generates the paper's tables and figures (`paper_jss/generated/*.tex`) from the frozen run. |
| **`predictions.md`** | The pre-registered predictions (P1–P7), locked before the definitive runs, with the deviation log. |
| **`results/_merged_results.json`** | **The definitive frozen run**, 5,208 units. Full raw record per unit: per-case outcomes, generated adapter code, raw model output, subset, provenance. Any later question is a re-analysis, not a re-generation. |
| **`results/campaigns/`** | The raw per-campaign files behind the merge (full provenance). |

## Re-run the experiment from scratch (needs the models)

**1. Install [Ollama](https://ollama.com)** and start it (`ollama serve`) — it serves the five local models over an OpenAI-compatible API.

**2. Pull the exact model tags** (a different quantization is a different model; ~27 GB total):

```bash
ollama pull gemma2:2b          # 1.6 GB
ollama pull qwen2.5:7b         # 4.7 GB
ollama pull llama3.1:8b        # 4.9 GB
ollama pull mistral-nemo:12b   # 7.1 GB
ollama pull qwen2.5:14b        # 9.0 GB
```

They fit on a 16 GB machine one at a time; the paper's runs used a 16 GB Apple M4 Mac mini, which caps the open-weight tier near 14B.

**3. The frontier models** run through their providers' OpenAI-compatible endpoints:

```bash
export ANTHROPIC_API_KEY=...     # for claude-opus-4-8
export OPENAI_API_KEY=...        # for gpt-5.6-sol
```

**4. Run** (locals only need no keys — drop the frontier tags from `MODELS`):

```bash
pip install -r requirements.txt
MODELS="gemma2:2b,qwen2.5:7b,llama3.1:8b,mistral-nemo:12b,qwen2.5:14b" \
  N_RUNS=5 ROUNDS=3 OUT=_campaign_locals.json python3 harness.py
python3 merge_runs.py --write     # rebuild the frozen dataset with provenance + grid audit
```

Model outputs are stochastic, so exact per-cell rates vary run to run; the direction and size of the effects are stable, and all headline comparisons carry task-cluster intervals.

## The mechanism, briefly

The failure is not a lack of skill. It is a fact that lives on the far side of the interface and is never obtained. `provided` shows the models *can* build the adapter once handed the fact. `forced` withholds it. `forced_flagged` names the ambiguous field so detection is no longer required — and silent failure still does not drop, which is how we know the failure is commitment across genuinely absent information, not a failure to flag it. `dialogue_answers_only` shows that the naked act of asking, with nothing volunteered, is what recovers most of the ceiling; `mitigation` shows that a blanket gated-commit rule removes silent failure but collapses completion on tasks whose convention was actually available.

## Citation

If you use this artifact, please cite the paper (Journal of Systems and Software, under review) and this archived release. A `CITATION.cff` and the Zenodo DOI are added at release.

## License

[MIT](LICENSE) © 2026 Camilo Chacón Sartori — Apeiron Intelligence.
