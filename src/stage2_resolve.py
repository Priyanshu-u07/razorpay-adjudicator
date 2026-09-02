"""
Stage 2: settle the requirement checklist against records the aggregator already
holds, before asking the merchant for anything.

This is the stage the corpus most directly demands. R036: a POS terminal was
deactivated for inactivity while the terminal had been broken for four months,
with an open ticket in the aggregator's own system. The evidence that exonerated
the merchant was already inside the building. Nothing joined it to the decision.

WHY THIS IS RECORD LINKAGE, NOT A LOOKUP
The flag arrives with a MID. The exculpatory ticket is filed under the merchant's
PHONE NUMBER. The fault log is filed under a DEVICE SERIAL. Nothing in the ticket
system knows what a MID is. Joining them requires:

    mid -> txn_store            (direct)
    mid -> entity_id -> kyc     (one hop through the payments record)
    mid -> asset_store          (reverse scan on assigned_mid)
        -> device_serial -> telemetry_store
    mid -> merchant phone/email (from KYC contact) -> ticket_store (reverse scan)
    mid -> settlement_store     (reverse scan on mid)

Every hop is recorded so the resulting decision carries its own audit trail. A
requirement marked satisfied always names the store, the key, and the path taken
to reach it.

WHAT IS MEASURED
For each case: did internal evidence RESOLVE the flag - explain the anomaly well
enough that the merchant need not be contacted at all? That is scored against the
`internally_resolvable` label in the case store.
"""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "case_store.json"
GROUND_TRUTH = ROOT / "data" / "flag_requirements.yaml"


# Which record types can satisfy which requirement ids, per flag.
# Hand-mapped. This is policy, not inference - an aggregator would maintain it.

SATISFIES = {
    "FLAG_TID_INACTIVITY": {
        "ticket":     ["TI1"],
        "telemetry":  ["TI2", "TI7", "TI8"],
        "asset":      ["TI9", "TI10"],
        "txn":        ["TI6"],
    },
    "FLAG_KYC_DISCREPANCY": {
        "kyc":        ["KD1", "KD5", "KD6"],
        "txn":        ["KD6"],
    },
    "FLAG_VOLUME_SPIKE": {
        "txn":        ["VS5"],
        "ticket":     ["VS1", "VS2"],
    },
    "FLAG_MCC_MISMATCH": {
        "txn":        ["MC6"],
        "kyc":        ["MC1", "MC6"],
        "ticket":     ["MC4"],
    },
    "FLAG_HIGH_REFUND": {
        "txn":        ["HR2", "HR6"],
    },
    "FLAG_THIRD_PARTY_BENEFICIARY": {
        "settlement": ["TP3", "TP7"],
        "kyc":        ["TP1"],
    },
    "FLAG_CPV_FAILURE": {
        "asset":      ["CP6"],
        "kyc":        ["CP2", "CP6"],
        "txn":        ["CP3"],
    },
}


# Resolution rules: does the linked evidence actually EXPLAIN the anomaly?
# Satisfying a checklist item is not the same as clearing the flag.

def explains(flag, ev):
    """Return (resolved, reason) - does internal evidence explain why this fired?"""
    t = ev.get("telemetry") or {}
    a = ev.get("asset") or {}
    k = ev.get("kyc") or {}
    x = ev.get("txn") or {}
    s = ev.get("settlement") or {}
    tk = ev.get("tickets") or []

    if flag == "FLAG_TID_INACTIVITY":
        hw = [t_ for t_ in tk if t_.get("category") == "hardware_fault" and t_.get("status") == "OPEN"]
        if hw and t.get("fault_code"):
            return True, (f"terminal fault {t['fault_code']} with OPEN hardware ticket "
                          f"{hw[0]['ticket_id']} unresolved for {hw[0]['age_days']}d - "
                          f"the aggregator caused the inactivity")
        if t.get("network_registered") is False:
            return True, f"device deregistered from network ({t.get('fault_code')}) - not merchant dormancy"
        if x.get("other_channel_active"):
            return True, "merchant still transacting on another channel on the same MID"
        return False, "device healthy, no fault ticket, no other active channel"

    if flag == "FLAG_KYC_DISCREPANCY":
        if k.get("mca_name_change_on_record"):
            return True, "MCA record shows a name change explaining the variant name"
        if k.get("penny_drop_name") and k.get("legal_name"):
            if _same_entity(k["penny_drop_name"], k["legal_name"]):
                return True, (f"penny-drop name '{k['penny_drop_name']}' matches legal name "
                              f"after suffix/format normalisation")
        return False, "penny-drop name differs from legal name beyond formatting"

    if flag == "FLAG_VOLUME_SPIKE":
        if x.get("platform_incident_in_window"):
            return True, "platform capture incident batched transactions - we caused the spike"
        notice = [t_ for t_ in tk if t_.get("category") == "volume_notice"]
        if notice:
            return True, f"merchant notified support of a sale in ticket {notice[0]['ticket_id']}"
        if x.get("new_api_key_days_before_event") is not None:
            return True, f"new integration activated {x['new_api_key_days_before_event']}d before the spike"
        if x.get("decline_rate", 0) > 0.3 or x.get("bin_concentration", 0) > 0.5:
            return False, "high declines / BIN concentration - card testing signature, escalate"
        return False, "no internal explanation for the volume change"

    if flag == "FLAG_MCC_MISMATCH":
        if x.get("descriptor_last_changed_by") == "SYSTEM_TOOL":
            return True, "descriptor was rewritten by an internal tool, not the merchant"
        if x.get("linked_mids"):
            return True, f"merchant holds linked MID {x['linked_mids'][0]} carrying the matching MCC"
        return False, "no internal record explains the category divergence"

    if flag == "FLAG_HIGH_REFUND":
        if x.get("platform_incident_in_window") and x.get("chargeback_reason_top") == "DUPLICATE":
            return True, "platform double-submit incident generated the duplicate-charge disputes"
        if x.get("descriptor_matches_brand") is False and x.get("chargeback_reason_top") == "UNRECOGNISED":
            return True, "descriptor not recognisable as the merchant brand - drives 'unrecognised charge' disputes"
        return False, "dispute reason codes point outward; merchant evidence required"

    if flag == "FLAG_THIRD_PARTY_BENEFICIARY":
        if k.get("penny_drop_name") and k.get("legal_name") and _same_entity(
                k["penny_drop_name"], k["legal_name"]):
            return True, "beneficiary name matches the legal entity after normalisation"
        return False, "beneficiary is not the legal entity - contractual question, documents required"

    if flag == "FLAG_CPV_FAILURE":
        # CPV is an ACTION flag, not an explanation flag. The outstanding thing
        # is a completed verification, not an understanding of why it failed.
        # Internal evidence clears it only when it either (a) supplies positive
        # proof the premises exist and are findable, or (b) shows the agent went
        # to the wrong place, so a corrected re-visit succeeds with no merchant
        # input. Evidence that the merchant is PROBABLY there does not complete
        # a verification - the agent still cannot find the door.
        v = ev.get("cpv") or {}
        if a.get("courier_delivered_signed"):
            return True, ("a device was couriered to this address and signed for - "
                          "premises exist and are findable")
        if v.get("agent_gps_km_from_onboarding_coords", 0) > 2.0:
            return True, (f"agent GPS was {v['agent_gps_km_from_onboarding_coords']}km from the "
                          f"onboarding coordinates - wrong locality, re-route the visit")
        if x.get("login_geo_near_registered_address") and a.get("status") == "DEPLOYED":
            return False, ("logins and a deployed device corroborate the address, but CPV "
                           "needs a completed visit - merchant must supply a landmark or "
                           "time window")
        return False, "no internal record places the merchant at the address"

    return False, "no rule for this flag type"


def detects_escalation(flag, ev):
    """Detection-based escalation. Returns (bool, reason).

    The pipeline must never read the case's `should_escalate` label - that is
    the answer key, and a system that escalates by reading the answer key has an
    escape rate of zero by definition rather than by competence. These rules act
    only on the linked evidence; the label is used afterwards, to SCORE them.
    """
    x = ev.get("txn") or {}
    k = ev.get("kyc") or {}
    s = ev.get("settlement") or {}

    if flag == "FLAG_VOLUME_SPIKE":
        if x.get("decline_rate", 0) > 0.3 or x.get("bin_concentration", 0) > 0.5:
            return True, (f"card-testing signature: decline rate "
                          f"{x.get('decline_rate', 0):.0%}, BIN concentration "
                          f"{x.get('bin_concentration', 0):.0%}")

    if flag == "FLAG_THIRD_PARTY_BENEFICIARY":
        mismatch = (k.get("penny_drop_name") and k.get("legal_name")
                    and not _same_entity(k["penny_drop_name"], k["legal_name"]))
        if (mismatch and s.get("changed_after_onboarding")
                and s.get("prior_successful_settlements", 0) == 0):
            return True, ("beneficiary does not match the legal entity, was changed "
                          "after onboarding, and has no settlement history - the "
                          "RBI-named third-party laundering pattern")

    return False, ""


def _same_entity(a, b):
    """Normalise the differences banks introduce on their own."""
    def norm(s):
        s = s.lower().replace(".", "").replace(",", "")
        for long, short in [("private limited", "pvt ltd"), ("limited", "ltd"),
                            ("m/s ", ""), ("and", "&")]:
            s = s.replace(long, short)
        return " ".join(s.split())
    na, nb = norm(a), norm(b)
    return na == nb or na.startswith(nb[:28]) or nb.startswith(na[:28])


# Entity resolution

def resolve(case, store):
    """Link every record bearing on this case. Returns (evidence, path_log)."""
    mid = case["mid"]
    ev, path = {}, []

    txn = store["txn_store"].get(mid)
    if txn:
        ev["txn"] = txn
        path.append(f"txn_store[mid={mid}]  (direct)")

    ent = (txn or {}).get("entity_id") or case["entity_id"]
    kyc = store["kyc_store"].get(ent)
    if kyc:
        ev["kyc"] = kyc
        path.append(f"txn_store.entity_id -> kyc_store[{ent}]  (1 hop)")

    # asset_store is keyed by serial; find ours by reverse scan on assigned_mid
    for serial, rec in store["asset_store"].items():
        if rec.get("assigned_mid") == mid:
            ev["asset"] = rec
            path.append(f"asset_store reverse-scan on assigned_mid -> serial {serial}")
            tel = store["telemetry_store"].get(serial)
            if tel:
                ev["telemetry"] = tel
                path.append(f"serial {serial} -> telemetry_store  (2 hops, no MID in that store)")
            break

    # ticket_store references the merchant by phone or email, never by MID
    tickets = []
    for tid, rec in store["ticket_store"].items():
        if (rec.get("raised_by_phone") == case["merchant_phone"]
                or rec.get("raised_by_email") == case["merchant_email"]):
            tickets.append(rec)
            key = "phone" if rec.get("raised_by_phone") else "email"
            path.append(f"merchant {key} -> ticket_store reverse-scan -> {tid}")
    if tickets:
        ev["tickets"] = tickets

    for acct, rec in store["settlement_store"].items():
        if rec.get("mid") == mid:
            ev["settlement"] = rec
            path.append(f"settlement_store reverse-scan on mid -> account ...{acct[-4:]}")
            break

    # cpv_store holds no MID at all - the only join is the address string the
    # agent was dispatched to, which we can only get from KYC.
    if kyc:
        for vid, rec in store.get("cpv_store", {}).items():
            if rec.get("address_visited") == kyc.get("registered_address"):
                ev["cpv"] = rec
                path.append(f"kyc.registered_address -> cpv_store reverse-scan -> {vid}  "
                            f"(3 hops, joined on an address string)")
                break

    priors = [r for r in store["prior_case_store"].values() if r.get("mid") == mid]
    if priors:
        ev["priors"] = priors
        path.append(f"prior_case_store reverse-scan on mid -> {len(priors)} case(s)")

    return ev, path


def satisfied_requirements(flag, ev):
    """Which checklist items does the linked evidence cover?"""
    smap = SATISFIES.get(flag, {})
    out = {}
    present = {"kyc": "kyc", "txn": "txn", "asset": "asset",
               "telemetry": "telemetry", "settlement": "settlement",
               "ticket": "tickets"}
    for rec_type, req_ids in smap.items():
        key = present.get(rec_type)
        if key and ev.get(key):
            for rid in req_ids:
                out[rid] = f"{rec_type}_store"
    return out


def run():
    data = json.loads(STORE.read_text(encoding="utf-8"))
    flags = {f["id"]: f for f in yaml.safe_load(
        GROUND_TRUTH.read_text(encoding="utf-8"))["flags"]}

    results, tp, fp, tn, fn = [], 0, 0, 0, 0
    for case in data["cases"]:
        ev, path = resolve(case, data)
        sat = satisfied_requirements(case["flag_type"], ev)
        resolved, reason = explains(case["flag_type"], ev)
        label = case["internally_resolvable"]

        if resolved and label:      tp += 1
        elif resolved and not label: fp += 1
        elif not resolved and label: fn += 1
        else:                        tn += 1

        n_req = len(flags[case["flag_type"]]["requirements"])
        results.append({**{k: case[k] for k in
                           ("case_id", "flag_type", "scenario", "internally_resolvable",
                            "should_escalate", "hypothesis_class")},
                        "resolved_internally": resolved, "reason": reason,
                        "requirements_satisfied": len(sat), "requirements_total": n_req,
                        "linkage_hops": len(path), "linkage_path": path})

    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "stage2.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")

    n = len(results)
    print(f"\nSTAGE 2 - internal evidence resolution over {n} cases\n" + "=" * 72)
    print(f"  resolved with ZERO merchant contact : {tp + fp:>3} / {n}")
    print(f"  correctly resolved   (TP)           : {tp:>3}")
    print(f"  wrongly resolved     (FP)           : {fp:>3}   <- cleared something it should not have")
    print(f"  correctly escalated  (TN)           : {tn:>3}")
    print(f"  missed a resolution  (FN)           : {fn:>3}   <- asked the merchant unnecessarily")
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    print(f"\n  precision {prec:.0%}   recall {rec:.0%}")
    print(f"  FALSE POSITIVES ARE THE DANGEROUS DIRECTION: clearing a flag that")
    print(f"  needed the merchant. FP = {fp}.")

    print("\n  " + "!" * 68)
    print("  READ THIS BEFORE QUOTING THE ACCURACY ABOVE.")
    print()
    print("  I wrote the scenario plants AND the resolution rules. A high score")
    print("  here means my rules correctly read my own plants. It is close to")
    print("  tautological and is NOT evidence that internal resolution works on")
    print("  real merchant data.")
    print()
    print("  What this run actually demonstrates:")
    print("    1. the linkage traverses stores that share no common key")
    print("    2. the decision for every case carries the path it was reached by")
    print("    3. one conceptual error was caught by running it (see LOG.md,")
    print("       CPV action-flag vs explanation-flag)")
    print()
    print("  Treat precision/recall here as an IMPLEMENTATION CORRECTNESS CHECK,")
    print("  not a result. The result that matters is in the Stage 1 evaluation,")
    print("  where the model had not seen the ground truth.")
    print("  " + "!" * 68)

    avg = sum(r["linkage_hops"] for r in results) / n
    print(f"\n  mean linkage steps per case: {avg:.1f}")
    print(f"  (a lookup would be 1; these records share no common key)")

    print(f"\n  by flag type:")
    for fid in flags:
        rs = [r for r in results if r["flag_type"] == fid]
        if rs:
            ok = sum(r["resolved_internally"] == r["internally_resolvable"] for r in rs)
            z = sum(r["resolved_internally"] for r in rs)
            print(f"    {fid:32} {ok}/{len(rs)} correct, {z} need no merchant contact")

    print(f"\n  written: results/stage2.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
