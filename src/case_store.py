"""
Synthetic case store: the internal records a payment aggregator already holds
when a risk flag fires.

WHY THIS EXISTS
Stage 2 of the pipeline settles a requirement checklist against evidence the
aggregator already has, before asking the merchant for anything. To measure that,
we need an evidence store. No aggregator will hand a student their merchant
records, so this is synthetic - but it is synthetic in a specific shape that
makes Stage 2 a real problem rather than a lookup.

THE SHAPE THAT MATTERS
Records live in SEPARATE STORES UNDER INCONSISTENT KEYS, which is how they live
in a real company:

    kyc_store         keyed by entity_id      (compliance system)
    ticket_store      keyed by ticket_id      (support desk; references the
                                               merchant by phone or email, and
                                               only sometimes by MID)
    asset_store       keyed by device_serial  (logistics; maps serial -> MID)
    telemetry_store   keyed by device_serial  (device platform; no MID at all)
    txn_store         keyed by mid            (payments core)
    settlement_store  keyed by beneficiary account number
    prior_case_store  keyed by case_id

Joining "is there an open ticket about this terminal" to a flag raised on a MID
requires: MID -> asset_store (find serial) -> telemetry_store (find fault) AND
MID -> merchant phone -> ticket_store (find complaint). That is record linkage
across systems with no shared key, which is exactly the gap the R036 case in the
corpus describes - the exculpatory evidence existed, and nothing joined it to the
decision.

DETERMINISM
Seeded. Same seed, same store, every run. No wall-clock, no unseeded randomness.

LIMITATIONS
- Volumes and distributions are plausible, not calibrated against real aggregator
  data. Nobody publishes that.
- Scenario mix is hand-chosen to cover the resolution paths we want to measure,
  not sampled from a real flag population. The proportion of internally-resolvable
  cases here is a design choice, NOT a finding about how often real flags are
  internally resolvable.
"""

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "case_store.json"
SEED = 20260830

FIRST = ["Anand", "Priya", "Rakesh", "Meena", "Suresh", "Kavita", "Imran", "Divya",
         "Vikram", "Farah", "Nitin", "Shalini", "Joseph", "Rhea", "Gopal"]
LAST = ["Sharma", "Iyer", "Reddy", "Banerjee", "Patel", "Khan", "Nair", "Gupta",
        "Desai", "Menon", "Rao", "Fernandes", "Chauhan", "Bose", "Kulkarni"]
CITY = ["Bengaluru", "Pune", "Kochi", "Indore", "Jaipur", "Surat", "Nagpur", "Patna"]


# Scenarios. Each names a resolution path we want the pipeline to have to find.
# `internally_resolvable` is the LABEL: can the flag be cleared from records the
# aggregator already holds, without contacting the merchant?

SCENARIOS = {
    "FLAG_TID_INACTIVITY": [
        {"key": "broken_terminal_open_ticket", "internally_resolvable": True,
         "note": "The R036 case. Terminal dead because our own technician left it "
                 "broken; ticket still open in our own system.",
         "plant": ["open_hardware_ticket", "telemetry_dead", "rental_still_billing"]},
        {"key": "sim_deactivated", "internally_resolvable": True,
         "note": "Connectivity cut; device healthy but offline. Visible in telemetry.",
         "plant": ["telemetry_no_network", "rental_still_billing"]},
        {"key": "merchant_moved_to_upi", "internally_resolvable": True,
         "note": "Card volume stopped, UPI QR on same MID still active.",
         "plant": ["other_channel_active"]},
        {"key": "genuinely_dormant", "internally_resolvable": False,
         "note": "Device healthy, no tickets, no other channel. Only the merchant "
                 "knows whether they are still trading.",
         "plant": ["telemetry_healthy"]},
    ],
    "FLAG_KYC_DISCREPANCY": [
        {"key": "suffix_abbreviation", "internally_resolvable": True,
         "note": "'Pvt Ltd' on the cheque vs 'Private Limited' on the CoI. "
                 "Penny-drop name settles it.",
         "plant": ["penny_drop_matches", "coi_on_file"]},
        {"key": "bank_field_truncation", "internally_resolvable": True,
         "note": "Bank truncated the name at 30 characters.",
         "plant": ["penny_drop_matches", "coi_on_file"]},
        {"key": "prior_name_change", "internally_resolvable": True,
         "note": "Company renamed; MCA record carries both names.",
         "plant": ["mca_name_change", "coi_on_file"]},
        {"key": "different_entity", "internally_resolvable": False,
         "note": "Account genuinely belongs to a director personally. Needs the "
                 "merchant.",
         "plant": ["penny_drop_mismatch"]},
    ],
    "FLAG_VOLUME_SPIKE": [
        {"key": "announced_sale", "internally_resolvable": True,
         "note": "Merchant told support about a festival sale two weeks before.",
         "plant": ["support_ticket_sale_notice", "refund_rate_normal"]},
        {"key": "settlement_backlog", "internally_resolvable": True,
         "note": "Our own capture failure batched four days of transactions into "
                 "one. We caused the spike.",
         "plant": ["platform_incident", "refund_rate_normal"]},
        {"key": "new_integration", "internally_resolvable": True,
         "note": "New API key activated the day before the spike.",
         "plant": ["new_api_key", "refund_rate_normal"]},
        {"key": "card_testing", "internally_resolvable": False,
         "note": "High decline rate, repeated BINs. Escalate, do not clear.",
         "plant": ["high_decline_rate", "bin_concentration"], "escalate": True},
    ],
    "FLAG_MCC_MISMATCH": [
        {"key": "descriptor_set_by_system", "internally_resolvable": True,
         "note": "Descriptor was rewritten by an internal tool, not the merchant.",
         "plant": ["descriptor_changed_by_system"]},
        {"key": "volume_moved_between_mids", "internally_resolvable": True,
         "note": "Merchant has a second MID with the correct MCC.",
         "plant": ["linked_mid_correct_mcc"]},
        {"key": "genuine_category_drift", "internally_resolvable": False,
         "note": "Business really did change. Only the merchant can confirm.",
         "plant": ["ticket_mix_shifted"]},
    ],
    "FLAG_HIGH_REFUND": [
        {"key": "unrecognisable_descriptor", "internally_resolvable": True,
         "note": "Descriptor is a brand name customers do not recognise; disputes "
                 "are all 'I don't recognise this charge'.",
         "plant": ["descriptor_unrecognisable", "reason_codes_unrecognised"]},
        {"key": "platform_duplicate_charges", "internally_resolvable": True,
         "note": "Our double-submit bug generated the duplicate-charge disputes.",
         "plant": ["platform_incident", "reason_codes_duplicate"]},
        {"key": "delivery_failure", "internally_resolvable": False,
         "note": "Item-not-received codes. Needs delivery proof from the merchant.",
         "plant": ["reason_codes_inr"]},
    ],
    "FLAG_THIRD_PARTY_BENEFICIARY": [
        {"key": "formatting_variation", "internally_resolvable": True,
         "note": "'M/s' prefix dropped. Penny-drop settles it.",
         "plant": ["penny_drop_matches"]},
        {"key": "partner_personal_account", "internally_resolvable": False,
         "note": "Account belongs to a partner personally. Contractual question - "
                 "needs documents.",
         "plant": ["beneficiary_is_partner"], "contractual": True},
        {"key": "unrelated_third_party", "internally_resolvable": False,
         "note": "Genuinely unrelated beneficiary. The RBI-named laundering "
                 "pattern. Escalate.",
         "plant": ["beneficiary_unrelated"], "contractual": True, "escalate": True},
    ],
    "FLAG_CPV_FAILURE": [
        {"key": "courier_delivered_here", "internally_resolvable": True,
         "note": "We couriered a QR standee to this exact address and it was "
                 "signed for six weeks ago.",
         "plant": ["courier_delivered", "logins_near_address"]},
        {"key": "agent_wrong_locality", "internally_resolvable": True,
         "note": "Agent's GPS is 4km from the onboarding coordinates.",
         "plant": ["agent_gps_mismatch"]},
        {"key": "informal_addressing", "internally_resolvable": False,
         "note": "Area genuinely has unnumbered addressing. Needs a landmark from "
                 "the merchant.",
         "plant": ["pincode_informal"]},
        {"key": "home_based_no_signage", "internally_resolvable": False,
         "note": "Right building, no nameplate. Needs a photo and a time window.",
         "plant": ["logins_near_address"]},
    ],
}


def build(seed=SEED):
    rng = random.Random(seed)
    store = {"kyc_store": {}, "ticket_store": {}, "asset_store": {},
             "telemetry_store": {}, "txn_store": {}, "settlement_store": {},
             "prior_case_store": {}, "cpv_store": {}}
    cases = []
    n = 0

    for flag_id, scenarios in SCENARIOS.items():
        for scen in scenarios:
            for rep in range(2):          # two cases per scenario
                n += 1
                mid = f"MID{4000 + n}"
                ent = f"ENT{7000 + n}"
                serial = f"DEV{rng.randint(100000, 999999)}"
                phone = f"9{rng.randint(100000000, 999999999)}"
                email = f"{rng.choice(FIRST).lower()}.{rng.choice(LAST).lower()}{n}@example.in"
                acct = f"{rng.randint(10**11, 10**12 - 1)}"
                legal = f"{rng.choice(LAST)} {rng.choice(['Traders','Retail','Systems','Enterprises','Solutions'])} Private Limited"
                plant = set(scen["plant"])

                # kyc_store: keyed by entity_id, NOT by mid
                store["kyc_store"][ent] = {
                    "entity_id": ent,
                    "legal_name": legal,
                    "pan": f"AA{rng.randint(1000,9999)}A",
                    "registered_address": f"{rng.randint(1,99)}, {rng.choice(CITY)}",
                    "coi_on_file": "coi_on_file" in plant,
                    "penny_drop_name": (legal if "penny_drop_matches" in plant
                                        else legal.replace("Private Limited", "Pvt Ltd")
                                        if "bank_field_truncation" in scen["key"]
                                        else f"{rng.choice(FIRST)} {rng.choice(LAST)}"
                                        if "penny_drop_mismatch" in plant
                                        or "beneficiary_is_partner" in plant
                                        or "beneficiary_unrelated" in plant
                                        else legal),
                    "mca_name_change_on_record": "mca_name_change" in plant,
                }

                # ticket_store: references merchant by PHONE, not mid
                if "open_hardware_ticket" in plant:
                    tid_ = f"TKT{rng.randint(10000,99999)}"
                    store["ticket_store"][tid_] = {
                        "ticket_id": tid_, "raised_by_phone": phone, "status": "OPEN",
                        "age_days": rng.randint(100, 140),
                        "subject": "Card machine not working - engineer visited, not fixed",
                        "category": "hardware_fault"}
                if "support_ticket_sale_notice" in plant:
                    tid_ = f"TKT{rng.randint(10000,99999)}"
                    store["ticket_store"][tid_] = {
                        "ticket_id": tid_, "raised_by_email": email, "status": "CLOSED",
                        "age_days": rng.randint(14, 30),
                        "subject": "Planning a festival sale - expect higher volume",
                        "category": "volume_notice"}
                if "ticket_mix_shifted" in plant:
                    tid_ = f"TKT{rng.randint(10000,99999)}"
                    store["ticket_store"][tid_] = {
                        "ticket_id": tid_, "raised_by_email": email, "status": "CLOSED",
                        "age_days": rng.randint(40, 90),
                        "subject": "How do I update the products listed on my account?",
                        "category": "account_change"}

                # asset_store: keyed by SERIAL, maps to mid
                if flag_id in ("FLAG_TID_INACTIVITY", "FLAG_CPV_FAILURE"):
                    store["asset_store"][serial] = {
                        "device_serial": serial, "assigned_mid": mid,
                        "status": "DEPLOYED",
                        "install_address": store["kyc_store"][ent]["registered_address"],
                        "rental_billing_active": "rental_still_billing" in plant,
                        "courier_delivered_signed": "courier_delivered" in plant}

                # telemetry_store: keyed by SERIAL, no mid at all
                if flag_id == "FLAG_TID_INACTIVITY":
                    store["telemetry_store"][serial] = {
                        "device_serial": serial,
                        "last_heartbeat_days_ago": (
                            120 if "telemetry_dead" in plant else
                            95 if "telemetry_no_network" in plant else 1),
                        "fault_code": ("PRINTER_HW_FAULT" if "telemetry_dead" in plant
                                       else "SIM_DEREGISTERED" if "telemetry_no_network" in plant
                                       else None),
                        "network_registered": "telemetry_no_network" not in plant}

                # txn_store: keyed by mid
                store["txn_store"][mid] = {
                    "mid": mid, "entity_id": ent, "months_active": rng.randint(3, 31),
                    "decline_rate": round(rng.uniform(0.35, 0.62), 3) if "high_decline_rate" in plant
                                    else round(rng.uniform(0.02, 0.08), 3),
                    "bin_concentration": round(rng.uniform(0.7, 0.95), 2) if "bin_concentration" in plant
                                         else round(rng.uniform(0.02, 0.15), 2),
                    "refund_rate": round(rng.uniform(0.01, 0.04), 3) if "refund_rate_normal" in plant
                                   else round(rng.uniform(0.01, 0.09), 3),
                    "other_channel_active": "other_channel_active" in plant,
                    "new_api_key_days_before_event": rng.randint(1, 3) if "new_api_key" in plant else None,
                    "platform_incident_in_window": "platform_incident" in plant,
                    "descriptor_last_changed_by": ("SYSTEM_TOOL" if "descriptor_changed_by_system" in plant
                                                   else "MERCHANT"),
                    "descriptor_matches_brand": "descriptor_unrecognisable" not in plant,
                    "linked_mids": ([f"MID{4000+n}B"] if "linked_mid_correct_mcc" in plant else []),
                    "chargeback_reason_top": (
                        "UNRECOGNISED" if "reason_codes_unrecognised" in plant else
                        "DUPLICATE" if "reason_codes_duplicate" in plant else
                        "ITEM_NOT_RECEIVED" if "reason_codes_inr" in plant else None),
                    "login_geo_near_registered_address": "logins_near_address" in plant,
                }

                # settlement_store: keyed by ACCOUNT NUMBER
                store["settlement_store"][acct] = {
                    "account_number": acct, "mid": mid,
                    "beneficiary_name": store["kyc_store"][ent]["penny_drop_name"],
                    "changed_after_onboarding": "beneficiary_unrelated" in plant,
                    "prior_successful_settlements": 0 if "beneficiary_unrelated" in plant
                                                   else rng.randint(3, 40)}

                # cpv_store: keyed by visit_id, references the merchant only
                # by the ADDRESS STRING the agent was sent to. No MID anywhere.
                if flag_id == "FLAG_CPV_FAILURE":
                    vid = f"CPV{rng.randint(10000,99999)}"
                    addr = store["kyc_store"][ent]["registered_address"]
                    store["cpv_store"][vid] = {
                        "visit_id": vid,
                        "address_visited": addr,
                        "agent_gps_km_from_onboarding_coords": (
                            round(rng.uniform(3.5, 6.0), 1) if "agent_gps_mismatch" in plant
                            else round(rng.uniform(0.0, 0.3), 1)),
                        "attempts": 1 if "agent_gps_mismatch" in plant else rng.randint(1, 3),
                        "visit_hour": 14,
                        "outcome": "UNTRACEABLE",
                        "pincode_informal_addressing": "pincode_informal" in plant,
                        "agent_remarks": ("could not locate building number"
                                          if "pincode_informal" in plant
                                          else "no signage at premises"
                                          if "home_based_no_signage" in scen["key"]
                                          else "address not found in this locality")}

                # prior_case_store
                if rng.random() < 0.25:
                    cid = f"CASE{rng.randint(1000,9999)}"
                    store["prior_case_store"][cid] = {
                        "case_id": cid, "mid": mid, "outcome": "CLEARED",
                        "age_days": rng.randint(60, 300),
                        "evidence_submitted": ["address_proof", "sample_invoices"]}

                cases.append({
                    "case_id": f"C{n:03d}", "flag_type": flag_id,
                    "scenario": scen["key"],
                    "mid": mid, "entity_id": ent, "device_serial": serial,
                    "merchant_phone": phone, "merchant_email": email,
                    "beneficiary_account": acct,
                    # LABELS
                    "internally_resolvable": scen["internally_resolvable"],
                    "should_escalate": scen.get("escalate", False),
                    "hypothesis_class": "contractual" if scen.get("contractual") else "operational",
                    # R035 from the corpus: a merchant below the Rs 20L turnover
                    # threshold is not eligible to register for GST, so a GST
                    # request can never be satisfied. Stage 4 must detect this
                    # and route to a human instead of looping forever.
                    "below_gst_threshold": (flag_id == "FLAG_KYC_DISCREPANCY"
                                            and not scen["internally_resolvable"]),
                    "note": scen["note"],
                })

    return {"seed": seed, "cases": cases, **store}


def main():
    data = build()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")

    cases = data["cases"]
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    print(f"  {len(cases)} cases across {len(SCENARIOS)} flag types")
    print(f"  internally resolvable : {sum(c['internally_resolvable'] for c in cases):>3}")
    print(f"  needs the merchant    : {sum(not c['internally_resolvable'] for c in cases):>3}")
    print(f"  should escalate       : {sum(c['should_escalate'] for c in cases):>3}")
    print(f"  contractual class     : {sum(c['hypothesis_class']=='contractual' for c in cases):>3}")
    print("\n  record counts by store (note the differing key types):")
    for k in ("kyc_store", "ticket_store", "asset_store", "telemetry_store",
              "txn_store", "settlement_store", "prior_case_store", "cpv_store"):
        print(f"    {k:20} {len(data[k]):>4}")
    print("\n  NOTE: the resolvable/not-resolvable split is a DESIGN CHOICE for")
    print("  coverage, not a finding about how often real flags are internally")
    print("  resolvable. No such statistic is claimed anywhere.")


if __name__ == "__main__":
    main()
