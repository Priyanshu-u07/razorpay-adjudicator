# Id-tagged Stage 1 — a different mode, not run 16

**This run is not comparable to the 15 blind runs and must never be scored
against the ground truth as if it were.** The blind runs tested whether a model
can *derive* the requirement set for a flag with no answer key. This run hands
the model the requirement library — the ids and item texts — and asks it to
*operate* it: decide each item's disposition (CHECK / ASK / ASK_IF gate / SKIP)
for the flag type.

Scoring it for recall would report 100% because it was given the answers. Its
output is judged on something else entirely: whether the dispositions and gates
are sensible, and whether the pipeline can consume them mechanically.

## Why this mode exists

The pipeline's stated central simplification (ARCHITECTURE §3) is that it uses
the frozen checklist as Stage 1's output — the model's real words never enter
the system, because mapping free prose to requirement ids is the same fuzzy
matching that made the keyword scorer unreliable. Id-tagged output removes the
mapping problem at the source: the model emits the ids, the pipeline parses
them.

It is also the production design. ARCHITECTURE §8 already lists "requirement
library rather than pure generation" — real aggregators maintain such libraries
as policy. The blind evaluation established the model can *build* one; this
demonstrates it can *run* one.

## The gate vocabulary

Conditions in `ASK_IF` lines are restricted to eight named internal findings
(`open_hardware_ticket`, `device_fault_code`, …) combined with `and`, `or`,
`not` and parentheses. The restriction is what makes the model's gating
decisions mechanically evaluable per case — free-text gates would reintroduce
the fuzzy-matching problem this mode exists to remove.

## Protocol

Identical to the other 15 runs: Claude, High effort, one fresh chat,
plain text pasted, no attachments, no project context. Response checked in
verbatim under `responses_idtagged/`.

Scope: one flag type (`FLAG_TID_INACTIVITY`, the flagship), n=1. This
demonstrates the mechanism on 8 of 50 pipeline cases; the other six flags
remain on the frozen-checklist simplification, which stays documented.
