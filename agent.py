"""The a11y agent — all four fix types in one place.

Each fixer: find the issue, produce a fix, apply it, let axe verify.
The LLM only ever writes the *content* of a fix; axe alone decides
what's broken and whether it cleared.
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
MAX_NODES_PER_TYPE = 5   # sample cap — keeps real-page runs fast

def short(html, limit=90):
    """Collapse whitespace and trim for display."""
    s = " ".join((html or "").split())
    return s if len(s) <= limit else s[:limit - 3] + "..."


# ---------- shared ----------

def scan(page):
    page.add_script_tag(content=AXE_PATH.read_text())
    return page.evaluate("async () => await axe.run()")


def find_violation(results, rule_id):
    for v in results["violations"]:
        if v["id"] == rule_id:
            return v
    return None


def node_selector(node):
    """axe TRUNCATES node['html'] on large elements, so exact string matching
    fails on real pages. Its 'target' CSS selector is reliable — use that."""
    target = node.get("target") or []
    if len(target) != 1:
        return None          # nested in an iframe — out of scope for v1
    return target[0]


def count_nodes(page, rule_id):
    v = find_violation(scan(page), rule_id)
    return len(v["nodes"]) if v else 0


def still_flagged(page, rule_id, selector):
    """Is THIS specific element still flagged? More precise than counting."""
    issue = find_violation(scan(page), rule_id)
    if issue is None:
        return False
    return any(node_selector(n) == selector for n in issue["nodes"])


def next_unseen(issue, seen):
    """First node we haven't already attempted."""
    for n in issue["nodes"]:
        sel = node_selector(n)
        if sel and sel not in seen:
            return n, sel
    return None, None


# ---------- 1. heading order (LLM judgment, Tier 1) ----------

def get_heading_outline(page):
    return page.evaluate("""() => Array.from(
        document.querySelectorAll('h1,h2,h3,h4,h5,h6')
    ).map(h => h.tagName.toLowerCase() + ': ' + h.textContent.trim().slice(0, 60))""")


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
    match = re.search(r"h[1-6]", raw)     # model sometimes replies "<h2>"
    return match.group(0) if match else "h2"


def apply_heading_fix(page, selector, new_level):
    page.evaluate("""({ sel, newLevel }) => {
        const h = document.querySelector(sel);
        if (!h) return;
        const fixed = document.createElement(newLevel);
        fixed.innerHTML = h.innerHTML;
        for (const a of h.attributes) fixed.setAttribute(a.name, a.value);
        h.replaceWith(fixed);
    }""", {"sel": selector, "newLevel": new_level})


def fix_headings(page):
    """Returns {'attempted', 'fixed', 'changes'}."""
    found = count_nodes(page, "heading-order")
    attempted = min(found, MAX_NODES_PER_TYPE)
    fixed = 0
    changes = []
    seen = set()

    for _ in range(attempted):
        issue = find_violation(scan(page), "heading-order")
        if issue is None:
            break
        node, sel = next_unseen(issue, seen)
        if node is None:
            break
        seen.add(sel)
        outline = get_heading_outline(page)
        before = node["html"]

        cleared = False
        after = before
        for _ in range(MAX_RETRIES):
            level = ask_llm_for_level(outline, before)
            apply_heading_fix(page, sel, level)
            after = re.sub(r"^<h[1-6]", f"<{level}", before)
            after = re.sub(r"</h[1-6]>$", f"</{level}>", after)
            if not still_flagged(page, "heading-order", sel):
                cleared = True
                fixed += 1
                break

        changes.append({"selector": sel, "before": short(before),
                        "after": short(after), "cleared": cleared})

    return {"attempted": attempted, "fixed": fixed, "changes": changes}


def fix_contrast(page):
    found = count_nodes(page, "color-contrast")
    attempted = min(found, MAX_NODES_PER_TYPE)
    fixed = 0
    changes = []
    seen = set()

    for _ in range(attempted):
        issue = find_violation(scan(page), "color-contrast")
        if issue is None:
            break
        node, sel = next_unseen(issue, seen)
        if node is None:
            break
        seen.add(sel)

        data = (node.get("any") or [{}])[0].get("data") or {}
        fg, bg = data.get("fgColor"), data.get("bgColor")
        if not fg or not bg:
            changes.append({"selector": sel, "before": short(node["html"]),
                            "after": "skipped — axe could not resolve a background colour",
                            "cleared": False})
            continue

        new_color = darken_until_readable(fg, bg)
        apply_color_fix(page, sel, new_color)
        cleared = not still_flagged(page, "color-contrast", sel)
        if cleared:
            fixed += 1

        changes.append({
            "selector": sel,
            "before": f"color: {fg} on {bg} (ratio {data.get('contrastRatio', '?')})",
            "after": f"color: {new_color} (ratio \u2265 4.5)",
            "cleared": cleared,
        })

    return {"attempted": attempted, "fixed": fixed, "changes": changes}


def fix_alt(page):
    found = count_nodes(page, "image-alt")
    attempted = min(found, MAX_NODES_PER_TYPE)
    fixed = 0
    quality_passed = 0
    changes = []
    seen = set()

    for _ in range(attempted):
        issue = find_violation(scan(page), "image-alt")
        if issue is None:
            break
        node, sel = next_unseen(issue, seen)
        if node is None:
            break
        seen.add(sel)

        data = get_image_data(page, sel)
        if data is None:
            changes.append({"selector": sel, "before": short(node["html"]),
                            "after": "skipped — image unreadable (svg, data URI, or blocked)",
                            "cleared": False, "quality": None})
            continue
        b64, mime = data

        alt = describe_image(b64, mime)
        apply_alt_fix(page, sel, alt)
        cleared = not still_flagged(page, "image-alt", sel)

        quality = None
        if cleared:
            fixed += 1                                   # Tier 2
            quality = judge_alt_quality(b64, mime, alt)  # Tier 3
            if quality:
                quality_passed += 1

        changes.append({"selector": sel, "before": short(node["html"]),
                        "after": f'alt="{alt}"', "cleared": cleared,
                        "quality": quality})

    return {"attempted": attempted, "fixed": fixed,
            "quality_pass": quality_passed, "changes": changes}


def fix_labels(page):
    found = count_nodes(page, "label")
    attempted = min(found, MAX_NODES_PER_TYPE)
    fixed = 0
    changes = []
    seen = set()

    for _ in range(attempted):
        issue = find_violation(scan(page), "label")
        if issue is None:
            break
        node, sel = next_unseen(issue, seen)
        if node is None:
            break
        seen.add(sel)

        label = suggest_label(node["html"])
        apply_label_fix(page, sel, label)
        cleared = not still_flagged(page, "label", sel)
        if cleared:
            fixed += 1

        changes.append({"selector": sel, "before": short(node["html"]),
                        "after": f'aria-label="{label}"', "cleared": cleared})

    return {"attempted": attempted, "fixed": fixed, "changes": changes}


def fix_page(page):
    h, c, a, l = (fix_headings(page), fix_contrast(page),
                  fix_alt(page), fix_labels(page))
    return {
        "heading-order": {"found": h["attempted"], "fixed": h["fixed"],
                          "changes": h["changes"]},
        "color-contrast": {"found": c["attempted"], "fixed": c["fixed"],
                           "changes": c["changes"]},
        "image-alt": {"found": a["attempted"], "fixed": a["fixed"],
                      "quality_pass": a["quality_pass"], "changes": a["changes"]},
        "label": {"found": l["attempted"], "fixed": l["fixed"],
                  "changes": l["changes"]},
    }

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


def apply_color_fix(page, selector, new_color):
    # !important — site CSS often outranks a plain inline style.
    page.evaluate("""({ sel, newColor }) => {
        const el = document.querySelector(sel);
        if (el) el.style.setProperty('color', newColor, 'important');
    }""", {"sel": selector, "newColor": new_color})


# ---------- 3. alt text (vision model, Tier 2 + Tier 3) ----------

OK_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def get_image_data(page, selector):
    """Fetch the image bytes. Local or remote. Returns (b64, mime) or None."""
    src = page.evaluate("""(sel) => {
        const img = document.querySelector(sel);
        return img ? (img.currentSrc || img.src) : null;
    }""", selector)

    if not src:
        return None

    if src.startswith("file://"):
        path = Path(unquote(urlparse(src).path))
        if not path.exists():
            return None
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return base64.b64encode(path.read_bytes()).decode("utf-8"), mime

    if src.startswith("http"):
        try:
            resp = page.request.get(src, timeout=15000)
            if not resp.ok:
                return None
            mime = (resp.headers.get("content-type") or "").split(";")[0].strip()
            if mime not in OK_TYPES:
                return None          # svg or unsupported
            return base64.b64encode(resp.body()).decode("utf-8"), mime
        except Exception:
            return None              # network error / blocked

    return None                      # data: URI or something else


def describe_image(b64, mime):
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": [
            {"type": "text", "text":
                "Write concise, accurate alt text for this image, for a screen reader. "
                "One sentence. Do not start with 'image of'. Reply with only the alt text."},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
    )
    return r.choices[0].message.content.strip()


def judge_alt_quality(b64, mime, alt_text):
    """Tier 3 — probabilistic. True if the judge says PASS."""
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": [
            {"type": "text", "text":
                f'Here is alt text written for the image below:\n\n"{alt_text}"\n\n'
                "Does it accurately and usefully describe the image for a blind user?\n"
                "Reply with ONLY one word: PASS or FAIL"},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
    )
    return r.choices[0].message.content.strip().upper().startswith("PASS")


def apply_alt_fix(page, selector, alt_text):
    page.evaluate("""({ sel, altText }) => {
        const img = document.querySelector(sel);
        if (img) img.setAttribute('alt', altText);
    }""", {"sel": selector, "altText": alt_text})



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


def apply_label_fix(page, selector, label_text):
    page.evaluate("""({ sel, labelText }) => {
        const inp = document.querySelector(sel);
        if (inp) inp.setAttribute('aria-label', labelText);
    }""", {"sel": selector, "labelText": label_text})

