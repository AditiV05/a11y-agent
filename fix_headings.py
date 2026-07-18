from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

AXE_PATH = Path(__file__).parent / "vendor" / "axe.min.js"
URL = (Path(__file__).parent / "test_page.html").resolve().as_uri()


def scan(page):
    """Inject axe and return its results for the current page."""
    page.add_script_tag(content=AXE_PATH.read_text())
    return page.evaluate("async () => await axe.run()")


def find_heading_issue(results):
    """Pull out the heading-order violation, if any."""
    for v in results["violations"]:
        if v["id"] == "heading-order":
            return v
    return None

def get_heading_outline(page):
    """Return the page's headings in order, like ['h1: Cooking Basics', 'h4: Eggs']."""
    return page.evaluate("""() => {
        const headings = document.querySelectorAll('h1,h2,h3,h4,h5,h6');
        return Array.from(headings).map(h => h.tagName.toLowerCase() + ': ' + h.textContent.trim());
    }""")


def ask_llm_for_level(outline, bad_html):
    """Ask the LLM what heading level the bad element should be. Returns e.g. 'h2'."""
    prompt = f"""This page has a heading-order accessibility problem (a heading level was skipped).

Page heading outline (in order):
{chr(10).join(outline)}

The problematic heading is: {bad_html}

What heading level SHOULD this be, so levels only increase by one?
Reply with ONLY the tag, like: h2
No explanation, no other text."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip().lower()

def apply_fix(page, bad_html, new_level):
    """Change the bad heading to the new level in the live page."""
    page.evaluate("""({ badHtml, newLevel }) => {
        const headings = document.querySelectorAll('h1,h2,h3,h4,h5,h6');
        for (const h of headings) {
            if (h.outerHTML === badHtml) {
                const fixed = document.createElement(newLevel);
                fixed.innerHTML = h.innerHTML;
                h.replaceWith(fixed);
                break;
            }
        }
    }""", {"badHtml": bad_html, "newLevel": new_level})


def get_bad_heading(page):
    """Re-scan and return the first bad heading's HTML, or None if all clear."""
    issue = find_heading_issue(scan(page))
    if issue is None:
        return None
    return issue["nodes"][0]["html"]

if __name__ == "__main__":
    MAX_RETRIES = 2

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="load")

        fixed_count = 0
        failed_count = 0

        # Type A: keep going while any bad heading remains.
        while True:
            bad_html = get_bad_heading(page)
            if bad_html is None:
                break  # all heading-order problems cleared

            print(f"\nProblem heading: {bad_html}")
            outline = get_heading_outline(page)

            # Type B: retry this one heading up to MAX_RETRIES times.
            cleared = False
            for attempt in range(1, MAX_RETRIES + 1):
                new_level = ask_llm_for_level(outline, bad_html)
                print(f"  attempt {attempt}: LLM suggests {new_level}")
                apply_fix(page, bad_html, new_level)

                # Did THIS heading get cleared? Re-scan and check.
                if get_bad_heading(page) != bad_html:
                    print(f"  ✅ cleared")
                    cleared = True
                    fixed_count += 1
                    break
                else:
                    print(f"  ↻ still flagged, retrying")

            if not cleared:
                print(f"  ❌ gave up after {MAX_RETRIES} attempts")
                failed_count += 1
                break  # stop so we don't loop forever on an unfixable heading

        print(f"\nDone. Fixed: {fixed_count}, Failed: {failed_count}")
        browser.close()