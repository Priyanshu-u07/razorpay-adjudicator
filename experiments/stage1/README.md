# Stage 1 experiment — recorded runs

This directory is **evidence, not code.** Nothing here is imported or read at
runtime. It exists so the Stage 1 design decision can be checked rather than
taken on trust.

## The question

Stage 1 asks a model to derive the complete set of evidence that would clear a
risk flag. Getting it complete is easy. Getting it complete **without burying the
merchant in demands** is the actual problem — and the first attempt returned 51
requirements for a broken card terminal, 22 of them addressed to the merchant.

Three prompt designs were run **blind** against seven flag types — the model was
never shown the ground truth. Everything was held constant except the constraint
on what belongs in the set. (A fourth directory pair, `*_idtagged`, is a
different kind of run and is described further down.)

| directory | variant | outcome |
|---|---|---|
| `prompts/` · `responses/` | **A — baseline**<br>"be exhaustive, better to over-ask" | 98% recall, **175 unconditional asks** |
| `prompts_proportionate/` · `responses_proportionate/` | **B — one necessity test** | pruned internal checks −48% vs merchant asks −32%. Backwards. Abandoned after one flag once diagnosed. |
| `prompts_asymmetric/` · `responses_asymmetric/` | **C — opposite rules per half** | 89% recall, **5 unconditional asks**. Shipped. |

## The difference between A and C

**Held constant, byte-identical:** the analyst role, the flag alert text, the
internal trigger, the merchant profile, and the required output format. 28 of 31
baseline lines are unchanged.

**Three blocks differ**, and it is worth being precise about that rather than
claiming a cleaner experiment than was run:

| | A (baseline) | C (asymmetric) |
|---|---|---|
| task statement | *"determine the **COMPLETE** set of evidence"* | *"determine the evidence required to resolve **THIS SPECIFIC FLAG**"* |
| framing line | *"Be exhaustive. Better to list a requirement that turns out unnecessary than omit one needed."* | *"The two halves of the answer follow **OPPOSITE** rules."* |
| the constraint | one sentence asking the model to tag each item internal or external | the 13-line block below |

All three express the same single intervention — proportionality — so the effect
cannot be attributed to the constraint block alone. A stricter experiment would
vary one at a time. **This one does not, and the result should be read as
"this prompt design beats that one", not "this sentence caused the change".**

**A (baseline):**

```
This matters: every requirement you miss becomes another round of back-and-forth
with the merchant, and their money stays frozen for the whole of it. Be
exhaustive. It is better to list a requirement that turns out to be unnecessary
than to omit one that is needed.
```

**C (asymmetric):**

```
The two halves of the answer follow OPPOSITE rules.

INTERNAL CHECKS - be exhaustive. Anything the aggregator can establish from its
own records costs the merchant nothing and delays them not at all. [...]
Omitting an internal check is a pure loss - it means asking the merchant for
something you could have answered yourself.

MERCHANT REQUESTS - be minimal. Every item here costs the merchant time and
effort while their money is frozen. Include an item ONLY if BOTH of these hold:

  1. You can name the specific hypothesis about THIS flag that it rules in or
     out. Not "it is standard practice", not "it is good to know".
  2. No internal record could answer it. If an internal check could settle the
     question, the internal check replaces the request; do not list both.

Where a merchant request is only necessary if an internal check comes back a
certain way, say so explicitly rather than asking for it unconditionally.
```

**That paragraph is worth 170 fewer unconditional demands on merchants**, at 100%
recall on operational flags. Nothing else in the system changed.

Confirm it yourself:

```bash
diff prompts/FLAG_TID_INACTIVITY.txt prompts_asymmetric/FLAG_TID_INACTIVITY.txt
```

## The fourth pair: `prompts_idtagged/` · `responses_idtagged/`

**Not a variant, and never scored against the other three.** In the three runs
above the model derives requirements from nothing but the alert. Here it is shown
the requirement library and asked to emit a disposition per id — `CHECK`, `ASK`,
`ASK_IF <gate>`, or `SKIP`:

```
TI1 CHECK
TI3 ASK_IF device_deployed
TI4 ASK_IF not (open_hardware_ticket or device_fault_code)
```

It exists because the pipeline's central simplification was that Stage 1's real
output never entered the system — mapping free prose onto requirement ids is the
same fuzzy matching that makes the keyword scorer unreliable. Emitting ids removes
the mapping problem at the source, so the plan can be executed rather than
paraphrased. [`src/stage1_plan.py`](../../src/stage1_plan.py) parses it and
[`src/pipeline.py`](../../src/pipeline.py) runs `FLAG_TID_INACTIVITY` on it.

**Scoring this for recall would be meaningless** — it was handed the answers, so
it would report 100% for the wrong reason. One flag, n=1; the other six still run
on the frozen checklist. The full warning lives in
[`prompts_idtagged/NOTE.md`](prompts_idtagged/NOTE.md), beside the files it
applies to.

One finding worth keeping: the model violated the output format, echoing a helper
line under every `CHECK` despite being told nothing should follow the last line.
Even an id-tagged format produced noise — which is itself the argument for
id-tagging over parsing free prose.

## How these were produced

Claude at High effort, one **fresh chat per prompt**, plain text pasted,
no file attachments, no project context. A single session for all seven would
have let later flags see earlier answers; a session with repo access would have
let the model read the answer key. Both would have inflated recall silently.

Prompts are regenerable — the source of truth is the `VARIANTS` dict in
[`src/stage1_eval.py`](../../src/stage1_eval.py):

```bash
python src/stage1_eval.py --dump --variant asymmetric
```

They are checked in so a reviewer does not have to run anything.

## Scoring

Every response was scored twice. Mechanically by keyword match against the frozen
ground truth, then adjudicated by hand where the scorer missed — with the
candidate text quoted so each ruling can be overturned
([results/adjudication.md](../../results/adjudication.md)).

The keyword scorer missed on wording in 6 of 7 flags. **Adjudication changed the
recall figures in every round and never once changed the ordering between
variants.**

## Honest limits

- **n=1 per flag per variant.** No repeats, no variance measured.
- **Single non-blind adjudicator**, who also wrote the ground truth, the prompts
  and the variants. The weakest link in the measurement.
- `FLAG_TID_INACTIVITY`'s ground truth was expanded after the first run using
  items the model produced. It is the one fitted flag; the other six are not, and
  the result holds on them.
- Variant B was run on one flag only. Its number is a single observation, kept
  because the *direction* of its failure is what produced variant C.

Full analysis: [PROBLEM.md](../../PROBLEM.md) · [ARCHITECTURE.md §3](../../ARCHITECTURE.md) · [LOG.md](../../LOG.md)
