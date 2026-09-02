"""
Parse and evaluate an id-tagged Stage 1 adjudication plan.

WHAT THIS IS
The pipeline's stated central simplification was that Stage 1's real output
never entered the system - it used the frozen checklist instead, because mapping
free prose onto requirement ids is the same fuzzy matching that made the keyword
scorer unreliable. The id-tagged mode removes the mapping problem at the source:
the model is shown the requirement library and emits a disposition per id:

    TI1 CHECK
    TI3 ASK_IF device_deployed
    TI4 ASK_IF not (open_hardware_ticket or device_fault_code)
    TI5 ASK

This module parses that plan and evaluates its gates against a case's linked
evidence. The plan for FLAG_TID_INACTIVITY is a real, checked-in model response
(experiments/stage1/responses_idtagged/), produced under the same manual
protocol as the other 15 runs. See the NOTE.md beside it: this mode is NOT
comparable to the blind derivation runs - the model was shown the library, so
scoring it for recall would be meaningless.

TWO HONESTY NOTES
- The model violated the output format: it echoed the helper line "answer this
  from the aggregator's own records, always" under each CHECK, despite "nothing
  after the last line". Even a strict format produced noise; the parser is
  tolerant by necessity, and that observation is itself a data point about why
  id-tagging beats free-prose parsing.
- One plan, one flag, n=1. The other six flags still run on the frozen-checklist
  simplification, which remains documented in ARCHITECTURE section 3.

GATE SAFETY
Conditions may only use the eight whitelisted finding names plus and/or/not and
parentheses. Every token is validated against that whitelist BEFORE evaluation;
anything else is rejected. Only then is the expression evaluated with no
builtins and the findings as the entire namespace.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN_DIR = ROOT / "experiments" / "stage1" / "responses_idtagged"

FINDINGS = [
    "open_hardware_ticket", "device_fault_code", "device_network_registered",
    "device_heartbeat_recent", "device_deployed", "rental_billing_active",
    "other_channel_active", "prior_cases_exist",
]

LINE = re.compile(
    r"^\s*(?P<id>[A-Z]{2}\d+)\s+"
    r"(?P<disp>CHECK|ASK_IF|ASK|SKIP)\s*"
    r"(?:-\s*)?(?P<rest>.*?)\s*$")

_TOKEN = re.compile(r"[a-z_]+|\(|\)")


class PlanError(ValueError):
    pass


def parse_plan(text):
    """Return {req_id: {"disp": ..., "cond": ...}}. Tolerant of stray lines."""
    plan = {}
    for raw in text.splitlines():
        m = LINE.match(raw)
        if not m:
            continue                     # echoed helper text, blank lines
        rid, disp, rest = m.group("id"), m.group("disp"), m.group("rest")
        cond = rest if disp == "ASK_IF" else ""
        if disp == "ASK_IF":
            _validate(cond)
        plan[rid] = {"disp": disp, "cond": cond}
    if not plan:
        raise PlanError("no plan lines found")
    return plan


def _validate(cond):
    """Whitelist every token before the expression is ever evaluated."""
    if not cond.strip():
        raise PlanError("ASK_IF with an empty condition")
    for tok in _TOKEN.findall(cond):
        if tok in ("and", "or", "not", "(", ")"):
            continue
        if tok not in FINDINGS:
            raise PlanError(f"condition uses unknown term {tok!r}")
    leftover = _TOKEN.sub("", cond).strip()
    if leftover:
        raise PlanError(f"condition contains disallowed characters: {leftover!r}")


def evaluate_gate(cond, findings):
    _validate(cond)
    return bool(eval(cond, {"__builtins__": {}}, findings))  # noqa: S307 - tokens whitelisted above


def compute_findings(ev):
    """The eight yes/no findings, from a case's linked evidence (stage2.resolve)."""
    t = ev.get("telemetry") or {}
    a = ev.get("asset") or {}
    x = ev.get("txn") or {}
    tickets = ev.get("tickets") or []
    return {
        "open_hardware_ticket": any(
            k.get("category") == "hardware_fault" and k.get("status") == "OPEN"
            for k in tickets),
        "device_fault_code": bool(t.get("fault_code")),
        "device_network_registered": bool(t.get("network_registered")),
        "device_heartbeat_recent": t.get("last_heartbeat_days_ago", 999) < 7,
        "device_deployed": a.get("status") == "DEPLOYED",
        "rental_billing_active": bool(a.get("rental_billing_active")),
        "other_channel_active": bool(x.get("other_channel_active")),
        "prior_cases_exist": bool(ev.get("priors")),
    }


def load_plans():
    """Plans by flag type. Currently one: the TID flagship, n=1."""
    plans = {}
    if PLAN_DIR.exists():
        for f in PLAN_DIR.glob("FLAG_*.txt"):
            plans[f.stem] = parse_plan(f.read_text(encoding="utf-8"))
    return plans


def asks_for_case(plan, ev, already_satisfied):
    """Which requirements does THIS plan ask the merchant for, on THIS evidence?

    CHECK items are never asked: the internal check itself is the answer,
    whatever it finds. The frozen-checklist pipeline got this wrong - it asked
    merchants for TI1 (ticket history) whenever no ticket existed, treating an
    empty result as an unanswered question instead of as the answer "none".
    """
    findings = compute_findings(ev)
    out = []
    for rid, p in plan.items():
        if rid in already_satisfied:
            continue
        if p["disp"] == "ASK":
            out.append(rid)
        elif p["disp"] == "ASK_IF" and evaluate_gate(p["cond"], findings):
            out.append(rid)
    return out, findings
