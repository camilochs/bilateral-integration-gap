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

# ════════════════════════════ subset API: API-derived tasks (T9–T24) ════════════════════════════
# Modeled on DOCUMENTED conventions of real public-API surfaces (no live API calls): the hidden
# fact in each task is a convention that really ships in production interfaces. T9–T20 are
# irreducible (the sample cannot reveal the convention); T21–T24 are inferable controls.

from datetime import date as _date, timedelta as _timedelta

# ── T9: PSP minor units — zero-decimal currencies (Stripe-style): JPY amounts are ALREADY whole yen ──
_ZERO_DECIMAL = {"JPY", "KRW"}
def ref_psp(a):
    amt = a["amount"]
    return {"value": float(amt) if a["currency"] in _ZERO_DECIMAL else round(amt / 100.0, 2),
            "currency": a["currency"]}
def naive_psp(a):
    return {"value": round(a["amount"] / 100.0, 2), "currency": a["currency"]}   # B divides everything

# ── T10: pagination base — A zero-based page index (search-engine style), B one-based ──
def ref_page(a):
    return {"pageNumber": a["page"] + 1}
def naive_page(a):
    return {"pageNumber": a["page"]}                # B assumes both sides count alike

# ── T11: shipment weight — A pounds (US carrier), B kilograms ──
def ref_weight(a):
    return {"kg": round(a["weight"] * 0.45359237, 3)}
def naive_weight(a):
    return {"kg": float(a["weight"])}               # B assumes it's already metric

# ── T12: equity quote — A quotes in GBX (pence sterling, LSE convention), B expects GBP ──
def ref_quote(a):
    return {"gbp": round(a["price"] / 100.0, 4)}
def naive_quote(a):
    return {"gbp": float(a["price"])}               # B reads the number as pounds

# ── T13: inventory — absent stock field means NOT TRACKED (not zero) ──
def ref_stock(a):
    tracked = "stock" in a
    return {"sku": a["sku"], "qty": a.get("stock", 0), "tracked": tracked}
def naive_stock(a):
    return {"sku": a["sku"], "qty": a.get("stock", 0), "tracked": True}   # B treats absent as qty 0, tracked

# ── T14: country codes — A uses legacy codes ("UK"), B requires ISO 3166-1 alpha-2 ("GB") ──
_LEGACY_CC = {"UK": "GB"}
def ref_cc(a):
    return {"country": _LEGACY_CC.get(a["country"], a["country"])}
def naive_cc(a):
    return {"country": a["country"]}                # B forwards the code untouched

# ── T15: price basis — A prices are VAT-INCLUSIVE (EU B2C display), B ledger needs NET at 21% ──
def ref_vat(a):
    return {"net": round(a["price"] / 1.21, 2)}
def naive_vat(a):
    return {"net": float(a["price"])}               # B assumes prices come ex-VAT

# ── T16: phone numbers — A stores national digits (country +34 implied), B requires E.164 ──
def ref_phone(a):
    return {"e164": "+34" + a["phone"]}
def naive_phone(a):
    return {"e164": a["phone"]}                     # B assumes numbers arrive fully qualified

# ── T17: spreadsheet dates — A exports Excel serial dates (epoch 1899-12-30), B assumes Unix-day counts ──
def ref_xldate(a):
    return {"date": (_date(1899, 12, 30) + _timedelta(days=a["serial"])).isoformat()}
def naive_xldate(a):
    return {"date": (_date(1970, 1, 1) + _timedelta(days=a["serial"])).isoformat()}

# ── T18: person names — A sends family-name-first ("Yamada Taro"), B splits assuming given-first ──
def ref_name(a):
    family, given = a["full_name"].split(" ", 1)
    return {"given": given, "family": family}
def naive_name(a):
    given, family = a["full_name"].split(" ", 1)
    return {"given": given, "family": family}

# ── T19: order quantity — A counts PACKS of 12 (wholesale EDI), B needs consumer UNITS ──
def ref_pack(a):
    return {"units": a["quantity"] * 12}
def naive_pack(a):
    return {"units": a["quantity"]}                 # B reads quantity as units

# ── T20: sensor temperature — A reports Fahrenheit (US industrial default), B stores Celsius ──
def ref_temp(a):
    return {"celsius": round((a["temp"] - 32) * 5.0 / 9.0, 2)}
def naive_temp(a):
    return {"celsius": float(a["temp"])}            # B assumes Celsius

# ── T21 (control): epoch milliseconds — 13-digit magnitude reveals the unit ──
def ref_epoch(a):
    return {"epoch_s": a["ts"] // 1000}
def naive_epoch(a):
    return {"epoch_s": a["ts"]}                     # B assumes seconds

# ── T22 (control): "1"/"0" string flag — bool(str) is truthy for "0" ──
def ref_flag10(a):
    return {"enabled": a["enabled"] == "1"}
def naive_flag10(a):
    return {"enabled": bool(a["enabled"])}

# ── T23 (control): ISO alpha-3 country ("ESP") — sample reveals the format; B needs alpha-2 ──
_A3_A2 = {"ESP": "ES", "FRA": "FR", "DEU": "DE", "USA": "US"}
def ref_a3(a):
    return {"country": _A3_A2[a["country"]]}
def naive_a3(a):
    return {"country": a["country"]}

# ── T24 (control): decimal comma ("89,90") — B strips the comma as a thousands separator ──
def ref_dcomma(a):
    return {"price": float(a["price"].replace(",", "."))}
def naive_dcomma(a):
    return {"price": float(a["price"].replace(",", ""))}

TASKS += [
    {
        "id": "T9_psp_minor_units",
        "domain": "payment-gateway settlement",
        "a_context": ("Your payment-gateway charge object is {\"amount\": int, \"currency\": str}. amount is "
                      "expressed in the SMALLEST unit of the currency: cents for EUR/USD, BUT for zero-decimal "
                      "currencies (JPY, KRW) the amount is already the whole-unit value. This follows your "
                      "processor's convention and cannot change."),
        "b_context": ("You feed an accounting system that requires {\"value\": float, \"currency\": str} in "
                      "MAJOR currency units (e.g. euros, yen), decimals allowed."),
        "mismatches": [{
            "field": "amount",
            "a_semantics": "minor units, EXCEPT zero-decimal currencies (JPY/KRW) which are already major units",
            "b_semantics": "major units; assumes a uniform divide-by-100 works for every currency",
            "surfacing_question": "Is amount always in hundredths, or are some currencies zero-decimal?",
            "probe_keywords": ["zero-decimal", "jpy", "yen", "minor unit", "smallest unit", "divide", "/100",
                               "currency-dependent", "exponent"],
            "inferable": False,   # an EUR sample cannot reveal the JPY exception
        }],
        "ref": ref_psp, "naive": naive_psp,
        "oracle": [
            {"a": {"amount": 2599, "currency": "EUR"}, "discriminating": False},  # /100 correct: silent pass
            {"a": {"amount": 5000, "currency": "JPY"}, "discriminating": True},   # 5000 yen, not 50.00
            {"a": {"amount": 120000, "currency": "KRW"}, "discriminating": True},
        ],
    },
    {
        "id": "T10_page_base",
        "domain": "search-index pagination bridge",
        "a_context": ("Your search API paginates with {\"page\": int} and pages are ZERO-BASED: page 0 is the "
                      "first page of results (an offset-style index, as in typical search engines)."),
        "b_context": ("You drive a storefront whose paging widget requires {\"pageNumber\": int} where 1 is "
                      "the first page. Page numbers below 1 are invalid."),
        "mismatches": [{
            "field": "page",
            "a_semantics": "zero-based page index",
            "b_semantics": "one-based page number; assumes both sides count the same way",
            "surfacing_question": "Is page zero-based or one-based?",
            "probe_keywords": ["zero-based", "one-based", "first page", "0 or 1", "index", "offset", "starts at"],
            "inferable": False,   # a sample like page=3 is valid under either convention
        }],
        "ref": ref_page, "naive": naive_page,
        "oracle": [
            # page 3 FIRST: it becomes the sample (no benign case) and is valid under either base;
            # a page-0 sample would leak the zero-based convention and break irreducibility.
            {"a": {"page": 3}, "discriminating": True},
            {"a": {"page": 0}, "discriminating": True},
        ],
    },
    {
        "id": "T11_weight_units",
        "domain": "cross-border shipping",
        "a_context": ("Your carrier API reports parcel {\"weight\": float} in POUNDS (lb), the domestic "
                      "convention of your US logistics stack. The field carries no unit suffix."),
        "b_context": ("Your customs declaration system requires {\"kg\": float} in kilograms, three decimals."),
        "mismatches": [{
            "field": "weight",
            "a_semantics": "pounds (lb)",
            "b_semantics": "kilograms; assumes the number is already metric",
            "surfacing_question": "Is weight in pounds or kilograms?",
            "probe_keywords": ["pound", "lb", "kg", "kilogram", "unit", "metric", "imperial", "convert", "0.45"],
            "inferable": False,   # a bare number like 10.5 does not reveal its unit
        }],
        "ref": ref_weight, "naive": naive_weight,
        "oracle": [
            {"a": {"weight": 0}, "discriminating": False},     # 0 lb == 0 kg: silent pass
            {"a": {"weight": 10.0}, "discriminating": True},
            {"a": {"weight": 2.2}, "discriminating": True},
        ],
    },
    {
        "id": "T12_gbx_pence",
        "domain": "equity market data",
        "a_context": ("Your market-data feed quotes London-listed equities as {\"price\": float} in GBX — "
                      "pence sterling, the LSE convention (a price of 4550 means 45.50 pounds)."),
        "b_context": ("Your portfolio valuation service requires {\"gbp\": float} in POUNDS sterling."),
        "mismatches": [{
            "field": "price",
            "a_semantics": "GBX (pence); 100 GBX = 1 GBP",
            "b_semantics": "pounds; assumes the quote is already GBP",
            "surfacing_question": "Is price quoted in pounds or in pence (GBX)?",
            "probe_keywords": ["gbx", "pence", "penny", "pounds", "gbp", "lse", "quote unit", "/100"],
            "inferable": False,   # 4550 is a plausible pound price for some listings
        }],
        "ref": ref_quote, "naive": naive_quote,
        "oracle": [
            {"a": {"price": 0}, "discriminating": False},
            {"a": {"price": 4550}, "discriminating": True},    # 45.50 GBP, not 4550 GBP
            {"a": {"price": 87.5}, "discriminating": True},
        ],
    },
    {
        "id": "T13_absent_stock",
        "domain": "inventory federation",
        "a_context": ("Your catalog item is {\"sku\": str, \"stock\": int} but stock is OPTIONAL: when the "
                      "field is ABSENT the item is NOT STOCK-TRACKED (made to order) — absence does not mean "
                      "zero. When present (even as 0) the item is tracked."),
        "b_context": ("Your warehouse system requires {\"sku\": str, \"qty\": int, \"tracked\": bool} with all "
                      "fields always present."),
        "mismatches": [{
            "field": "stock",
            "a_semantics": "absent field = not tracked (made to order); present (incl. 0) = tracked",
            "b_semantics": "assumes every item is tracked and a missing quantity is just 0",
            "surfacing_question": "What does a missing stock field mean — zero stock, or not tracked at all?",
            "probe_keywords": ["absent", "missing", "optional", "tracked", "made to order", "null", "omitted",
                               "not present"],
            "inferable": False,   # the sample shows a present stock; absence semantics is A's private fact
        }],
        "ref": ref_stock, "naive": naive_stock,
        "oracle": [
            {"a": {"sku": "A1", "stock": 7}, "discriminating": False},
            {"a": {"sku": "B2", "stock": 0}, "discriminating": False},   # present zero: tracked in both
            {"a": {"sku": "C3"}, "discriminating": True},                # absent: tracked flag silently wrong
        ],
    },
    {
        "id": "T14_legacy_country",
        "domain": "customer-data onboarding",
        "a_context": ("Your CRM exports {\"country\": str} using the company's LEGACY code list, which "
                      "predates ISO adoption: the United Kingdom is stored as \"UK\" (not \"GB\"). Most other "
                      "codes coincide with ISO 3166-1 alpha-2."),
        "b_context": ("Your compliance screening service requires {\"country\": str} as STRICT ISO 3166-1 "
                      "alpha-2; \"UK\" is not a valid ISO code (the United Kingdom is \"GB\")."),
        "mismatches": [{
            "field": "country",
            "a_semantics": "legacy list: United Kingdom = \"UK\"; others match ISO",
            "b_semantics": "strict ISO alpha-2; assumes incoming codes are already ISO",
            "surfacing_question": "Do your country codes follow ISO exactly — how is the United Kingdom coded?",
            "probe_keywords": ["uk", "gb", "iso", "3166", "legacy", "code list", "united kingdom", "mapping"],
            "inferable": False,   # a sample like "US" or "DE" cannot reveal the UK divergence
        }],
        "ref": ref_cc, "naive": naive_cc,
        "oracle": [
            {"a": {"country": "US"}, "discriminating": False},
            {"a": {"country": "DE"}, "discriminating": False},
            {"a": {"country": "UK"}, "discriminating": True},   # forwarded "UK" silently fails ISO screening
        ],
    },
    {
        "id": "T15_vat_inclusive",
        "domain": "retail-to-ledger pricing",
        "a_context": ("Your storefront exposes {\"price\": float} as the consumer-facing price, which by "
                      "EU B2C display rules is VAT-INCLUSIVE (your VAT rate is 21%)."),
        "b_context": ("Your accounting ledger books revenue NET of tax: it requires {\"net\": float}, the "
                      "price excluding VAT, two decimals."),
        "mismatches": [{
            "field": "price",
            "a_semantics": "gross, VAT (21%) included",
            "b_semantics": "assumes the incoming price is already net of tax",
            "surfacing_question": "Is price tax-inclusive or tax-exclusive, and at what VAT rate?",
            "probe_keywords": ["vat", "tax", "inclusive", "exclusive", "gross", "net", "21", "iva"],
            "inferable": False,   # a bare price cannot reveal whether tax is inside
        }],
        "ref": ref_vat, "naive": naive_vat,
        "oracle": [
            {"a": {"price": 0}, "discriminating": False},
            {"a": {"price": 121.0}, "discriminating": True},   # net 100.00, not 121.00
            {"a": {"price": 59.99}, "discriminating": True},
        ],
    },
    {
        "id": "T16_phone_e164",
        "domain": "CRM telephony sync",
        "a_context": ("Your customer records store {\"phone\": str} as NATIONAL digits only (e.g. "
                      "\"612345678\"): every customer is in Spain, so the +34 country prefix is implied and "
                      "never stored."),
        "b_context": ("Your SMS provider requires {\"e164\": str} in full E.164 form with a leading + and "
                      "country code (e.g. \"+34612345678\"). Numbers without a prefix are rejected or "
                      "misrouted."),
        "mismatches": [{
            "field": "phone",
            "a_semantics": "national digits; +34 implied by an out-of-band assumption",
            "b_semantics": "full E.164; assumes numbers arrive fully qualified",
            "surfacing_question": "Do stored numbers include a country prefix — which country are they from?",
            "probe_keywords": ["prefix", "country code", "+34", "e.164", "e164", "international", "spain",
                               "national"],
            "inferable": False,   # nine bare digits do not reveal the country
        }],
        "ref": ref_phone, "naive": naive_phone,
        "oracle": [
            {"a": {"phone": "612345678"}, "discriminating": True},
            {"a": {"phone": "934020100"}, "discriminating": True},
        ],
    },
    {
        "id": "T17_excel_serial",
        "domain": "spreadsheet export ingestion",
        "a_context": ("Your finance team exports records as {\"serial\": int} where serial is the SPREADSHEET "
                      "date serial (Excel convention: day counts anchored so that 46113 is 2026-04-01; the "
                      "effective epoch is 1899-12-30)."),
        "b_context": ("Your data warehouse requires {\"date\": \"YYYY-MM-DD\"}. Your own tooling habitually "
                      "treats integer day counts as days since the Unix epoch (1970-01-01)."),
        "mismatches": [{
            "field": "serial",
            "a_semantics": "Excel date serial, epoch 1899-12-30",
            "b_semantics": "assumes days since Unix epoch 1970-01-01",
            "surfacing_question": "What epoch does the day serial count from?",
            "probe_keywords": ["epoch", "1900", "1899", "excel", "serial", "unix", "1970", "day count",
                               "anchored"],
            "inferable": False,   # a five-digit integer is plausible under either epoch
        }],
        "ref": ref_xldate, "naive": naive_xldate,
        "oracle": [
            {"a": {"serial": 46113}, "discriminating": True},
            {"a": {"serial": 46200}, "discriminating": True},
        ],
    },
    {
        "id": "T18_name_order",
        "domain": "HR directory import",
        "a_context": ("Your employee feed provides {\"full_name\": str} written FAMILY-NAME FIRST, the "
                      "convention of your Japanese HR system: \"Yamada Taro\" is family name Yamada, given "
                      "name Taro."),
        "b_context": ("Your directory requires {\"given\": str, \"family\": str} as separate fields. Names in "
                      "your locale are conventionally written given-name first."),
        "mismatches": [{
            "field": "full_name",
            "a_semantics": "family name first",
            "b_semantics": "splits assuming given name first",
            "surfacing_question": "Is full_name written family-first or given-first?",
            "probe_keywords": ["family", "given", "surname", "first name", "last name", "order", "japanese",
                               "name order"],
            "inferable": False,   # "Yamada Taro" parses under either convention
        }],
        "ref": ref_name, "naive": naive_name,
        "oracle": [
            {"a": {"full_name": "Lee Lee"}, "discriminating": False},     # identical either way: silent pass
            {"a": {"full_name": "Yamada Taro"}, "discriminating": True},
            {"a": {"full_name": "Sato Hanako"}, "discriminating": True},
        ],
    },
    {
        "id": "T19_pack_quantity",
        "domain": "wholesale order relay",
        "a_context": ("Your wholesale EDI feed sends {\"quantity\": int} counted in PACKS: your products ship "
                      "in fixed cases of 12 consumer units, and quantity is the number of cases."),
        "b_context": ("Your marketplace listing system requires {\"units\": int}, the number of individual "
                      "consumer units."),
        "mismatches": [{
            "field": "quantity",
            "a_semantics": "packs (cases of 12 units)",
            "b_semantics": "assumes quantity already counts individual units",
            "surfacing_question": "Does quantity count individual units or packs — and how many units per pack?",
            "probe_keywords": ["pack", "case", "carton", "units per", "12", "each", "inner", "multiplier"],
            "inferable": False,   # quantity 3 is plausible as either packs or units
        }],
        "ref": ref_pack, "naive": naive_pack,
        "oracle": [
            {"a": {"quantity": 0}, "discriminating": False},
            {"a": {"quantity": 3}, "discriminating": True},    # 36 units, not 3
            {"a": {"quantity": 10}, "discriminating": True},
        ],
    },
    {
        "id": "T20_temp_scale",
        "domain": "industrial IoT telemetry",
        "a_context": ("Your plant sensors report {\"temp\": float} in DEGREES FAHRENHEIT, the default of "
                      "your US-sourced monitoring hardware. No unit is transmitted."),
        "b_context": ("Your process-control dashboard stores {\"celsius\": float}, two decimals. Process "
                      "temperatures at this plant range roughly from ambient to a few hundred degrees, so "
                      "readings are plausible on either scale."),
        "mismatches": [{
            "field": "temp",
            "a_semantics": "Fahrenheit",
            "b_semantics": "assumes Celsius",
            "surfacing_question": "Is temp in Fahrenheit or Celsius?",
            "probe_keywords": ["fahrenheit", "celsius", "scale", "degrees", "unit", "convert", "f or c"],
            "inferable": False,   # 160.0 is a plausible industrial reading on either scale
        }],
        "ref": ref_temp, "naive": naive_temp,
        "oracle": [
            {"a": {"temp": -40.0}, "discriminating": False},   # the one point where F == C: silent pass
            {"a": {"temp": 160.0}, "discriminating": True},
            {"a": {"temp": 72.0}, "discriminating": True},
        ],
    },
    {
        "id": "T21_epoch_ms",
        "domain": "telemetry timestamp bridge",
        "a_context": ("Your event bus emits {\"ts\": int} as Unix epoch MILLISECONDS (13 digits for "
                      "present-day times), the JavaScript convention of your stack."),
        "b_context": ("Your metrics store requires {\"epoch_s\": int} in Unix epoch SECONDS."),
        "mismatches": [{
            "field": "ts",
            "a_semantics": "epoch milliseconds",
            "b_semantics": "epoch seconds; a 13-digit value is three orders of magnitude off",
            "surfacing_question": "Is ts in seconds or milliseconds?",
            "probe_keywords": ["millisecond", "ms", "seconds", "13 digits", "epoch", "divide", "1000"],
            "inferable": True,    # 13-digit magnitude reveals milliseconds for any current date
        }],
        "ref": ref_epoch, "naive": naive_epoch,
        "oracle": [
            # no benign case: the sample must be a 13-digit value — that magnitude IS the inferable
            # signal (a ts=0 sample would hide it and silently break the control's rationale).
            {"a": {"ts": 1784544000000}, "discriminating": True},
            {"a": {"ts": 1800000000000}, "discriminating": True},
        ],
    },
    {
        "id": "T22_flag_10",
        "domain": "feature-flag sync",
        "a_context": ("Your config store keeps {\"enabled\": str} as the STRING \"1\" for on and \"0\" for "
                      "off (a key-value store limitation)."),
        "b_context": ("Your runtime requires {\"enabled\": bool} — a real JSON boolean."),
        "mismatches": [{
            "field": "enabled",
            "a_semantics": "string \"1\"/\"0\"",
            "b_semantics": "JSON bool; bool(str) is truthy for the non-empty string \"0\"",
            "surfacing_question": "How is enabled encoded — what are its possible string values?",
            "probe_keywords": ["\"0\"", "\"1\"", "string", "truthy", "boolean", "encode", "values", "cast"],
            "inferable": True,    # a "1"/"0" flag is a stock pattern; the sample reveals the encoding
        }],
        "ref": ref_flag10, "naive": naive_flag10,
        "oracle": [
            {"a": {"enabled": "1"}, "discriminating": False},  # bool("1")==True: silent pass
            {"a": {"enabled": "0"}, "discriminating": True},   # bool("0")==True: silent WRONG
        ],
    },
    {
        "id": "T23_alpha3_country",
        "domain": "trade-document routing",
        "a_context": ("Your customs feed uses {\"country\": str} as ISO 3166-1 ALPHA-3 codes (\"ESP\", "
                      "\"FRA\", \"DEU\", \"USA\")."),
        "b_context": ("Your address validator requires ISO 3166-1 ALPHA-2 (\"ES\", \"FR\", \"DE\", \"US\"). "
                      "The feed carries only these four markets; no other code ever appears."),
        "mismatches": [{
            "field": "country",
            "a_semantics": "ISO alpha-3",
            "b_semantics": "ISO alpha-2; forwarding a three-letter code fails validation",
            "surfacing_question": "Are country codes alpha-2 or alpha-3?",
            "probe_keywords": ["alpha-2", "alpha-3", "three-letter", "two-letter", "iso", "3166", "convert"],
            "inferable": True,    # the sample value "ESP" reveals the format; the ISO table is standard knowledge
        }],
        "ref": ref_a3, "naive": naive_a3,
        "oracle": [
            {"a": {"country": "ESP"}, "discriminating": True},
            {"a": {"country": "DEU"}, "discriminating": True},
        ],
    },
    {
        "id": "T24_decimal_comma",
        "domain": "invoice ingestion",
        "a_context": ("Your invoicing partner exports {\"price\": str} with EUROPEAN decimal notation: a "
                      "COMMA is the decimal separator (\"89,90\" means 89.90). No thousands separators are "
                      "used."),
        "b_context": ("Your parser requires {\"price\": float}. Your own locale uses the comma as a "
                      "THOUSANDS separator, so your habitual cleanup strips commas before parsing."),
        "mismatches": [{
            "field": "price",
            "a_semantics": "decimal comma (\"89,90\" = 89.90)",
            "b_semantics": "strips commas as thousands separators (\"89,90\" -> 8990.0)",
            "surfacing_question": "Is the comma a decimal separator or a thousands separator?",
            "probe_keywords": ["comma", "decimal", "separator", "thousands", "locale", "89,90", "notation"],
            "inferable": True,    # "89,90" with two trailing digits reveals the decimal-comma convention
        }],
        "ref": ref_dcomma, "naive": naive_dcomma,
        "oracle": [
            # no benign case: the sample must SHOW a comma value ("89,90") — the two trailing digits
            # are the inferable signal (a comma-free sample like "120" would hide the convention).
            {"a": {"price": "89,90"}, "discriminating": True},  # 89.90 vs 8990.0: silent wrong
            {"a": {"price": "5,25"}, "discriminating": True},
        ],
    },
]

# subset annotation: SYN = original synthetic eight (frozen), API = API-derived expansion
_SYN_IDS = {"T1_order_date", "T2_money_units", "T3_timezone", "T4_status_enum",
            "T5_null_default", "T6_bool_encoding", "T7_id_shape", "T8_cardinality"}
for _t in TASKS:
    _t["subset"] = "SYN" if _t["id"] in _SYN_IDS else "API"


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
