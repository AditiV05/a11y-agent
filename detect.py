import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

# Where we saved axe-core, and which page to scan.
AXE_PATH = Path(__file__).parent / "vendor" / "axe.min.js"

# Take the page from the command line; fall back to test_page.html if none given.
if len(sys.argv) > 1:
    URL = (Path(__file__).parent / sys.argv[1]).resolve().as_uri()
else:
    URL = (Path(__file__).parent / "test_page.html").resolve().as_uri()

def scan(url):
    axe_source = AXE_PATH.read_text()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="load")
        page.add_script_tag(content=axe_source)        # inject axe-core
        results = page.evaluate("async () => await axe.run()")  # run it
        browser.close()
    return results


def show(results):
    violations = results["violations"]
    order = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3}
    violations.sort(key=lambda v: order.get(v["impact"], 4))

    print(f"\nFound {len(violations)} violations\n")
    for i, v in enumerate(violations, 1):
        print(f"{i}. [{v['impact']}] {v['id']} — {v['help']}")
        print(f"   affects {len(v['nodes'])} element(s)")
        print(f"   {v['helpUrl']}\n")


if __name__ == "__main__":
    show(scan(URL))