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


def verify(page):
    """Re-run axe and check if the heading-order problem is gone."""
    results = scan(page)
    return find_heading_issue(results) is None

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="load")

        issue = find_heading_issue(scan(page))

        if not issue:
            print("No heading-order problem found.")
        else:
            bad_html = issue["nodes"][0]["html"]
            outline = get_heading_outline(page)
            print("Bad heading:", bad_html)

            new_level = ask_llm_for_level(outline, bad_html)
            print("LLM suggests:", new_level)

            apply_fix(page, bad_html, new_level)
            print("Applied fix.")

            if verify(page):
                print("✅ VERIFIED — heading-order problem is gone.")
            else:
                print("❌ Fix did not clear the violation.")

        browser.close()