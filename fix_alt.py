import base64
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

AXE_PATH = Path(__file__).parent / "vendor" / "axe.min.js"
URL = (Path(__file__).parent / "test_alt.html").resolve().as_uri()
IMAGE_PATH = Path(__file__).parent / "fox.jpeg"

def encode_image(path):
    """Read an image file and turn it into base64 text for the API."""
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def describe_image(image_path):
    """Send the image to the vision model, get back alt text."""
    b64 = encode_image(image_path)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text":
                    "Write concise, accurate alt text for this image, for a screen reader. "
                    "Describe what's shown in one sentence. "
                    "Do not start with 'image of' or 'picture of'. Reply with only the alt text."},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}"
                }},
            ],
        }],
    )
    return response.choices[0].message.content.strip()

def judge_alt_quality(image_path, alt_text):
    """Tier 3: a separate model pass that scores whether the alt text fits the image.
    Probabilistic — this is a judgment, not a deterministic check."""
    b64 = encode_image(image_path)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text":
                    f'Here is alt text written for the image below:\n\n"{alt_text}"\n\n'
                    "Does it accurately and usefully describe the image for a blind user? "
                    "Reply in this exact format:\n"
                    "VERDICT: PASS or FAIL\n"
                    "REASON: one short sentence"},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}"
                }},
            ],
        }],
    )
    return response.choices[0].message.content.strip()

def scan(page):
    page.add_script_tag(content=AXE_PATH.read_text())
    return page.evaluate("async () => await axe.run()")


def find_alt_issue(results):
    for v in results["violations"]:
        if v["id"] == "image-alt":
            return v
    return None


def apply_alt_fix(page, bad_html, alt_text):
    """Add the alt attribute to the flagged image in the live page."""
    page.evaluate("""({ badHtml, altText }) => {
        const imgs = document.querySelectorAll('img');
        for (const img of imgs) {
            if (img.outerHTML === badHtml) {
                img.setAttribute('alt', altText);
                break;
            }
        }
    }""", {"badHtml": bad_html, "altText": alt_text})


if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="load")

        issue = find_alt_issue(scan(page))
        if not issue:
            print("No missing-alt-text problem found.")
        else:
            bad_html = issue["nodes"][0]["html"]
            print("Image missing alt:", bad_html)

            # Fix: vision model writes the description
            alt_text = describe_image(IMAGE_PATH)
            print("Generated alt:", alt_text)

            apply_alt_fix(page, bad_html, alt_text)

            # Tier 2 verify: does axe confirm alt now exists?
            if find_alt_issue(scan(page)) is None:
                print("✅ TIER 2 VERIFIED — alt text is present.")

                # Tier 3 judge: is the alt text actually good? (probabilistic)
                verdict = judge_alt_quality(IMAGE_PATH, alt_text)
                print("\n--- TIER 3 (quality, probabilistic) ---")
                print(verdict)
            else:
                print("❌ Fix did not clear the violation.")

        browser.close()