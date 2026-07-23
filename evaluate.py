"""Run the agent, report honest tiered metrics, emit a before/after diff report."""

import html as esc
import sys
from datetime import datetime
from pathlib import Path
from report import write_report

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