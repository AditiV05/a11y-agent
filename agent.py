"""The a11y agent — all four fix types in one place.

Each fixer follows the same shape: find the issue, produce a fix,
apply it, then let axe verify. The LLM only ever writes the *content*
of a fix; axe alone decides what's broken and whether it cleared.
"""

import base64
import re
from pathlib import Path
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

AXE_PATH = Path(__file__).parent / "vendor" / "axe.min.js"
MAX_RETRIES = 2


# ---------- shared ----------

def scan(page):
    page.add_script_tag(content=AXE_PATH.read_text())
    return page.evaluate("async () => await axe.run()")


def find_violation(results, rule_id):
    for v in results["violations"]:
        if v["id"] == rule_id:
            return v
    return None


def count_nodes(page, rule_id):
    v = find_violation(scan(page), rule_id)
    return len(v["nodes"]) if v else 0


# ---------- 1. heading order (LLM judgment, Tier 1) ----------

def get_heading_outline(page):
    return page.evaluate("""() => Array.from(
        document.querySelectorAll('h1,h2,h3,h4,h5,h6')
    ).map(h => h.tagName.toLowerCase() + ': ' + h.textContent.trim())""")


def ask_llm_for_level(outline, bad_html):
    prompt = (
        "This page has a heading-order accessibility problem "
        "(a heading level was skipped).\n\n"
        f"Page heading outline (in order):\n{chr(10).join(outline)}\n\n"
        f"The problematic heading is: {bad_html}\n\n"
        "What heading level SHOULD this be, so levels only increase by one?\n"
        "Reply with ONLY the tag, like: h2"
    )
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    raw = r.choices[0].message.content.strip().lower()
    # The model sometimes replies "<h2>" or "h2." — keep only h1..h6.
    match = re.search(r"h[1-6]", raw)
    return match.group(0) if match else "h2"


def apply_heading_fix(page, bad_html, new_level):
    page.evaluate("""({ badHtml, newLevel }) => {
        for (const h of document.querySelectorAll('h1,h2,h3,h4,h5,h6')) {
            if (h.outerHTML === badHtml) {
                const fixed = document.createElement(newLevel);
                fixed.innerHTML = h.innerHTML;
                h.replaceWith(fixed);
                break;
            }
        }
    }""", {"badHtml": bad_html, "newLevel": new_level})


def fix_headings(page):
    """Returns (found, fixed). Loops over issues; retries each once."""
    found = count_nodes(page, "heading-order")
    fixed = 0

    while True:
        issue = find_violation(scan(page), "heading-order")
        if issue is None:
            break
        bad_html = issue["nodes"][0]["html"]
        outline = get_heading_outline(page)

        cleared = False
        for _ in range(MAX_RETRIES):
            level = ask_llm_for_level(outline, bad_html)
            apply_heading_fix(page, bad_html, level)
            issue_now = find_violation(scan(page), "heading-order")
            still_same = issue_now and issue_now["nodes"][0]["html"] == bad_html
            if not still_same:
                cleared = True
                fixed += 1
                break
        if not cleared:
            break  # unfixable — stop rather than loop forever

    return found, fixed


# ---------- 2. contrast (pure math, Tier 1 — the control case) ----------

def _luminance(rgb):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(rgb1, rgb2):
    l1, l2 = _luminance(rgb1), _luminance(rgb2)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def darken_until_readable(fg_hex, bg_hex, target=4.5):
    fg = list(_hex_to_rgb(fg_hex))
    bg = _hex_to_rgb(bg_hex)
    while _ratio(tuple(fg), bg) < target:
        fg = [max(0, c - 5) for c in fg]
        if fg == [0, 0, 0]:
            break
    return "#{:02x}{:02x}{:02x}".format(*fg)


def apply_color_fix(page, bad_html, new_color):
    page.evaluate("""({ badHtml, newColor }) => {
        for (const el of document.querySelectorAll('*')) {
            if (el.outerHTML === badHtml) { el.style.color = newColor; break; }
        }
    }""", {"badHtml": bad_html, "newColor": new_color})


def fix_contrast(page):
    found = count_nodes(page, "color-contrast")
    fixed = 0
    for _ in range(found):
        issue = find_violation(scan(page), "color-contrast")
        if issue is None:
            break
        node = issue["nodes"][0]
        data = node["any"][0]["data"]
        new_color = darken_until_readable(data["fgColor"], data["bgColor"])
        apply_color_fix(page, node["html"], new_color)
        if count_nodes(page, "color-contrast") < found - fixed:
            fixed += 1
    return found, fixed


# ---------- 3. alt text (vision model, Tier 2 + Tier 3) ----------

def _encode(path):
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def get_image_path(page, bad_html):
    """Resolve the flagged <img>'s real file path on disk."""
    src = page.evaluate("""(badHtml) => {
        for (const img of document.querySelectorAll('img')) {
            if (img.outerHTML === badHtml) return img.src;
        }
        return null;
    }""", bad_html)
    if not src or not src.startswith("file://"):
        return None
    return Path(unquote(urlparse(src).path))


def describe_image(image_path):
    b64 = _encode(image_path)
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": [
            {"type": "text", "text":
                "Write concise, accurate alt text for this image, for a screen reader. "
                "One sentence. Do not start with 'image of'. Reply with only the alt text."},
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}],
    )
    return r.choices[0].message.content.strip()


def judge_alt_quality(image_path, alt_text):
    """Tier 3 — probabilistic. Returns True if the judge says PASS."""
    b64 = _encode(image_path)
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": [
            {"type": "text", "text":
                f'Here is alt text written for the image below:\n\n"{alt_text}"\n\n'
                "Does it accurately and usefully describe the image for a blind user?\n"
                "Reply with ONLY one word: PASS or FAIL"},
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}],
    )
    return r.choices[0].message.content.strip().upper().startswith("PASS")


def apply_alt_fix(page, bad_html, alt_text):
    page.evaluate("""({ badHtml, altText }) => {
        for (const img of document.querySelectorAll('img')) {
            if (img.outerHTML === badHtml) { img.setAttribute('alt', altText); break; }
        }
    }""", {"badHtml": bad_html, "altText": alt_text})


def fix_alt(page):
    """Returns (found, presence_fixed, quality_passed)."""
    found = count_nodes(page, "image-alt")
    fixed = 0
    quality_passed = 0

    for _ in range(found):
        issue = find_violation(scan(page), "image-alt")
        if issue is None:
            break
        bad_html = issue["nodes"][0]["html"]
        img_path = get_image_path(page, bad_html)
        if img_path is None or not img_path.exists():
            break  # can't read the image — honest failure

        alt = describe_image(img_path)
        apply_alt_fix(page, bad_html, alt)

        if count_nodes(page, "image-alt") < found - fixed:
            fixed += 1                       # Tier 2: presence confirmed
            if judge_alt_quality(img_path, alt):
                quality_passed += 1          # Tier 3: quality judged

    return found, fixed, quality_passed


# ---------- 4. form labels (LLM judgment, Tier 2) ----------

def suggest_label(input_html):
    prompt = (
        f"This form input has no accessible label:\n\n{input_html}\n\n"
        "Suggest a short, clear label based on its type/name attributes.\n"
        "Reply with ONLY the label text, like: Email address"
    )
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content.strip()


def apply_label_fix(page, bad_html, label_text):
    page.evaluate("""({ badHtml, labelText }) => {
        for (const inp of document.querySelectorAll('input')) {
            if (inp.outerHTML === badHtml) {
                inp.setAttribute('aria-label', labelText);
                break;
            }
        }
    }""", {"badHtml": bad_html, "labelText": label_text})


def fix_labels(page):
    found = count_nodes(page, "label")
    fixed = 0
    for _ in range(found):
        issue = find_violation(scan(page), "label")
        if issue is None:
            break
        bad_html = issue["nodes"][0]["html"]
        apply_label_fix(page, bad_html, suggest_label(bad_html))
        if count_nodes(page, "label") < found - fixed:
            fixed += 1
    return found, fixed


# ---------- run all four on one page ----------

def fix_page(page):
    """Run every fixer on the loaded page. Returns a per-type record."""
    h_found, h_fixed = fix_headings(page)
    c_found, c_fixed = fix_contrast(page)
    a_found, a_fixed, a_quality = fix_alt(page)
    l_found, l_fixed = fix_labels(page)

    return {
        "heading-order": {"found": h_found, "fixed": h_fixed},
        "color-contrast": {"found": c_found, "fixed": c_fixed},
        "image-alt": {"found": a_found, "fixed": a_fixed, "quality_pass": a_quality},
        "label": {"found": l_found, "fixed": l_fixed},
    }