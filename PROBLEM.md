# The Problem

**Razorpay Buildathon 2026 — Track 02, AI Risk Manager**

---

## The claim, in one paragraph

Payment aggregators are legally responsible for the merchants they onboard. In September 2025 the RBI made that responsibility explicit and continuous: PAs must monitor merchants' *subsequent* transactions against their declared business profile, allot the correct MCC, and scrutinise settlements made to a merchant on behalf of an unrelated third party. Razorpay's public API models merchant risk as a **binary flag** — an account is `activated` or `suspended`, with no score, no contributing signals, and no appeal handle — and a settlement hold placed with no duration is, by their own documentation, **indefinite**. A binary control fails in both directions at once: rings run undetected until law enforcement arrives, and legitimate merchants are switched off with no stated reason and no bounded remedy.

But the merchant-visible failure is narrower — and far more tractable — than "there is no risk score." Primary research coding 37 merchant and payer reviews (§7) finds that a review process plainly *does* exist behind the flag. **It simply has no memory.** Requirements arrive one at a time at 48–72 hour intervals; requirements already satisfied are re-asked weeks later; some requirements cannot be satisfied at all; and funds are held for the entire duration. The harm is not the flag. The harm is `N rounds × 48h`, with `N` unbounded. This project builds the adjudication layer that is missing: an agent that derives the complete evidence requirement for a flag **once**, settles it against what the aggregator already holds, asks the merchant for the genuine remainder in a **single** round, and never re-asks a satisfied item.

---

## 1. Why this matters to Razorpay now

**Margins are compressing.** FY25 revenue grew 65% to ₹3,783 crore, but gross profit grew only 41% to ₹1,277 crore [1]. Implied gross margin fell roughly 570 basis points in one year. The cause is structural: UPI is now over 60% of volume flowing through payment aggregators, at a take rate of about 0.3–0.4 basis points [2].

**The listing is close.** Razorpay filed a confidential DRHP with SEBI on 12 June 2026, targeting a ₹5,000–6,000 crore issue at a $5–6B valuation [3] — below the $7.5B raised in 2021.

**And the front door just got much faster.** On 12 March 2026 Razorpay announced the **Razorpay Agentic Platform** [4]. On onboarding, in their own words:

> *"By providing just your PAN, the platform validates your identity against government infrastructure and CKYC records in real-time. There are no dropdowns or manual selections; **if you drop in your website URL, the system auto-identifies your business category**."*

They frame the trajectory explicitly: days in 2010, hours in 2017, **minutes now**. The platform is currently early-access.

That is a genuine conversion win. It is also, unavoidably, a risk-surface expansion. Investigators attribute payments banks' outsized share of suspicious VPA activity — roughly 41% — directly to *fast, low-friction onboarding* [5].

**And note what the launch does not cover.** The Agentic Platform spans onboarding, integration, and an agentic dashboard for reconciliation, revenue recovery and "autonomous guardrails" — plus an **Agent Studio** hosting purpose-built agents for *"advanced revenue recovery, dispute management, and collection strategies"* [4]. Merchant risk monitoring appears nowhere in it. Razorpay has now shipped AI across effectively the whole merchant lifecycle **except** the control that decides whether a merchant should be there at all.

**The compensating control for a faster front door is stronger continuous monitoring behind it.** That control is not present in the public API surface.

---

## 2. The evidence: a binary flag, and a review loop with no memory

Razorpay's Partner sub-merchant **Account entity** [6] exposes:

`id`, `type`, `status`, `email`, `phone`, `legal_business_name`, `customer_facing_business_name`, `business_type`, `reference_id`, `profile`, `legal_info`, `brand`, `notes`, `contact_name`, `contact_info`, `apps`, `activated_at`, `live`, `hold_funds`, `created_at`

**There is no risk score, no risk band, no contributing-signal field, and no appeal or review handle.** The only risk expression is the `status` enum:

| status | meaning (per docs) |
|---|---|
| `created` | account created |
| `activated` | KYC approved |
| `needs_clarification` | clarifications requested on KYC |
| `under_review` | all KYC requirements submitted |
| `suspended` | **"the merchant account is identified as potentially fraudulent"** |
| `rejected` | KYC details rejected during manual review |

And on the action side, Razorpay's own settlement-hold documentation states that a hold placed **without a duration value is indefinite** [7].

So the data model permits: *terminal, binary, unexplained, unbounded.*

### And behind the flag, the loop

The schema gap is the static half of the problem. The dynamic half is what merchants actually experience, and §7 documents it directly. Four independent merchants describe the same mechanism:

- **Requirements are issued serially, not as a set.** *"Instead of collecting all required information at once, they send queries one at a time — each followed by a 48-72 hour delay"* (May 2025).
- **The goalposts move after full submission.** *"Even after submitting every document, new and unexpected demands arise, such as a board resolution in a specific format"* (May 2025); *"even after providing everything, they had the audacity to ask for social media links"* — from a B2B server reseller that has none (Oct 2024).
- **The process does not remember what it already asked.** *"Razorpay replied with the same irrelevant questions which was asked 1 month before"* (Feb 2024).
- **Some requirements cannot be satisfied at all.** Funds withheld pending GST registration from a merchant below the ₹20 lakh turnover threshold, and therefore legitimately unregistered (May 2024).

None of this requires the original flag to have been wrong. It requires only that the process resolving it holds no state.

Razorpay's actual risk product, **Thirdwatch**, is buyer-side — RTO and COD fraud prediction — and has been merged into Magic Checkout [8]. It protects merchants from bad buyers. It does not address bad merchants.

> **Scope of this claim.** This describes the *public* API surface and documentation only. Razorpay almost certainly operates internal merchant risk systems; they would be non-compliant otherwise. The claim here is that no graded, explainable merchant risk signal is *exposed* to platform partners, and that the published data model has no field in which to express one.

---

## 3. Why now: the regulator described the threat model

The **RBI (Regulation of Payment Aggregators) Directions, 2025**, issued 15 September 2025, supersede the 2020–21 guidelines. Three changes are directly on point [9]:

1. **Continuous post-onboarding monitoring.** PAs are *"now also required to monitor the subsequent transactions undertaken by the merchants to ensure that the transactions are in line with"* their business profile. A category detected once at signup does not satisfy an ongoing obligation.

2. **Correct MCC allotment is the PA's job.** The Directions *"explicitly stipulate that the PA is required to facilitate allotment of appropriate MCC and merchant ID / terminal ID to the merchants."* Declared-versus-observed MCC drift is therefore the PA's liability, not the merchant's.

3. **Third-party-beneficiary flows must be scrutinised.** PAs *"may need to relook certain flows involving settlement of payments to a particular merchant for or on behalf of an unrelated third-party beneficiary."*

That third item is the textbook definition of **transaction laundering** — a merchant running someone else's payments through its own approved account [10]. The regulator wrote the threat model into the rules.

Also confirmed in the 2025 Directions: mandatory **Contact Point Verification** of merchants, explicit **FIU-IND registration** and PMLA reporting-entity status for non-bank PAs, and a required **grievance redressal officer**.

---

## 4. The cost of getting it wrong, in both directions

### False negatives

**Card network penalties.** Visa's **VIRP** (Integrity Risk Program) and Mastercard's **BRAM** (Business Risk Assessment and Mitigation) fine *acquirers* for processing illegal or brand-damaging transactions. Fines run **as high as six figures per transaction**, and **transaction laundering is a frequent BRAM violation** [11]. Critically, acquirers running a merchant monitoring solution qualify for **fine mitigation of 75–100%** — the networks explicitly price the control.

**Law enforcement.** The ED froze ₹46.67 crore across four payment gateway accounts including Razorpay's in the Chinese loan-app case, on the basis of 18 FIRs, and subsequently filed a chargesheet [12].

**Regulatory action.** In December 2022 the RBI ordered Razorpay to stop onboarding new merchants pending a compliance audit. Before the embargo Razorpay was signing up roughly **60,000 merchants per month** [13]. *(Causal note: the embargo concerned PA licence compliance broadly, of which merchant due diligence is one component — not merchant-fraud detection specifically.)*

**Ecosystem scale.** I4C has flagged over **2.47 million Layer-1 mule accounts**, with **524,121 in March 2026 alone** [14]. RBI has deployed *MuleHunter* AI across 26 banks — but that is bank-side. The aggregator layer has no equivalent.

### False positives

A binary flag with an unbounded hold has, by construction, **unbounded false-positive cost.** The merchant-visible form of that is documented:

> *"every day new doubts are being raised and my payment is being blocked"*
> — merchant, six-figure sum held, all requested documents submitted (June 2025) [15]

A direct competitor states the causal chain publicly. Cashfree, describing collusion fraud by merchants, notes it results in *"losses for aggregators **and triggering stricter checks for legitimate merchants**"* [16]. Merchant fraud produces the loss *and* the over-tightening that punishes honest businesses.

**We cannot size Razorpay's merchant-fraud losses.** No Indian PA publishes such a figure and we will not estimate one. The case here rests on (a) an unconditional regulatory obligation, (b) fat-tailed downside evidenced by the embargo and the chargesheet, and (c) a priced card-network penalty regime.

---

## 5. What the rest of the industry does

Global acquirers sit on a clear generational ladder:

| Gen | Approach | Who |
|---|---|---|
| 1 | **Shared blacklists** — MATCH (Mastercard) and VMSS (Visa) terminated-merchant databases; acquirers *must* query before onboarding. Reactive: only catches merchants someone already terminated. | Industry-wide, mandatory [17] |
| 2 | **Manual underwriting + periodic re-underwriting** — KYB documents, human review on a schedule. | Worldpay, Payrix, most acquirers |
| 3 | **Specialist monitoring vendors** — continuous web-content and digital-presence monitoring. LegitScript is a registered Mastercard Merchant Monitoring Program provider running checks on all merchants **at least daily**; SafetyKit runs AI agents over hundreds of pages per merchant to catch merchants that *"start processing for undisclosed businesses, or drift into prohibited categories."* | LegitScript, G2 Risk Solutions, SafetyKit [18] |
| 4 | **In-house continuous graded scoring** — Stripe's Radar for Platforms (27 May 2026) ships 0–100 fraud scores per business, a Fraudulent Website signal, a Fraudulent Merchant signal, a Merchant Delinquency Risk signal, **AI explanations of why an account was flagged**, and graduated responses: raise review, pause payouts, set reserves, request identity verification. Capital One runs graph networks over entity relationships in a combined real-time fraud + AML platform. Adyen flags with ML and routes to **human analysts** for AML review. | Stripe, Capital One, Adyen, PayPal [19] |

**Razorpay's public surface sits at Gen 1–2. No Indian payment aggregator exposes Gen 4.**

### The whole ladder is about detection. None of it is about what happens next.

Merchant-monitoring practice describes detection in three parts [20]:

> *"The laundering only becomes visible when transaction patterns are correlated against the merchant's **actual web presence, product catalog** and traffic behavior. At the transaction level, the system examines **volume patterns, MCC-to-processing-volume alignment, velocity anomalies**, and **cross-merchant behavior** that might indicate unauthorized aggregation."*

That is a rich literature on **finding** suspect merchants. What none of these vendors describe — and what Stripe's graduated responses gesture at without specifying — is the **evidence loop that resolves a flag once raised**: who decides what would clear it, whether the requirement set is issued once or discovered incrementally, and what stops a satisfied requirement being re-asked.

> **We are not competing on detection.** LegitScript, G2 Risk Solutions and SafetyKit sell merchant monitoring; Stripe ships graded scores with AI explanations; Capital One has run graph-based entity analysis for years. This project takes detection as given and addresses the stage after it. The contribution is a stateful, evidence-complete adjudication loop, measured on rounds-to-resolution and days-of-held-funds rather than on detection accuracy, in the Indian PA regulatory context.

---

## 6. What this project builds

**An evidence-complete review agent: resolve a risk flag in one round instead of N.**

Not a better detector. Razorpay operates internal merchant risk systems and this project does not claim to out-detect them. The claim is narrower and better evidenced: the **adjudication** that follows a flag holds no state, and that is where the merchant harm is generated. A correct flag and a stateless review loop still bankrupt an honest business.

### The four stages

| Stage | What it does | Method |
|---|---|---|
| **1 · Requirement synthesis** | Given the flag reason and merchant type, derive the evidence set that would clear it — once, up front, with format specifications attached. Must be **complete and proportionate**: everything needed to resolve *this* flag, and nothing that merely re-verifies the merchant in general. | LLM. Genuine inference from a fuzzy risk reason to a closed checklist. |
| **2 · Internal satisfaction** | Before asking the merchant for anything, settle the checklist against what the aggregator **already holds**: KYC on file, submissions from this case *and prior cases*, transaction history, open support tickets. Strike off everything already satisfied. | **Entity resolution.** Linking one requirement to records scattered across separate stores under inconsistent keys is a record-linkage problem, not a lookup. No LLM in the matching itself. |
| **3 · Single consolidated request** | Ask for the genuine remainder. Once. With formats. Proportionate to the flag — a broken terminal is not an occasion to re-run KYC. | Templated. |
| **4 · Stateful verification** | Verify submissions against the requirement set. A satisfied item can never be re-asked. Unsatisfied items return a specific reason. Hold duration is bounded and scales with residual risk. | Deterministic ledger + LLM for document adequacy. |

**Stage 1 is the mechanism; Stage 2 bounds the ask.** An earlier draft of this document called Stage 2 the contribution. Two measurements corrected that, and both are logged in [`LOG.md`](LOG.md):

- Auditing the ground truth put **Stage 2's ceiling at 37%** of 47 requirements — the majority genuinely must come from the merchant. Internal satisfaction shrinks the ask; it does not collapse the rounds.
- Stage 1 run 1 (30 Aug 2026, `FLAG_TID_INACTIVITY`, n=1, pilot) returned **100% recall and 12% precision** — 51 requirements for a broken card terminal, 22 of them demanded from the merchant. Completeness is achievable. **Proportionality is the open problem**, and asking for everything at once is a wall rather than a corridor.

So the round collapse comes from Stage 1 asking once, and the burden reduction comes from Stage 2 — with the caveat that a complete-but-disproportionate single round reproduces the harm in a different shape.

The evidence still points hardest at Stage 2 for one flag class in particular. The strongest single row in the corpus is a POS merchant whose terminal was deactivated on an inactivity signal — *"the TID has been deactivated for no transactions since more than 3 months"* — while the reason for that inactivity was a machine that had been non-functional for four months, with a support ticket their own technician never closed sitting in Razorpay's own system. The exculpatory evidence was already inside the building. Nothing joined it to the decision. That flag class has the highest Stage 2 headroom of the seven, at 70% — though that figure is partly a consequence of expanding this flag's requirement set after run 1, and should be read alongside the bias warning in `data/flag_requirements.yaml`.

### Non-negotiable design constraints

- **The system never freezes anyone.** Its only powers are to *clear faster* or to *escalate to a human*. Bounded action space, always.
- **Hold duration scales with residual risk.** Never a constant, never unbounded.
- **A satisfied requirement is permanently satisfied.** Enforced structurally, not by policy.
- **Impossible requirements are detected, not looped.** A sub-₹20 lakh merchant cannot produce a GST registration; the system must route that to a human rather than re-ask forever.
- **Every decision ships its evidence** — the requirement set, what satisfied each item, and the source it came from.
- **Defense-only.** The system triages and clears. No offense-capable component. The case simulator emits abstract requirement/latency distributions calibrated on public review text; it encodes no operational tradecraft and no evasion guidance.

### Evaluation

Temporal split, never random.

**The two headline numbers are the two that can fail.**

**1 · Requirement-set completeness (Stage 1).** Against a ground-truth checklist per flag type:

- **Recall** — of the requirements genuinely needed, how many were asked in round one? *Recall below 1.0 means a second round, and the entire thesis collapses.* This is the load-bearing metric.
- **Precision** — of the requirements asked, how many were genuinely needed? Low precision reproduces the harm in a single round instead of four.

**2 · Escape rate.** Cases cleared that should have been escalated. Speed that lets fraud through is not a win. Reported either way, and reported against a do-nothing baseline.

Supporting metrics:

- **Days funds held** — the merchant harm, in days × rupees.
- **Re-ask rate** — requests for information already supplied. Non-zero in the corpus at a one-month lag (§7). Should be **0** by construction, so this verifies the ledger rather than measuring a model.
- **Impossible-requirement detection** — does the system route the GST-exempt case to a human, or loop forever?
- **Rounds to resolution.** Reported, but see the caveat below.

> **On the Stage 2 ablation.** Running the pipeline with and without internal
> satisfaction will reduce rounds — checking what you already hold before asking
> is close to true by construction, and on a simulator whose parameters we set,
> the magnitude is largely what we dialled in. It is reported as a **mechanism
> demonstration, not a discovery**, and it is not the headline. The corpus also
> contains **no explicit round counts** (§7), so any numeric
> "baseline of N rounds" is inferred from described patterns rather than
> measured. The honest baseline statement is qualitative: requirements issued
> serially, goalposts moved after full submission, and at least one requirement
> re-asked a month after it was satisfied.

### Data

A case simulator whose parameters are taken from the coded review corpus in §7 — round counts, 48–72 hour inter-round latencies, re-ask frequency, and the document types merchants actually report being asked for (board resolution in a named format, GST registration, social media links, undertakings on card storage, address verification). Labelled cases span three populations: legitimate merchants with complete evidence, legitimate merchants with awkward-but-genuine gaps (the GST-exempt merchant, the B2B firm with no social presence), and bad actors whose evidence does not reconcile.

This is synthetic, but it is synthetic **calibrated on primary research** rather than invented — which is a materially stronger position than a hand-specified fraud simulator, and is stated as such rather than claimed as real-world validation.

---

## 7. Primary research: merchant review coding

37 reviews coded against a pre-registered schema. Protocol, changelog and raw data: [`research/complaints/`](research/complaints/).

Schema v1 was fixed before coding began. Round 2 surfaced three patterns v1 could not express; **schema v2 was applied and all 37 rows re-coded** rather than adding categories silently. `tid_deactivation` became an `event_type`; `stateless_rereq` and `impossible_req` are properties of the *review loop*, not event classes, so they moved to a new `loop_pathology` column; and `rounds_stated` was added because rounds-to-resolution is the project's headline metric.

**Stratified sample** across positive-skewed sources (G2 4.3/5, Capterra 3.6/5) and negative-skewed sources (MouthShut 2.9/5, ConsumerComplaints 2.8/5 with 3,556 complaints, Trustpilot 1.4/5, PissedConsumer 1.7/5).

Of 37 rows: **29 merchant**, 8 excluded (6 payers, 1 employee, 1 self-identified consumer). Of the 29 merchant rows, **22 coded `no_risk_event`** and **7 record a risk-affected outcome** — 5 settlement holds, 1 terminal deactivation, 1 underwriting rejection.

Across those 7, `loop_pathology` codes to: `sequential_requests` + `goalpost_move` (2), `goalpost_move` (1), `stateless_rereq` (1), `impossible_req` (1), `none` (1), `n/a` (1).

**And `rounds_stated` is empty on all 37 rows.** No merchant states an explicit round count. Reviews describe the *pattern* — "one at a time", "48-72 hour delay", "asked again 1 month later" — but never a total. The corpus therefore supports a qualitative characterisation of the loop and **cannot** support a numeric round baseline. That constraint is carried into §6.

### Findings

**1. Settlements are reliable in normal operation.** Three merchants volunteered this unprompted: *"in 16 months of usage settlements have never been delayed"*, *"settlements are reliable"*, *"settlement is always on time"*.

This refutes the naive claim that Razorpay has a settlement problem. The infrastructure works. **It breaks in one circumstance: when a risk flag fires.** That is a far narrower and more defensible claim than the complaint sites alone would support — and it is why the positive stratum was sampled first.

**2. The distribution is bimodal — merchants either never meet the risk layer, or it defines their entire experience.**

| Stratum | Merchant rows | Risk-affected |
|---|---|---|
| Positive-skewed (G2, Capterra) | 22 | **1** (4.5%) |
| Negative-skewed (MouthShut, ConsumerComplaints, Voxya) | 7 | **6** (86%) |

In the positive stratum the single exception is an international-payments underwriting rejection — no settlement holds, no suspensions. Dislikes there cluster on support latency (6), pricing (3) and dashboard complexity (2). In the negative stratum, five of the six are settlement holds and the sixth is the terminal deactivation.

This is what makes the harm easy to miss from inside. Nearly every merchant is fine, so aggregate satisfaction metrics stay healthy while the affected minority is dealt with catastrophically.

**3. The rating split localises the failure.** G2 4.3 (people evaluating the technology) versus Trustpilot 1.4 (people whose money is stuck). Same company. The payments engine is not the problem.

**4. A satisfied customer corroborates the failure mode.** A five-star reviewer independently described a *"strict and elaborate KYC process that may end up blocking the merchant's account instantly if there are any small discrepancies in the documents."* Coded `SECONDHAND` — described as known market behaviour, not personally experienced.

**5. Public complaint channels are payer-dominated.** 8 of 37 rows were consumers with failed payments, employees, or self-identified shoppers, not merchants; browsing ConsumerComplaints chronologically returned zero merchant rows. Merchant complaints exist but must be searched for — B2B customers escalate through account managers, and a merchant mid-negotiation over held funds has an active incentive not to go public.

**6. The review loop is stateless, and four merchants describe it identically.** This is the finding the design in §6 is built on. Requirements issued one at a time at 48–72 hour intervals (May 2025); goalposts moved after full submission (May 2025, Oct 2024, Jun 2025); and — decisively — *"Razorpay replied with the same irrelevant questions which was asked 1 month before"* (Feb 2024). A process that re-asks a satisfied requirement after a month is not applying a stricter policy. It is not tracking the case.

**7. At least one requirement class is impossible to satisfy.** A merchant below the ₹20 lakh turnover threshold, and therefore legitimately GST-unregistered, had funds withheld pending GST registration (May 2024). No amount of merchant compliance resolves this; only a human with authority to grant an exception does. A loop that cannot recognise this class will run forever.

**8. The exonerating evidence is often already inside the aggregator.** A POS merchant's terminal was deactivated for *"no transactions since more than 3 months"* — because the terminal had been non-functional for four months, with an open support ticket their own technician never closed (May 2025). A naive behavioural signal fired; the fact that refuted it was sitting in the same company's ticketing system. This single row is the clearest statement of the §6 thesis in the corpus.

**9. First-response resolution is achievable, and sometimes achieved.** A merchant reporting 8–10 tickets over three years — including a KYC document resubmission and a failed payout — records that *"every single one of these was resolved in the first response"* (Jul 2026). The one-round target in §6 is not hypothetical; it is the same organisation's own better outcome.

---

## 8. Limitations — what this document does not claim

1. **No loss figure.** No public data exists on Razorpay's merchant-fraud losses. None is estimated here.
2. **Public surface only.** Internal merchant risk systems very likely exist. The claim concerns what is exposed and what the published data model can express.
3. **Complaint data measures failure *modes*, not base rates.** Self-selected samples. No percentage in §7 is a population statistic.
4. **Merchant risk complaints cluster in 2021–2024 and thin out after mid-2025.** The most recent coded risk events are May–June 2025 (three independent cases). Two readings we still cannot distinguish: (a) Razorpay materially improved, or (b) complaint boards lost traffic to X and Reddit. Reading (a) would weaken the urgency of this work; it does not remove the schema gap or the 2025 regulatory obligation.
5. **G2's rating is not a neutral sample.** Four separate reviewers cite the same unusual "₹4,999 competitor AMC" argument and the same "93% success rate" figure; two independently cite Instamojo at "80%". That pattern indicates solicited reviews. The ratio is discounted accordingly; the factual statements within reviews are retained.
6. **Coding method.** 37 rows, single human coder, LLM-assisted against a pre-registered schema with every row human-verified. No inter-rater reliability beyond a self re-code. Three categories surfaced in round 2 that schema v1 could not express; schema v2 was applied and **all 37 rows re-coded**, with the change logged in [`research/complaints/CODING.md`](research/complaints/CODING.md). No category was added silently.

7. **The round-count baseline is inferred, not measured.** `rounds_stated` is empty across the entire corpus — merchants describe the pattern of the loop but never state a total. No numeric baseline for rounds-to-resolution is claimed, and the Stage 2 ablation is reported as a mechanism demonstration rather than a discovery (§6).
8. **The T+1 claim was investigated and dropped.** Secondary sources asserted the 2025 Directions impose a T+1 settlement ceiling. Primary law-firm analysis of the Directions contains no such provision; settlement timing appears to be contractual subject to a transparency requirement. The claim is not made.
9. **The simulator is calibrated on complainant accounts, not on Razorpay's process.** Round counts and 48–72 hour latencies are as *stated* by merchants in public reviews. They parameterise a simulator; they are not measurements of Razorpay's actual review queue, and are not presented as such.

10. **Stage 2 runs against a simulated evidence store.** The internal-satisfaction pass assumes access to KYC files, prior submissions, transaction history and support tickets. This project has none of these. The store is synthetic, so the headline ablation measures the *mechanism*, not its yield on Razorpay's real data.

11. **Two negative-stratum sources could not be sampled cleanly.** Trustpilot (437 reviews, 1.4/5) returns HTTP 403 to automated access and remains unsampled — the largest known gap. PissedConsumer's "1.8K reviews" pool Razorpay with "Razer Gold" gift-card complaints for a different company, making its count and rating unusable as denominators. MouthShut's rating is diluted by a cluster of near-identical Mar–Apr 2022 employee posts; only page 1 was sampled.

12. **This project does not claim better detection.** It claims better adjudication after detection. Whether Razorpay's flags are well-calibrated is outside what this evidence can establish — and at least one coded case (a dedicated-server reseller, a category with genuine laundering exposure) may well have been flagged correctly and handled badly.

---

## Sources

1. Razorpay FY25 results — https://www.plindia.com/news/razorpay-posts-65-revenue-jump-in-fy25-as-ipo-preparations-advance/
2. UPI share of PA volume and take rate — https://inc42.com/features/upis-monetisation-moment-why-mdr-is-back-on-the-table/
3. DRHP filing, June 2026 — https://www.kotakneo.com/news/ipos/razorpay-confidential-ipo-sebi-filing-june-2026-valuation/
4. Razorpay Agentic Platform, 12 March 2026 (Razorpay blog; marketing content, cited only for what Razorpay states it ships) — https://razorpay.com/blog/razorpay-agentic-platform/
5. Mule account concentration and low-friction onboarding — https://the420.in/india-mule-accounts-upi-fraud-march-2026-report/
6. Razorpay Account Entity (Partners) — https://razorpay.com/docs/api/partners/account-onboarding/entity/
7. Modify Settlement Hold — https://razorpay.com/docs/api/payments/route/modify-settlement-hold/
8. Thirdwatch merged into Magic Checkout — https://razorpay.com/blog/thirdwatch-has-merged-with-magic-checkout/
9. RBI PA Directions 2025 analysis (Khaitan & Co ERGO, 3 Oct 2025) — https://www.khaitanco.com/sites/default/files/2025-10/ERGO%20-%20PA%20Master%20Directions%20-%203%20Oct%202025_0.pdf · also https://www.ikigailaw.com/article/639/rbi-rewrites-the-payment-aggregator-rulebook
10. Transaction laundering definition — https://www.sardine.ai/learn/transaction-laundering
11. BRAM / VIRP penalties and mitigation — https://www.legitscript.com/bram-virp/ · https://docs.nuvei.com/documentation/security-docs/risk-guide/schemes-programs/
12. ED chargesheet, Chinese loan apps — https://inc42.com/buzz/chinese-loan-apps-ed-files-chargesheet-against-razorpay-others/
13. RBI onboarding embargo, Dec 2022 — https://yourstory.com/2022/12/razorpay-pine-labs-stripe-withhold-onboarding-new-merchants-audit-payment-aggregator
14. I4C mule account figures — https://the420.in/india-mule-accounts-upi-fraud-march-2026-report/
15. Merchant settlement hold complaint, 30 June 2025 — https://voxya.com/consumer-complaints/razorpay-payment-settlement-issue/246352
16. Cashfree on merchant collusion fraud — https://www.cashfree.com/blog/types-of-merchant-fraud-encountered-by-payment-aggregators-and-measures-to-tackle-it/
17. MATCH and VMSS — https://developer.visa.com/capabilities/visa-merchant-screening-service · https://en.wikipedia.org/wiki/Terminated_merchant_file
18. Merchant monitoring vendors — https://www.legitscript.com/solutions/merchant-risk-solutions/ · https://www.safetykit.com/merchant-investigations/transaction-laundering · https://g2risksolutions.com/persistent-merchant-monitoring/
19. Stripe Radar for Platforms, 27 May 2026 — https://stripe.com/blog/expanding-stripe-radar-to-protect-more-of-your-business
20. Merchant monitoring practice — https://onlayer.com/en/guides/what-is-merchant-monitoring
