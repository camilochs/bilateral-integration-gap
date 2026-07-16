"""Outcome scoring for the bilateral-integration harness — separated so it is unit-testable without any
model/network dependency. STRICT silent-failure definition (fixes the confound Codex flagged 2026-07-16):
an outcome is 'silent' ONLY if the adapter ran on EVERY case with no exception anywhere, passed every
benign case, and returned a WRONG value on >=1 discriminating case. A crash on ANY case is loud
(error_failure), never silent.
"""
import re

_QWORDS = re.compile(r"\b(is|are|does|do|can|could|would|should|which|what|when|how|please confirm|clarif)\b", re.I)

def is_balk(raw):
    """No runnable adapter, but the text ASKED (a question) instead of committing to a guess."""
    raw = raw or ""
    return ("?" in raw) and bool(_QWORDS.search(raw))

def outcome(results, raw, task):
    """results: per-case states in {'pass','wrong','error'} aligned to task['oracle'], or None if no
    runnable adapter was produced. Returns mutually-exclusive flags.

      success        = every case passed.
      silent_failure = ran on EVERY case (no 'error' anywhere) AND every benign case passed AND >=1
                       discriminating case returned a WRONG value. Runs clean, looks done, is wrong.
      error_failure  = a runnable adapter that is not success and not silent (it raised on some case,
                       or returned wrong on a benign/common case) — a loud, detectable failure.
      asked / garbage = no runnable adapter: asked for the missing fact vs produced non-code.
    """
    if results is None:
        asked = is_balk(raw)
        return {"invalid": True, "asked": asked, "garbage": not asked,
                "success": False, "silent_failure": False, "error_failure": False}
    disc = [c["discriminating"] for c in task["oracle"]]
    success = all(r == "pass" for r in results)
    has_error = any(r == "error" for r in results)
    benign_pass = all(r == "pass" for r, d in zip(results, disc) if not d)
    wrong_on_disc = any(r == "wrong" for r, d in zip(results, disc) if d)
    silent = bool((not success) and (not has_error) and benign_pass and wrong_on_disc)
    return {"invalid": False, "asked": False, "garbage": False,
            "success": success, "silent_failure": silent,
            "error_failure": bool((not success) and (not silent))}
