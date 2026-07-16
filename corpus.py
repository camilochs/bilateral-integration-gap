"""Corpus of BILATERAL integration tasks under asymmetric partial knowledge.

Setup per task: System A and System B belong to different organizations. Agent A is given ONLY
`a_context` (A's output schema + A's semantics/quirks). Agent B is given ONLY `b_context` (B's
expected input schema + B's semantics/quirks). Together they must produce an adapter
`adapt(a_payload) -> b_payload`. Correctness requires facts NEITHER holds alone (a hidden mismatch:
date order, units, enum coding, null-default, bool coding, id shape, cardinality).

The phenomenon: an agent that does NOT surface the mismatch writes the adapter its OWN convention
implies (`naive_adapt`). That adapter passes the BENIGN cases (silent) and breaks on the
DISCRIMINATING cases (the oracle catches it). The `reference_adapt` is what the pair writes AFTER
surfacing the mismatch. `probe_keywords` mark whether a dialogue turn raised the mismatch.

This file is BOTH the corpus and its own well-formedness proof. Run `python3 corpus.py`:
  - reference_adapt must pass EVERY case (task is solvable once the gap is surfaced),
  - naive_adapt must pass every BENIGN case and FAIL >=1 DISCRIMINATING case
    (the hidden mismatch is real, silent on benign inputs, breaking on discriminating ones).
No LLM judge anywhere: the oracle is exact-match on payloads (float tol 1e-9).
"""

# ── task 1: order date — A day-first (DD/MM/YYYY), B expects ISO; B's default reads month-first ──
def ref_dates(a):
    d, m, y = a["order_date"].split("/")
    return {"orderId": a["order_id"], "orderDate": f"{y}-{int(m):02d}-{int(d):02d}"}
def naive_dates(a):
    m, d, y = a["order_date"].split("/")           # B assumes MM/DD/YYYY (its own locale)
    return {"orderId": a["order_id"], "orderDate": f"{y}-{int(m):02d}-{int(d):02d}"}

# ── task 2: money — A integer cents, B float dollars; B assumes the number is already dollars ──
def ref_money(a):
    return {"total": round(a["amount"] / 100.0, 2)}
def naive_money(a):
    return {"total": float(a["amount"])}

# ── task 3: timestamp — A naive local (Europe/Madrid, +02:00 summer), B expects UTC ISO ──
def _shift(hhmm, delta):
    h, m = map(int, hhmm.split(":"))
    return f"{(h + delta) % 24:02d}:{m:02d}"
def ref_tz(a):
    return {"ts": a["day"] + "T" + _shift(a["local_time"], -2) + ":00Z"}
def naive_tz(a):
    return {"ts": a["day"] + "T" + a["local_time"] + ":00Z"}   # B assumes it's already UTC

# ── task 4: status — A integer codes, B expects strings; the map is A's private knowledge AND NON-CANONICAL,
#    so guessing the intuitive 1=active,2=pending,3=closed is WRONG — the only way to be right is to ask A. ──
_STATUS = {1: "closed", 2: "active", 3: "pending"}   # legacy, deliberately non-obvious (the truth)
def ref_status(a):
    return {"state": _STATUS[a["status"]]}
def naive_status(a):
    # the confident CANONICAL guess a model makes when it does not ask — wrong under the legacy mapping
    return {"state": {1: "active", 2: "pending", 3: "closed"}[a["status"]]}

# ── task 5: discount — A: field absent means 0%, present as integer percent; B: always present, fraction 0..1 ──
def ref_discount(a):
    return {"discountPct": a.get("discount", 0) / 100.0}
def naive_discount(a):
    return {"discountPct": float(a["discount"])}    # B assumes present + already a fraction

# ── task 6: active flag — A "Y"/"N", B bool; B coerces the string with bool() ──
def ref_flag(a):
    return {"active": a["active"] == "Y"}
def naive_flag(a):
    return {"active": bool(a["active"])}            # bool("N") is True — the silent one

# ── task 7: customer id — A prefixed string "CUST-00042", B expects bare integer ──
def ref_cid(a):
    return {"customerId": int(a["customer_id"].split("-")[1])}
def naive_cid(a):
    return {"customerId": a["customer_id"]}         # B passes the string through

# ── task 8: cardinality — A returns a single object for one item, a list for many; B always wants a list ──
def ref_card(a):
    it = a["items"]
    return {"items": it if isinstance(it, list) else [it]}
def naive_card(a):
    return {"items": a["items"]}                    # B forwards whatever A sent

TASKS = [
    {
        "id": "T1_order_date",
        "domain": "e-commerce order sync",
        "a_context": ("You expose an Orders API. Each order is {\"order_id\": int, \"order_date\": str}. "
                      "order_date is written day-first as DD/MM/YYYY (e.g. 03/05/2026 is the 3rd of May). "
                      "This is fixed by your legacy billing system and cannot change."),
        "b_context": ("You consume an incoming order feed and must emit {\"orderId\": int, \"orderDate\": str} "
                      "with orderDate in ISO 8601 (YYYY-MM-DD). Dates in your region are conventionally written "
                      "month-first."),
        "mismatches": [{
            "field": "order_date",
            "a_semantics": "DD/MM/YYYY (day first)",
            "b_semantics": "assumes MM/DD/YYYY on the wire, needs ISO out",
            "surfacing_question": "Is order_date day-first or month-first?",
            "probe_keywords": ["day", "month", "dd/mm", "mm/dd", "day-first", "month-first", "date format", "order of"],
            "inferable": False,   # 03/05/2026 is genuinely ambiguous between DD/MM and MM/DD
        }],
        "ref": ref_dates, "naive": naive_dates,
        "oracle": [
            {"a": {"order_id": 1, "order_date": "07/07/2026"}, "discriminating": False},  # day==month: silent pass
            {"a": {"order_id": 2, "order_date": "03/05/2026"}, "discriminating": True},   # silent wrong (both valid)
            {"a": {"order_id": 3, "order_date": "13/05/2026"}, "discriminating": True},   # day>12: invalid under naive
            {"a": {"order_id": 4, "order_date": "25/12/2026"}, "discriminating": True},
        ],
    },
    {
        "id": "T2_money_units",
        "domain": "payments reconciliation",
        "a_context": ("Your Payments API returns {\"amount\": int} — the value is an integer number of CENTS "
                      "(euro cents). You never send fractional values. (The field is named just \"amount\".)"),
        "b_context": ("The ledger you feed expects {\"total\": float} in whole currency units (euros), "
                      "two decimals."),
        "mismatches": [{
            "field": "amount",
            "a_semantics": "integer cents",
            "b_semantics": "float major units; assumes the incoming number is already euros",
            "surfacing_question": "Is amount in cents or in euros?",
            "probe_keywords": ["cent", "cents", "unit", "euros", "minor unit", "divide", "/100", "scale"],
            "inferable": False,   # field name "amount" + a value like 2599 does not reveal cents-vs-euros
        }],
        "ref": ref_money, "naive": naive_money,
        "oracle": [
            {"a": {"amount": 0}, "discriminating": False},     # 0c == 0e: silent pass
            {"a": {"amount": 100}, "discriminating": True},    # 100x off
            {"a": {"amount": 2599}, "discriminating": True},
        ],
    },
    {
        "id": "T3_timezone",
        "domain": "event log federation",
        "a_context": ("Your events carry {\"day\": \"YYYY-MM-DD\", \"local_time\": \"HH:MM\"}. Times are "
                      "wall-clock LOCAL time in Europe/Madrid, which is UTC+02:00 in July. There is no zone "
                      "suffix in your data."),
        "b_context": ("You store events as {\"ts\": ISO-8601 with a Z suffix}, i.e. UTC. You must output a "
                      "single UTC timestamp string like 2026-07-01T12:30:00Z."),
        "mismatches": [{
            "field": "timestamp",
            "a_semantics": "naive local time, UTC+02:00",
            "b_semantics": "UTC; assumes incoming time is already UTC",
            "surfacing_question": "Is local_time UTC or a local wall-clock time with an offset?",
            "probe_keywords": ["timezone", "utc", "offset", "local", "madrid", "+02", "zone", "wall-clock"],
            "inferable": False,   # a bare HH:MM cannot reveal its zone
        }],
        "ref": ref_tz, "naive": naive_tz,
        "oracle": [
            {"a": {"day": "2026-07-01", "local_time": "14:30"}, "discriminating": True},
            {"a": {"day": "2026-07-01", "local_time": "09:00"}, "discriminating": True},
        ],
    },
    {
        "id": "T4_status_enum",
        "domain": "CRM status mapping",
        "a_context": ("Your API returns {\"status\": int} where the integer is a LEGACY internal code with a "
                      "non-obvious meaning: in your system 1 means CLOSED, 2 means ACTIVE, and 3 means PENDING. "
                      "(The numbering does not follow the intuitive order; it is historical.)"),
        "b_context": ("You require {\"state\": str} with one of the exact strings \"active\", \"pending\", "
                      "\"closed\". You do not know any numeric coding."),
        "mismatches": [{
            "field": "status",
            "a_semantics": "legacy int codes 1=closed,2=active,3=pending (non-canonical; intuitive guess is wrong)",
            "b_semantics": "string labels; no knowledge of the codes",
            "surfacing_question": "What does each status integer mean?",
            "probe_keywords": ["code", "mean", "map", "mapping", "1", "2", "3", "enum", "value", "stand for"],
            "inferable": False,   # non-canonical: the intuitive 1=active guess is wrong -> must ask A
        }],
        "ref": ref_status, "naive": naive_status,
        "oracle": [
            {"a": {"status": 1}, "discriminating": True},
            {"a": {"status": 2}, "discriminating": True},
            {"a": {"status": 3}, "discriminating": True},
        ],
    },
    {
        "id": "T5_null_default",
        "domain": "pricing integration",
        "a_context": ("Your quote object is {\"sku\": str, \"discount\": int} but the discount field is "
                      "OPTIONAL: if it is absent, the discount is 0 percent. When present it is an integer "
                      "percentage (e.g. 20 means 20%)."),
        "b_context": ("You require {\"discountPct\": float} ALWAYS present, expressed as a fraction between "
                      "0.0 and 1.0. A missing or null discount is a validation error on your side."),
        "mismatches": [
            {"field": "discount_presence",
             "a_semantics": "absent field means 0%",
             "b_semantics": "requires an explicit value; null is an error",
             "surfacing_question": "What does a missing discount field mean?",
             "probe_keywords": ["absent", "missing", "optional", "null", "default", "present", "not there", "omitted"],
             "inferable": False},   # "absent means 0%" is a private convention, not recoverable from the schema
            {"field": "discount_scale",
             "a_semantics": "integer percent (20 == 20%)",
             "b_semantics": "fraction 0..1 (0.2)",
             "surfacing_question": "Is discount a percent or a fraction?",
             "probe_keywords": ["percent", "percentage", "fraction", "0..1", "scale", "/100", "0.2", "ratio"],
             "inferable": True},    # 20 as a fraction (2000%) is absurd -> a capable model can infer percent
        ],
        "ref": ref_discount, "naive": naive_discount,
        "oracle": [
            {"a": {"sku": "A", "discount": 0}, "discriminating": False},   # 0 present: silent pass
            {"a": {"sku": "B"}, "discriminating": True},                   # absent: naive KeyError
            {"a": {"sku": "C", "discount": 20}, "discriminating": True},   # scale: 20.0 vs 0.2
        ],
    },
    {
        "id": "T6_bool_encoding",
        "domain": "subscription flag sync",
        "a_context": ("Your record uses {\"active\": str} encoded as \"Y\" for yes and \"N\" for no."),
        "b_context": ("You require {\"active\": bool} — a real JSON boolean true/false."),
        "mismatches": [{
            "field": "active",
            "a_semantics": "\"Y\"/\"N\" string flag",
            "b_semantics": "JSON bool; a naive cast bool(str) is truthy for any non-empty string",
            "surfacing_question": "How is the active flag encoded — what are its possible string values?",
            "probe_keywords": ["y/n", "yes", "no", "\"n\"", "boolean", "encode", "truthy", "flag", "values"],
            "inferable": True,    # a Y/N flag is a common pattern; sample "Y" + prior lets a model handle it
        }],
        "ref": ref_flag, "naive": naive_flag,
        "oracle": [
            {"a": {"active": "Y"}, "discriminating": False},   # bool("Y")==True: silent pass
            {"a": {"active": "N"}, "discriminating": True},    # bool("N")==True: silent WRONG
        ],
    },
    {
        "id": "T7_id_shape",
        "domain": "customer master-data merge",
        "a_context": ("Your API returns {\"customer_id\": str} formatted as \"CUST-\" followed by a "
                      "zero-padded integer, e.g. \"CUST-00042\"."),
        "b_context": ("You require {\"customerId\": int} — a bare integer primary key. You reject "
                      "non-integer identifiers."),
        "mismatches": [{
            "field": "customer_id",
            "a_semantics": "prefixed zero-padded string CUST-00042",
            "b_semantics": "bare int 42",
            "surfacing_question": "Is the customer id a plain integer or a prefixed string?",
            "probe_keywords": ["prefix", "cust-", "format", "string", "integer", "padded", "shape", "parse"],
            "inferable": True,    # the sample value "CUST-00042" already reveals the format
        }],
        "ref": ref_cid, "naive": naive_cid,
        "oracle": [
            {"a": {"customer_id": "CUST-00042"}, "discriminating": True},
            {"a": {"customer_id": "CUST-01000"}, "discriminating": True},
        ],
    },
    {
        "id": "T8_cardinality",
        "domain": "catalog item feed",
        "a_context": ("Your feed returns {\"items\": ...} where items is a SINGLE object when there is one "
                      "item, and a LIST of objects when there are several (a common JS-serialization habit)."),
        "b_context": ("You require {\"items\": list} — ALWAYS a JSON array, even for a single element."),
        "mismatches": [{
            "field": "items",
            "a_semantics": "single object OR list depending on count",
            "b_semantics": "always a list",
            "surfacing_question": "Is items always an array, or can it be a single object when there is one item?",
            "probe_keywords": ["array", "list", "single", "one item", "cardinality", "wrap", "always", "object"],
            "inferable": False,   # a list-valued sample hides that a single item arrives unwrapped
        }],
        "ref": ref_card, "naive": naive_card,
        "oracle": [
            {"a": {"items": [{"sku": "X"}, {"sku": "Y"}]}, "discriminating": False},  # already list: silent pass
            {"a": {"items": {"sku": "Z"}}, "discriminating": True},                   # single object: naive wrong
        ],
    },
]


# ─────────────────────────── deterministic oracle ───────────────────────────
def _eq(x, y):
    if isinstance(x, float) or isinstance(y, float):
        try:
            return abs(float(x) - float(y)) < 1e-9
        except (TypeError, ValueError):
            return False
    if isinstance(x, dict) and isinstance(y, dict):
        return x.keys() == y.keys() and all(_eq(x[k], y[k]) for k in x)
    if isinstance(x, list) and isinstance(y, list):
        return len(x) == len(y) and all(_eq(a, b) for a, b in zip(x, y))
    return x == y

def run_case(adapter, expected, a_payload):
    """Return True iff adapter(a_payload) equals expected; a raised exception counts as a fail."""
    try:
        return _eq(adapter(a_payload), expected)
    except Exception:
        return False

def score(adapter, task):
    """Score one adapter on one task: (pass_benign, fail_discriminating, all_pass)."""
    exp = task["ref"]
    benign_ok = True
    discr_fail = 0
    n_discr = 0
    all_ok = True
    for c in task["oracle"]:
        want = exp(c["a"])
        got_ok = run_case(adapter, want, c["a"])
        all_ok &= got_ok
        if c["discriminating"]:
            n_discr += 1
            if not got_ok:
                discr_fail += 1
        else:
            benign_ok &= got_ok
    return benign_ok, discr_fail, n_discr, all_ok


if __name__ == "__main__":
    print(f"{'task':18s} {'cases':>5s} {'discr':>5s}  ref_all  naive_benign  naive_discr_fail  WELL-FORMED")
    ok_all = True
    for t in TASKS:
        rb, rdf, rnd, r_all = score(t["ref"], t)              # reference should pass everything
        nb, ndf, nnd, n_all = score(t["naive"], t)            # naive should pass benign, fail some discr
        well = r_all and nb and (ndf >= 1)
        ok_all &= well
        n_cases = len(t["oracle"])
        print(f"{t['id']:18s} {n_cases:5d} {nnd:5d}  {str(r_all):>7s}  {str(nb):>12s}  "
              f"{str(ndf)+'/'+str(nnd):>16s}  {'OK' if well else 'FAIL <<<'}")
    print("\n" + ("ALL TASKS WELL-FORMED: every gap is solvable once surfaced, silent on benign inputs, "
                  "breaking on discriminating ones." if ok_all else "SOME TASKS MALFORMED — inspect FAIL rows."))
    print(f"tasks={len(TASKS)}  mismatches={sum(len(t['mismatches']) for t in TASKS)}  "
          f"oracle_cases={sum(len(t['oracle']) for t in TASKS)}")
