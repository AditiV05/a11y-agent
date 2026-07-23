"""Report rendering for a11y-agent.

The design premise: not all "fixed" means the same thing, so confidence —
not the page, not the issue type — is the primary organising idea. The
confidence readout at the top encodes each tier with a distinct fill
*pattern* as well as a distinct hue, because a tool that audits colour
contrast should not itself rely on colour alone to carry meaning.

The generated page is also built to pass its own audit: correct heading
order, a lang attribute, visible focus, no colour-only signalling.
"""

import html as esc
from datetime import datetime

TYPES = ["heading-order", "color-contrast", "image-alt", "label"]

TYPE_TIER = {
    "heading-order": 1,
    "color-contrast": 1,
    "image-alt": 2,
    "label": 2,
}

TIER_NAME = {
    1: "Deterministic",
    2: "Presence",
    3: "Probabilistic",
}

TIER_PROVES = {
    1: "axe re-scan confirms the violation is gone",
    2: "the required attribute now exists — quality unverified",
    3: "a separate vision model judged the alt text — not a deterministic check",
}

CSS = """
:root {
  --ink:      #14161a;
  --ink-soft: #5b6069;
  --paper:    #fcfcfb;
  --card:     #ffffff;
  --rule:     #e3e3df;
  --t1:       #1c5c4b;
  --t2:       #8a6216;
  --t3:       #5c4a91;
  --del-bg:   #fdf3f2;  --del-ink: #8f1f1a;
  --add-bg:   #f1f7f2;  --add-ink: #14532d;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  --serif: Charter, "Iowan Old Style", "Palatino Linotype", Georgia, serif;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  padding: 0 24px 96px;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 15px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}

.wrap { max-width: 940px; margin: 0 auto; }

:focus-visible {
  outline: 2px solid var(--t3);
  outline-offset: 2px;
}

/* ---------- masthead ---------- */

.masthead { padding: 64px 0 28px; border-bottom: 1px solid var(--ink); }

h1 {
  font-family: var(--serif);
  font-weight: 400;
  font-size: clamp(34px, 6vw, 52px);
  line-height: 1.05;
  letter-spacing: -0.015em;
  margin: 0 0 18px;
}
h1 em { font-style: italic; }

.meta {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-soft);
  text-transform: uppercase;
  letter-spacing: 0.09em;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
}

/* ---------- the readout (signature) ---------- */

.readout { padding: 40px 0 8px; }

.readout-head {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ink-soft);
  margin-bottom: 22px;
}

.tier { padding: 18px 0; border-top: 1px solid var(--rule); }
.tier:first-of-type { border-top: none; }

.tier-top {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 9px;
}

.tier-id {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.12em;
  padding: 2px 7px;
  border: 1px solid currentColor;
  border-radius: 2px;
}

.tier-name {
  font-family: var(--serif);
  font-size: 21px;
  letter-spacing: -0.01em;
}

.tier-count {
  font-family: var(--mono);
  font-size: 13px;
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}

.tier-proves { font-size: 13.5px; color: var(--ink-soft); margin-bottom: 12px; }

.gauge {
  height: 13px;
  background: #ececea;
  border: 1px solid var(--rule);
  border-radius: 2px;
  overflow: hidden;
}
.gauge-fill { height: 100%; }

/* Pattern, not just hue — the point of the whole thing. */
.t1 { color: var(--t1); }
.t1 .gauge-fill { background: var(--t1); }

.t2 { color: var(--t2); }
.t2 .gauge-fill {
  background: repeating-linear-gradient(
    -45deg, var(--t2) 0 3px, #ffffff 3px 6px);
}

.t3 { color: var(--t3); }
.t3 .gauge-fill {
  background: radial-gradient(var(--t3) 42%, transparent 44%) 0 0 / 6px 6px;
  background-color: #ffffff;
}

/* ---------- headline sentence ---------- */

.claim {
  font-family: var(--serif);
  font-size: 19px;
  line-height: 1.5;
  margin: 34px 0 0;
  padding: 22px 0 0;
  border-top: 1px solid var(--ink);
}
.claim strong { font-weight: 600; }
.claim .qual { display: block; margin-top: 8px; font-size: 15.5px; color: var(--ink-soft); }

/* ---------- controls ---------- */

.controls {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 14px 0;
  margin-top: 48px;
  background: var(--paper);
  border-bottom: 1px solid var(--rule);
}
.controls span {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-soft);
  margin-right: 4px;
}
.controls button {
  font-family: var(--mono);
  font-size: 11.5px;
  letter-spacing: 0.06em;
  padding: 5px 11px;
  border: 1px solid var(--rule);
  border-radius: 2px;
  background: var(--card);
  color: var(--ink-soft);
  cursor: pointer;
}
.controls button[aria-pressed="true"] {
  border-color: var(--ink);
  color: var(--ink);
  background: #f0efec;
}

/* ---------- pages ---------- */

.page { padding-top: 46px; }

h2 {
  font-family: var(--mono);
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.01em;
  word-break: break-all;
  margin: 0 0 4px;
}
.page-tally {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-soft);
  margin-bottom: 22px;
  font-variant-numeric: tabular-nums;
}

h3 {
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  margin: 30px 0 11px;
  display: flex;
  align-items: center;
  gap: 9px;
}
.rule-tier {
  font-family: var(--mono);
  font-weight: 400;
  letter-spacing: 0.06em;
  padding: 1px 6px;
  border: 1px solid currentColor;
  border-radius: 2px;
  font-size: 10px;
}

/* ---------- change cards ---------- */

.change {
  background: var(--card);
  border: 1px solid var(--rule);
  border-left-width: 3px;
  border-radius: 3px;
  padding: 12px 14px;
  margin-bottom: 9px;
}
.change.is-applied { border-left-color: var(--t1); }
.change.is-skipped { border-left-color: var(--rule); background: #faf9f7; }

.change-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 9px;
}
.sel {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-soft);
  word-break: break-all;
  flex: 1 1 320px;
  min-width: 0;
}
.state {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  white-space: nowrap;
}
.state.applied { color: var(--t1); }
.state.skipped { color: var(--t2); }
.judge {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.05em;
  white-space: nowrap;
  color: var(--t3);
}
.judge.fail { color: #8f1f1a; }

.line {
  font-family: var(--mono);
  font-size: 12.5px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  padding: 5px 9px;
  border-radius: 2px;
  margin-top: 4px;
}
.line.del { background: var(--del-bg); color: var(--del-ink); }
.line.add { background: var(--add-bg); color: var(--add-ink); }
.line .mark { user-select: none; opacity: 0.55; }

/* ---------- colophon ---------- */

footer {
  margin-top: 90px;
  padding-top: 26px;
  border-top: 1px solid var(--ink);
}
.colophon-head {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ink-soft);
  margin: 0 0 18px;
}
.colophon {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 44px;
}
.colophon p {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.65;
  color: var(--ink-soft);
  max-width: 46ch;
}
footer strong { color: var(--ink); font-weight: 600; }

@media (max-width: 720px) {
  .colophon { grid-template-columns: 1fr; gap: 14px; }
}
"""

JS = """
const buttons = document.querySelectorAll('[data-filter]');
buttons.forEach(btn => btn.addEventListener('click', () => {
  const want = btn.dataset.filter;
  buttons.forEach(b => b.setAttribute('aria-pressed', String(b === btn)));
  document.querySelectorAll('.change').forEach(card => {
    const state = card.dataset.state;
    card.hidden = !(want === 'all' || want === state);
  });
  document.querySelectorAll('.rule-group').forEach(g => {
    g.hidden = !g.querySelector('.change:not([hidden])');
  });
  document.querySelectorAll('.page').forEach(p => {
    p.hidden = !p.querySelector('.rule-group:not([hidden])');
  });
}));
"""

def _pct(n, d):
    return f"{(n / d * 100):.0f}%" if d else "—"


def _gauge(n, d, tier):
    width = (n / d * 100) if d else 0
    return (
        f'<div class="tier t{tier}">'
        f'  <div class="tier-top">'
        f'    <span class="tier-id">TIER {tier}</span>'
        f'    <span class="tier-name">{TIER_NAME[tier]}</span>'
        f'    <span class="tier-count">{n}/{d} &nbsp;{_pct(n, d)}</span>'
        f'  </div>'
        f'  <p class="tier-proves">{TIER_PROVES[tier]}</p>'
        f'  <div class="gauge" role="img" aria-label="{n} of {d} — {_pct(n, d)}">'
        f'    <div class="gauge-fill" style="width:{width:.1f}%"></div>'
        f'  </div>'
        f'</div>'
    )


def _change_card(ch, tier):
    applied = bool(ch["cleared"])
    state = "applied" if applied else "skipped"
    judge = ""
    if ch.get("quality") is True:
        judge = '<span class="judge">judged adequate</span>'
    elif ch.get("quality") is False:
        judge = '<span class="judge fail">judged inadequate</span>'

    return (
        f'<div class="change is-{state}" data-state="{state}">'
        f'  <div class="change-head">'
        f'    <code class="sel">{esc.escape(ch["selector"])}</code>'
        f'    <span class="state {state}">{state}</span>{judge}'
        f'  </div>'
        f'  <div class="line del"><span class="mark">− </span>'
        f'{esc.escape(ch["before"])}</div>'
        f'  <div class="line add"><span class="mark">+ </span>'
        f'{esc.escape(ch["after"])}</div>'
        f'</div>'
    )


def write_report(results, totals, alt_quality, overall, path):
    """overall is (fixed, found, pct_string, alt_quality_pct_string)."""
    total_x, total_f, pct, qpct = overall

    t1_f = totals["heading-order"]["found"] + totals["color-contrast"]["found"]
    t1_x = totals["heading-order"]["fixed"] + totals["color-contrast"]["fixed"]
    t2_f = totals["image-alt"]["found"] + totals["label"]["found"]
    t2_x = totals["image-alt"]["fixed"] + totals["label"]["fixed"]
    t3_f = totals["image-alt"]["fixed"]

    readout = "".join([
        _gauge(t1_x, t1_f, 1),
        _gauge(t2_x, t2_f, 2),
        _gauge(alt_quality, t3_f, 3),
    ])

    pages = []
    for res in results:
        groups = []
        tally = []
        for t in TYPES:
            rec = res["record"][t]
            if rec["found"]:
                tally.append(f'{t} {rec["fixed"]}/{rec["found"]}')
            changes = rec["changes"]
            if not changes:
                continue
            tier = TYPE_TIER[t]
            cards = "".join(_change_card(c, tier) for c in changes)
            extra = " + tier 3" if t == "image-alt" else ""
            groups.append(
                f'<div class="rule-group">'
                f'  <h3>{t}<span class="rule-tier t{tier}">'
                f'tier {tier}{extra}</span></h3>'
                f'  {cards}'
                f'</div>'
            )
        if groups:
            pages.append(
                f'<section class="page">'
                f'  <h2>{esc.escape(res["name"])}</h2>'
                f'  <p class="page-tally">{esc.escape("  ·  ".join(tally))}</p>'
                f'  {"".join(groups)}'
                f'</section>'
            )

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>a11y-agent — fix report</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

  <header class="masthead">
    <h1>Every fix, and <em>how far</em> to trust it.</h1>
    <p class="meta">
      <span>a11y-agent</span>
      <span>{datetime.now():%d %b %Y · %H:%M}</span>
      <span>{len(results)} page(s)</span>
      <span>cap 5 nodes / issue / page</span>
    </p>
  </header>

  <main>

  <section class="readout">
    <h2 class="readout-head">Confidence by verification tier</h2>
    {readout}

    <p class="claim">
      <strong>Resolves {total_x} of {total_f} ({pct}) axe-detected violations
      of the four supported types</strong>, confirmed by re-scan.
      <span class="qual">Of the alt text applied, {qpct} was rated adequate by an
      independent vision model — a probabilistic judgement, not a guarantee.</span>
    </p>
  </section>

  <div class="controls">
    <span>Show</span>
    <button data-filter="all" aria-pressed="true">All</button>
    <button data-filter="applied" aria-pressed="false">Applied</button>
    <button data-filter="skipped" aria-pressed="false">Skipped</button>
  </div>

  {"".join(pages)}

  </main>

  <footer>
    <p class="colophon-head">The guarantee</p>
    <div class="colophon">
      <p><strong>Detection and verification are deterministic.</strong> axe-core
      decides what is broken and whether a fix cleared. The language model only
      writes the content of a fix — the heading level, the alt text, the label.</p>
      <p><strong>Nothing is written to the live site.</strong> Fixes are applied
      to an in-memory copy of the page. These are suggested diffs: copilot,
      not autopilot.</p>
    </div>
  </footer>

</div>
<script>{JS}</script>
</body>
</html>"""
    
    path.parent.mkdir(exist_ok=True)
    path.write_text(doc, encoding="utf-8")
    print(f"\nReport written to {path}")