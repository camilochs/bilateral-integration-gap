<div align="center">

# When LLM Integrators Cannot Ask
### Silent Failure under Split Specifications

Corpus, deterministic oracle, and reproduction harness for the paper.

[![License: MIT](https://img.shields.io/badge/License-MIT-C23E63.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-2E9C8E.svg)](https://www.python.org/)
[![Reproducible](https://img.shields.io/badge/numbers-reproducible%20offline-7E5AA6.svg)](#reproduce-the-paper-in-30-seconds-no-models-needed)

<img src="figures/fig1.png" width="640" alt="Outcomes by condition for capable models on the irreducible gaps.">

</div>

---

## The result in one line

Two LLM agents from different organizations must build an integration, and the fact that makes it correct is held by the other side. **Given that fact, capable models build the integration correctly 89% of the time. Forbidden to ask and forced to commit, the same models ship an adapter that runs clean and returns the wrong value — a _silent failure_ — 69% of the time.** Naming the underspecified field does not lower that rate (76%): the fact is *absent*, not merely unmarked. Capability does not close the gap — asking does, and that behavior does not track model scale.

Deterministic oracle, **no LLM judge**. Six models from 2B to a frontier system (Opus 4.8). Every number in the paper is regenerated from the shipped run by `analyze.py`, with no models and no API keys.

## What this repository is

| File | What it is |
|---|---|
| **`corpus.py`** | The 8 bilateral integration tasks. Each gives System A's context and System B's context (asymmetric partial knowledge) and plants one hidden mismatch — date order, unit scale, timezone, a legacy enum map, a null convention, a boolean encoding, an id shape, list-vs-single cardinality. **Self-validating**: run it and it proves each gap is solvable once surfaced, silent on benign inputs, breaking on the discriminating ones. |
| **`scoring.py`** | The strict outcome definition. A *silent failure* = the adapter ran on every case with **no exception**, passed every benign case, and returned a **wrong value** on a discriminating case. A crash anywhere is loud, never silent. |
| **`harness.py`** | The experiment: five conditions × six models × three runs. `provided` (fact given = capability ceiling), `forced` (commit, cannot ask), `forced_flagged` (the ambiguous field is named, still cannot ask), `nodialogue`, `dialogue`. |
| **`test_scoring.py`** | Unit tests for the scoring, including the edge cases (a wrong value on one case plus a crash on another is *loud*, not silent). |
| **`analyze.py`** | Regenerates the paper's tables and figure numbers straight from `results/harness_results.json`. **No models, no keys.** |
| **`results/harness_results.json`** | The definitive run. Full raw record per unit: per-case outcomes, the generated adapter code, the raw model output, and the decoding temperature — so any later question is a re-analysis, not a re-generation. |

## Reproduce the paper in 30 seconds (no models needed)

```bash
pip install -r requirements.txt      # only needs nothing for these three; openai is for re-running
python3 corpus.py                    # the corpus proves itself well-formed
python3 test_scoring.py              # the scoring passes its unit tests
python3 analyze.py                   # every table/figure number, straight from the shipped run
```

`analyze.py` prints Table 1, the Figure 1 values (89% / 69% / 76% / 53%), and the concentration of silent failure on the irreducible gaps (0.69) versus the inferable controls (0.22).

## Re-run the experiment from scratch (needs the models)

```bash
bash setup.sh                        # installs deps and pulls the six local models via Ollama
export ANTHROPIC_API_KEY=...         # only for the frontier model (Opus 4.8)
MODELS="gemma2:2b,qwen2.5:7b,llama3.1:8b,mistral-nemo:12b,qwen2.5:14b,claude-opus-4-8" \
  N_RUNS=3 ROUNDS=3 python3 harness.py
```

The local models run through [Ollama](https://ollama.com)'s OpenAI-compatible endpoint (`http://localhost:11434/v1`); the frontier model runs through the Anthropic OpenAI-compatible endpoint. Model outputs are stochastic, so exact per-cell rates vary run to run; the direction and size of the Forced-vs-Provided gap are stable.

## The mechanism, briefly

The failure is not a lack of skill. It is a fact that lives on the far side of the interface and is never obtained. `provided` shows the models *can* build the adapter once handed the fact. `forced` withholds it. `forced_flagged` names the ambiguous field so detection is no longer required — and silent failure still does not drop, which is how we know the failure is commitment across genuinely absent information, not a failure to notice.

## License

[MIT](LICENSE) © 2026 Camilo Chacón Sartori — Apeiron Intelligence.
