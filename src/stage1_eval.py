"""
Stage 1 evaluation: can an LLM derive a COMPLETE requirement set from a fuzzy
risk flag?

This is the load-bearing test for the whole project. If recall < 1.0, the
merchant goes into a second round anyway and the "resolve in one round" thesis
collapses. We find that out here, before building anything else.

Usage - none of these need an API key
    python src/stage1_eval.py --audit     # audits the ground truth
    python src/stage1_eval.py --dump      # writes the prompt files to run by hand
    python src/stage1_eval.py --score-manual   # scores the pasted responses
    python src/stage1_eval.py --compare   # all variants side by side
    python src/stage1_eval.py --flag FLAG_TID_INACTIVITY --show

There is an API path (ask_model) and it was NOT used for any recorded run. All
16 responses in experiments/stage1/ were produced by hand under the protocol in
that directory's README. The path needs an API key and pydantic, neither of
which this repo declares, so it will not run as shipped. It is kept because it
documents what the automated version would call.

Scoring is deterministic keyword matching against data/flag_requirements.yaml.
That UNDER-counts semantically correct predictions worded unusually, so the
recall reported here is a LOWER BOUND. Every scorer miss is adjudicated by hand
with the candidate text quoted - see results/adjudication.md - and both numbers
are reported.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
GROUND_TRUTH = ROOT / "data" / "flag_requirements.yaml"
RESULTS_DIR = ROOT / "results"

MODEL = "claude-opus-5"

SYSTEM = """You are a risk operations analyst at an Indian payment aggregator \
regulated by the RBI.

A risk flag has been raised on a merchant account and their settlements are on \
hold. Your job is to determine the COMPLETE set of evidence required to resolve \
this flag, in one pass.

This matters: every requirement you miss becomes another round of back-and-forth \
with the merchant, and their money stays frozen for the whole of it. Be \
exhaustive. It is better to list a requirement that turns out to be unnecessary \
than to omit one that is needed.

For each requirement, state whether the aggregator could satisfy it from records \
it already holds (KYC files, prior submissions, transaction history, support \
tickets, terminal telemetry) rather than asking the merchant."""

# Variant B. Identical task, identical output format, identical flag data.
# The ONLY change is the constraint on what belongs in the set. This is the A/B:
# does a principled proportionality test raise precision without costing recall?
#
# Deliberately NOT a hard cap on item count. A cap would improve precision
# trivially by truncation and would tell us nothing about whether the model can
# reason about necessity.
SYSTEM_PROPORTIONATE = """You are a risk operations analyst at an Indian payment \
aggregator regulated by the RBI.

A risk flag has been raised on a merchant account and their settlements are on \
hold. Your job is to determine the evidence required to resolve THIS SPECIFIC \
FLAG, in one pass.

Two constraints, and they pull against each other. Hold both.

COMPLETE. Every requirement you miss becomes another round of back-and-forth, \
and the merchant's money stays frozen throughout. A missed requirement is a \
serious failure.

PROPORTIONATE. Every item you ask the merchant for costs them time and effort \
while their funds are held. A flag is not an occasion to re-verify the merchant \
in general. Do not sweep in routine KYC refresh, licence renewals, tax filings, \
or financial statements unless the flag itself cannot be resolved without them.

Apply this test to every candidate requirement before including it:

  Name the specific hypothesis this item would rule in or rule out about THIS
  flag. If you cannot name one - if the honest answer is "it is generally good
  to know" or "it is standard practice" - leave it out.

For each requirement, state whether the aggregator could satisfy it from records \
it already holds (KYC files, prior submissions, transaction history, support \
tickets, terminal telemetry) rather than asking the merchant."""

# Variant C. Variant B failed in a specific, diagnosable way: it pruned INTERNAL
# checks (-48%) harder than merchant ASKs (-32%), which is backwards. Internal
# checks cost the merchant nothing, so there is no reason to be parsimonious
# about them - and they are exactly the items that resolve a flag without
# involving the merchant at all.
#
# Root cause: variant B applied one necessity test to EVERY candidate. The cost
# it described was merchant burden, but the test was applied to items that carry
# no merchant burden. Proportionality has to be ASYMMETRIC.
#
# Also: variant B's prohibition list ("do not sweep in KYC refresh, licence
# renewals, tax filings") was hedged rather than obeyed - all five categories
# came back wrapped in "if the one on file has expired". Variant C states a
# positive rule instead of a list of things not to do.
SYSTEM_ASYMMETRIC = """You are a risk operations analyst at an Indian payment \
aggregator regulated by the RBI.

A risk flag has been raised on a merchant account and their settlements are on \
hold. Your job is to determine the evidence required to resolve THIS SPECIFIC \
FLAG, in one pass.

The two halves of the answer follow OPPOSITE rules.

INTERNAL CHECKS - be exhaustive. Anything the aggregator can establish from its \
own records costs the merchant nothing and delays them not at all. List every \
internal record that bears on this flag: transaction and settlement history, \
device telemetry and fault logs, connectivity records, asset and inventory \
status, billing and rental history, support tickets, prior submissions, earlier \
risk decisions, other accounts and terminals held by the same merchant. Omitting \
an internal check is a pure loss - it means asking the merchant for something \
you could have answered yourself.

MERCHANT REQUESTS - be minimal. Every item here costs the merchant time and \
effort while their money is frozen. Include an item ONLY if BOTH of these hold:

  1. You can name the specific hypothesis about THIS flag that it rules in or
     out. Not "it is standard practice", not "it is good to know" - a specific
     hypothesis about why this flag fired.
  2. No internal record could answer it. If an internal check could settle the
     question, the internal check replaces the request; do not list both.

Where a merchant request is only necessary if an internal check comes back a \
certain way, say so explicitly rather than asking for it unconditionally.

Mark each item [INTERNAL] or [ASK] accordingly."""

VARIANTS = {
    "baseline": SYSTEM,
    "proportionate": SYSTEM_PROPORTIONATE,
    "asymmetric": SYSTEM_ASYMMETRIC,
}

PROMPT = """RISK FLAG RAISED

Alert issued to merchant: "{alert_text}"

Internal trigger: {trigger}

Merchant on file:
- Entity type: {business_type}
- Declared MCC: {mcc_declared}
- Months active: {months_active}

List the complete set of evidence required to resolve this flag."""

MANUAL_SUFFIX = """

Return ONLY a numbered list, one requirement per line, in exactly this format:

1. [ASK] <requirement>
2. [INTERNAL] <requirement>

Use [INTERNAL] if the aggregator could satisfy the item from records it already
holds. Use [ASK] if the merchant must supply it. No preamble, no closing remarks,
nothing after the list."""


def load_flags():
    with open(GROUND_TRUTH, encoding="utf-8") as f:
        return yaml.safe_load(f)["flags"]


# audit mode

def audit(flags):
    """Validate the ground truth and report Stage 2 headroom. No API needed."""
    print(f"\nGROUND TRUTH AUDIT  ({GROUND_TRUTH.relative_to(ROOT)})\n" + "=" * 72)

    total = 0
    sat = {"true": 0, "false": 0, "partial": 0}
    problems = []
    seen_ids = set()

    for fl in flags:
        reqs = fl["requirements"]
        total += len(reqs)
        counts = {"true": 0, "false": 0, "partial": 0}
        for r in reqs:
            key = str(r["internally_satisfiable"]).lower()
            if key not in sat:
                problems.append(f"{r['id']}: bad internally_satisfiable={key!r}")
                continue
            sat[key] += 1
            counts[key] += 1
            if r["id"] in seen_ids:
                problems.append(f"duplicate requirement id: {r['id']}")
            seen_ids.add(r["id"])
            if len(r.get("match_keywords", [])) < 3:
                problems.append(f"{r['id']}: fewer than 3 match_keywords")

        internal = counts["true"] + 0.5 * counts["partial"]
        print(f"\n{fl['id']}")
        print(f"  {fl['label']}")
        print(f"  requirements: {len(reqs)}   "
              f"internal: {counts['true']}  partial: {counts['partial']}  "
              f"merchant-only: {counts['false']}")
        print(f"  Stage 2 headroom: {internal / len(reqs):.0%} of items "
              f"potentially satisfiable without asking the merchant")

    print("\n" + "=" * 72)
    print(f"TOTAL: {len(flags)} flag types, {total} requirements")
    print(f"  internally satisfiable : {sat['true']:>3}  ({sat['true']/total:.0%})")
    print(f"  partial                : {sat['partial']:>3}  ({sat['partial']/total:.0%})")
    print(f"  merchant must supply   : {sat['false']:>3}  ({sat['false']/total:.0%})")

    headroom = (sat["true"] + 0.5 * sat["partial"]) / total
    print(f"\n  >> Stage 2 headroom overall: {headroom:.0%}")
    print("     Upper bound on what internal evidence could remove from the ask.")
    print("     NOTE: this is a property of the hand-built ground truth, not a")
    print("     measurement of Razorpay. It sets the ceiling, not the result.")

    if problems:
        print(f"\n  {len(problems)} PROBLEM(S):")
        for p in problems:
            print(f"    - {p}")
    else:
        print("\n  No structural problems found.")
    return 0 if not problems else 1


# scoring

def norm(s):
    return " ".join(str(s).lower().replace("-", " ").split())


def load_adjudications():
    f = RESULTS_DIR / "adjudications.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8")).get("rulings", {})


def score(flag, predicted, adjudged=None):
    """Match predicted requirements against ground truth by keyword alias.

    `adjudged` maps requirement_id -> "present" for items a human ruled
    semantically covered that the keyword scorer missed. Both numbers are kept.
    """
    gt = flag["requirements"]
    pred_norm = [norm(p) for p in predicted]

    matched_gt, matched_pred = {}, set()
    for r in gt:
        hit = None
        for i, p in enumerate(pred_norm):
            if any(norm(k) in p for k in r["match_keywords"]):
                hit = i
                matched_pred.add(i)
                break
        matched_gt[r["id"]] = hit

    found = [rid for rid, h in matched_gt.items() if h is not None]
    missed = [rid for rid, h in matched_gt.items() if h is None]
    extra = [predicted[i] for i in range(len(predicted)) if i not in matched_pred]

    internal_gt = [r["id"] for r in gt
                   if str(r["internally_satisfiable"]).lower() in ("true", "partial")]
    internal_found = [r for r in found if r in internal_gt]

    adjudged = adjudged or {}
    adj_found = set(found) | {k for k, v in adjudged.items() if v == "present"}
    adj_missed = [r["id"] for r in gt if r["id"] not in adj_found]
    adj_internal_found = [r for r in adj_found if r in internal_gt]

    return {
        "flag": flag["id"],
        "recall": len(found) / len(gt),
        "adj_recall": len(adj_found) / len(gt),
        "adj_precision": (len(adj_found) / len(predicted)) if predicted else 0.0,
        "adj_missed": adj_missed,
        "adj_internal_recall": (len(adj_internal_found) / len(internal_gt)) if internal_gt else None,
        "precision": len(found) / len(predicted) if predicted else 0.0,
        "n_ground_truth": len(gt),
        "n_predicted": len(predicted),
        "found": found,
        "missed": missed,
        "unmatched_predictions": extra,
        "internal_recall": (len(internal_found) / len(internal_gt)) if internal_gt else None,
    }


# model call

def ask_model(client, flag, variant="baseline"):
    from pydantic import BaseModel

    class Requirement(BaseModel):
        item: str
        why_needed: str
        aggregator_already_has_this: bool

    class RequirementSet(BaseModel):
        requirements: list[Requirement]

    ctx = flag["merchant_context"]
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=VARIANTS[variant],
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": PROMPT.format(
            alert_text=flag["alert_text"], **ctx)}],
        output_format=RequirementSet,
    )
    return resp.parsed_output.requirements


def run(flags, only=None, show=False, variant="baseline"):
    try:
        import anthropic
    except ImportError:
        print("ERROR: pip install anthropic pydantic", file=sys.stderr)
        return 2

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("ERROR: no credentials found.\n"
              "  set ANTHROPIC_API_KEY, or run `ant auth login`.\n"
              "  Meanwhile `--audit` works with no key.", file=sys.stderr)
        return 2

    client = anthropic.Anthropic()
    targets = [f for f in flags if only is None or f["id"] == only]
    if not targets:
        print(f"no flag matching {only!r}", file=sys.stderr)
        return 2

    results = []
    for fl in targets:
        print(f"\n{'='*72}\n{fl['id']}  -  {fl['label']}\n{'='*72}")
        try:
            reqs = ask_model(client, fl, variant)
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            continue

        s = score(fl, [r.item for r in reqs])
        s["model_flagged_internal"] = [r.item for r in reqs if r.aggregator_already_has_this]
        results.append(s)

        print(f"  recall    {s['recall']:.0%}   ({len(s['found'])}/{s['n_ground_truth']})")
        print(f"  precision {s['precision']:.0%}   ({len(s['found'])}/{s['n_predicted']})")
        if s["internal_recall"] is not None:
            print(f"  recall on internally-satisfiable items: {s['internal_recall']:.0%}")
        if s["missed"]:
            print("  MISSED:")
            for rid in s["missed"]:
                item = next(r["item"] for r in fl["requirements"] if r["id"] == rid)
                print(f"    - [{rid}] {item}")
        if show:
            print("  PREDICTED:")
            for r in reqs:
                mark = "[internal]" if r.aggregator_already_has_this else "[ask]     "
                print(f"    {mark} {r.item}")

    if results:
        n = len(results)
        mr = sum(r["recall"] for r in results) / n
        mp = sum(r["precision"] for r in results) / n
        ir = [r["internal_recall"] for r in results if r["internal_recall"] is not None]
        print(f"\n{'='*72}\nAGGREGATE over {n} flag types")
        print(f"  mean recall    {mr:.1%}   <- load-bearing metric")
        print(f"  mean precision {mp:.1%}")
        if ir:
            print(f"  mean recall on internal items {sum(ir)/len(ir):.1%}")
        print(f"  perfect recall on {sum(1 for r in results if r['recall'] == 1.0)}/{n} flags")
        print("\n  Keyword matching under-counts. Treat recall as a LOWER BOUND.")

        RESULTS_DIR.mkdir(exist_ok=True)
        out = RESULTS_DIR / "stage1_eval.json"
        out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\n  written: {out.relative_to(ROOT)}")
    return 0


# manual mode

EXPERIMENTS = ROOT / "experiments" / "stage1"


def dirs_for(variant):
    """Baseline keeps the plain names; variants get their own directories."""
    suffix = "" if variant == "baseline" else f"_{variant}"
    return EXPERIMENTS / f"prompts{suffix}", EXPERIMENTS / f"responses{suffix}"


def dump(flags, variant="baseline"):
    """Write one prompt file per flag, for pasting into a chat interface."""
    PROMPTS_DIR, RESPONSES_DIR = dirs_for(variant)
    PROMPTS_DIR.mkdir(exist_ok=True)
    RESPONSES_DIR.mkdir(exist_ok=True)
    for fl in flags:
        body = (VARIANTS[variant] + "\n\n---\n\n"
                + PROMPT.format(alert_text=fl["alert_text"], **fl["merchant_context"])
                + MANUAL_SUFFIX + "\n")
        (PROMPTS_DIR / f"{fl['id']}.txt").write_text(body, encoding="utf-8")

    print(f"\nWrote {len(flags)} prompts to {PROMPTS_DIR.name}/   [variant: {variant}]\n")
    print("PROCEDURE - follow exactly or the result is invalid:\n")
    print("  1. Open a BRAND NEW chat. A fresh one for EVERY prompt.")
    print("     Reusing a chat lets flag 2 see flag 1's answer. That inflates recall.")
    print("  2. Do NOT use the conversation where this project was designed.")
    print("     That model has seen the ground truth and would score near-perfect")
    print("     for the wrong reason.")
    print("  3. Paste the whole file. Copy the reply verbatim.")
    print(f"  4. Save it as {RESPONSES_DIR.name}/<FLAG_ID>.txt")
    print("  5. Use the same model for all seven. Note which one.\n")
    print("  Then: python src/stage1_eval.py --score-manual\n")
    for fl in flags:
        print(f"    {PROMPTS_DIR.name}/{fl['id']}.txt  ->  {RESPONSES_DIR.name}/{fl['id']}.txt")
    return 0


# number prefix is optional - models often drop it despite the format instruction
LINE_RE = re.compile(r"^\s*(?:\d+[.)]\s*)?\[(INTERNAL|ASK)\]\s*[:\-]?\s*(.+?)\s*$", re.I)

# An ASK gated on an internal check costs the merchant nothing unless that check
# comes back inconclusive. Unconditional asks are the real merchant burden, so
# they are counted separately.
COND_RE = re.compile(r"only (?:if|when|needed if|required if)|conditional on|contingent on|if and only if", re.I)


def parse_manual(text):
    items = []
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if m:
            txt = m.group(2).strip()
            items.append({"item": txt,
                          "internal": m.group(1).upper() == "INTERNAL",
                          "conditional": bool(COND_RE.search(txt))})
        elif line.strip().startswith(("-", "*", "•")):
            s = line.strip().lstrip("-*• ").strip()
            if len(s) > 8:
                items.append({"item": s, "internal": False,
                              "conditional": bool(COND_RE.search(s))})
    return items


def score_manual(flags, variant="baseline"):
    _, RESPONSES_DIR = dirs_for(variant)
    if not RESPONSES_DIR.exists():
        print(f"no {RESPONSES_DIR.name}/ directory. Run --dump first.", file=sys.stderr)
        return 2

    results, missing = [], []
    for fl in flags:
        p = RESPONSES_DIR / f"{fl['id']}.txt"
        if not p.exists():
            missing.append(fl["id"])
            continue
        items = parse_manual(p.read_text(encoding="utf-8"))
        if not items:
            print(f"  {fl['id']}: PARSED 0 ITEMS - check the response format")
            continue

        s = score(fl, [i["item"] for i in items],
                  load_adjudications().get(variant, {}).get(fl["id"], {}))
        s["model_flagged_internal"] = [i["item"] for i in items if i["internal"]]
        results.append(s)

        print(f"\n{'='*72}\n{fl['id']}  -  {fl['label']}\n{'='*72}")
        print(f"  recall    {s['recall']:.0%}   ({len(s['found'])}/{s['n_ground_truth']})")
        print(f"  precision {s['precision']:.0%}   ({len(s['found'])}/{s['n_predicted']})")
        if s["internal_recall"] is not None:
            print(f"  recall on internally-satisfiable items: {s['internal_recall']:.0%}")
        if s["missed"]:
            print("  MISSED:")
            for rid in s["missed"]:
                item = next(r["item"] for r in fl["requirements"] if r["id"] == rid)
                print(f"    - [{rid}] {item}")
        if s["unmatched_predictions"]:
            print("  PREDICTED BUT UNMATCHED (inspect - may be a ground-truth gap):")
            for e in s["unmatched_predictions"]:
                print(f"    ? {e}")

    if missing:
        print(f"\n  missing responses: {', '.join(missing)}")
    if not results:
        return 1

    n = len(results)
    mr = sum(r["recall"] for r in results) / n
    mp = sum(r["precision"] for r in results) / n
    ir = [r["internal_recall"] for r in results if r["internal_recall"] is not None]
    print(f"\n{'='*72}\nAGGREGATE over {n}/{len(flags)} flag types  (MANUAL RUN)")
    print(f"  mean recall    {mr:.1%}   <- load-bearing metric")
    print(f"  mean precision {mp:.1%}")
    if ir:
        print(f"  mean recall on internal items {sum(ir)/len(ir):.1%}")
    print(f"  perfect recall on {sum(1 for r in results if r['recall'] == 1.0)}/{n} flags")
    print("\n  Keyword matching under-counts. Recall is a LOWER BOUND.")
    print("  Inspect every MISSED item and sort it into one of three buckets:")
    print("    (a) model genuinely missed a real requirement")
    print("    (b) model said it in different words  -> add the alias, re-score")
    print("    (c) the ground-truth item was wrong   -> fix the YAML, log the change")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"stage1_eval_manual_{variant}.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n  written: {out.relative_to(ROOT)}")
    return 0


# compare mode

def compare(flags):
    """Score every variant that has responses, side by side, across all flags."""
    adj = load_adjudications()
    variants = [v for v in VARIANTS if dirs_for(v)[1].exists()]
    data = {}

    for v in variants:
        _, rdir = dirs_for(v)
        for fl in flags:
            f = rdir / f"{fl['id']}.txt"
            if not f.exists():
                continue
            items = parse_manual(f.read_text(encoding="utf-8"))
            if not items:
                continue
            s = score(fl, [i["item"] for i in items],
                      adj.get(v, {}).get(fl["id"], {}))
            s["ask"] = sum(1 for i in items if not i["internal"])
            s["internal"] = sum(1 for i in items if i["internal"])
            s["ask_uncond"] = sum(1 for i in items
                                  if not i["internal"] and not i.get("conditional"))
            data[(v, fl["id"])] = s

    if not data:
        print("no responses found in any responses*/ directory", file=sys.stderr)
        return 2

    print("\n" + "=" * 94)
    print("VARIANT COMPARISON   kw = keyword scorer (mechanical) | adj = human-adjudicated")
    print("=" * 94)

    for fl in flags:
        have = [v for v in variants if (v, fl["id"]) in data]
        if not have:
            continue
        n_gt = len(fl["requirements"])
        print(f"\n{fl['id']}   ({n_gt} ground-truth requirements)")
        print(f"  {'variant':16}{'kw-rec':>8}{'adj-rec':>9}{'adj-prec':>10}"
              f"{'items':>7}{'ASK':>6}{'uncond':>8}{'INT':>6}")
        for v in have:
            d = data[(v, fl["id"])]
            print(f"  {v:16}{d['recall']:>7.0%}{d['adj_recall']:>9.0%}"
                  f"{d['adj_precision']:>10.0%}"
                  f"{d['n_predicted']:>7}{d['ask']:>6}{d['ask_uncond']:>8}{d['internal']:>6}")
        for v in have:
            m = data[(v, fl["id"])]["adj_missed"]
            if m:
                print(f"    {v} still missing: {', '.join(m)}")

    print("\n" + "=" * 94)
    print("AGGREGATE")
    print(f"  {'variant':16}{'flags':>7}{'kw-rec':>8}{'adj-rec':>9}"
          f"{'adj-prec':>10}{'items':>7}{'ASK':>6}{'uncond':>8}{'INT':>6}")
    for v in variants:
        rows = [d for (vv, _), d in data.items() if vv == v]
        if not rows:
            continue
        n = len(rows)
        avg = lambda k: sum(r[k] for r in rows) / n
        tot = lambda k: sum(r[k] for r in rows)
        print(f"  {v:16}{n:>7}{avg('recall'):>7.0%}{avg('adj_recall'):>9.0%}"
              f"{avg('adj_precision'):>10.0%}"
              f"{tot('n_predicted'):>7}{tot('ask'):>6}{tot('ask_uncond'):>8}{tot('internal'):>6}")

    done = {v: sum(1 for (vv, _) in data if vv == v) for v in variants}
    todo = [(v, fl["id"]) for v in variants for fl in flags if (v, fl["id"]) not in data]
    print(f"\n  coverage: {done}   of {len(flags)} flags each")
    if todo:
        print(f"  {len(todo)} runs outstanding:")
        for v, fid in todo[:16]:
            print(f"    prompts{'' if v=='baseline' else '_'+v}/{fid}.txt")
    if any(n == 1 for n in done.values()):
        print("\n  WARNING: n=1 on at least one variant. Ordering is suggestive, not established.")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / "comparison.json"
    out.write_text(json.dumps(
        {f"{v}|{f}": d for (v, f), d in data.items()}, indent=2), encoding="utf-8")
    print(f"\n  written: {out.relative_to(ROOT)}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true", help="audit ground truth, no API")
    ap.add_argument("--dump", action="store_true", help="write prompts for manual running")
    ap.add_argument("--score-manual", action="store_true", help="score pasted responses")
    ap.add_argument("--compare", action="store_true", help="all variants side by side")
    ap.add_argument("--flag", help="run a single flag id")
    ap.add_argument("--show", action="store_true", help="print predicted requirements")
    ap.add_argument("--variant", default="baseline", choices=sorted(VARIANTS),
                    help="prompt variant (A/B test)")
    a = ap.parse_args()

    flags = load_flags()
    if a.audit:
        return audit(flags)
    if a.dump:
        return dump(flags, a.variant)
    if a.compare:
        return compare(flags)
    if a.score_manual:
        return score_manual(flags, a.variant)
    return run(flags, a.flag, a.show, a.variant)


if __name__ == "__main__":
    sys.exit(main())
