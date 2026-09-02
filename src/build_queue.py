"""
Render the analyst review queue.

WHY THIS EXISTS
The design says the system "emits a ranked queue with evidence and a recommended
action, and a human approves". Until now that queue only existed as JSON. This
renders it as the screen a risk analyst would actually work from.

Generated from results/pipeline.json and results/stage2.json, so it cannot drift
from the run:

    python src/pipeline.py && python src/build_queue.py

Output: results/queue.html - self-contained, no server, no network, no CDN.

LAYOUT
Master-detail. Fifty stacked cards cannot be scanned; a rail of cases on the left
with one case open on the right can. The rail carries the burden percentage per
case so the worst offenders are findable without opening anything.

WHAT IT SPENDS VISUAL WEIGHT ON, IN ORDER
  1. demands avoided        what an ask-everything policy would have demanded
                            against what was actually asked. The point of the
                            whole system, so it is the largest number on screen
                            and repeated per case.
  2. the verdict            in words, not a score
  3. the evidence path      the differentiator - records joined across stores
                            that share no key

Filters and Approve/Override work client-side. Nothing is persisted; there is no
backend, so a reload restores the queue. Disclosed on the page rather than left
to be discovered.
"""

import hashlib
import html
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "queue.html"
SOURCES = ["results/pipeline.json", "results/stage2.json"]


def fingerprint():
    """Content hash of the files this page is rendered from.

    Embedded in the page and re-checked by verify_claims.py. A timestamp would
    tell a human when the page was built but could not tell them the data has
    since changed - the page is static with no network, so it cannot read
    pipeline.json at view time. A hash moves that detection to the one tool that
    CAN run the comparison, and keeps rebuilds byte-identical when nothing moved.

    Line endings are normalised before hashing. Git checks these files out as
    CRLF on Windows and LF elsewhere, so hashing raw bytes reported STALE PAGE
    on byte-identical data. A check that fires on a correct page is worse than
    none.
    """
    h = hashlib.sha256()
    for rel in SOURCES:
        h.update((ROOT / rel).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:12]


def state_of(r):
    # Escalation happens two ways and they are not the same thing for a merchant:
    # caught internally before any contact, or escalated after one round because
    # the judgement is contractual.
    if r["outcome"] == "human_review":
        return "escalated_clean" if r["rounds"] == 0 else "escalated_after_ask"
    return "zero_contact" if r["rounds"] == 0 else "one_round"


PRIORITY = {"escalated_after_ask": 0, "escalated_clean": 1,
            "one_round": 2, "zero_contact": 3}

BADGE = {
    "escalated_after_ask": "ESCALATED · 1 ROUND",
    "escalated_clean":     "ESCALATED · 0 CONTACT",
    "one_round":           "RELEASED · 1 ROUND",
    "zero_contact":        "RELEASED · 0 CONTACT",
}

SUB = {
    "escalated_after_ask": "Documents supplied · judgement reserved to an analyst",
    "escalated_clean":     "Caught internally · merchant never contacted",
    "one_round":           "Asked once, then cleared",
    "zero_contact":        "Internal evidence alone resolved it",
}

ACTION = {
    "escalated_after_ask": "Review the submitted documents, then release the funds or keep them on hold",
    "escalated_clean":     "Review the evidence, then release the funds or keep them on hold",
    "one_round":           "Confirm release — merchant supplied the outstanding items",
    "zero_contact":        "Confirm release — merchant was never contacted",
}

# On an escalated case the system declined to decide. Rendering a primary
# button on either side would have the interface express a preference the
# system does not hold. Equal weight is the honest rendering.
BUTTONS = {
    "escalated_after_ask": [("alt", "Keep on hold"), ("alt", "Release funds")],
    "escalated_clean":     [("alt", "Keep on hold"), ("alt", "Release funds")],
    "one_round":           [("alt", "Override"), ("ok", "Approve release")],
    "zero_contact":        [("alt", "Override"), ("ok", "Approve release")],
}

RAIL = {
    "escalated_after_ask": "needs an analyst",
    "escalated_clean":     "needs an analyst",
    "one_round":           "released",
    "zero_contact":        "released",
}


def build():
    pipe = json.loads((ROOT / "results" / "pipeline.json").read_text(encoding="utf-8"))
    s2 = {c["case_id"]: c for c in
          json.loads((ROOT / "results" / "stage2.json").read_text(encoding="utf-8"))}
    flags_yaml = yaml.safe_load(
        (ROOT / "data" / "flag_requirements.yaml").read_text(encoding="utf-8"))["flags"]
    sizes = {f["id"]: len(f["requirements"]) for f in flags_yaml}
    # id -> plain text. A chip reading "TI3" is an internal identifier leaking
    # into a user-facing surface; it tells an analyst nothing.
    text = {r["id"]: r["item"] for f in flags_yaml for r in f["requirements"]}

    rows = sorted(pipe, key=lambda r: (PRIORITY[state_of(r)], r["case_id"]))
    n_esc = sum(1 for r in pipe if state_of(r).startswith("escalated"))
    n_one = sum(1 for r in pipe if state_of(r) == "one_round")
    n_zero = sum(1 for r in pipe if state_of(r) == "zero_contact")
    asked = sum(r["asked_of_merchant"] for r in pipe)
    full = sum(sizes[r["flag_type"]] for r in pipe)

    cases = []
    for r in rows:
        s = s2.get(r["case_id"], {})
        st = state_of(r)
        would, did = sizes[r["flag_type"]], r["asked_of_merchant"]
        asks = [e for e in r["events"] if e["event"] == "requested"]
        sat = [e for e in r["events"] if e["event"] == "satisfied"
               and e.get("source") != "merchant_submission"]
        imp = [e for e in r["events"] if e["event"] == "impossible"]
        cases.append({
            "id": r["case_id"],
            "flag": r["flag_type"].replace("FLAG_", "").replace("_", " ").title()
                    .replace("Tid", "TID").replace("Mcc", "MCC")
                    .replace("Kyc", "KYC").replace("Cpv", "CPV"),
            "state": st, "badge": BADGE[st], "sub": SUB[st], "action": ACTION[st],
            "buttons": BUTTONS[st],
            "railState": RAIL[st],
            "verdict": r["reason"], "rounds": r["rounds"], "hold": r["hold_days"],
            "internal": len(sat), "asked": did, "would": would,
            "avoided": round((would - did) / would * 100) if would else 0,
            "path": s.get("linkage_path", []),
            "requested": [{"id": rid, "text": text.get(rid, rid)}
                          for rid in (asks[0]["requirements"] if asks else [])],
            "impossible": [{"req": e["requirement"], "why": e["reason"]} for e in imp],
        })

    data = json.dumps(cases, ensure_ascii=False)
    fp = fingerprint()

    return f"""<!doctype html>
<!-- source-fingerprint: {fp} -->
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Merchant risk &middot; review queue</title>
<style>
:root{{--bg:#fff;--panel:#f8fafc;--ink:#0f172a;--mute:#64748b;--line:#e2e8f0;
--blue:#2b4de0;--red:#b42318;--amber:#b54708;--green:#067647}}
*{{box-sizing:border-box}}
html,body{{height:100%}}
body{{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
display:flex;flex-direction:column}}
b,strong{{font-weight:650}}

/* ---- header ---- */
.head{{display:flex;justify-content:space-between;align-items:flex-start;gap:40px;
padding:22px 28px 18px;flex-wrap:wrap}}
h1{{font-size:21px;margin:0 0 5px;letter-spacing:-.015em}}
.lede{{color:var(--mute);margin:0;font-size:13px;max-width:60ch}}
.hero{{border-left:3px solid var(--blue);padding-left:18px;flex:0 0 auto}}
.hero span{{display:block;color:var(--mute);font-size:10.5px;text-transform:uppercase;
letter-spacing:.06em}}
.hero b{{font-size:40px;line-height:1.05;letter-spacing:-.03em;
font-variant-numeric:tabular-nums;font-weight:700}}
.hero em{{font-style:normal;color:var(--mute);font-size:13px;margin-left:7px}}
.hero i{{display:block;font-style:normal;color:var(--mute);font-size:12px;margin-top:3px}}

/* ---- filters ---- */
.filters{{display:flex;gap:8px;padding:0 28px 16px;flex-wrap:wrap;
border-bottom:1px solid var(--line)}}
.filters button{{font:inherit;font-size:13px;padding:6px 14px 6px 11px;border-radius:99px;
border:1px solid var(--line);background:var(--bg);color:var(--ink);cursor:pointer;
display:inline-flex;align-items:center;gap:7px}}
.filters button:hover:not(:disabled){{border-color:#cbd5e1}}
.filters button u{{text-decoration:none;font-weight:650;font-variant-numeric:tabular-nums}}
.filters button[aria-pressed=true]{{background:var(--blue);border-color:var(--blue);color:#fff}}
.filters button:disabled{{opacity:.45;cursor:default}}

/* ---- split ---- */
.split{{display:flex;flex:1;min-height:0}}
.rail{{width:330px;flex:0 0 330px;border-right:1px solid var(--line);overflow-y:auto}}
.railhead{{display:flex;justify-content:space-between;padding:11px 16px;
font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);
border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg)}}
.row{{display:flex;justify-content:space-between;gap:10px;padding:12px 16px;
border:0;border-bottom:1px solid var(--line);border-left:3px solid transparent;
cursor:pointer;width:100%;text-align:left;font:inherit;color:inherit;background:none}}
.row:focus-visible{{outline:2px solid var(--blue);outline-offset:-2px}}
.row:hover{{background:var(--panel)}}
.row[aria-selected=true]{{background:#eef2ff;border-left-color:var(--blue)}}
.row .cid{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--mute);
font-size:12.5px;margin-right:8px}}
.row .nm{{font-weight:600}}
.row .meta{{color:var(--mute);font-size:12px;margin-top:3px}}
.row .pc{{font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap}}
.row.actioned{{opacity:.42}}

/* ---- detail ---- */
.detail{{flex:1;overflow-y:auto;background:var(--panel);display:flex;flex-direction:column}}
.dinner{{padding:22px 28px;flex:1}}
.dhead{{display:flex;justify-content:space-between;align-items:flex-start;gap:18px}}
.dhead h2{{font-size:20px;margin:0;letter-spacing:-.01em}}
.dhead h2 span{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
color:var(--mute);font-size:15px;font-weight:500;margin-right:10px}}
.dsub{{color:var(--mute);font-size:13px;margin:6px 0 0}}
.badge{{font-size:11px;font-weight:650;letter-spacing:.04em;padding:6px 12px;
border-radius:99px;white-space:nowrap}}
.badge.escalated_after_ask,.badge.escalated_clean{{background:#fef3f2;color:var(--red)}}
.badge.one_round{{background:#fffaeb;color:var(--amber)}}
.badge.zero_contact{{background:#ecfdf3;color:var(--green)}}
.verdict{{font-size:15px;margin:0 0 20px}}
.burden{{background:var(--bg);border:1px solid var(--line);border-radius:10px;
padding:16px 18px;margin:18px 0}}
.brow{{display:flex;justify-content:space-between;align-items:baseline;gap:16px}}
.brow .pc{{color:var(--blue);font-weight:650;font-variant-numeric:tabular-nums;
white-space:nowrap}}
.bbar{{height:7px;background:#e2e8f0;border-radius:99px;margin-top:12px;overflow:hidden}}
.bbar i{{display:block;height:100%;background:var(--blue);border-radius:99px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:0;
background:var(--bg);border:1px solid var(--line);border-radius:10px;overflow:hidden}}
.grid div{{padding:14px 18px;border-right:1px solid var(--line)}}
.grid div:last-child{{border-right:0}}
.grid span{{display:block;color:var(--mute);font-size:10.5px;text-transform:uppercase;
letter-spacing:.05em;margin-bottom:3px}}
.grid b{{font-size:21px;font-variant-numeric:tabular-nums}}
h4{{font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);
margin:22px 0 8px;font-weight:650}}
h4 em{{font-style:normal;text-transform:none;letter-spacing:0;font-weight:400;opacity:.85}}
.path{{background:var(--bg);border:1px solid var(--line);border-radius:10px;overflow:hidden}}
.path div{{display:flex;gap:14px;padding:11px 18px;border-bottom:1px solid var(--line);
font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;
overflow-x:auto;white-space:nowrap}}
.path div:last-child{{border-bottom:0}}
.path i{{font-style:normal;color:#94a3b8;flex:0 0 14px}}
.chips{{display:flex;flex-direction:column;gap:6px}}
.chip{{font-size:13px;background:var(--bg);border:1px solid var(--line);
border-radius:7px;padding:8px 12px;display:flex;gap:10px;align-items:baseline}}
.chip u{{text-decoration:none;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
font-size:11.5px;color:var(--mute);flex:0 0 34px}}
.warn{{background:#fef3f2;border:1px solid #fecdca;border-radius:10px;padding:13px 16px;
font-size:13px}}
.warn code{{background:#fff;padding:1px 5px;border-radius:4px}}
.foot{{position:sticky;bottom:0;background:var(--bg);border-top:1px solid var(--line);
padding:15px 28px;display:flex;justify-content:space-between;align-items:center;
gap:16px;flex-wrap:wrap}}
.foot .rec{{color:var(--mute);font-size:13px}}
.foot button{{font:inherit;font-size:13px;padding:9px 20px;border-radius:8px;
border:1px solid var(--line);background:var(--bg);color:var(--ink);cursor:pointer;
margin-left:9px}}
.foot button.ok{{background:var(--blue);border-color:var(--blue);color:#fff;font-weight:600}}
.stamp{{color:var(--green);font-weight:650;font-size:13px}}
.note{{padding:18px 28px 26px;color:var(--mute);font-size:12.5px;
border-top:1px solid var(--line);background:var(--bg)}}
.note dl{{display:grid;grid-template-columns:max-content 1fr;gap:8px 20px;
margin:0;max-width:1180px}}
.note dt{{font-size:10px;letter-spacing:.09em;text-transform:uppercase;
color:var(--mute);white-space:nowrap;padding-top:3px}}
.note dd{{margin:0;line-height:1.6;color:#334155}}
.note dd.lead{{color:var(--ink)}}
.note b{{color:var(--ink)}}
@media (max-width:640px){{.note dl{{grid-template-columns:1fr;gap:3px 0}}
.note dt{{padding-top:9px}}}}
@media (max-width:900px){{
  .split{{flex-direction:column}}
  .rail{{width:auto;flex:0 0 auto;max-height:230px;border-right:0;
    border-bottom:1px solid var(--line)}}
}}
</style>

<div class="head">
  <div>
    <h1>Merchant risk &middot; review queue</h1>
    <p class="lede">Ranked by what needs a human first. Every case shows the records
    consulted and the route taken to reach them. Nothing is released or upheld
    without an analyst.</p>
  </div>
  <div class="hero">
    <span>Demands avoided</span>
    <b>{full - asked}</b><em>of {full} an ask-everything policy would issue</em>
    <i>Only {asked} items actually asked across {len(pipe)} cases</i>
  </div>
</div>

<div class="filters" id="filters">
  <button data-f="esc"          aria-pressed="false"><u>{n_esc}</u> Need an analyst</button>
  <button data-f="all"          aria-pressed="true"><u>{len(pipe)}</u> All cases</button>
  <button data-f="one_round"    aria-pressed="false"><u>{n_one}</u> Asked once</button>
  <button data-f="zero_contact" aria-pressed="false"><u>{n_zero}</u> Never contacted</button>
  <button data-f="none" disabled><u>0</u> Second rounds</button>
</div>

<div class="split">
  <div class="rail">
    <div class="railhead"><span id="railcount"></span><span>Burden avoided</span></div>
    <div id="rows"></div>
  </div>
  <div class="detail">
    <div class="dinner" id="detail"></div>
    <div class="foot" id="foot"></div>
  </div>
</div>

<div class="note">
<dl>
<dt>Not a result</dt>
<dd class="lead">The cases are synthetic, and one person wrote both the case
store and the rules that resolve it, so these counts show <b>designed
behaviour on data designed for it</b>. The measured result here is the
Stage&nbsp;1 evaluation, where the model had not seen the ground truth. See
<b>README.md</b> and <b>LOG.md</b>.</dd>

<dt>Buttons</dt>
<dd>Approve and Override work, but nothing is saved. There is no backend, so
reloading restores the queue. They exist because the design reserves every
release decision to a human.</dd>

<dt>Provenance</dt>
<dd>{len(pipe)} cases from <code>results/pipeline.json</code>, fingerprint
<code>{fp}</code> over pipeline.json and stage2.json.
<code>python src/verify_claims.py</code> recomputes it and fails if this page is
stale against the repo.</dd>
</dl>
</div>

<script>
var CASES = {data};
var actioned = {{}}, filter = 'all', current = null;

function esc(s) {{
  return String(s).replace(/[&<>"]/g, function (c) {{
    return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c];
  }});
}}
function visible() {{
  return CASES.filter(function (c) {{
    return filter === 'all' || c.state === filter ||
           (filter === 'esc' && c.state.indexOf('escalated') === 0);
  }});
}}
function renderRail() {{
  var list = visible();
  var lbl = document.querySelector('#filters [aria-pressed=true]');
  document.getElementById('railcount').textContent =
    list.length + (list.length === 1 ? ' case · ' : ' cases · ') +
    (lbl ? lbl.textContent.replace(/^\\s*\\d+\\s*/, '') : '');
  document.getElementById('rows').innerHTML = list.map(function (c) {{
    return '<button type="button" class="row' + (actioned[c.id] ? ' actioned' : '') +
      '" data-id="' + c.id +
      '" aria-selected="' + (c.id === current) + '"><div><div><span class="cid">' + c.id +
      '</span><span class="nm">' + esc(c.flag) + '</span></div><div class="meta">' +
      c.rounds + ' round' + (c.rounds === 1 ? '' : 's') + ' · ' +
      (actioned[c.id] || c.railState) + ' · ' + c.path.length + ' hops</div></div>' +
      '<div class="pc">' + c.avoided + '%</div></button>';
  }}).join('') || '<div style="padding:22px 16px;color:#64748b">No cases.</div>';
  if (list.length && list.every(function (c) {{ return c.id !== current; }})) select(list[0].id);
}}
function renderDetail() {{
  var c = CASES.filter(function (x) {{ return x.id === current; }})[0];
  var d = document.getElementById('detail'), f = document.getElementById('foot');
  if (!c) {{ d.innerHTML = ''; f.innerHTML = ''; return; }}
  d.innerHTML =
    '<div class="dhead"><div><h2><span>' + c.id + '</span>' + esc(c.flag) + '</h2>' +
    '<p class="dsub">' + esc(c.sub) + '</p></div>' +
    '<span class="badge ' + c.state + '">' + c.badge + '</span></div>' +
    '<div class="burden"><div class="brow"><div>Ask-everything would demand <b>' +
    c.would + '</b> items · this asked <b>' + (c.asked || 'nothing') + '</b></div>' +
    '<div class="pc">' + c.avoided + '% avoided</div></div>' +
    '<div class="bbar"><i style="width:' + (100 - c.avoided) + '%"></i></div></div>' +
    '<p class="verdict">' + esc(c.verdict) + '</p>' +
    '<div class="grid"><div><span>Rounds</span><b>' + c.rounds + '</b></div>' +
    '<div><span>Hold</span><b>' + c.hold + 'd</b></div>' +
    '<div><span>From our records</span><b>' + c.internal + '</b></div>' +
    '<div><span>From merchant</span><b>' + c.asked + '</b></div></div>' +
    '<h4>Evidence path <em>' + c.path.length +
    ' hops · these stores share no key</em></h4><div class="path">' +
    c.path.map(function (p, i) {{
      return '<div><i>' + (i + 1) + '</i><span>' + esc(p) + '</span></div>';
    }}).join('') + '</div>' +
    (c.requested.length ? '<h4>Requested · one round</h4><div class="chips">' +
      c.requested.map(function (r) {{
        return '<span class="chip"><u>' + esc(r.id) + '</u>' + esc(r.text) + '</span>';
      }}).join('') + '</div>' : '') +
    (c.impossible.length ? '<h4>Cannot be satisfied by this merchant</h4><div class="warn">' +
      c.impossible.map(function (x) {{
        return '<code>' + esc(x.req) + '</code> — ' + esc(x.why);
      }}).join('<br>') + '<br><em>Routed to a human rather than re-asked.</em></div>' : '');
  f.innerHTML = actioned[c.id]
    ? '<span class="stamp">' + actioned[c.id] +
      ' by analyst · not persisted (no backend in this prototype)</span>'
    : '<span class="rec">' + esc(c.action) + '</span><span>' +
      c.buttons.map(function (b) {{
        return '<button class="' + b[0] + '" data-act="' + esc(b[1]) + '">' +
               esc(b[1]) + '</button>';
      }}).join('') + '</span>';
}}
function select(id) {{ current = id; renderRail(); renderDetail(); }}

document.getElementById('rows').addEventListener('click', function (e) {{
  var r = e.target.closest('.row'); if (r) select(r.dataset.id);
}});
document.getElementById('filters').addEventListener('click', function (e) {{
  var b = e.target.closest('button'); if (!b || b.disabled) return;
  document.querySelectorAll('#filters button').forEach(function (x) {{
    x.setAttribute('aria-pressed', String(x === b));
  }});
  filter = b.dataset.f; current = null; renderRail(); renderDetail();
}});
document.getElementById('foot').addEventListener('click', function (e) {{
  var b = e.target.closest('button'); if (!b) return;
  actioned[current] = b.dataset.act;
  var k = document.querySelector('#filters [data-f=esc] u');
  var c = CASES.filter(function (x) {{ return x.id === current; }})[0];
  if (c && c.state.indexOf('escalated') === 0) {{
    k.textContent = Math.max(0, parseInt(k.textContent, 10) - 1);
  }}
  renderRail(); renderDetail();
}});
renderRail(); renderDetail();
</script>
"""


def main():
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size/1024:.0f} KB, self-contained)")
    print("  master-detail: case rail left, one case open right")
    print("  filters and Approve/Override are live; state is not persisted")


if __name__ == "__main__":
    main()
