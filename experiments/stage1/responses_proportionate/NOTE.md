# Only one response here, deliberately

Variant B was run on `FLAG_TID_INACTIVITY` and abandoned after that single flag.

It did not fail by being merely worse. It failed in a **specific, diagnosable
direction**: it pruned INTERNAL checks by 48% while pruning merchant ASKs by only
32% — backwards, since internal checks cost the merchant nothing. Recall on
internally-satisfiable items collapsed from 100% to 29%.

The cause was in the prompt, not the model: variant B described the cost as
merchant burden but applied one necessity test to *every* candidate, including
items carrying no merchant burden. That diagnosis produced variant C directly.

Running B on the remaining six flags would have cost an hour to re-confirm a
failure already understood. The six unused prompts are kept so the variant is
reproducible if anyone wants to check the diagnosis.

Full analysis: [LOG.md](../../../LOG.md), entry "variant B failed, and the failure
names the fix".
