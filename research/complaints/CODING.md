# Merchant Complaint Coding Protocol

Primary research for PROBLEM.md.

**Schema v1** fixed before coding began.
**Schema v2** (29 Aug 2026) applied after round 2, with all 37 rows re-coded.
Changelog in "Schema v2" below.

**On the date.** Both this file and `complaints.csv` were last written
2026-08-29 12:20, so the v2 re-code is dated from that. It is a file mtime, not
a measurement of when the work started: round 1 and round 2 may have begun
earlier. Dated from the evidence that exists.

---

## Sampling design (stratified — do not skip this)

Sample from BOTH satisfied and dissatisfied sources, so the result is not
pure selection bias:

| Stratum | Sources | Rows |
|---|---|---|
| Positive-skewed | G2 (4.3/5), Capterra (3.6/5) | 24 |
| Negative-skewed | MouthShut, ConsumerComplaints, Voxya | 13 |

Code in the order reviews appear. Do NOT skim for dramatic ones.

## Screening: merchant vs payer

Only `actor = merchant` rows enter the analysis. Keep the others in the file
anyway — the count of excluded payer complaints is an honest denominator.

Merchant tells: settlement, payout, my customers, KYC, dashboard, MID,
                account activation, my business, refund I issued
Payer tells:    I made a payment, amount debited, order/ticket not received,
                refund I am owed, recharge failed

Ambiguous -> `unclear`, exclude from analysis, keep the row.

---

## Field values (schema v2)

```
actor             merchant | payer | employee | unclear
event_type        settlement_hold | account_suspended | account_rejected |
                  kyc_block | funds_withheld_post_termination |
                  payout_blocked | tid_deactivation | no_risk_event | other
loop_pathology    sequential_requests | goalpost_move | stateless_rereq |
                  impossible_req | none | n/a      [multi-value, ";" separated]
rounds_stated     integer — number of request rounds the merchant explicitly
                  states. Blank if not stated. NEVER inferred.
reason_given      none | generic_tos | specific | docs_request | n/a
docs_submitted    yes | no | unclear | n/a
appeal_mentioned  yes | no | unclear
hold_days_stated  integer, blank if not stated. Use the number THEY state.
resolution        resolved | unresolved | unknown | n/a
amount_inr        integer, blank if not stated
quote             <=200 chars, verbatim, no paraphrase
notes             anything that doesn't fit a column
```

`no_risk_event` is important: a merchant review that never mentions a risk
action still counts as a coded merchant row. That's what makes the
denominator real.

`n/a` = no event occurred. Blank = event occurred but the reviewer did not say.

---

## Schema v2 — what changed and why

Round 2 surfaced three recurring patterns that v1 could not express. Rather
than cram all three into `event_type`, they were split by kind:

**1. `tid_deactivation` added to `event_type`.**
A genuine event class — a POS terminal deactivated on an inactivity signal.
R036 recoded from `other`.

**2. New column `loop_pathology`.**
`stateless_rereq` and `impossible_req` are **not** event types. They are
properties of the review loop that resolves an event. R034 is a
`settlement_hold` *that also* re-asked a satisfied requirement; collapsing
those into one field destroys information. Multi-value, `;` separated:

| value | meaning |
|---|---|
| `sequential_requests` | requirements issued one at a time rather than as a set |
| `goalpost_move` | new requirements after the merchant submitted everything asked |
| `stateless_rereq` | a requirement re-asked after it had already been satisfied |
| `impossible_req` | a requirement the merchant cannot lawfully satisfy |
| `none` | risk event occurred, no loop pathology described |
| `n/a` | no risk event |

**3. New column `rounds_stated`.**
Rounds-to-resolution is the project's headline metric, so the corpus must
record it explicitly rather than by impression.

> **Result: `rounds_stated` is empty on all 37 rows.** No merchant states an
> explicit round count. Reviews describe the *pattern* ("one at a time",
> "48-72 hour delay", "asked again 1 month later") but never a total.
> Any numeric round baseline is therefore **inferred, not measured**, and
> must be presented as such. This is a limitation, not a finding.

Per rule 1, all 37 rows were re-coded under v2. No row was left on v1.

---

## Rules

1. Schema changes require re-coding **every** prior row, and a changelog
   entry above. Never add a category silently.
2. Verbatim quotes only. Never paraphrase into the quote column.
3. Record what the complainant says, not what you infer. "Docs submitted"
   means they said they submitted docs.
4. `rounds_stated` and `hold_days_stated` take only numbers the merchant
   states. If they describe a pattern without a number, it goes in `notes`.
5. Stop when 10 consecutive rows add no new category. Record which stop
   condition fired.
6. Re-code 10 random rows later without looking at the originals.
   Disagree on more than 2? The scheme is too fuzzy — tighten and re-run.

---

## Sources

- https://www.g2.com/products/razorpay/reviews            (4.3/5, 150)
- https://www.capterra.com/p/179263/Razorpay/reviews/     (3.6/5, 114)
- https://www.mouthshut.com/websites/razorpay-reviews-925992393  (2.9/5)
- https://www.consumercomplaints.in/razorpay-b115695      (2.8/5, 3556)
- https://voxya.com  (search "razorpay")
- https://www.trustpilot.com/review/razorpay.com          (1.4/5, 437) [NOT SAMPLED]
- https://razorpay.pissedconsumer.com/review.html         (1.7/5) [CONTAMINATED]

## Source quality notes (round 2, 29 Aug 2026)

- **PissedConsumer is contaminated.** Its "1.8K reviews" pool Razorpay with
  "Razer Gold" gift-card complaints — a different company. The headline count
  and the 1.7/5 rating are both unusable as denominators. Not sampled.
- **MouthShut's tail is employee reviews.** Page 1 is merchant/payer
  complaints; pages 2+ are dominated by a cluster of near-identical
  Mar–Apr 2022 staff posts — the same solicitation tell found on G2.
  The 2.9/5 is diluted accordingly. Page 1 sampled; tail excluded.
- **Trustpilot could not be sampled.** Returns HTTP 403 to automated access.
  437 reviews at 1.4/5 remain unsampled — the largest known gap in the
  negative stratum.
- **G2 shows solicitation.** Four reviewers cite the same unusual "₹4,999
  competitor AMC" argument and the same "93% success rate"; two independently
  cite Instamojo at "80%". The ratio is discounted; the factual statements
  within reviews are retained.

## Saturation

Categories saturated by round 2:
- sequential document requests (R031, R032, R033, R034)
- goalpost movement after full submission (R031, R032, R033)

Strongest single row: **R036.** The exculpatory evidence — an open support
ticket on hardware Razorpay's own technician left broken — was already
inside Razorpay when the deactivation fired.

---

## Limitations (goes verbatim into PROBLEM.md)

- Self-selected samples. Measures failure MODES, not base rates.
  No percentage here is a population statistic.
- Single coder, LLM-assisted, every row human-verified. No inter-rater
  reliability beyond the self re-code.
- Complainant accounts are one-sided and unverified.
- Findings describe the SHAPE of a failure, which is enough to justify
  design requirements. Nothing more is claimed.
- Latency figures ("48-72 hours", "1 month later") are as STATED by
  complainants. They parameterise a simulator; they are not measurements
  of Razorpay's actual review process.
- **No round counts exist in the corpus.** See Schema v2 note above.
