"""
Recompute every headline claim from source, then check the README states them.

WHY THIS EXISTS
Four times in this project a sentence written from memory disagreed with the
artefact it described - stale figures in PROBLEM.md section 7, a docstring
claiming the pipeline read files it never opened, an overstated "byte-identical"
claim about two prompts, and wrong theme counts. Each was caught by hand. This
closes the loop: every number in the README is recomputed from the file that
produces it, and the README is checked for the result.

    python src/verify_claims.py           # print the table, verify the README
    python src/verify_claims.py --write   # also refresh results/claims.md

Exit code 1 if any claim in the README is unsupported. That makes it usable as a
pre-commit check.
"""

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OPERATIONAL = {"FLAG_TID_INACTIVITY", "FLAG_VOLUME_SPIKE", "FLAG_MCC_MISMATCH",
               "FLAG_KYC_DISCREPANCY", "FLAG_CPV_FAILURE"}


def claims():
    """Recompute everything. Returns [(claim, value, source, how_to_verify)]."""
    out = []

    # Stage 1 evaluation
    comp = json.loads((ROOT / "results" / "comparison.json").read_text(encoding="utf-8"))

    def agg(variant, flags=None):
        rows = [d for k, d in comp.items()
                if k.startswith(variant + "|") and (flags is None or k.split("|")[1] in flags)]
        return rows

    for v in ("baseline", "asymmetric"):
        rows = agg(v)
        out.append((f"Stage 1 · {v} · mean adjudicated recall",
                    f"{sum(r['adj_recall'] for r in rows)/len(rows):.0%}",
                    "results/comparison.json",
                    "python src/stage1_eval.py --compare"))
        out.append((f"Stage 1 · {v} · unconditional merchant asks (7 flags)",
                    str(sum(r["ask_uncond"] for r in rows)),
                    "results/comparison.json",
                    "python src/stage1_eval.py --compare"))

    for label, flags in (("operational (5 flags)", OPERATIONAL),
                         ("contractual (2 flags)", None)):
        f = flags if flags else {"FLAG_HIGH_REFUND", "FLAG_THIRD_PARTY_BENEFICIARY"}
        for v in ("baseline", "asymmetric"):
            rows = agg(v, f)
            out.append((f"Stage 1 · {label} · {v} recall",
                        f"{sum(r['adj_recall'] for r in rows)/len(rows):.0%}",
                        "results/comparison.json", "python src/stage1_eval.py --compare"))

    # pipeline
    pipe = json.loads((ROOT / "results" / "pipeline.json").read_text(encoding="utf-8"))
    _cases = {c["case_id"]: c for c in json.loads(
        (ROOT / "data" / "case_store.json").read_text(encoding="utf-8"))["cases"]}

    def _lbl(cid, key):
        return _cases[cid][key]

    gt = {f["id"]: f for f in yaml.safe_load(
        (ROOT / "data" / "flag_requirements.yaml").read_text(encoding="utf-8"))["flags"]}
    full = sum(len(gt[r["flag_type"]]["requirements"]) for r in pipe)
    asked = sum(r["asked_of_merchant"] for r in pipe)

    out += [
        ("Pipeline · cases", str(len(pipe)), "results/pipeline.json", "python src/pipeline.py"),
        ("Pipeline · resolved with zero merchant contact",
         f"{sum(r['rounds'] == 0 for r in pipe)}", "results/pipeline.json", "python src/pipeline.py"),
        ("Pipeline · routed to human review",
         f"{sum(1 for r in pipe if r['outcome'] == 'human_review')}",
         "results/pipeline.json", "python src/pipeline.py"),
        ("Pipeline · resolved in ONE round",
         f"{sum(1 for r in pipe if r['rounds'] == 1)}",
         "results/pipeline.json", "python src/pipeline.py"),
        ("Pipeline · needed more than one round",
         f"{sum(r['rounds'] > 1 for r in pipe)}", "results/pipeline.json", "python src/pipeline.py"),
        ("Pipeline · escape rate",
         f"{sum(1 for r in pipe if r['outcome'] == 'released' and _lbl(r['case_id'], 'should_escalate'))}",
         "results/pipeline.json", "python src/pipeline.py"),
        ("Pipeline · detected and escalated",
         f"{sum(1 for r in pipe if r['outcome'] == 'human_review' and _lbl(r['case_id'], 'should_escalate'))}",
         "results/pipeline.json", "python src/pipeline.py"),
        ("Pipeline · items asked of merchants", str(asked),
         "results/pipeline.json", "python src/pipeline.py"),
        ("Pipeline · items an ask-everything policy would", str(full),
         "results/pipeline.json", "python src/pipeline.py"),
        ("Pipeline · maximum hold on any case",
         str(max(r["hold_days"] for r in pipe)), "results/pipeline.json", "python src/pipeline.py"),
    ]

    # Stage 2
    s2 = json.loads((ROOT / "results" / "stage2.json").read_text(encoding="utf-8"))
    r036 = [c for c in s2 if c["scenario"] == "broken_terminal_open_ticket"][0]
    out += [
        ("Stage 2 · mean linkage hops per case",
         f"{sum(c['linkage_hops'] for c in s2)/len(s2):.1f}",
         "results/stage2.json", "python src/stage2_resolve.py"),
        ("Stage 2 · R036 case linkage hops", str(r036["linkage_hops"]),
         "results/stage2.json", "python src/stage2_resolve.py"),
    ]

    # corpus
    rows = list(csv.DictReader(
        (ROOT / "research" / "complaints" / "complaints.csv").open(encoding="utf-8")))
    merch = [r for r in rows if r["actor"] == "merchant"]
    out += [
        ("Corpus · reviews coded", str(len(rows)),
         "research/complaints/complaints.csv", "open the CSV"),
        ("Corpus · merchant rows", str(len(merch)),
         "research/complaints/complaints.csv", "open the CSV"),
        ("Corpus · merchant rows with a risk-affected outcome",
         str(sum(1 for r in merch if r["event_type"] != "no_risk_event")),
         "research/complaints/complaints.csv", "open the CSV"),
        ("Corpus · rows stating an explicit round count",
         str(sum(1 for r in rows if r["rounds_stated"].strip())),
         "research/complaints/complaints.csv", "open the CSV"),
    ]

    # ground truth
    out += [
        ("Ground truth · flag types", str(len(gt)),
         "data/flag_requirements.yaml", "python src/stage1_eval.py --audit"),
        ("Ground truth · requirements", str(sum(len(f["requirements"]) for f in gt.values())),
         "data/flag_requirements.yaml", "python src/stage1_eval.py --audit"),
    ]

    # ledger tests
    src = (ROOT / "src" / "test_ledger.py").read_text(encoding="utf-8")
    out.append(("Ledger · adversarial tests", str(len(re.findall(r"^def test_", src, re.M))),
                "src/test_ledger.py", "python src/test_ledger.py"))

    return out


def table(rows):
    lines = ["| claim | value | substantiated by | verify with |",
             "|---|---|---|---|"]
    lines += [f"| {c} | **{v}** | `{s}` | `{h}` |" for c, v, s, h in rows]
    return "\n".join(lines)


def main():
    rows = claims()
    print("\nCLAIM -> EVIDENCE\n" + "=" * 78)
    for c, v, s, _ in rows:
        print(f"  {c:<58} {v:>6}   {s}")

    # Check the README against the artefacts.
    #
    # The first version checked five hand-picked values. That is exactly how
    # "routed to human review: 4" went stale while the pipeline produced 6 -
    # the figure sat in a results block the check never looked at. A
    # hand-picked list has an invisible boundary, and the boundary was the
    # defect, not the missing entry.
    #
    # Now every "label : number" line inside a fenced block in the README is
    # matched to a computed value by label. A quoted figure with no computed
    # claim behind it is reported too, so the boundary cannot move silently.
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    computed = {c.split("·")[-1].strip().lower(): v for c, v, _, _ in rows}

    LINE = re.compile(r"^\s*([A-Za-z][A-Za-z \-]{6,45}?)\s*:\s*(\d+)", re.M)
    blocks = re.findall(r"```[a-z]*\n(.*?)```", readme, re.S)

    mismatches, unchecked, checked = [], [], 0
    for blk in blocks:
        for label, stated in LINE.findall(blk):
            key = label.strip().lower()
            hit = next((k for k in computed if k == key or k in key or key in k), None)
            if hit is None:
                unchecked.append(f"{label.strip()} = {stated}")
                continue
            checked += 1
            if computed[hit] != stated:
                mismatches.append(f"README says '{label.strip()}: {stated}', "
                                  f"artefacts say {computed[hit]}")

    # Is the rendered queue built from the data currently in the repo?
    #
    # queue.html is static with no network, so it cannot check this itself at
    # view time - whatever it embedded was frozen when it was built. The check
    # has to live here, in the tool that can read both. build_queue.py stamps a
    # content hash of pipeline.json + stage2.json into an HTML comment; this
    # recomputes it. A hash rather than a timestamp so that rebuilding
    # unchanged data leaves the file byte-identical.
    queue = ROOT / "results" / "queue.html"
    stale_page = None
    if queue.exists():
        h = hashlib.sha256()
        for rel in ("results/pipeline.json", "results/stage2.json"):
            # must match build_queue.fingerprint() exactly - see its docstring
            h.update((ROOT / rel).read_bytes().replace(b"\r\n", b"\n"))
        want = h.hexdigest()[:12]
        m = re.search(r"<!-- source-fingerprint: ([0-9a-f]+) -->",
                      queue.read_text(encoding="utf-8"))
        got = m.group(1) if m else None
        if got != want:
            stale_page = (got, want)

    print("\n" + "=" * 78)
    if stale_page:
        got, want = stale_page
        print(f"  STALE PAGE  results/queue.html was built from data "
              f"fingerprinted {got or 'none'}; the repo now holds {want}.")
        print("              Rebuild:  python src/build_queue.py")
    elif queue.exists():
        print("  OK - results/queue.html matches the current run data.")
    for m in mismatches:
        print(f"  MISMATCH  {m}")
    if unchecked:
        print(f"  {len(unchecked)} quoted figure(s) with no computed claim behind them:")
        for u in unchecked:
            print(f"    ? {u}")
        print("    Add a claim in claims() or these can drift unnoticed.")
    if mismatches or stale_page:
        parts = []
        if mismatches:
            parts.append(f"{len(mismatches)} stale figure(s) in README.md")
        if stale_page:
            parts.append("results/queue.html built from older data")
        print(f"\n  FAIL - {'; '.join(parts)}. Reconcile before shipping.")
        return 1
    print(f"  OK - {checked} quoted figure(s) in README.md match the artefacts"
          + (f"; {len(unchecked)} unbacked." if unchecked else "; none unbacked."))

    if "--write" in sys.argv:
        out = ROOT / "results" / "claims.md"
        out.write_text(
            "# Claims and where each is substantiated\n\n"
            "Generated by `python src/verify_claims.py --write`. Every value is\n"
            "recomputed from the file named beside it - none is typed by hand.\n\n"
            + table(rows) + "\n", encoding="utf-8")
        print(f"  written: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
