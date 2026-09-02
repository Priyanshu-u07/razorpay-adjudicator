# Manual adjudication of scorer misses

The keyword scorer under-counts semantically correct predictions. Rather than add
aliases after seeing responses — which fits a frozen ground truth to the answers
and compounds the bias already logged — every miss is ruled here, with the
candidate text quoted so the ruling can be checked or overturned.

**Two numbers are reported everywhere.** Keyword recall is mechanical and
reproducible. Adjudicated recall is my judgement and is stated as such. Neither
replaces the other.

Adjudicated by: project author (single adjudicator, not blind). 2026-08-30.

Rule applied: **PRESENT** only if the candidate would cause an analyst to perform
the same check. Partial or adjacent coverage counts as ABSENT.

---

## Variant A — baseline

Keyword recall 10/10. No misses to adjudicate.

**Adjudicated recall: 100% (10/10).**

---

## Variant B — proportionate

Keyword recall 4/10. Six misses.

| Item | Candidate text | Ruling |
|---|---|---|
| **TI3** possession | *"Confirmation that the terminal device is still physically with the merchant at the registered address and has not been moved, sold, or given to anyone else."* | **PRESENT** — same check, different words. Aliases were `possession` / `physical custody`; neither appears. |
| **TI6** other terminals | *"Transaction history on any other payment products the merchant uses with the aggregator (UPI QR, payment links, online gateway)"* | **ABSENT** — checks other *products*, not other terminals on the same MID. Adjacent, not equivalent. |
| **TI7** error/decline logs | *"…and whether the device reported faults"* (inside the telemetry item) | **ABSENT** — folded into telemetry as a clause. Does not ask whether transactions were *attempted and failed*, which is the discriminating question. |
| **TI8** SIM/connectivity | — | **ABSENT** — not present in any form. |
| **TI9** asset record | *"Records of the terminal's assigned location and device serial number"* | **ABSENT** — location and serial, not deployment status. Does not answer "returned to stock?". |
| **TI10** rental history | — | **ABSENT** — not present in any form. |

**Adjudicated recall: 50% (5/10).** Keyword 40%.

---

## Variant C — asymmetric

Keyword recall 7/10. Three misses.

| Item | Candidate text | Ruling |
|---|---|---|
| **TI3** possession | *"The physical condition and location of the terminal (working, damaged, lost, or in storage)"* | **PRESENT** — explicitly the device's physical state and whereabouts. Alias `device location` missed *"location of the terminal"* on word order. |
| **TI6** other terminals | *"Activity on all other TIDs, QR codes, UPI handles, or online payment accounts held by the same merchant"* | **PRESENT** — names other TIDs directly. Alias was `any other tid`; text says `all other TIDs`. Missed on one word. |
| **TI9** asset record | *"Asset and inventory records for this terminal, to check if it was already returned, replaced, swapped, or marked for pickup."* | **PRESENT** — asset and inventory status including return-to-stock, which is exactly the discriminating question. Alias `asset record` missed *"Asset and inventory records"*. |

**Adjudicated recall: 100% (10/10).** Keyword 70%.

---

## Summary

```
variant          kw-recall   adj-recall   kw-prec   adj-prec   total   ASK   INTERNAL
baseline            100%        100%        20%       20%        51     22      29
proportionate        40%         50%        13%       17%        30     15      15
asymmetric           70%        100%        44%       63%        16      3      13
```

## What the adjudication does and does not change

It does **not** change the ordering or the conclusion. Variant C matches
baseline completeness with a third of the items and an eighth of the merchant
requests, under either scorer.

It does show the keyword scorer is unreliable at this granularity — three of
three misses on variant C were wording, not substance. Before any of these
numbers are published:

1. An **independent adjudicator** should re-rule these, blind to variant identity.
   A single non-blind adjudicator who also wrote the ground truth and the prompts
   is the weakest link in this measurement.
2. Or an **LLM judge** should rule semantic equivalence, with the disagreement
   rate against this human adjudication reported.

Until one of those happens, adjudicated recall is a judgement, not a measurement.

---

## Variant A — baseline — FLAG_VOLUME_SPIKE

Keyword recall 5/6. One miss.

| Item | Candidate text | Ruling |
|---|---|---|
| **VS5** refund/chargeback rate | *"Chargeback, dispute, and refund history for the account, including any disputes already raised on spike-period transactions."* — marked [INTERNAL] | **PRESENT** — an analyst pulling that history for the spike period has the rate. Aliases wanted `refund rate` / `chargeback rate`; text says `history`. |

**Adjudicated recall: 100% (6/6).** Keyword 83%.

### Scorer quirk noted

Two ground-truth items can match the same prediction, which inflates the
"unmatched predictions" list without affecting recall. Here VS1 and VS2 both
matched prediction 1 (*"…or a marketing campaign"*), so prediction 2 (*"campaign
screenshots"*) appears unmatched despite being a legitimate VS2 match. Recall is
unaffected; the unmatched list is noisier than it looks and should not be read as
"the model said this and it was wrong".

---

## FLAG_MCC_MISMATCH — both variants

Keyword recall 4/6 on both. Four misses, all wording.

### Baseline

| Item | Candidate text | Ruling |
|---|---|---|
| **MC4** business-model change | *"Confirmation from the merchant of whether their business activity has changed since onboarding, and if so, when it changed"* + *"An updated Udyam registration or shop and establishment certificate if the business activity listed on it has changed"* | **PRESENT** — aliases wanted `business model change` / `updated registration`; text says `business activity has changed` / `updated Udyam registration`. |
| **MC6** declared MCC on file | *"The declared MCC 5941 on file and the date it was assigned, plus any earlier MCC the account carried before it"* | **PRESENT** — alias `declared category` against `declared MCC`. |

### Asymmetric

| Item | Candidate text | Ruling |
|---|---|---|
| **MC3** volume split by category | *"…with a rough breakdown of sales by product type"* | **PRESENT** — alias `breakdown by category` against `breakdown of sales by product type`. |
| **MC6** declared MCC on file | *"Review the original onboarding file: the declared business description, product list, website or shop details, and the reason MCC 5941 was assigned"* | **PRESENT** — retrieves the declared category and why the code was assigned. |

**Adjudicated recall: 100% both.** Keyword 67% both.

### Note

The keyword scorer has now missed on wording in 4 of 5 scored flag-variant pairs.
It is systematically pessimistic and its absolute numbers should not be quoted
without the adjudicated figure beside them. The ORDERING between variants has
never once been affected by adjudication — that is the finding that survives.

---

## FLAG_KYC_DISCREPANCY — both variants

Keyword recall 4/6 on both. Same two misses on both, both wording.

| Item | Baseline text | Asymmetric text | Ruling |
|---|---|---|---|
| **KD1** which field mismatched | *"character-by-character comparison of the two names and classify the mismatch type: abbreviation, truncation by bank field length, missing suffix…"* | *"Confirm the flag as raised concerns only the name field…"* | **PRESENT** both — aliases wanted `specific mismatch` / `which field`. |
| **KD2** corrected OVD | *"A fresh bank proof in the company's exact legal name as per the certificate of incorporation"* | *"a bank-issued document that carries the full legal entity name: a bank account statement on bank letterhead, a bank confirmation letter, or a passbook first page"* | **PRESENT** both — aliases wanted `corrected document` / `matching name`. |

**Adjudicated recall: 100% both.** Keyword 67% both.

## FLAG_HIGH_REFUND — asymmetric HR4 ruled ABSENT

| Item | Candidate | Ruling |
|---|---|---|
| **HR4** customer communication logs for disputed orders | Nothing requested. Nearest internal item: *"any customer complaints, issuer retrieval requests, or pre-arbitration notices we already hold, including their text."* | **ABSENT** — the complaint text the aggregator holds is what the customer told their bank. The merchant's own correspondence with that customer is a different record, held only by the merchant, and is frequently what wins a representment. Adjacent, not equivalent. |

This is the only genuine recall failure asymmetric has produced. Ruling it
present would have preserved a clean 100% and hidden the experiment's one real
weakness.

---

## FLAG_THIRD_PARTY_BENEFICIARY — asymmetric fails here

Keyword: baseline 43%, asymmetric 0%. Adjudicated: baseline 86%, asymmetric 43%.

### Present despite scorer miss (both variants)

| Item | Baseline | Asymmetric | Ruling |
|---|---|---|---|
| **TP1** beneficiary identity/relationship | *"Confirmation… that the beneficiary account belongs to the firm itself and not to a partner personally, a group company, an agent, or any other third party."* | *"state in writing who owns that account and why settlements are being directed to it"* + *"Check whether the beneficiary account name matches a partner of the firm"* | **PRESENT** both |
| **TP3** third party onboarded elsewhere | *"whether this same beneficiary account number is linked to any other merchant ID on the platform"* | *"Check all other merchant accounts, terminals and MIDs linked to the same PAN, GST, partners, email, phone or bank account, and see whether the same beneficiary account appears elsewhere in our book"* | **PRESENT** both |
| **TP7** account on file + change history | *"beneficiary account change audit log — when the account was added or edited"* | *"Check the change history on the beneficiary account: when the account was added or last edited"* | **PRESENT** both — alias was `change log`. |

### Genuinely absent from asymmetric

| Item | Ruling |
|---|---|
| **TP2** written agreement governing the arrangement | **ABSENT** — asymmetric asks *who owns the account and why*, which is the explanation, not the agreement. The document itself is never requested. |
| **TP4** invoices showing goods/services actually supplied by the merchant | **ABSENT** — the only invoice reference is *"billing, rental and invoice records"*, which is the aggregator's own billing of the merchant, not the merchant's sales invoices. Behavioural review of ticket size and volume is not documentary proof of supply. |
| **TP5** confirmation no sub-merchant aggregation is occurring | **ABSENT** — never asked. The linked-account check partially addresses it within our own book, but says nothing about aggregation for entities outside it. |
| **TP6** marketplace agreement and seller list | **ABSENT** — both variants. Neither considered the marketplace case. |

### Why this matters more than the number

This is the RBI-named transaction-laundering pattern — settlement to a merchant
on behalf of an unrelated third-party beneficiary (`PROBLEM.md` §3). It is the
highest-stakes flag in the set, and it is the one where asymmetric performs
worst.

The mechanism is rule 2 of the asymmetric prompt: *"if an internal check could
settle the question, the internal check replaces the request."* For operational
flags — a dead terminal, a volume spike, a name spelling — internal records
genuinely do settle the question. For a **relationship** question they do not.
Behavioural data can suggest an arrangement exists; it cannot establish who
contracted with whom. Only documents can.

**The boundary condition: asymmetric is strongest on operational flags and
weakest on contractual ones.** That is a deployable rule, and it is a real limit
on the approach rather than a tuning problem.
