"""Run the agent, report honest tiered metrics, emit a before/after diff report."""

import html as esc
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from agent import fix_page

PAGES_DIR = Path(__file__).parent / "pages"
OUT_DIR = Path(__file__).parent / "output"
TYPES = ["heading-order", "color-contrast", "image-alt", "label"]

TIER_LABEL = {
    "heading-order": "Tier 1 — deterministic",
    "color-contrast": "Tier 1 — deterministic",
    "image-alt": "Tier 2 — presence (+ Tier 3 quality)",
    "label": "Tier 2 — presence",
}

REAL_SITES = [
    "https://jaipur.manipal.edu/",
    "https://sfsdelhi.com/",
    "https://vvdav.org/",
    "https://hyppy.in/",
]


def print_changes(record):
    for t in TYPES:
        for ch in record[t]["changes"]:
            mark = "OK  " if ch["cleared"] else "SKIP"
            print(f"    [{mark}] {t}  ({ch['selector']})")
            print(f"        - {ch['before']}")
            print(f"        + {ch['after']}")


def run(targets):
    """targets: list of (display_name, url)."""
    totals = {t: {"found": 0, "fixed": 0} for t in TYPES}
    alt_quality = 0
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, url in targets:
            page = browser.new_page()
            try:
                page.goto(url, wait_until="load", timeout=45000)
            except Exception as e:
                print(f"\n{name}\n  could not load ({type(e).__name__})")
                page.close()
                continue

            record = fix_page(page)
            page.close()

            line = []
            for t in TYPES:
                r = record[t]
                totals[t]["found"] += r["found"]
                totals[t]["fixed"] += r["fixed"]
                if r["found"]:
                    line.append(f"{t} {r['fixed']}/{r['found']}")
            alt_quality += record["image-alt"].get("quality_pass", 0)

            print(f"\n{name}")
            print(f"  {'  '.join(line) or 'nothing in scope'}")
            print_changes(record)
            results.append({"name": name, "url": url, "record": record})

        browser.close()
    return totals, alt_quality, results


def report(totals, alt_quality):
    print("\n" + "=" * 58)
    print("RESULTS — by issue type")
    print("=" * 58)
    for t in TYPES:
        f, x = totals[t]["found"], totals[t]["fixed"]
        pct = f"{(x / f * 100):.0f}%" if f else "—"
        print(f"  {t:16} {x}/{f} resolved   {pct}")

    t1_f = totals["heading-order"]["found"] + totals["color-contrast"]["found"]
    t1_x = totals["heading-order"]["fixed"] + totals["color-contrast"]["fixed"]
    t2_f = totals["image-alt"]["found"] + totals["label"]["found"]
    t2_x = totals["image-alt"]["fixed"] + totals["label"]["fixed"]
    total_f, total_x = t1_f + t2_f, t1_x + t2_x
    alt_fixed = totals["image-alt"]["fixed"]
    q = f"{(alt_quality / alt_fixed * 100):.0f}%" if alt_fixed else "—"

    print("\n" + "=" * 58)
    print("RESULTS — by verification tier")
    print("=" * 58)
    print(f"  Tier 1 (deterministic re-scan)      {t1_x}/{t1_f}"
          f"   {'%.0f%%' % (t1_x / t1_f * 100) if t1_f else '—'}")
    print(f"  Tier 2 (presence-verified only)     {t2_x}/{t2_f}"
          f"   {'%.0f%%' % (t2_x / t2_f * 100) if t2_f else '—'}")
    print(f"  Tier 3 (alt quality, probabilistic) {alt_quality}/{alt_fixed}   {q}")

    print("\n" + "=" * 58)
    print("HEADLINE")
    print("=" * 58)
    overall = f"{(total_x / total_f * 100):.0f}%" if total_f else "—"
    print(f"  Resolves {overall} of axe-detected violations")
    print(f"  of the four supported types ({total_x}/{total_f}), confirmed by re-scan.")
    print(f"\n  Of alt text applied, {q} rated adequate by an")
    print("  independent LLM judge (probabilistic).")
    return total_x, total_f, q


def write_report(results, totals, alt_quality, overall, path):
    rows = []
    for res in results:
        blocks = []
        for t in TYPES:
            changes = res["record"][t]["changes"]
            if not changes:
                continue
            items = []
            for ch in changes:
                badge = ("applied" if ch["cleared"] else "skipped")
                cls = "ok" if ch["cleared"] else "skip"
                qual = ""
                if ch.get("quality") is True:
                    qual = '<span class="q pass">quality: pass</span>'
                elif ch.get("quality") is False:
                    qual = '<span class="q fail">quality: fail</span>'
                items.append(f"""
        <div class="change">
          <div class="sel"><code>{esc.escape(ch['selector'])}</code>
            <span class="badge {cls}">{badge}</span>{qual}</div>
          <div class="before">- {esc.escape(ch['before'])}</div>
          <div class="after">+ {esc.escape(ch['after'])}</div>
        </div>""")
            blocks.append(f"""
      <div class="type">
        <h3>{t} <small>{TIER_LABEL[t]}</small></h3>
        {''.join(items)}
      </div>""")
        if blocks:
            rows.append(f"""
    <section>
      <h2>{esc.escape(res['name'])}</h2>
      {''.join(blocks)}
    </section>""")

    by_type = "".join(
        f"<tr><td>{t}</td><td>{totals[t]['fixed']}/{totals[t]['found']}</td>"
        f"<td>{TIER_LABEL[t]}</td></tr>"
        for t in TYPES
    )

    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>a11y-agent report</title>
<style>
 body {{ font: 15px/1.55 -apple-system, system-ui, sans-serif;
        max-width: 900px; margin: 40px auto; padding: 0 20px; color: #1a1a1a; }}
 h1 {{ margin-bottom: 4px; }}
 .meta {{ color: #666; font-size: 13px; margin-bottom: 28px; }}
 .headline {{ background:#f4f7ff; border:1px solid #d4e0ff; border-radius:8px;
              padding:16px 20px; margin-bottom:28px; }}
 table {{ border-collapse: collapse; width: 100%; margin-bottom: 32px; }}
 th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid #eee; font-size:14px; }}
 section {{ border-top:2px solid #eee; padding-top:18px; margin-top:28px; }}
 h2 {{ font-size: 17px; }}
 h3 {{ font-size: 14px; margin: 18px 0 8px; }}
 h3 small {{ font-weight: normal; color:#888; margin-left:8px; }}
 .change {{ border:1px solid #eee; border-radius:6px; padding:10px 12px; margin-bottom:8px; }}
 .sel code {{ font-size:12px; color:#555; }}
 .badge {{ font-size:11px; padding:2px 7px; border-radius:10px; margin-left:8px; }}
 .badge.ok {{ background:#e6f6ea; color:#1a7f37; }}
 .badge.skip {{ background:#fdf1e3; color:#9a6700; }}
 .q {{ font-size:11px; margin-left:6px; color:#666; }}
 .q.fail {{ color:#b32d2d; }}
 .before, .after {{ font-family: ui-monospace, Menlo, monospace; font-size:12.5px;
                    white-space: pre-wrap; padding:3px 6px; border-radius:4px; margin-top:4px; }}
 .before {{ background:#fff1f0; }} .after {{ background:#f0fff4; }}
 footer {{ margin-top:40px; color:#888; font-size:12.5px; border-top:1px solid #eee; padding-top:16px; }}
</style></head><body>
<h1>a11y-agent — fix report</h1>
<div class="meta">Generated {datetime.now():%Y-%m-%d %H:%M} · {len(results)} page(s) ·
  sample cap 5 nodes per issue type per page</div>

<div class="headline">
  <strong>Resolves {overall[0]}/{overall[1]} ({overall[2]}) of axe-detected violations
  of the four supported types</strong>, confirmed by re-scan.<br>
  Of alt text applied, {overall[3]} rated adequate by an independent LLM judge
  <em>(probabilistic — not a deterministic check)</em>.
</div>

<table>
  <tr><th>Issue type</th><th>Resolved</th><th>Verification</th></tr>
  {by_type}
</table>

{''.join(rows)}

<footer>
  Detection and verification are deterministic (axe-core). The language model only
  writes the content of a fix. Fixes are applied to an in-memory copy of the page —
  nothing is sent back to the site. Suggested diffs only: copilot, not autopilot.
</footer>
</body></html>"""

    path.parent.mkdir(exist_ok=True)
    path.write_text(doc, encoding="utf-8")
    print(f"\nReport written to {path}")


if __name__ == "__main__":
    real = len(sys.argv) > 1 and sys.argv[1] == "--real"
    if real:
        targets = [(u, u) for u in REAL_SITES]
    else:
        targets = [(p.name, p.resolve().as_uri())
                   for p in sorted(PAGES_DIR.glob("*.html"))]

    totals, alt_quality, results = run(targets)
    total_x, total_f, q = report(totals, alt_quality)
    pct = f"{(total_x / total_f * 100):.0f}%" if total_f else "—"

    name = "report-real.html" if real else "report-controlled.html"
    write_report(results, totals, alt_quality,
                 (total_x, total_f, pct, q), OUT_DIR / name)