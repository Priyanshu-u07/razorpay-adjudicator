"""
Adversarial tests for the Stage 4 ledger.

A guarantee nothing ever tries to violate is not demonstrated, it is merely
asserted. The pipeline run reports "re-ask rate 0/50" - but that is an absence,
not a proof. These tests attack the ledger directly and show it refusing.

Each test corresponds to a documented failure in the coded corpus
(research/complaints/). Run:  python src/test_ledger.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from pipeline import Ledger, RequirementAlreadySatisfied  # noqa: E402

PASS, FAIL = [], []


def check(name, corpus_ref, fn):
    try:
        fn()
        PASS.append((name, corpus_ref))
        print(f"  PASS  {name}")
    except AssertionError as e:
        FAIL.append((name, corpus_ref, str(e)))
        print(f"  FAIL  {name}: {e}")



def test_cannot_reask_satisfied():
    """R034: 'Razorpay replied with the same irrelevant questions which was
    asked 1 month before.' Must be impossible, not merely discouraged."""
    led = Ledger("T1", "FLAG_TID_INACTIVITY")
    led.satisfy("TI1", "ticket_store")
    try:
        led.request(["TI1", "TI3"])
    except RequirementAlreadySatisfied as e:
        assert "TI1" in str(e), "exception did not name the offending requirement"
        assert "ticket_store" in str(e), "exception did not name the original source"
        return
    raise AssertionError("ledger allowed a satisfied requirement to be re-asked")


def test_reask_blocked_across_rounds():
    """The guarantee must survive a later round, not just the same one."""
    led = Ledger("T2", "FLAG_KYC_DISCREPANCY")
    led.request(["KD2", "KD3"])
    led.satisfy("KD2", "merchant_submission")
    try:
        led.request(["KD2"])
    except RequirementAlreadySatisfied:
        return
    raise AssertionError("ledger allowed a re-ask in a subsequent round")


def test_internal_satisfaction_also_blocks_asking():
    """If Stage 2 found it internally, the merchant must never see it.
    R036: the answer was in our own ticket system; the merchant was asked anyway."""
    led = Ledger("T3", "FLAG_TID_INACTIVITY")
    led.satisfy("TI2", "telemetry_store")
    try:
        led.request(["TI2"])
    except RequirementAlreadySatisfied as e:
        assert "telemetry_store" in str(e)
        return
    raise AssertionError("ledger asked for something already held internally")


def test_satisfy_is_idempotent():
    """Re-satisfying must not corrupt the record or double-log."""
    led = Ledger("T4", "FLAG_VOLUME_SPIKE")
    led.satisfy("VS5", "txn_store")
    led.satisfy("VS5", "some_other_store")
    assert led.satisfied["VS5"] == "txn_store", "second satisfy overwrote the first source"
    assert sum(1 for e in led.events if e["event"] == "satisfied") == 1, "double-logged"


def test_impossible_requirement_routes_to_human():
    """R035: a sub-Rs 20L merchant cannot register for GST. The loop must exit."""
    led = Ledger("T5", "FLAG_KYC_DISCREPANCY")
    led.request(["KD5"])
    led.mark_impossible("KD5", "turnover below Rs 20L - not eligible to register")
    out = led.close("human_review", "impossible requirement")
    assert "KD5" in out["impossible"]
    ev = [e for e in led.events if e["event"] == "impossible"][0]
    assert ev["action"] == "route_to_human", "impossible requirement did not route to a human"


def test_hold_is_always_bounded():
    """Razorpay's own API documents that a hold with no duration is indefinite.
    No outcome here may be unbounded."""
    from pipeline import HOLD_DAYS
    assert all(isinstance(v, int) and v < 365 for v in HOLD_DAYS.values()), \
        "an outcome carries an unbounded or absurd hold"
    assert HOLD_DAYS["released"] == 0, "a released case still holds funds"


def test_every_decision_carries_its_evidence():
    """A cleared requirement must name where it came from - no bare booleans."""
    led = Ledger("T7", "FLAG_CPV_FAILURE")
    led.satisfy("CP6", "cpv_store")
    ev = [e for e in led.events if e["event"] == "satisfied"][0]
    assert ev.get("source"), "a satisfied requirement carries no source"
    assert ev.get("requirement"), "a satisfied event does not name the requirement"


def test_request_records_the_round():
    """Rounds must be countable, since rounds-to-resolution is the headline metric."""
    led = Ledger("T8", "FLAG_HIGH_REFUND")
    assert led.round == 0
    led.request(["HR1"])
    assert led.round == 1
    led.request(["HR3"])
    assert led.round == 2 and led.asked["HR3"] == 2


def test_pipeline_is_blind_to_the_label():
    """The escape rate is only a measurement if the pipeline cannot see the
    answer key. Run the same case with its should_escalate label flipped both
    ways: the outcome must be identical, because the label must not influence
    the decision. An earlier version branched on the label directly, which made
    escape rate 0 by construction rather than by detection."""
    import copy
    import json
    import yaml
    from pipeline import run_case
    store = json.loads((ROOT / "data" / "case_store.json").read_text(encoding="utf-8"))
    flags = {f["id"]: f for f in yaml.safe_load(
        (ROOT / "data" / "flag_requirements.yaml").read_text(encoding="utf-8"))["flags"]}

    checked = 0
    for case in store["cases"]:
        a = copy.deepcopy(case)
        b = copy.deepcopy(case)
        a["should_escalate"] = True
        b["should_escalate"] = False
        ra = run_case(a, store, flags)
        rb = run_case(b, store, flags)
        assert (ra["outcome"], ra["rounds"], ra["reason"]) == \
               (rb["outcome"], rb["rounds"], rb["reason"]), \
            f"{case['case_id']}: outcome changed with the label - the pipeline is reading the answer key"
        checked += 1
    assert checked == 50


def main():
    print("\nSTAGE 4 LEDGER - adversarial tests")
    print("=" * 72)
    print("Each test attacks a guarantee the corpus says the real process breaks.\n")

    check("cannot re-ask a satisfied requirement",        "R034", test_cannot_reask_satisfied)
    check("re-ask blocked across later rounds",           "R034", test_reask_blocked_across_rounds)
    check("internal satisfaction blocks the ask",         "R036", test_internal_satisfaction_also_blocks_asking)
    check("satisfy is idempotent",                        "-",    test_satisfy_is_idempotent)
    check("impossible requirement routes to a human",     "R035", test_impossible_requirement_routes_to_human)
    check("hold duration is always bounded",              "docs", test_hold_is_always_bounded)
    check("every decision carries its evidence",          "R036", test_every_decision_carries_its_evidence)
    check("rounds are counted",                           "-",    test_request_records_the_round)
    check("pipeline is blind to the escalation label",    "-",    test_pipeline_is_blind_to_the_label)

    print("\n" + "=" * 72)
    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for n, ref, e in FAIL:
            print(f"    FAILED {n} [{ref}]: {e}")
        return 1
    print("\n  The re-ask guarantee is enforced by the data structure. Three tests")
    print("  above try to break it and receive an exception. That is the")
    print("  difference between 're-ask rate was 0' and 're-asking is impossible'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
