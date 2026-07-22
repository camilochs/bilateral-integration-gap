# Pre-registered predictions — expanded run (JSS version)

**Written 2026-07-21, BEFORE reading any pilot or definitive results of the expanded corpus.**
The v1 frozen run (8 tasks, 5 arms, `_harness_results.json`) is known and published; everything
below concerns the NEW conditions: subset API (16 API-derived tasks), the two dialogue-mechanism
arms, and the mitigation arm. Pilot data (`_pilot_results.json`) may be used ONLY to fix broken
mechanics (prompt parsing, task validity), documented in the deviation log below — not to revise
these predictions.

## Design locked before the definitive run

- Corpus: 24 tasks (8 subset SYN frozen from v1 + 16 subset API), self-validated by `corpus.py`.
  17 fully-irreducible, 6 fully-inferable controls, 1 mixed (T5).
- Arms (7): provided, nodialogue, forced, forced_flagged, dialogue_answers_only,
  dialogue_volunteers, mitigation.
- Models: 5 local (gemma2:2b, qwen2.5:7b, llama3.1:8b, mistral-nemo:12b, qwen2.5:14b) + frontier
  Opus 4.8; second frontier family (GPT) pending director budget confirmation.
- Runs: 5 per cell local, 3 per cell frontier.
- Capability gates: pooled Provided-success >= 0.8 (model level); per-cell = Provided success on
  every run of that model-task cell.
- Primary comparisons use task-cluster bootstrap CIs (`analyze.py`); we read direction and
  magnitude, not two-digit precision.

## Predictions

- **P1 (RQ1, generality).** On subset-API irreducible tasks, capable models under Forced produce
  silent failure at >= 0.50. The v1 phenomenon (0.69 pooled on subset S) generalizes in direction
  to API-derived tasks; we do not predict which subset is higher.
- **P2 (RQ2, flagging).** Forced-flagged does not reduce silent failure vs Forced on irreducible
  tasks: difference within +-10pp, cluster CI overlapping 0.
- **P3 (RQ2, localization).** Forced silent failure is >= 20pp higher on irreducible tasks than on
  inferable controls (capable models).
- **P4 (RQ3, scale).** Cold ask-rate does not increase monotonically with local model size; the
  frontier model asks at a high rate (>= 0.8), as in v1.
- **P5 (RQ4, mechanism).** Ordering: volunteers >= answers-only > no-dialogue in success on
  irreducible tasks. Interpretation committed in advance: if answers-only is within 10pp of
  volunteers, asking is the load-bearing mechanism; if volunteers exceeds answers-only by > 10pp,
  provider volunteering carries a substantial share of the recovery. Either result is reportable;
  no post-hoc reframing.
- **P6 (RQ5, mitigation).** The gated-commit rule reduces silent failure vs Forced on irreducible
  tasks by >= 20pp, primarily by converting silent commits into explicit abstentions. On inferable
  controls, mitigation success is within 15pp of Forced success (no completion collapse).
  Named risk: models may over-abstain on controls; if so, that is an honest negative result on the
  mitigation's precision and will be reported as such.
- **P7 (exploratory, no prediction).** Subset SYN vs API rate differences are exploratory.

## Deviation log

- 2026-07-21: subset labels renamed S/R -> SYN/API (cosmetic; avoids confusion with the R
  language). The pilot JSON (`_pilot_results.json`), launched before the rename, carries the old
  "R" label; pilot data is mechanics-validation only. No design change.
- 2026-07-21 (mechanics fix, allowed category): adapter-writer max_tokens raised 800 -> 2000 after
  the Opus stage revealed truncation bias: thorough adapters embedding full mapping tables (ISO
  alpha-3, legacy country maps) were cut mid-code and misclassified as garbage (35/384 units,
  concentrated in T23/T14/T15/T20/T13). GPT stage already ran with a 3200 cap (unaffected). Fix:
  affected Opus TASKS re-run in full (all arms x runs) under the new cap; locals campaign killed at
  100/4200 and relaunched clean. No prediction or scoring change.
- 2026-07-21 (task fix, mechanics category): T23_alpha3_country b_context now states the feed
  carries only the four listed markets. Reason: frontier models answered the unbounded version
  with a complete ISO table (~250 entries) that exceeded any reasonable output cap and was
  misclassified as garbage (15/21 Opus units even at the raised cap); the unbounded task measured
  output-length appetite, not the inferable-control construct. T23 cells re-run for ALL models
  under the bounded wording; prior T23 records discarded. No prediction change.
