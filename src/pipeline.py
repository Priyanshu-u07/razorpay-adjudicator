"""
End-to-end adjudication pipeline: flag in, decision out.

    Stage 1  requirement synthesis   (recorded LLM output - see note below)
    Stage 2  internal satisfaction   (entity resolution across stores)
    Stage 3  consolidated request    (one round, only what is left, with formats)
    Stage 4  stateful verification   (ledger; a satisfied item cannot be re-asked)

ON STAGE 1 - ONE FLAG RUNS ON REAL MODEL OUTPUT, SIX ON A SIMPLIFICATION
Stage 1 is LLM-driven and was evaluated separately in src/stage1_eval.py across
three prompt variants and seven flag types. Those runs are checked in verbatim
under experiments/stage1/.

For FLAG_TID_INACTIVITY the pipeline consumes an actual model plan: an id-tagged
adjudication plan (experiments/stage1/responses_idtagged/, parsed by
src/stage1_plan.py) in which the model was shown the requirement library and
decided each item's disposition - CHECK internally, ASK the merchant, ASK_IF a
gate over named internal findings, or SKIP. Its gates are evaluated per case
against the linked evidence, so e.g. "why is the terminal inactive?" is only
asked when no hardware ticket or fault code already explains it. That run is NOT
comparable to the blind evaluation runs (the model was handed the library - see
the NOTE.md beside it); it demonstrates the production mechanism on the flagship
flag, n=1.

The OTHER SIX flags still take the frozen checklist in
data/flag_requirements.yaml as Stage 1's output. That remains a real
simplification with the same two flattering effects as before: it removes the
model's over-production, and it removes wording variance - the fuzzy-matching
problem the id-tagged format exists to eliminate. Extending the id-tagged mode
to the remaining flags is mechanical (one manual run each) and intentionally
left undone rather than half-done silently.

The pipeline remains deterministic and runs on a clean clone with no key and no
spend: the model output it consumes is a checked-in artefact, not an API call.

WHAT STAGE 4 ENFORCES STRUCTURALLY, NOT BY POLICY
The corpus documents a merchant re-asked the same questions a month after
answering them (R034). Here that is impossible by construction: Ledger.request()
raises if any requirement in the request has already been satisfied. The
guarantee is a property of the data structure, not a rule someone has to
remember.
"""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "case_store.json"
GROUND_TRUTH = ROOT / "data" / "flag_requirements.yaml"

import sys
sys.path.insert(0, str(ROOT / "src"))
from stage2_resolve import (resolve, satisfied_requirements, explains,  # noqa: E402
                            detects_escalation)
from stage1_plan import load_plans, asks_for_case  # noqa: E402

# Id-tagged Stage 1 plans - real model output, parsed by id. Currently one flag
# (FLAG_TID_INACTIVITY); the remaining six use the frozen checklist, and that
# simplification stays documented in ARCHITECTURE section 3.
PLANS = load_plans()

# Hold policy. Bounded always; never the API default of indefinite.
HOLD_DAYS = {"released": 0, "awaiting_merchant": 7, "human_review": 14}


class RequirementAlreadySatisfied(Exception):
    """Raised when something tries to re-ask for evidence already on file."""


class Ledger:
    """Append-only case record. A satisfied requirement can never be re-asked."""

    def __init__(self, case_id, flag_type):
        self.case_id = case_id
        self.flag_type = flag_type
        self.events = []
        self.satisfied = {}       # req_id -> source
        self.asked = {}           # req_id -> round
        self.impossible = {}      # req_id -> reason
        self.round = 0

    def _log(self, kind, **kw):
        self.events.append({"round": self.round, "event": kind, **kw})

    def satisfy(self, req_id, source):
        if req_id in self.satisfied:
            return
        self.satisfied[req_id] = source
        self._log("satisfied", requirement=req_id, source=source)

    def request(self, req_ids):
        """Issue one consolidated request. Refuses to re-ask anything satisfied."""
        clash = [r for r in req_ids if r in self.satisfied]
        if clash:
            raise RequirementAlreadySatisfied(
                f"{self.case_id}: refused to re-ask {clash} - already satisfied by "
                f"{[self.satisfied[c] for c in clash]}")
        self.round += 1
        for r in req_ids:
            self.asked[r] = self.round
        self._log("requested", requirements=list(req_ids), count=len(req_ids))
        return list(req_ids)

    def mark_impossible(self, req_id, reason):
        """R035: a requirement the merchant cannot lawfully satisfy. Never loop."""
        self.impossible[req_id] = reason
        self._log("impossible", requirement=req_id, reason=reason,
                  action="route_to_human")

    def close(self, outcome, reason):
        self._log("closed", outcome=outcome, reason=reason,
                  hold_days=HOLD_DAYS[outcome])
        return {"case_id": self.case_id, "flag_type": self.flag_type,
                "outcome": outcome, "reason": reason,
                "rounds": self.round, "hold_days": HOLD_DAYS[outcome],
                "satisfied_internally": len(self.satisfied),
                "asked_of_merchant": len(self.asked),
                "impossible": list(self.impossible),
                "events": self.events}


def stage3_build_request(flag, ledger, all_reqs):
    """Everything still outstanding, once. Formats attached. Nothing already held."""
    outstanding = [r for r in all_reqs if r["id"] not in ledger.satisfied]
    return outstanding


def simulate_merchant(case, requested):
    """
    SIMULATION ONLY - stands in for a real merchant reply so Stage 4 can be
    exercised. Not a model of merchant behaviour and no finding rests on it.
    Rule: the merchant supplies everything asked, except that a GST-registration
    request to a below-threshold merchant is refused as impossible (the R035
    case from the corpus).
    """
    supplied, impossible = [], []
    for r in requested:
        if "gst" in r["item"].lower() and case.get("below_gst_threshold"):
            impossible.append((r["id"], "turnover below Rs 20L - not eligible to register"))
        else:
            supplied.append(r["id"])
    return supplied, impossible


def run_case(case, store, flags):
    flag = flags[case["flag_type"]]
    led = Ledger(case["case_id"], case["flag_type"])

    # Stage 2
    ev, path = resolve(case, store)
    for rid, src in satisfied_requirements(case["flag_type"], ev).items():
        led.satisfy(rid, src)
    resolved, reason = explains(case["flag_type"], ev)
    led._log("stage2", linkage_hops=len(path), resolved=resolved, reason=reason)

    # Escalation is DETECTED from the linked evidence, checked before anything
    # can release. An earlier version branched on case["should_escalate"] - the
    # ground-truth label - which made the escape rate zero by reading the answer
    # key rather than by competence. The label is now used only in main(), to
    # score these detections after the fact.
    esc, esc_reason = detects_escalation(case["flag_type"], ev)
    if esc:
        led._log("escalate", reason=esc_reason, basis="detection")
        return led.close("human_review",
                         f"escalated on detection, without merchant burden: {esc_reason}")

    if resolved:
        return led.close("released", f"internal evidence resolved the flag: {reason}")

    # Stage 3: one request, only what is outstanding
    plan = PLANS.get(case["flag_type"])
    if plan:
        # Stage 1 = the model's actual plan. CHECK items are never asked - the
        # internal check is the answer, whatever it found. ASK_IF gates are
        # evaluated against this case's linked evidence.
        ask_ids, findings = asks_for_case(plan, ev, led.satisfied)
        led._log("stage1_plan", mode="id_tagged_model_output",
                 findings=findings, asked=ask_ids)
        outstanding = [r for r in flag["requirements"] if r["id"] in ask_ids]
    else:
        led._log("stage1_plan", mode="frozen_checklist_simplification")
        outstanding = stage3_build_request(flag, led, flag["requirements"])
    led.request([r["id"] for r in outstanding])

    # Stage 4: verify, never re-ask
    supplied, impossible = simulate_merchant(case, outstanding)
    for rid in supplied:
        led.satisfy(rid, "merchant_submission")
    for rid, why in impossible:
        led.mark_impossible(rid, why)

    if led.impossible:
        return led.close("human_review",
                         f"{len(led.impossible)} requirement(s) cannot be satisfied by "
                         f"this merchant - routed to a human rather than re-asked")

    # routing by hypothesis class
    # The Stage 1 evaluation measured a hard boundary: an asymmetric evidence
    # policy holds 100% recall on operational flags and drops to 43% on
    # contractual ones, because behavioural data can suggest an arrangement
    # exists but only a document establishes who contracted with whom.
    #
    # A contractual flag that could not be resolved internally therefore does
    # NOT auto-release on receipt of documents. Whether a beneficiary
    # relationship is legitimate is a judgement about a contract, and the
    # measurement says this system is worst exactly there. It goes to a human,
    # with the evidence and the submissions attached.
    if case.get("hypothesis_class") == "contractual":
        led._log("route", hypothesis_class="contractual",
                 reason="contractual hypothesis - documents received but the "
                        "relationship judgement is not automatable")
        return led.close("human_review",
                         "contractual flag: merchant supplied the requested documents "
                         "in one round, but a beneficiary-relationship judgement is "
                         "reserved to an analyst")

    return led.close("released", "all requirements satisfied in one round")


def main():
    data = json.loads(STORE.read_text(encoding="utf-8"))
    flags = {f["id"]: f for f in yaml.safe_load(
        GROUND_TRUTH.read_text(encoding="utf-8"))["flags"]}

    out, reask_violations = [], 0
    for case in data["cases"]:
        try:
            out.append(run_case(case, data, flags))
        except RequirementAlreadySatisfied as e:
            reask_violations += 1
            print(f"  LEDGER BLOCKED A RE-ASK: {e}")

    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "pipeline.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")

    n = len(out)
    zero = [r for r in out if r["rounds"] == 0]
    one = [r for r in out if r["rounds"] == 1]
    more = [r for r in out if r["rounds"] > 1]
    human = [r for r in out if r["outcome"] == "human_review"]
    asks = sum(r["asked_of_merchant"] for r in out)
    full = sum(len(flags[r["flag_type"]]["requirements"]) for r in out)

    print(f"\nPIPELINE - {n} cases\n" + "=" * 72)
    print(f"  resolved with ZERO merchant contact : {len(zero):>3} / {n}   ({len(zero)/n:.0%})")
    print(f"  resolved in ONE round               : {len(one):>3}")
    print(f"  needed more than one round          : {len(more):>3}")
    print(f"  routed to human review              : {len(human):>3}")
    print(f"\n  requirement-items asked of merchants : {asks:>4}")
    print(f"  items an ask-everything policy would : {full:>4}")
    print(f"  reduction                            : {1 - asks/full:.0%}")
    print(f"\n  re-ask rate            : 0/{n}   (structurally enforced)")
    print(f"  ledger violations      : {reask_violations}   (exceptions raised)")
    print(f"  max hold, any case     : {max(r['hold_days'] for r in out)} days   (never unbounded)")

    # escape rate: detections scored against the labels
    # PROBLEM.md names this headline metric #2. Escalation is decided by
    # detects_escalation() on the linked evidence; only HERE is the
    # should_escalate label read, to grade those decisions.
    outcome = {r["case_id"]: r["outcome"] for r in out}
    labelled = [c for c in data["cases"] if c["should_escalate"]]
    escapes = [c["case_id"] for c in labelled if outcome.get(c["case_id"]) == "released"]
    caught = [c["case_id"] for c in labelled if outcome.get(c["case_id"]) == "human_review"]
    false_esc = [r["case_id"] for r in out
                 if "escalated on detection" in r["reason"]
                 and not next(c for c in data["cases"]
                              if c["case_id"] == r["case_id"])["should_escalate"]]

    print(f"\n  ESCAPE RATE            : {len(escapes)}/{len(labelled)}   "
          f"(labelled bad actors that were RELEASED)")
    if escapes:
        print(f"    ESCAPED: {', '.join(escapes)}")
    print(f"  detected + escalated   : {len(caught)}/{len(labelled)}")
    print(f"  false escalations      : {len(false_esc)}   (detection fired on a case not labelled)")
    print(f"  (Escalation is decided by detection rules on the evidence; the label is")
    print(f"   read only here, to score them. On designed data these rules were written")
    print(f"   against the same scenarios they detect - see the warning below.)")

    print(f"\n  by flag type:")
    for fid in flags:
        rs = [r for r in out if r["flag_type"] == fid]
        if rs:
            z = sum(r["rounds"] == 0 for r in rs)
            h = sum(r["outcome"] == "human_review" for r in rs)
            print(f"    {fid:32} {z}/{len(rs)} zero-contact, {h} to human")

    print("\n  " + "!" * 68)
    print("  Stage 2's resolution rules and the case store were written by the")
    print("  same person. These counts show the pipeline behaves as designed on")
    print("  data designed for it. They are NOT evidence about real flag")
    print("  populations. The measured result in this project is the Stage 1")
    print("  evaluation, where the model had not seen the ground truth.")
    print("  " + "!" * 68)
    print(f"\n  written: results/pipeline.json")


if __name__ == "__main__":
    main()
