# Engineering log

Written as things happen. Not reconstructed. Dates are to the day, checked
against file timestamps.

## 2026-08-30 — Stage 1 run 1: recall works, precision is the real problem

**Setup.** Claude, High effort, claude.ai Chat, one fresh session, no project
context. `FLAG_TID_INACTIVITY` only (the R036 broken-POS case). n=1.

**Result.**

```
recall    100%  (6/6)
precision  12%  (6/51)
recall on internally-satisfiable items: 100%
ASK items: 22    INTERNAL items: 29
```

**The load-bearing assumption holds.** Stage 1 recall was the thing that could kill
this project — miss one requirement and the merchant is in round two anyway. It found
every ground-truth item, including TI1, the support-ticket check that is the entire
point of the R036 case. Generation-based requirement synthesis works. Stage 1 does not
need to become retrieval.

**But precision is 12%, and that is not a scoring artifact.** The model returned 51
requirements for a restaurant whose card machine stopped working, **22 of which it
wants to demand from the merchant**: income tax return, GST returns for the dormant
period, 6–12 months of bank statements, live video verification of the proprietor,
FSSAI licence, Shop & Establishment licence, geo-tagged shopfront photographs, rent
agreement, utility bill, fresh KYC.

For a broken terminal.

**This is the harm restructured, not removed.** `PROBLEM.md` §6 predicted it in the
abstract — *"low precision reproduces the harm in a single round instead of four"* —
and run 1 produced it concretely. A merchant handed a 22-item demand is not better off
than one dripped four requirements over eight days. Arguably worse: it is now a wall
instead of a corridor.

**So the thesis gains a second half.** "Ask everything at once" is not the product.
The requirement set must be complete **and proportionate** — scoped to what resolves
*this* flag, not everything that could conceivably be verified about a merchant. That
is a harder problem than completeness and a more interesting one.

**Secondary finding: the model already knows to look internally.** 29 of 51 items
marked INTERNAL, and 100% recall on the internally-satisfiable subset. It reached for
support tickets, terminal telemetry and asset records unprompted. So the R036 failure
was not hard to avoid — a competent reasoner gets there in one pass. The real process
still didn't. That strengthens the argument rather than weakening it.

**Ground-truth gaps found (bucket c).** Four items the model raised that I had missed
and that are genuinely correct for this flag type:

- terminal error and decline logs — were transactions *attempted* and failing?
- SIM / connectivity records
- device asset record — still deployed to this merchant, or recovered into stock?
- terminal rental invoice history — did rentals keep debiting, did they bounce?

My TID requirement set should be ~10 items, not 6. The test improved the ground truth,
which is what it was supposed to do.

**One measurement artifact (bucket b).** TI6 initially scored as missed. The model said
*"any other MID or TID with the aggregator"*; my aliases had `same mid` but not
`other mid`. Semantically identical. Alias added and logged in the YAML — adding
aliases after seeing the answer fits ground truth to the response if done silently.

**Next.** Add a proportionality constraint to the Stage 1 prompt and re-run the same
flag. Measure whether precision rises without recall falling. That A/B is the actual
product decision, and it can go either way.

---

## 2026-08-30 — ground truth expanded, then frozen

Folded the four gaps run 1 exposed into `FLAG_TID_INACTIVITY` as TI7–TI10:
terminal error/decline logs, SIM connectivity records, device asset status,
rental invoice history. All four are internally satisfiable and all four are
genuinely correct requirements the v1 set missed.

Corpus: 43 → 47 requirements. Overall Stage 2 headroom: 31% → 37%.
TID headroom: 50% → 70%.

**This introduces a bias and I am not going to pretend otherwise.** Adding
requirements the model itself produced makes the model score better next time —
recall rises because it already generates them, precision rises because more of
its output now matches. Run 2 numbers are therefore **not comparable** to run 1.

Handling:

- Run 1 stands as a **pilot** against the 6-item set. Recorded, superseded, not
  deleted.
- The ground truth is now **frozen**. All seven flags, including a TID re-run,
  are scored against this version. Further changes require a dated entry in the
  YAML and a re-run of every flag already scored.
- Precision across the two versions is never quoted side by side.

The mitigation that actually matters: **the other six flag types have not been
through a run.** Their requirement sets are un-fitted to any model output. If
run 1's over-asking pattern repeats on those six, it cannot be an artifact of
this adjustment — and that is the result worth having.

Also reconciled `PROBLEM.md` §6 against both measurements. It previously read
"Stage 2 is the contribution", which the audit and run 1 both contradict. Now:
Stage 1 is the mechanism for collapsing rounds, Stage 2 bounds the size of the
ask. Stage 1 and Stage 3 descriptions gained the proportionality requirement.

---

## 2026-08-30 — full verification pass

Ran a repo-wide integrity check before going further. Found and fixed real errors.

**Link check.** 24 unique source URLs in `PROBLEM.md`. 23 return HTTP 200. The
one exception (YourStory) returns 403 to automated requests — bot detection, not
a dead link; opens normally in a browser.

**Integrity check.** All files present. All text valid UTF-8, no replacement
characters. CSV: 37 rows, schema v2 header, no duplicate ids, no ragged rows.
YAML: 7 flags, 47 requirements, no duplicate ids, all fields well-formed. Both
CLI modes exit 0.

**Error found and fixed — §7 finding 2 was stale.** It read *"21 of 22 merchant
reviews coded no_risk_event… Settlement holds: zero. Suspensions: zero."* That
was true of the original G2-only sample, but the corpus now has 29 merchant rows
including **five settlement holds**. As written it described the whole corpus and
was simply false.

Correctly scoped, it is a better finding than the one it replaces:

```
positive stratum (G2/Capterra):  22 merchant rows, 1 risk-affected  (4.5%)
negative stratum (MouthShut/CC/Voxya): 7 merchant rows, 6 risk-affected (86%)
```

The distribution is bimodal. Nearly every merchant never meets the risk layer,
so aggregate satisfaction stays healthy while the affected minority is handled
catastrophically. That is precisely why this harm is invisible from inside.

Theme counts were also wrong (dashboard complexity stated as 4, actually 2) and
are now computed from the CSV rather than remembered.

**Also fixed.** A bare `CODING.md` reference in §7 that pointed at nothing —
now `research/complaints/CODING.md`.

**Lesson.** Every numeric claim in prose needs to be recomputed from the data
whenever the data changes. Three of the numbers in §7 were carried over from an
earlier corpus and nobody noticed for two days. Counts belong in a script.

---

## 2026-08-30 — variant B written; the ground-truth bias, made visible

**The bias is not hypothetical.** Re-scoring the *unchanged* run-1 response
against the frozen 10-item TID set:

```
                        recall      precision
run 1, 6-item set       100% (6/6)     12%  (6/51)
run 1, 10-item set      100% (10/10)   20%  (10/51)
```

Same model output. Same 51 predictions. Precision rose 8 points purely because
I added four requirements the model had already produced. Nothing about the
model improved. This is exactly what the bias warning in the YAML predicted, and
it is why run-1 and run-2 precision are never quoted side by side.

**Variant B written.** Identical task, identical user prompt, identical flag
data, identical output format. The only change is the constraint on what belongs
in the set:

> *Name the specific hypothesis this item would rule in or rule out about THIS
> flag. If you cannot name one — if the honest answer is "it is generally good to
> know" or "it is standard practice" — leave it out.*

Plus an explicit instruction not to sweep in routine KYC refresh, licence
renewals, tax filings or financial statements unless the flag cannot be resolved
without them. Those were the worst offenders in run 1: income tax return, GST
returns, FSSAI licence, live video verification of the proprietor — for a broken
card terminal.

**Deliberately not a hard item cap.** "Return at most 8 requirements" would raise
precision by truncation and tell us nothing about whether the model can reason
about necessity. It would also risk cutting real requirements, which is the one
failure mode this project cannot tolerate. The constraint has to be a test the
model applies, not a ceiling imposed on the output.

**The A/B is now clean.** `--variant baseline|proportionate` on dump, score and
API paths; separate `prompts_proportionate/` and `responses_proportionate/`
directories so the two runs cannot contaminate each other.

**The question this answers, and it can go either way.** If precision rises and
recall holds, Stage 1 has its design. If recall drops, there is a real tension
between completeness and proportionality, and that tension is itself the finding
— it would mean the one-round promise cannot be kept without over-asking, which
would reshape the product.

---

## 2026-08-30 — variant B failed, and the failure names the fix

Ran variant B (proportionality constraint) on `FLAG_TID_INACTIVITY`, same
conditions as run 1. Scored against the frozen 10-item set.

```
                    recall   internal-recall   precision   total   ASK   INTERNAL
baseline             100%          100%           20%        51     22      29
proportionate         40%           29%           13%        30     15      15
```

**The constraint pruned the wrong side.** INTERNAL items fell 48%; merchant ASKs
fell only 32%. That is exactly backwards. Internal checks cost the merchant
nothing — there is no reason to be parsimonious about them, and they are
precisely the items that can resolve a flag without involving the merchant at
all. Recall on internally-satisfiable items collapsed from 100% to 29%.

Lost outright: SIM/connectivity records, rental and MDR billing history, device
asset status, terminal error and decline logs. Those are the diagnostics that
would have told an analyst the R036 terminal was dead rather than dormant.

**Root cause is mine, not the model's.** Variant B described the cost as
*merchant burden* but applied its necessity test to *every* candidate, including
items carrying no merchant burden. One test, two populations with opposite cost
structures. Proportionality has to be asymmetric.

**Second finding: the prohibition list was hedged, not obeyed.** Variant B
explicitly said not to sweep in routine KYC refresh, licence renewals, tax
filings or financial statements. All five came back — FSSAI licence, shop and
establishment licence, PAN/Aadhaar re-KYC, live video KYC, GST — each wrapped in
"if the one on file has expired". Negative constraints get conditionalised
rather than dropped. State a positive rule instead of a list of prohibitions.

**Caveat on the 40%.** Some misses are keyword artifacts, not real. TI3
(physical possession) is present in variant B's output — "still physically with
the merchant… not moved, sold, or given to anyone else" — but my aliases were
`possession` / `physical custody`, neither of which appears. Adjusted recall is
roughly 50-70%, not 40%. The drop is real; its size is not precise. Aliases were
NOT added this time — the ground truth is frozen and fitting it to a second
response would compound the bias already logged.

**Variant C written.** Asymmetric: exhaustive on INTERNAL, minimal on ASK, with
the necessity test applied only to merchant requests plus a second gate — if an
internal check could answer it, the internal check replaces the request. Positive
rule, no prohibition list. Conditional asks stated as conditional.

Three variants now, one flag, n=1 each. The A/B/C is the finding; the absolute
numbers are not yet trustworthy.

---

## 2026-08-30 — variant C: the asymmetry hypothesis holds

```
variant          kw-recall   adj-recall   kw-prec   adj-prec   total   ASK   INTERNAL
baseline            100%        100%        20%       20%        51     22      29
proportionate        40%         50%        13%       17%        30     15      15
asymmetric           70%        100%        44%       63%        16      3      13
```

**Variant C matches baseline completeness with 16 items instead of 51, and
3 merchant requests instead of 22.**

All ten ground-truth requirements are present. The three scorer misses were
wording, not substance — TI6's alias was `any other tid` and the text said
`all other TIDs`; TI9's was `asset record` against *"Asset and inventory
records"*. Ruled individually in `results/adjudication.md` with the candidate
text quoted, rather than fixed by adding aliases to a frozen ground truth.

**The asymmetry hypothesis was right.** Splitting the cost model — exhaustive on
internal, minimal on ask — recovered every internal diagnostic variant B had
dropped (SIM status, rental billing, asset records, fault logs) while cutting
merchant requests by 86% against baseline.

**And all three surviving asks are conditional**, which is not something the
prompt demanded in that form:

> *"…only needed if telemetry shows the device has been fully offline and there
> is no support ticket, since an offline device leaves no internal trace of its
> physical state."*

That is the product. The merchant is asked nothing at all unless the internal
checks come back inconclusive, and when they do, they are asked three things
with the reason attached.

**On the R036 case specifically.** Variant C's internal list would have resolved
it without contacting the merchant at all: fault logs, connectivity status,
support ticket history, rental billing. The broken terminal leaves a trace in
four separate internal systems. Nothing needed to be asked.

**Caveats, and they are not small.**

- n=1 per variant, one flag, no repeats. Sampling variance is unmeasured.
- The flag tested is the one whose ground truth I expanded after run 1. It is the
  most fitted of the seven and therefore the most flattering.
- Adjudication was done by me — the same person who wrote the ground truth, the
  prompts and the variants. That is the weakest link in the whole measurement.
- The keyword scorer missed 3 of 3 on variant C. At this granularity it is not
  trustworthy on its own.

**Next, in order.** Run variants A and C on the remaining six flags — those
ground truths are un-fitted, so they are the real test. Then get the
adjudication redone blind, or by an LLM judge with the disagreement rate
reported.

---

## 2026-08-30 — replicated on an un-fitted flag; the metric changed

Ran baseline and asymmetric on `FLAG_VOLUME_SPIKE`. This flag's ground truth has
never been touched after a run, so it cannot be explained by the fitting bias
logged earlier.

```
FLAG_VOLUME_SPIKE (6 requirements)
  variant       kw-rec  adj-rec  adj-prec  items  ASK  uncond  INT
  baseline        83%     100%      19%      32    15     15    17
  asymmetric     100%     100%      17%      35     7      1    28

AGGREGATE (2 flags)
  baseline        92%     100%      19%      83    37     37    46
  asymmetric      85%     100%      40%      51    10      1    41
```

**The finding replicates.** Same completeness, 37 unconditional merchant demands
down to 1.

**The right metric was not precision.** Asymmetric on VOLUME_SPIKE returns MORE
total items than baseline (35 vs 32) and slightly worse precision (17% vs 19%) —
because internal checks went 17 to 28. That is not a regression. Internal checks
are free to the merchant; doing more of them is the point. Precision punishes
exactly the behaviour we want.

**What actually matters is unconditional merchant asks**, and it is now tracked.
Six of asymmetric's seven asks on VOLUME_SPIKE are gated on an internal result:

> *"Only if internal records show the settlement bank account was changed near
> the spike: confirmation of the change from an authorised signatory, to rule
> out account takeover."*

The merchant is contacted only when the internal checks come back inconclusive,
and then with a named reason. Baseline demands all 15 up front regardless —
including a beneficial-ownership refresh and an address proof, for a sales spike.

**Bug in my own instrument.** The conditional-ask detector reported zero
conditionals on a response visibly full of "Only if". Cause: writing the regex
through a shell heredoc turned every `\b` word-boundary into a literal backspace
character (0x08), so the pattern was matching control characters. Silent - the
regex compiled fine and simply never matched. Found by printing the compiled
pattern rather than trusting the output. Four backspace characters removed;
detector verified against all four responses before any number was reported.

Second time a measurement artifact has produced a wrong number here. Both were
caught by checking the instrument rather than the result. Every new metric gets
verified against known-answer cases before it is used.

---

## 2026-08-30 — three flags, and the "did we cause this?" pattern generalises

```
AGGREGATE (3 flags, adjudicated)
  variant       adj-recall   items   ASK   uncond   INTERNAL
  baseline         100%       139     67      67       72
  asymmetric       100%        78     15       3       63
```

**67 unconditional merchant demands down to 3, at identical completeness.**

`FLAG_MCC_MISMATCH` is the most extreme case so far. Baseline returned 56 items
with **30 unconditional asks** for a descriptor and ticket-size mismatch,
including: the proprietor's income tax return, audited profit-and-loss and
balance sheet, 14 months of bank statements from two separate accounts, the
courier partner's agreement, customer contact details so the aggregator can ring
the merchant's own customers, and a fresh KYC refresh with photograph.

Asymmetric returned 27 items, 5 asks, 2 unconditional.

**The R036 insight generalised on its own.** Asymmetric, on a completely
different flag, independently reached for:

> *"Check whether the descriptor was set by the merchant during onboarding,
> edited later by the merchant, or auto-generated or altered by an internal tool,
> bank, or integration partner — **a system-generated mismatch is not merchant
> misconduct**."*

That is exactly the broken-terminal pattern — ask whether the aggregator caused
the anomaly before demanding the merchant explain it — arriving unprompted on a
flag that has nothing to do with hardware. The prompt never mentions R036 or POS
terminals. It falls out of "check internal records first".

It also added: *"Pull every prior submission the merchant has already made… so
nothing already supplied is requested a second time."* That is the stateless
re-request pathology from the corpus (R034), solved without being told about it.

**Adjudication note.** Four misses this round, all wording, all ruled present
with the candidate text quoted. The keyword scorer has now missed on wording in
4 of 5 scored pairs — it is systematically pessimistic. But adjudication has
**never once changed the ordering between variants**, which is the result that
matters.

Three of seven flags. Four runs to go.

---

## 2026-08-30 — four flags, and the first genuine cost of the asymmetric prompt

```
AGGREGATE (4 flags, adjudicated)
  variant       adj-recall   items   ASK   uncond   INTERNAL
  baseline         100%       191     95      95       96
  asymmetric        96%       109     21       5       88
```

**95 unconditional merchant demands down to 5.** But asymmetric is no longer at
100%, and the reason is worth more than the number.

**HR4 is a real miss, not a scorer artifact.** The ground truth asks for
*customer communication logs for a sample of disputed transactions*. Asymmetric
never requests them. Instead it lists internal sources: *"any customer
complaints, issuer retrieval requests, or pre-arbitration notices we already
hold, including their text."*

That is a defensible substitution and it is exactly what the prompt told it to
do — *"if an internal check could settle the question, the internal check
replaces the request"*. But it is not equivalent. The complaint text the
aggregator holds is what the customer said to their bank. The merchant's own
correspondence with that customer is a different record, held only by the
merchant, and it is often the thing that wins a representment.

**So the asymmetric constraint has a specific failure mode: it can over-trust an
internal substitute.** The rule needs a qualifier — an internal record replaces a
merchant request only when it answers the *same* question, not merely an adjacent
one. That is variant D, and it is a real refinement rather than a tweak.

Ruled ABSENT deliberately. Ruling it present would have kept a clean 100% and
hidden the only genuine weakness the experiment has surfaced.

**Third appearance of the "did we cause this?" pattern**, now on a chargeback
flag with no hardware involved:

> *"Payment gateway and API error logs, checkout failure rates, and
> duplicate-charge or double-submit incidents **on our side** that could have
> generated genuine duplicate-transaction disputes."*
>
> *"Any outage, timeout, or reconciliation incident **on our platform** during
> the spike window that could have caused failed-but-charged transactions."*

Three flags, three spontaneous appearances, never prompted. It is a reliable
consequence of "check internal records first", not a one-off.

**And it questioned the trigger itself:** *"confirm the 0.4% benchmark is drawn
from comparable MCC 5651 merchants of similar size and channel mix, not the whole
portfolio."* Before asking the merchant to explain a deviation, check the
deviation is real.

**Baseline, for contrast**, asked this apparel merchant for audited financial
statements, GST returns, 6-12 months of bank statements, a board resolution
naming who may reply, disclosure of every other aggregator relationship they
have ever had, disclosure of any data breach, agreement to purchase a third-party
dispute-alert service, and acceptance of a volume cap. 28 unconditional demands,
for a chargeback rate.

---

## 2026-08-30 — five flags. KYC discrepancy is the clearest case in the set.

```
AGGREGATE (5 flags, adjudicated)
  variant       adj-recall   items   ASK   uncond   INTERNAL
  baseline         100%       233    115     115      118
  asymmetric        97%       124     24       5      100
```

**115 unconditional merchant demands down to 5.**

`FLAG_KYC_DISCREPANCY` is the sharpest illustration produced so far. The trigger:
the entity name on the bank proof does not exactly match the certificate of
incorporation. The merchant has been active **zero months** — they have not
processed a single rupee and are waiting to be activated.

```
  baseline     42 items, 20 unconditional asks
  asymmetric   15 items,  3 asks, ZERO unconditional
```

Baseline demands, for a name-spelling difference on a cheque: the shareholding
pattern, a beneficial-ownership declaration naming everyone above 25%, the
memorandum and articles of association, the full director list with DINs, a
shareholder special resolution, registered-office address proof, a written
business-model description with expected monthly volume, and the contact details
of a named compliance person.

Asymmetric asks for nothing at all unless an internal check fails first:

> *"Compare the two names after normalising for the differences banks commonly
> introduce on their own: abbreviation of the suffix, dropped or added full
> stops, extra or missing spaces, letter case, and truncation caused by bank
> field length limits. **A difference that is fully explained by any of these is
> a formatting mismatch, not an identity mismatch, and needs nothing from the
> merchant.**"*

Then MCA register lookup by CIN, then penny-drop beneficiary name, then
cross-check against the other documents already on file. Only if all four leave
a real difference does it ask — and each of its three asks names the hypothesis
it rules out.

This is the corpus finding, inverted. The complaints describe merchants sent
round after round over exactly this class of paperwork discrepancy. Asymmetric
resolves the common case without contacting them at all.

**Adjudication:** both variants missed KD1 and KD2 on wording; both ruled
present with text quoted. Keyword 67% both, adjudicated 100% both. Ordering
unaffected — as in every round so far.

Two pairs left: THIRD_PARTY_BENEFICIARY, CPV_FAILURE.

---

## 2026-08-30 — six flags. Asymmetric loses badly on the one that matters most.

```
AGGREGATE (6 flags, adjudicated)
  variant       adj-recall   items   ASK   uncond   INTERNAL
  baseline          98%       277    136     136      141
  asymmetric        88%       145     28       5      117
```

**`FLAG_THIRD_PARTY_BENEFICIARY`: baseline 86%, asymmetric 43%.** The worst
result asymmetric has produced, on the highest-stakes flag in the set.

Asymmetric omits four requirements outright: the written agreement governing the
third-party arrangement, invoices showing the merchant actually supplied the
goods, confirmation that no sub-merchant aggregation is occurring, and the
marketplace agreement and seller list. Baseline gets three of those four.

**The cause is rule 2 of the asymmetric prompt** — *"if an internal check could
settle the question, the internal check replaces the request."* For operational
flags that rule is correct: a dead terminal, a volume spike and a name spelling
really are settleable from internal records. For a **relationship** question it
is wrong. Behavioural data can suggest an arrangement exists; it cannot
establish who contracted with whom. Only documents can.

And this is precisely the RBI-named transaction-laundering pattern from
`PROBLEM.md` §3 — settlement to a merchant on behalf of an unrelated third-party
beneficiary. The flag where under-asking is most dangerous is the flag where
asymmetric under-asks most.

**The boundary condition, stated plainly: asymmetric is strongest on operational
flags and weakest on contractual ones.** That is a real limit on the approach,
not a prompt-tuning problem, and it belongs in the write-up as prominently as
the 136-to-5 headline.

**Variant D, if there is time.** Rule 2 needs a carve-out: an internal record
replaces a merchant request only when it answers the same question. Where the
hypothesis concerns a contract, an ownership relationship, or a party outside
the aggregator's book, no behavioural internal check substitutes for the
document. HR4 (customer communication logs) failed the same way — that is now
two failures with one shared cause.

Two failures, one mechanism, found by measurement. That is worth more to this
project than a clean sweep would have been.

---

## 2026-08-30 — pre-registered prediction for CPV_FAILURE

Recorded BEFORE running, so the result cannot be rationalised after the fact.

CPV failure is an **operational** flag — a field agent could not trace the
registered address. Under the boundary condition proposed after
THIRD_PARTY_BENEFICIARY, asymmetric should hold recall here.

But CPV is also the least internally-satisfiable flag in the set: only 1 of 6
requirements is internal, 1 partial, Stage 2 headroom 25%. Premises
photographs, a utility bill, an alternate operating address and availability
for a re-visit genuinely live with the merchant, and no internal record
substitutes for any of them.

**Prediction A (boundary condition holds):** asymmetric keeps recall at or above
83% and issues 3-4 asks, more than on TID (3) or KYC (3), because it correctly
recognises the evidence must come from the merchant. This would confirm that the
failure mode is contractual questions specifically, and variant D is aimed
correctly.

**Prediction B (boundary condition wrong):** asymmetric drops recall with 0-1
asks, meaning rule 2 over-trusts internal records whenever it can construct any
plausible substitute, regardless of flag type. Variant D would then need
rewriting around a different principle.

I expect A, roughly 70/30. Writing that down so the 30 is not quietly forgotten
if B happens.

---

## 2026-08-30 — seven flags complete. Prediction A confirmed; the split is clean.

```
AGGREGATE (7 flags, adjudicated)
  variant       adj-recall   items   ASK   uncond   INTERNAL
  baseline          98%       348    175     175      173
  asymmetric        89%       175     32       5      143
```

**175 unconditional merchant demands down to 5, at 89% versus 98% mean recall.**

(Mean across flags. The 89% is dragged down almost entirely by one flag —
THIRD_PARTY_BENEFICIARY at 43%. On the five operational flags asymmetric is
100%.)

**The pre-registered prediction was A, and A is what happened.** CPV held recall
(100% adjudicated) and issued 4 asks, marginally more than TID or KYC, exactly as
predicted for a flag whose evidence genuinely lives with the merchant. The
boundary condition survives its test.

And the split by flag type is cleaner than expected:

```
OPERATIONAL                       base rec  asym rec  base ask  asym uncond
  FLAG_TID_INACTIVITY                100%      100%        22          0
  FLAG_VOLUME_SPIKE                  100%      100%        15          1
  FLAG_MCC_MISMATCH                  100%      100%        30          2
  FLAG_KYC_DISCREPANCY               100%      100%        20          0
  FLAG_CPV_FAILURE                   100%      100%        39          0

CONTRACTUAL / DOCUMENTARY
  FLAG_HIGH_REFUND                   100%       83%        28          2
  FLAG_THIRD_PARTY_BENEFICIARY        86%       43%        21          0
```

**Five for five at 100% on operational flags, with 3 unconditional asks against
126.** Both failures sit in the other group, and both have the same cause: rule 2
lets an internal behavioural check stand in for a document that establishes a
relationship. Behaviour can suggest an arrangement; only a document establishes
who contracted with whom.

**The result, stated with its limit:**

> On operational risk flags, an asymmetric evidence policy — exhaustive
> internally, minimal and conditional externally — resolves the flag with the
> same completeness as an exhaustive-ask policy while reducing unconditional
> merchant demands by roughly 97%. On flags whose hypothesis is contractual, the
> same policy under-asks and loses recall.

That is a better claim than an unqualified win. It names where it works, where it
does not, and why.

### Caveats that stay attached

- n=1 per flag per variant. No repeats, no variance measured.
- Single non-blind adjudicator who also wrote the ground truth, the prompts and
  the variants. This remains the weakest link.
- The keyword scorer missed on wording in 6 of 7 flags. Adjudication changed
  recall figures in every round but **never once changed the ordering between
  variants**.
- TID's ground truth was expanded after run 1 and is the one fitted flag. The
  other six are not, and the result holds on them.
- Variant B was run on one flag only, then abandoned with its failure diagnosed.

---

## 2026-08-30 — Stage 2 built. It runs. The 100% means almost nothing.

`src/case_store.py` generates 50 cases across 8 stores that share **no common
key** — kyc by entity_id, tickets by phone or email, assets and telemetry by
device serial, txns by MID, settlements by account number, CPV visits by the
address string the agent was dispatched to. `src/stage2_resolve.py` links them.

```
50 cases, 0 false positives, 0 false negatives, mean 4.0 linkage hops per case
32 / 50 resolve with zero merchant contact
```

**The accuracy is close to tautological and I am not going to present it as a
result.** I wrote the scenario plants and I wrote the resolution rules. A high
score means my rules correctly read my own plants. It says nothing about whether
internal resolution works on real merchant data. That warning now prints in the
tool's own output so it cannot be quoted without it.

**What the run does demonstrate**, and this part is real:

1. The linkage traverses systems with no shared key — four hops on average. The
   R036 case needs `mid -> asset_store` (reverse scan) `-> serial ->
   telemetry_store`, and separately `mid -> kyc -> phone -> ticket_store`
   (reverse scan). Nothing in the ticket system knows what a MID is.
2. Every decision carries the path it was reached by. A cleared flag names the
   store, the key and the hops.
3. It caught a conceptual error of mine by failing.

**The error, which is the useful part.** First run: CPV scored 4/8 with two
false positives — the dangerous direction. Cause: my rule treated *"dashboard
logins cluster near the registered address and a device is deployed there"* as
resolving the flag.

It doesn't. **CPV is an action flag, not an explanation flag.** The outstanding
thing is a completed verification, not an understanding of why it failed.
Evidence that the merchant is *probably* there does not let the agent find the
door. Internal evidence clears CPV only when it supplies positive proof the
premises exist and are findable (a signed courier delivery), or shows the agent
went to the wrong locality so a corrected re-visit succeeds without merchant
input.

That distinction was not in the design. It came out of a false positive, and it
generalises: some flags want an explanation, others want an action completed,
and internal evidence substitutes for the first far more readily than the
second.

The two false negatives were a plainer bug — I planted agent-GPS evidence in the
scenario table and never materialised it in any store, so it could not be found.
`cpv_store` now exists.

Next: Stages 3 and 4, then the end-to-end run report.

---

## 2026-08-30 — pipeline runs end to end; the ledger guarantee is now proved, not asserted

```
PIPELINE - 50 cases
  resolved with ZERO merchant contact : 36/50  (72%)
  resolved in ONE round               : 14
  needed more than one round          :  0
  routed to human review              :  4
  requirement-items asked of merchants:  48   (vs 338 ask-everything)  -86%
  max hold on any case                : 14 days, never unbounded
```

**The re-ask guarantee was asserted, not demonstrated.** The pipeline reported
"re-ask rate 0/50", but nothing had *tried* to re-ask — that is an absence, not a
proof. `src/test_ledger.py` now attacks the ledger directly: eight adversarial
tests, three of which try to re-ask a satisfied requirement and receive an
exception naming both the requirement and the store it was originally satisfied
from.

Every test maps to a documented failure in the corpus:

```
cannot re-ask a satisfied requirement      R034  (same questions, 1 month later)
re-ask blocked across later rounds         R034
internal satisfaction blocks the ask       R036  (answer was in our own tickets)
impossible requirement routes to a human   R035  (sub-Rs 20L merchant, GST demanded)
hold duration is always bounded            Razorpay docs (hold with no duration
                                                 is indefinite)
every decision carries its evidence        R036
```

8 passed. That is the difference between *"re-asking did not happen"* and
*"re-asking is impossible"* — the first is a run-time observation, the second is
a property of the data structure.

**Stage 2 satisfying a requirement also prevents it being asked**, which produced
a nice side effect: the GST-impossible path never fires in the pipeline, because
KD5 is satisfied internally before anyone thinks to ask for a GST certificate.
The merchant who legally cannot register for GST is never asked for it. The
fallback still exists and is unit-tested for the case where the ask does go out.

**Honesty markers now print inside the tools themselves**, so the numbers cannot
be quoted without them. Both `stage2_resolve.py` and `pipeline.py` print a block
stating that the resolution rules and the case store were written by the same
person, that the counts show designed behaviour on data designed for it, and
that the measured result in this project is the Stage 1 evaluation — where the
model had not seen the ground truth.

The repo now runs. `python src/case_store.py && python src/stage2_resolve.py &&
python src/pipeline.py && python src/test_ledger.py` goes from nothing to a
decision on 50 cases with an audit trail, on a clean clone, with no API key.

---

## 2026-08-30 — a false claim in my own docstring

Re-read `pipeline.py` to check what actually consumes the recorded responses.
Found its module docstring stating:

> *"The pipeline consumes those recorded outputs rather than calling the API"*

**It does not.** `run_case()` takes `flag["requirements"]` — the frozen checklist
from `data/flag_requirements.yaml`. It never opens `responses_asymmetric/`. The
claim had also propagated into `ARCHITECTURE.md`.

Corrected in `pipeline.py`, `ARCHITECTURE.md` §3 and §8, and the README
limitations. The corrected version is less flattering than the original:

Substituting the frozen checklist for the model's actual output **flatters the
pipeline twice over**. It removes the model's over-production — real Stage 1
returned 16 items for the terminal flag against a 10-item checklist, so the
pipeline never has to cope with the extra six. And it removes wording variance
entirely, which is the same fuzzy-matching problem that made the keyword scorer
miss on 6 of 7 flags. The pipeline sidesteps a difficulty the real system faces.

Fix named rather than hand-waved: id-tagged Stage 1 output, so the model emits
requirement ids alongside its prose and Stage 2 consumes the real thing.

**Third documentation-versus-code discrepancy this project.** The first two were
instrument bugs producing wrong numbers; this one was a wrong sentence about
working code, which is arguably worse — a reviewer who read the docstring and
then the code would have found it, and would have been right to discount
everything around it.

Rule going in: any sentence claiming what the code does gets checked against the
code before it ships. The same discipline already applied to numeric claims after
the §7 stale-figures incident.

---

## 2026-08-30 — the A/C comparison is less controlled than I described it

Writing the README for `experiments/stage1/`, I claimed the two prompts were
"identical except the constraint block" — then actually diffed them before
shipping the sentence. **Three blocks differ, not one:**

```
28 of 31 baseline lines identical (role, alert text, trigger, merchant
profile, output format - all byte-identical)

differing:
  task statement   "the COMPLETE set of evidence"
                -> "the evidence required to resolve THIS SPECIFIC FLAG"
  framing line     "Be exhaustive..."
                -> "The two halves of the answer follow OPPOSITE rules."
  the constraint   1 sentence -> 13 lines
```

All three express the same intervention, so the comparison is still meaningful —
but it is a **prompt-design comparison, not a single-variable ablation.** The
result cannot be attributed to the constraint block alone. A stricter experiment
would vary one at a time.

Corrected in the experiments README, with the differing blocks shown in a table
so a reader sees the imprecision without having to run the diff.

**Fourth documentation-versus-reality discrepancy, and the second I caught by
verifying my own sentence before publishing it rather than after.** The pattern
across all four is the same: prose written from memory of what the artefact
should contain, rather than from the artefact. The rule already applied to
numbers and to code claims now applies to claims about data too - if a sentence
describes a file, open the file.

---

## 2026-08-30 — the README now checks itself

Four times in this project a sentence written from memory disagreed with the
artefact it described: stale figures in `PROBLEM.md` §7, wrong theme counts, a
`pipeline.py` docstring claiming it read files it never opens, and an overstated
"byte-identical" claim about two prompts. Every one was caught by hand, and the
fourth only because I happened to verify before publishing rather than after.

`src/verify_claims.py` closes the loop. It recomputes all 23 headline figures
from the files that produce them — `comparison.json`, `pipeline.json`,
`stage2.json`, the CSV, the YAML, and the test file — then greps the README for
the load-bearing ones and **exits 1 if any is missing**.

```
OK - all 7 headline values in README.md match the artefacts.
```

Usable as a pre-commit check. It also emits `results/claims.md`, a table of every
claim, its value, the file that substantiates it, and the command that
regenerates it.

The point is not that the numbers are right today. It is that they cannot
silently stop being right — which is the failure mode that actually occurred here
four times.

---

## 2026-08-30 — the review queue existed only as a promise

`PROBLEM.md` and `ARCHITECTURE.md` both said the system "emits a ranked queue
with evidence and a recommended action, and a human approves". That queue lived
entirely in `pipeline.json`. There was nothing to look at, and the design's
central safety property — a human decides — was invisible.

`src/build_queue.py` renders it from the run output to a self-contained
`results/queue.html`. No server, no network calls, no scripts. Cannot drift from
the results because it is generated from them.

**One thing it exposed immediately.** The first version grouped cases by
`outcome`, which produced 46 "released" and 4 "escalated". That collapses the
entire finding: 32 of those 46 were released **without contacting the merchant**
and 14 only after a round. Released-vs-not is not the distinction that matters —
**contacted-vs-not is.**

Relabelled around merchant contact:

```
  32   merchant never contacted     (green)
  14   asked once, cleared          (amber)
   4   escalated to an analyst      (red, sorted to top)
   0   needed a second round
```

Escalations sort first, because that is what an analyst opens the queue to find.

A UI decision that hides the result is a bad UI even when every number in it is
correct. **Show the thing that distinguishes, not the thing that summarises.**

---

## 2026-08-30 — the review queue exposed a claim the code did not implement

Rendered the queue, looked at it, and found `C040 Third Party Beneficiary ·
RELEASED · 1 ROUND`. A third-party-beneficiary case — the RBI-named
transaction-laundering pattern, and the flag class this system scores **worst**
on (43% recall) — auto-releasing the moment documents arrived.

Checked the code. `hypothesis_class` is generated in the case store, carried
through `stage2_resolve.py`, and **branched on nowhere**. `ARCHITECTURE.md` §3
stated flatly that routing selects the policy by class. It did not.

**Fifth documentation-versus-code discrepancy.** Found by looking at the output,
not by reading the code — which is the argument for building the queue at all.
Fifty rows of JSON hid it; fifty cards did not.

**Fixed in the code, not in the prose.** A contractual flag that could not be
resolved internally now closes to `human_review` rather than releasing:

```
  C037/C038  formatting variation      released, 0 contact   (unchanged)
  C039/C040  partner personal account  human_review, 1 round (was: released)
  C041/C042  unrelated beneficiary     human_review, 0 contact (unchanged)

  human review: 4 -> 6
```

The justification is the measurement: whether a beneficiary relationship is
legitimate is a judgement about a contract, and the Stage 1 evaluation showed
this system is at its worst on exactly that question. So it does not make the
call.

**And the architecture doc now separates two routing decisions that it had
merged into one.** Prompt selection by class is *designed and not implemented* —
the pipeline never runs Stage 1, so it has no prompt to select. Outcome routing
by class is *implemented*. Presenting both as done would have overclaimed.

Fifth time, same root cause: a sentence describing intent, written before the
code caught up, never revisited. The rule now covers data, numbers, code
behaviour — and evidently still needs the artefact opened every time.

---

## 2026-08-31 — a card that contradicted itself

Reviewing the rendered queue: `C040` showed

```
  ESCALATED     "Needs an analyst decision · merchant not contacted"
  ROUNDS 1      ASKED OF MERCHANT 4      REQUESTED: TP2, TP4, TP5, TP6
```

The label said the merchant was not contacted. The card underneath showed four
items requested in one round. Both cannot be true.

**Cause: the routing fix made earlier today created a second kind of escalation
and I reused the old label for both.**

```
  escalated BEFORE any contact   C041, C042  unrelated beneficiary, caught internally
  escalated AFTER one round      C039, C040  contractual - documents received, but the
                                             relationship judgement is not automatable
```

These are not the same thing from the merchant's side. One cost them nothing;
the other cost them a round. Collapsing them into "merchant not contacted" was
false for half the cases.

Split into `escalated_clean` and `escalated_after_ask`, with
escalated-after-ask sorted first — an analyst reviewing submitted documents is
holding someone's money *and* has their evidence waiting, so it is the most
urgent thing in the queue.

```
   2  ESCALATED · 1 ROUND    documents supplied, analyst must judge
   4  ESCALATED · 0 CONTACT  caught internally, merchant never involved
  12  RELEASED · 1 ROUND
  32  RELEASED · 0 CONTACT
```

**Caught by reading the screen, not by any check I wrote.** The claim verifier
compares numbers to artefacts; it cannot notice that a caption contradicts the
numbers beside it. Every automated check in this repo passed on that card.

Second time in an hour the queue has surfaced something the JSON hid. I built it
to make the work visible; its actual value has been making wrong things visible
to me.

---

## 2026-08-31 — a control that looked like a control and was not one

Clicked the second stat card in the queue expecting it to filter. Nothing
happened.

I had styled the first stat card dark navy to mark it as the most important
number. But dark reads as **selected**, not as *important*. Six cards in a row
with the first one filled = a tab strip with tab one active. So the natural move
is to click card two — and nothing happened, because the real filters were a row
of pale pills underneath, styled weaker than the thing that looked interactive.

Not a user error. A control that looks like a control and is not one, with the
actual controls given less visual weight than the decoration.

**Fixed by making them what they appeared to be.** The stat cards are now the
filters. `Second rounds · 0` is explicitly `disabled` and greyed - nothing to
filter to, and a button that does nothing on click is precisely the defect being
removed.

Header rebalanced at the same time: title and lede left, the headline number
right against a rule, container widened 1000 -> 1120px so the row does not wrap.

**Third defect the rendered screen has surfaced**, after the laundering case
auto-releasing and the card that contradicted its own numbers. All three passed
every automated check in the repo, because none of them was a wrong number - they
were a wrong decision, a wrong caption, and a wrong affordance. No test I can
write catches those. Someone has to look.

---

## 2026-08-31 — queue rebuilt as master-detail

Looked at a master-detail mockup - case rail left, one case open right.
It is a better layout than the stacked cards I built, for a reason worth
recording: **fifty cards in a column cannot be scanned.** You cannot see the
shape of the queue, cannot compare cases, and cannot find one without scrolling.
A rail carrying `id · flag · rounds · hold · burden-avoided %` gives all of that
at a glance, and the detail pane then has room to breathe.

Rebuilt accordingly. Also adopted from the mockup: evidence-path steps as
separated numbered rows rather than a code block, and requested items as chips
rather than a comma list. Both are easier to read and neither costs anything.

Kept from mine: the burden comparison, which is the point of the system and was
not in the mockup at all.

**Deliberately did not adopt the mockup's data.** It showed case names like
"Settlement Drift", "Device Reassignment", "Chargeback Cluster", and states like
"awaiting merchant · 3d hold". None exist in this project - the seven flag types
are fixed in `flag_requirements.yaml` and holds are 0 or 14 days. Rendering
invented cases would have made the queue the only artefact in the repo not
generated from the run.

Side effect: the file shrank 86 KB -> 47 KB. Embedding the case data once as JSON
and rendering on demand beats emitting fifty fully-rendered cards.

---

## 2026-08-31 — the verifier had a boundary, and the boundary was the bug

Re-reading `README.md` against the run: it states `routed to human review: 4`
while the pipeline produces 6. Stale since the contractual-routing change
earlier today. `results/queue.html` was already correct at 6; only the README
had drifted.

**The number being wrong is not the interesting part. The verifier not catching
it is.**

`verify_claims.py` existed precisely to stop a README figure going stale. It
checked five hand-picked values. "Routed to human review" was not among them, so
it drifted inside a results block the check never opened. A hand-picked list has
an **invisible boundary**, and nothing marks where it falls - the tool reported
"OK, all 7 headline values match" while a wrong number sat four lines away.

Rewritten. It now parses every `label : number` line inside every fenced block in
the README and pairs each with a computed claim by label. Two consequences:

- a stale figure fails the run (verified by deliberately corrupting one and
  confirming exit 1)
- a quoted figure with **no computed claim behind it** is reported as unbacked,
  so the boundary announces itself instead of hiding

First run under the new check found two unbacked figures - "resolved in ONE
round" and "maximum hold on any case". Both now have claims. Output is
`6 quoted figures match; none unbacked`.

**Also corrected a real granularity inconsistency the review nearly found.**
`ARCHITECTURE.md` said `hypothesis_class` marks each *flag*. It marks each
*scenario*: `FLAG_THIRD_PARTY_BENEFICIARY` is `{operational: 2, contractual: 4}`.
Stage 1 classes the whole flag type conservatively because at synthesis time the
flag is all it knows; outcome routing classes the individual case because Stage 2
has since established which kind it is. That is defensible - more information
later than earlier - but it existed only in my head. Now in §3 with the
consequence stated: C037/C038 release without an analyst, and are permitted to,
because internal evidence showed there is no third party to judge.

Sixth documentation-versus-reality discrepancy. The lesson is narrower than the
previous five: **a checking tool with a hand-maintained scope will eventually be
narrower than the thing it checks, and will report success from inside its own
blind spot.** Scope has to be derived, not listed.

---

## 2026-08-31 — UI pass; one of my own fixes was logically impossible

Seven changes to `build_queue.py`. Six were straightforward. One exposed a hole
in my own proposed solution.

**The hole.** Wanting a build stamp so a stale page announces itself, I first
proposed embedding the build time and the source mtime and having the page "say
so loudly" if they diverged. That cannot work: **queue.html is static with no
network** - a property the page itself advertises - so at view time it cannot
read `pipeline.json` to compare against. Whatever is baked in is frozen at build
time. The page can never learn its data moved.

I had proposed runtime detection inside an artefact with no runtime.

**What works instead.** Hash `pipeline.json` + `stage2.json` at build time into an
HTML comment; `verify_claims.py` recomputes and fails on mismatch. That puts the
check in the only tool that can run it, and - answering my determinism objection
- a hash of unchanged data is unchanged, so rebuilds stay byte-identical and git
stays quiet. Verified adversarially: mutating `stage2.json` without rebuilding
gives

```
STALE PAGE  results/queue.html was built from data fingerprinted b308ff748df2;
            the repo now holds 762adfbfb22a.
            Rebuild:  python src/build_queue.py
FAIL - results/queue.html built from older data.
```

Exit 1 with the README untouched, so a stale page fails on its own.

**The other six:**

1. **Requirement chips show text, not ids.** `TP2` became "Written agreement
   governing the arrangement". An internal identifier had been leaking into a
   user-facing surface and telling an analyst nothing.
4. **Escalated cases get equal-weight buttons** - `Uphold hold` / `Release`, both
   secondary. Previously every case showed a blue "Approve release", including
   ones the system had explicitly refused to auto-release. Same class of defect
   as the stale 4-vs-6: the surface asserting something the design denies. Went
   further than the first idea, which was to relabel with uphold as primary;
   neither should be primary, because the system holds no preference.
5. Escaped the chip and impossible-requirement inserts. No live bug; consistency.
3. Removed an empty `<h4>` used as a spacer. Dead markup reads as a defect.
6. Hop count added to the rail. Included because it tells an analyst how many
   separate systems were consulted before deciding - not because it makes the
   6-hop demo case easier to find, which was the reason offered.
7. Rail rows are now real `<button>` elements rather than divs with `tabindex`.
   Keyboard access and screen-reader semantics come free and it needs *less* JS.

**Pattern worth keeping.** Two of these - the frozen-comparison hole and the
"approve release" button on a case the system declined to decide - are the same
failure as the stale README figure: **an artefact asserting something the system
does not support.** Numbers, captions, affordances and now button labels have all
done it. The verifier covers the numbers; nothing covers the rest except reading
the thing.

---

## 2026-08-31 — "Uphold hold" needed explaining, so it was the wrong words

Had to stop and work out what the buttons meant. That is the finding: if the
person who built the screen has to work out what its primary action does, an
analyst will too.

`Uphold hold` is correct risk-and-compliance register and it is also clumsy to
read - *uphold... hold* - and opaque unless you already work in the field. It
carried domain vocabulary at the cost of being understood.

```
  Uphold hold   ->  Keep on hold
  Release       ->  Release funds
```

The recommended-action line now uses the same words as the buttons rather than
different ones for the same act: *"Review the submitted documents, then release
the funds or keep them on hold."*

Both remain equal-weight on escalated cases. The reason is unchanged - the system
declined to decide, so the interface must not express a preference. Only the
labels changed.

**The trade-off is real and would flip in production.** On a live ops console,
where analysts share a vocabulary, the domain register wins. Here it cost
comprehension for no gain, so clarity wins.

---

## 2026-08-31 — the pipeline was escalating by reading the answer key

PROBLEM.md names the escape rate as headline metric #2 and the pipeline summary
never printed it. Checking why it would obviously be zero exposed the real
problem:

```python
if case["should_escalate"]:
    led._log("escalate", reason="scenario carries an escalation label")
    return led.close("human_review", ...)
```

**The pipeline branched on the ground-truth label.** `should_escalate` is the
answer key. Escape rate was zero not because bad actors were detected but
because the system was told who they were. At least the log message admitted it
- "scenario carries an escalation label" - so this was transparent label
leakage rather than hidden, but printing "escape rate: 0/50" on top of it, as
suggested, would have converted an unreported metric into a reported fake one.

**Fixed: escalation is now detected, and the label only scores it.**
`detects_escalation()` in stage2_resolve.py acts on the linked evidence alone -
a card-testing signature (decline rate over 30%, BIN concentration over 50%),
or a beneficiary that fails entity matching AND was changed after onboarding
AND has no settlement history. `run_case` no longer reads the label at all;
`main()` reads it afterwards to grade the detections:

```
ESCAPE RATE            : 0/4   (labelled bad actors that were RELEASED)
detected + escalated   : 4/4
false escalations      : 0
```

**And the blindness is proved, not asserted.** New adversarial test: run all 50
cases with `should_escalate` flipped both ways; outcome, rounds and reason must
be identical. 9/9 tests pass. The old code fails this test immediately.

The caveat stays attached: on designed data, the detection rules were written
against the same scenarios they detect. 4/4 here is a correctness check of the
wiring, not evidence the thresholds survive real traffic.

**Seventh discrepancy, new category.** Previous ones were artefacts asserting
things the system did not support. This one was the system itself asserting a
competence it did not have - the metric was honest only because it was never
printed. Deciding to print it was not what found the leakage; asking *why* the
number would be zero did.

---

## 2026-08-31 — the pipeline consumes real model output for the first time

The central disclosed simplification - "the model's words never enter the
pipeline" - is now closed for the flagship flag.

**The mode.** A 16th manual run, deliberately different from the 15 blind ones:
the model was shown the TID requirement library (ids + text) and a vocabulary of
eight internal findings, and asked to emit an adjudication plan - one
disposition per id. Same protocol as ever: Claude, High, fresh chat, pasted
text. Response checked in verbatim under
`experiments/stage1/responses_idtagged/`, with a NOTE.md stating loudly that
this run is never scored for recall - it was handed the library, so recall
against it is meaningless.

**The plan it produced:**

```
TI1  CHECK                                            (tickets)
TI2  CHECK                                            (telemetry)
TI3  ASK_IF device_deployed                           (possession)
TI4  ASK_IF not (open_hardware_ticket or device_fault_code)
TI5  ASK                                              (reactivation intent)
TI6-TI10  CHECK
```

TI4's gate is the R036 remedy expressed as machine-evaluable logic: only ask the
merchant why the terminal is inactive if our own systems do not already explain
it. Nobody wrote that gate - the model did, given the vocabulary.

**Wiring.** `src/stage1_plan.py` parses the plan (tokens whitelisted before any
gate is evaluated; no builtins in the eval namespace) and computes the eight
findings from a case's linked evidence. For TID cases the pipeline asks exactly
what the plan says to ask; the other six flags stay on the frozen checklist,
restated as such in the pipeline docstring, ARCHITECTURE §3 and the README.

**Measured effect: items asked fell 48 -> 46.** The two genuinely-dormant cases
now ask 3 items instead of 4. The one no longer asked is TI1 - ticket history.
The frozen-checklist pipeline had been asking MERCHANTS for ticket information
whenever Stage 2 found no ticket, treating an empty internal result as an
unanswered question. The plan treats "checked: none found" as the answer it is.
A small number, but it is the id-tagged mode catching a real defect in the
simplification it replaces.

**Honesty note on the response itself.** The model violated the strict format -
it echoed the helper line "answer this from the aggregator's own records,
always" under every CHECK despite "nothing after the last line". Even an
id-tagged format produced noise; the parser tolerates it. Worth keeping: it is a
live demonstration of why free-prose parsing (the alternative this mode
replaces) would have been so much worse.

All checks green after the change: 9/9 adversarial tests including label
blindness, queue fingerprint current, 8 README figures verified, none unbacked.

## 2026-09-01 — CI: a clean machine reruns the whole argument

Added `.github/workflows/verify.yml` and `requirements.txt` (one line: pyyaml).
The workflow does not just run tests - it rebuilds the case store from the
seed, reruns Stage 2 and the pipeline, rebuilds the queue page, audits the
ground truth, RESCORES the 16 checked-in model responses, runs the 9
adversarial tests, and finishes with verify_claims.py checking every figure
quoted in the README against what it just produced. No API key exists in the
pipeline, so all of this runs on a public runner with no secrets.

The point: a reviewer does not have to trust that my numbers match my code.
A fresh machine holding nothing but a clone of the repo checks it on every
push.

Deliberately left out: linting. A lint step added the night before submission
signals checkbox-ticking, not discipline, and no figure in the README depends
on it.

Ran the exact sequence locally in workflow order before committing the file:
all steps green, 9/9 tests, 8 README figures verified, exit 0. The badge in
the README stays grey until the repo is pushed to GitHub - noted here so a
grey badge is not mistaken for a failure.

## 2026-09-01 — the eighth documentation-vs-reality discrepancy

Reviewing flag_requirements.yaml for comments that could be cut. Found the
opposite: a comment that had gone stale.

LIMITATIONS #5 still read "An LLM-judge scorer should be run as a cross-check
before any number is published." That cross-check WAS run - by hand, not by an
LLM judge. results/adjudication.md rules every scorer miss with the candidate
text quoted, dated 2026-08-30, and both numbers are reported side by side
everywhere. The file was recommending future work that was already finished.

This is the same defect I fixed in the stage1_eval.py docstring, in a second
file. Fixing a sentence in one place and leaving its twin elsewhere is exactly
how the two drift apart. Rule for the rest of the project: when a claim is
corrected, grep for the claim, not just the file.

Rewritten to say what was actually done, and to keep the limitation that
genuinely remains - a single non-blind adjudicator who also wrote the ground
truth and the prompts. Weaker than an independent judge, stated as such.

Two smaller header inaccuracies fixed at the same time:
  - `internally_satisfiable` was documented as "TRUE if ..." while the field
    takes three values. Twelve lines below, LIMITATIONS #3 said three. Now the
    FIELDS block says three.
  - `note` appears on 13 requirements and was not in the FIELDS block at all.
    Now documented, including that no code reads it - it is for human readers.
  - REVIEW STATUS said v1, but TI7-TI10 and a TI6 alias were added after run 1.
    Now v2 (frozen 2026-08-30), with the reason run 1 and run 2 are not
    comparable stated in the header rather than only at the bottom.

Decided AGAINST removing any commentary. Nothing in the code reads these notes;
they exist for the reviewer deciding whether the ground truth is trustworthy.
Without them the file is 47 assertions with no provenance. The TI1 note carries
the R036 argument at the point it is encoded, and the TI6 note admits an alias
was added after seeing model output - self-incriminating, and the most useful
line in the file for that reason.

Re-ran everything after the edit: 7 flags / 47 requirements unchanged, YAML
parses, audit and compare clean, 9/9 tests, queue fingerprint current, 8 README
figures verified.

## 2026-09-01 — three wrong numbers in my own prose, verifier green throughout

Writing the README captions for the two queue screenshots, I put three wrong
numbers in the surrounding prose. "Six linkage hops across FOUR systems" - it is
six: txn, kyc, asset, telemetry, ticket, settlement. The same error then turned
up at line 193, in a second place I had not grepped after fixing the first. And
"recomputes all 23 headline figures", written when claims() was shorter; it
returns 27.

**verify_claims.py passed on all three.** It scans "label : number" lines inside
fenced blocks. A number inside a sentence is invisible to it.

That is a second boundary on the same tool. The first was a hand-picked list of
values, fixed by deriving the scope from the README itself. This one is not
fixable the same way - it is the difference between a figure quoted in a results
block and arithmetic written into a paragraph. The verifier covers the first.
Prose numbers are checked by nobody.


## 2026-09-01 — the staleness check could fail on a page that was current

The queue's source fingerprint hashed raw bytes of pipeline.json and
stage2.json. Git stores those with LF and checks them out as CRLF on Windows, so
the hash was platform-dependent: a page built on one OS reports STALE PAGE on
another against byte-identical data.

Noticed because the fingerprint in queue.html moved without any result changing.
Confirmed the three files differ from HEAD only in line endings - identical
after normalising, 2831 CRLF pairs against 0.

Both computations now strip CRLF before hashing, in build_queue.fingerprint()
and in verify_claims. Verified the hash is identical for the same data stored
either way.

**A check that can fail on correct data is worse than no check.** A missed
defect is a gap; a false alarm discredits a run that was right, and this one
fires on the tool the README points at to prove nothing has gone stale. CI never
saw it because it rebuilds both files on one machine - the failure only appears
for someone who clones and verifies without rebuilding, which is exactly the
reviewer the check exists for.
