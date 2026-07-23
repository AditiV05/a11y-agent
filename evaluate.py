"""Slice 5 — run the agent across all test pages and report honest, tiered metrics."""

from pathlib import Path
from playwright.sync_api import sync_playwright

from agent import fix_page

PAGES_DIR = Path(__file__).parent / "pages"
TYPES = ["heading-order", "color-contrast", "image-alt", "label"]


def run_all():
    pages = sorted(PAGES_DIR.glob("*.html"))
    totals = {t: {"found": 0, "fixed": 0} for t in TYPES}
    alt_quality = 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for path in pages:
            page = browser.new_page()
            page.goto(path.resolve().as_uri(), wait_until="load")

            record = fix_page(page)

            line = []
            for t in TYPES:
                r = record[t]
                totals[t]["found"] += r["found"]
                totals[t]["fixed"] += r["fixed"]
                if r["found"]:
                    line.append(f"{t} {r['fixed']}/{r['found']}")
            alt_quality += record["image-alt"].get("quality_pass", 0)

            print(f"{path.name:12} {'  '.join(line) or 'nothing to fix'}")
            page.close()
        browser.close()

    return totals, alt_quality


def report(totals, alt_quality):
    print("\n" + "=" * 58)
    print("RESULTS — by issue type")
    print("=" * 58)
    for t in TYPES:
        f, x = totals[t]["found"], totals[t]["fixed"]
        pct = f"{(x / f * 100):.0f}%" if f else "—"
        print(f"  {t:16} {x}/{f} resolved   {pct}")

    # Tier 1 = deterministic verification (heading order, contrast)
    t1_found = totals["heading-order"]["found"] + totals["color-contrast"]["found"]
    t1_fixed = totals["heading-order"]["fixed"] + totals["color-contrast"]["fixed"]

    # Tier 2 = presence only (alt text, labels)
    t2_found = totals["image-alt"]["found"] + totals["label"]["found"]
    t2_fixed = totals["image-alt"]["fixed"] + totals["label"]["fixed"]

    total_found = t1_found + t2_found
    total_fixed = t1_fixed + t2_fixed

    print("\n" + "=" * 58)
    print("RESULTS — by verification tier")
    print("=" * 58)
    print(f"  Tier 1 (deterministic re-scan)  {t1_fixed}/{t1_found}"
          f"   {'%.0f%%' % (t1_fixed / t1_found * 100) if t1_found else '—'}")
    print(f"  Tier 2 (presence-verified only) {t2_fixed}/{t2_found}"
          f"   {'%.0f%%' % (t2_fixed / t2_found * 100) if t2_found else '—'}")

    alt_fixed = totals["image-alt"]["fixed"]
    q = f"{(alt_quality / alt_fixed * 100):.0f}%" if alt_fixed else "—"
    print(f"  Tier 3 (alt quality, probabilistic) {alt_quality}/{alt_fixed}   {q}")

    print("\n" + "=" * 58)
    print("HEADLINE")
    print("=" * 58)
    overall = f"{(total_fixed / total_found * 100):.0f}%" if total_found else "—"
    print(f"  Resolves {overall} of axe-detected violations")
    print(f"  of the four supported types ({total_fixed}/{total_found}), confirmed by re-scan.")
    print(f"\n  Of alt text applied, {q} rated adequate by an")
    print(f"  independent LLM judge (probabilistic).")


if __name__ == "__main__":
    totals, alt_quality = run_all()
    report(totals, alt_quality)