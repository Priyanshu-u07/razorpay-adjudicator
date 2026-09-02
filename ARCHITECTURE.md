# Architecture

How the adjudicator is built, and — for every non-obvious decision — the
measurement or corpus evidence that forced it.

This document was written **after** the evaluation, deliberately. Writing it
first would have described a system whose central assumption had not been tested,
and two of the design decisions below reverse what I would have written on day
one.

---

## 1. Shape

```
                    RISK FLAG (mid, flag_type, trigger)
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │  STAGE 1                │   LLM
                    │  requirement synthesis  │   closed action space
                    │                         │   output: checklist
                    └────────────┬────────────┘   (prompt selection by
                                 ▼                 hypothesis_class: DESIGNED,
                    ┌─────────────────────────┐    NOT IMPLEMENTED - see §3)
                    │  STAGE 2                │   entity resolution
                    │  internal satisfaction  │   NO LLM
                    │                         │   output: satisfied[] + path[]
                    └────────────┬────────────┘
                                 │
                 resolved? ──yes──▶  RELEASE  (0 merchant contact, hold 0d)
                                 │
                 escalate? ──yes──▶  HUMAN    (0 merchant contact, hold ≤14d)
                                 │ no
                                 ▼
                    ┌─────────────────────────┐
                    │  STAGE 3                │   templated
                    │  consolidated request   │   outstanding items only
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │  STAGE 4                │   append-only ledger
                    │  stateful verification  │   re-ask raises an exception
                    └────────────┬────────────┘
                                 │
      impossible requirement? ───▶  HUMAN
                                 │
      hypothesis_class ==     ───▶  HUMAN    ◀── outcome routing: IMPLEMENTED.
        "contractual"?           │            A contract judgement is never
                                 │            made automatically.
                                 ▼
                              RELEASE
```

The system's only powers are **clear faster** or **escalate to a human**. It
cannot freeze anyone, cannot extend a hold, and cannot issue a second request
for anything already satisfied.

---

## 2. Decisions, and what forced them

| Decision | Forced by |
|---|---|
| Attack adjudication, not detection | Razorpay already ships detection. Their [Agentic Platform](https://razorpay.com/blog/razorpay-agentic-platform/) covers onboarding, integration, reconciliation, revenue recovery and disputes — and nothing on risk. Competing on detection is competing with their data. |
| Stage 1 asks **once**, completely | Corpus: requirements issued serially at 48–72h intervals, funds held throughout (R031–R034). |
| Completeness is **not** enough — proportionality too | Stage 1 run 1: 100% recall, 51 requirements for a broken terminal, **22 demanded from the merchant**. A wall instead of a corridor. |
| Proportionality must be **asymmetric** | Variant B pruned internal checks −48% and merchant asks only −32%. Backwards. One necessity test applied to two populations with opposite cost structures. |
| Positive rules, never prohibition lists | Variant B was told not to request KYC refresh, licences or tax filings. All came back wrapped in *"if the one on file has expired"*. |
| **Route by hypothesis class** | Asymmetric holds 100% recall on 5 operational flags and drops to 43% on the RBI-named third-party-beneficiary pattern. Behaviour can suggest an arrangement; only a document establishes who contracted with whom. |
| Stage 2 before any merchant contact | R036 — the exculpatory evidence was in the aggregator's own ticket system. |
| Satisfied ⇒ structurally un-askable | R034 — *"Razorpay replied with the same irrelevant questions which was asked 1 month before."* |
| Impossible requirements route to a human | R035 — a sub-₹20L merchant, legally ineligible for GST registration, was told funds would be released on producing one. |
| Holds always bounded | Razorpay's own docs: a hold with no duration passed is **indefinite**. |
| Every decision carries its path | The complaint is never "you flagged me", it is "nobody told me why". |

---

## 3. Stage 1 — requirement synthesis

**Input:** flag type, trigger text, merchant profile.
**Output:** a checklist, each item tagged `[INTERNAL]` or `[ASK]`, asks carrying
the hypothesis they rule out and any gate condition.

The prompt applies **opposite rules to the two halves of the answer**:

> **INTERNAL — be exhaustive.** Anything establishable from our own records costs
> the merchant nothing. Omitting one is a pure loss: it means asking for
> something we could have answered ourselves.
>
> **ASK — be minimal.** Include an item only if you can name the specific
> hypothesis about *this* flag it rules in or out, **and** no internal record
> could answer it. If an internal check could settle the question, the check
> replaces the request.

Three variants were built and measured ([results](results/adjudication.md)):

| variant | recall | unconditional asks | verdict |
|---|---|---|---|
| A · ask everything | 98% | 175 | complete, unusable |
| B · single necessity test | 50%¹ | 15 | pruned the wrong side |
| C · asymmetric | 89% | **5** | shipped |

¹ one flag only; abandoned once the failure was diagnosed.

**Routing — two decisions, and only one of them is implemented.**

**The two stages classify at different granularity, deliberately.**

| stage | classifies | why |
|---|---|---|
| **Stage 1** | the whole **flag type** | All that is known at synthesis time is the flag. `FLAG_THIRD_PARTY_BENEFICIARY` is treated as contractual throughout — that is where the 43% recall figure comes from. |
| **Outcome routing** | the individual **case** | By this point Stage 2 has established *which kind* of case this is. In `case_store.json`, `hypothesis_class` is set per scenario: a beneficiary mismatch that turns out to be a dropped `M/s` prefix is `operational`; one where the account belongs to a partner personally is `contractual`. |

So `FLAG_THIRD_PARTY_BENEFICIARY` is `{operational: 2, contractual: 4}` in the
case store, while Stage 1 treats all six as contractual. That is not an
inconsistency — it is the system acting on more information later than it had
earlier. Stage 1 must be conservative because it cannot yet tell the two apart.

The consequence worth stating plainly: **C037 and C038 release with no analyst
even though the flag is third-party-beneficiary.** They are permitted to, because
internal evidence established there is no third party — the name matched after
normalisation. No contract judgement is being automated; the system determined
there was no contract question to judge.

The measurement supports two consequences:

**1. Prompt selection — designed, not implemented.** `operational` should get
variant C, `contractual` variant A, because C under-asks exactly where documents
are irreplaceable. The pipeline does **not** do this, for the reason in the
simplification below: it never runs Stage 1, so it has no prompt to select.
Implementing it requires the pipeline to call the model, which is the same change
as consuming Stage 1's real output.

**2. Outcome routing — implemented** (`src/pipeline.py`, `run_case`). A
contractual flag that could not be resolved internally does **not** auto-release
when documents arrive. Whether a beneficiary relationship is legitimate is a
judgement about a contract, and the measurement says this system is at its worst
exactly there. It closes to `human_review` with the evidence and the submissions
attached.

The distinction matters: the second is a real mitigation, the first is a stated
intention. Treating them as one would overclaim.

**A simplification, stated plainly — now closed for one flag.** All 15 blind
model runs are checked in verbatim under
[`experiments/stage1/`](experiments/stage1/). The pipeline does **not** parse
that free text — for six of seven flags it takes the frozen checklist in
`data/flag_requirements.yaml` as Stage 1's output.

For **`FLAG_TID_INACTIVITY`** the mechanism is demonstrated for real: a 16th
manual run — a different mode, the model shown the requirement library and asked
to emit an id-tagged adjudication plan (`TI1 CHECK`, `TI4 ASK_IF not
(open_hardware_ticket or device_fault_code)`, …) — is checked in under
`experiments/stage1/responses_idtagged/` and parsed by `src/stage1_plan.py`. Its
gates are evaluated per case against the linked evidence. Because the model was
handed the library, this run is **never scored for recall** — see the NOTE.md
beside it. Measurable effect: the two genuinely-dormant TID cases now ask 3
items instead of 4, because the plan treats "internal check found no ticket" as
an answer, where the frozen checklist asked the merchant for their own ticket
history.

That approximates Stage 1 closely on operational flags, where variant C recovers
100% of the checklist. It also **flatters the pipeline in two ways**: it removes
the model's over-production (16 real items versus 10 checklist items on the
terminal flag), and it removes wording variance entirely — the same fuzzy-matching
problem that made the keyword scorer miss on 6 of 7 flags. The pipeline sidesteps
a difficulty the real system would face.

The fix for the remaining six is the same mechanism: have the model emit
requirement ids alongside its prose. It is demonstrated above on
`FLAG_TID_INACTIVITY`; extending it is one manual run per flag, and the other
six intentionally stay on the frozen checklist rather than being half-closed
silently (§8).

---

## 4. Stage 2 — entity resolution

The technical core, and the reason R036 happened.

**A flag arrives carrying a MID. The evidence that clears it does not live under
a MID.** Each internal system was built for its own purpose and keys records the
way that purpose demanded:

```
   store              primary key       references the merchant by
   ─────────────────────────────────────────────────────────────────
   txn_store          mid               mid                    ← the flag's key
   kyc_store          entity_id         entity_id
   asset_store        device_serial     assigned_mid
   telemetry_store    device_serial     nothing. no MID at all.
   ticket_store       ticket_id         phone OR email
   settlement_store   account_number    mid
   cpv_store          visit_id          the address string only
   prior_case_store   case_id           mid
```

Resolving one flag traverses this:

```
                          ┌──────────────┐
              (direct)    │  txn_store   │
   mid ──────────────────▶│    [mid]     │
    │                     └──────┬───────┘
    │                            │ .entity_id            ┌──────────────┐
    │                            └──────────────────────▶│  kyc_store   │
    │                                                    │ [entity_id]  │
    │                                                    └──┬────────┬──┘
    │  reverse-scan       ┌──────────────┐    .phone/.email │        │ .address
    ├────────────────────▶│ asset_store  │    reverse-scan  │        │ reverse-scan
    │  on assigned_mid    │  [serial]    │                  ▼        ▼
    │                     └──────┬───────┘         ┌────────────┐ ┌──────────┐
    │                            │ serial          │ticket_store│ │cpv_store │
    │                            ▼                 │ [ticket_id]│ │[visit_id]│
    │                     ┌──────────────┐         └────────────┘ └──────────┘
    │                     │  telemetry   │
    │                     │   [serial]   │  ← 2 hops. this store has never
    │                     └──────────────┘    heard of a MID.
    │  reverse-scan       ┌──────────────┐
    └────────────────────▶│ settlement   │
       on mid             │  [account#]  │
                          └──────────────┘
```

Mean **4.0 linkage steps per case**. A lookup would be 1.

The R036 verdict needs two independent branches to meet: `mid → asset_store →
serial → telemetry_store` produces `PRINTER_HW_FAULT`, and `mid → kyc → phone →
ticket_store` produces an open hardware ticket 120 days old. Neither alone
clears the flag. Together they say *the aggregator caused the inactivity.*

**Every hop is recorded.** A cleared requirement names the store, the key and the
path. That is the audit trail, and it is a by-product of the resolution rather
than a separate logging concern.

**Satisfying a checklist item is not clearing the flag.** `explains()` holds
per-flag rules that ask whether the linked evidence accounts for the *anomaly*.
Collecting nine records and explaining nothing releases nobody.

### One rule that was wrong, and the distinction it produced

First run, CPV scored 4/8 with **two false positives** — the dangerous direction.
The rule treated *"dashboard logins cluster near the registered address and a
device is deployed there"* as resolving the flag.

It does not. **CPV is an action flag, not an explanation flag.** What is
outstanding is a *completed verification*, not an understanding of why one
failed. Evidence that the merchant is probably there does not help the agent
find the door. Internal evidence now clears CPV only on positive proof the
premises exist and are findable (a signed courier delivery), or proof the agent
went to the wrong locality (a corrected re-visit will succeed unaided).

That distinction was not in the design. It came out of a false positive, and it
generalises: internal evidence substitutes readily for an *explanation* and
poorly for an *action*.

---

## 5. Stage 3 — consolidated request

Everything outstanding, once, with formats attached. Items satisfied by Stage 2
are already gone; items gated on an internal result appear only if the gate
fired.

Format specifications ship **with** the request. The corpus records a merchant
asked for *"a board resolution in a specific format"* — with the format supplied
afterwards, which is a second round wearing the clothes of a first.

---

## 6. Stage 4 — the ledger

Append-only. Three fields: `satisfied` (requirement → source), `asked`
(requirement → round), `impossible` (requirement → reason).

```python
def request(self, req_ids):
    clash = [r for r in req_ids if r in self.satisfied]
    if clash:
        raise RequirementAlreadySatisfied(...)   # names item and original source
```

**The guarantee is a property of the data structure, not a rule someone
remembers.** `re-ask rate: 0` across 50 cases is an absence — nothing tried.
`src/test_ledger.py` attacks it directly: nine tests, three of which attempt a
re-ask and receive an exception. Each maps to a corpus failure (R034, R035,
R036).

`mark_impossible()` exists because a loop that cannot recognise an unsatisfiable
requirement runs forever. It logs `action: route_to_human` and terminates the
case.

Hold duration is a bounded function of outcome — `released` 0d,
`awaiting_merchant` 7d, `human_review` 14d. Never a constant applied to everyone,
never unbounded.

---

## 7. Where AI is used, and where it deliberately is not

| Stage | AI? | Why |
|---|---|---|
| 1 · requirement synthesis | **Yes** | Inferring the complete evidence set from a fuzzy risk reason is genuine judgement over unstructured input. Nothing else does it. |
| 2 · entity resolution | **No** | Deterministic record linkage. An LLM here would be slower, non-reproducible, and would remove the audit trail's guarantee that a link is real rather than plausible. |
| 2 · resolution rules | **No** | These decide whether money is released. They must be inspectable, versionable and identical every run. |
| 3 · request assembly | **No** | Templated. The content was already decided in Stage 1. |
| 4 · ledger | **No** | The re-ask guarantee must be structural. A model that usually does not re-ask is not a guarantee. |

**The restraint is the design.** One LLM call per flag type, at the only point
where the input is unstructured and the output requires domain inference.
Everything touching money is deterministic and reviewable.

---

## 8. What production would need that this does not have

- **Real connectors** in place of the synthetic store, with the same key
  mismatches — that is the actual integration work, and it is not small.
- **Fuzzy linkage.** Every join here is exact. Real record linkage needs
  thresholds, blocking, and a policy for ambiguous matches — a wrong join is
  worse than a missing one when the output releases funds.
- **A merchant-facing surface** for the Stage 3 request and Stage 4 submission.
- **Analyst review UI** for the escalation queue, since nothing auto-clears a
  contractual flag.
- **Requirement library** rather than pure generation. Format specs like *"board
  resolution in the aggregator's prescribed format"* are institutional policy no
  model can infer.
- **Id-tagged Stage 1 output — demonstrated on one flag, six remaining.** The
  TID plan is real model output consumed by the pipeline (§3). Extending it is
  one manual run per flag; the remaining six intentionally stay on the frozen
  checklist rather than being half-closed silently.
- **Drift monitoring.** Flag distributions move; a requirement set correct today
  is stale in six months.

---

## 9. Known failure modes

1. **Contractual flags.** Asymmetric under-asks. The implemented mitigation is
   outcome routing — such a case never auto-releases, it closes to a human. That
   bounds the damage; it does not fix the under-asking. Variant D — carve rule 2
   so an internal record replaces a request only when it answers the *same*
   question — is specified and untested.
2. **Over-trusting an internal proxy.** HR4: the aggregator's held complaint text
   is what the customer told their *bank*, not the merchant's correspondence with
   that customer. Adjacent evidence is not equivalent evidence.
3. **Action flags versus explanation flags.** Handled for CPV. Not audited across
   the other six.
4. **Exact-match linkage.** A merchant whose phone number changed loses their
   ticket history and gets asked for something already answered — reintroducing
   the exact harm this system exists to remove.
