from pathlib import Path
from playwright.sync_api import sync_playwright

AXE_PATH = Path(__file__).parent / "vendor" / "axe.min.js"
URL = (Path(__file__).parent / "test_contrast.html").resolve().as_uri()

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(URL, wait_until="load")
    page.add_script_tag(content=AXE_PATH.read_text())
    results = page.evaluate("async () => await axe.run()")
    browser.close()

# Find the contrast violation and print the details axe gives us
for v in results["violations"]:
    if v["id"] == "color-contrast":
        node = v["nodes"][0]
        print("HTML:", node["html"])
        print("\nWhat axe knows about the colors:")
        print(node["any"][0]["data"])