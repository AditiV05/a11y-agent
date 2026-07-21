from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

AXE_PATH = Path(__file__).parent / "vendor" / "axe.min.js"
URL = (Path(__file__).parent / "test_label.html").resolve().as_uri()


def scan(page):
    page.add_script_tag(content=AXE_PATH.read_text())
    return page.evaluate("async () => await axe.run()")


def find_label_issue(results):
    for v in results["violations"]:
        if v["id"] == "label":
            return v
    return None


def suggest_label(input_html):
    """Ask the LLM for a short label based on the input's HTML."""
    prompt = f"""This form input has no accessible label:

{input_html}

Suggest a short, clear label for it (based on its type/name attributes).
Reply with ONLY the label text, like: Email address
No explanation, no colon, no other text."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


def apply_label_fix(page, bad_html, label_text):
    """Add an aria-label to the flagged input in the live page."""
    page.evaluate("""({ badHtml, labelText }) => {
        const inputs = document.querySelectorAll('input');
        for (const inp of inputs) {
            if (inp.outerHTML === badHtml) {
                inp.setAttribute('aria-label', labelText);
                break;
            }
        }
    }""", {"badHtml": bad_html, "labelText": label_text})


if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="load")

        issue = find_label_issue(scan(page))
        if not issue:
            print("No missing-label problem found.")
        else:
            # There are 2 unlabeled inputs — fix each one
            for node in issue["nodes"]:
                bad_html = node["html"]
                label = suggest_label(bad_html)
                print(f"{bad_html}  →  label: {label}")
                apply_label_fix(page, bad_html, label)

            # Tier 2 verify: does axe confirm labels now exist?
            if find_label_issue(scan(page)) is None:
                print("\n✅ TIER 2 VERIFIED — all inputs now have labels.")
            else:
                print("\n❌ Some inputs still missing labels.")

        browser.close()