from pathlib import Path
from playwright.sync_api import sync_playwright

AXE_PATH = Path(__file__).parent / "vendor" / "axe.min.js"
URL = (Path(__file__).parent / "test_contrast.html").resolve().as_uri()


def scan(page):
    page.add_script_tag(content=AXE_PATH.read_text())
    return page.evaluate("async () => await axe.run()")


def find_contrast_issue(results):
    for v in results["violations"]:
        if v["id"] == "color-contrast":
            return v
    return None


# ---- The contrast math (WCAG standard) ----

def _relative_luminance(rgb):
    """How bright a color is, per WCAG. rgb = (r, g, b), each 0-255."""
    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(rgb1, rgb2):
    """Ratio between two colors, 1.0 (same) to 21.0 (black vs white)."""
    l1, l2 = _relative_luminance(rgb1), _relative_luminance(rgb2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def darken_until_readable(fg_hex, bg_hex, target=4.5):
    """Darken the text color step by step until it meets the target ratio."""
    fg = list(_hex_to_rgb(fg_hex))
    bg = _hex_to_rgb(bg_hex)

    while _contrast_ratio(tuple(fg), bg) < target:
        # nudge each channel toward black
        fg = [max(0, c - 5) for c in fg]
        if fg == [0, 0, 0]:  # can't get darker than black
            break
    return _rgb_to_hex(tuple(fg))

def apply_color_fix(page, bad_html, new_color):
    """Set the text color of the flagged element in the live page."""
    page.evaluate("""({ badHtml, newColor }) => {
        const els = document.querySelectorAll('*');
        for (const el of els) {
            if (el.outerHTML === badHtml) {
                el.style.color = newColor;
                break;
            }
        }
    }""", {"badHtml": bad_html, "newColor": new_color})


if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="load")

        issue = find_contrast_issue(scan(page))
        if not issue:
            print("No contrast problem found.")
        else:
            node = issue["nodes"][0]
            bad_html = node["html"]
            colors = node["any"][0]["data"]
            fg, bg = colors["fgColor"], colors["bgColor"]

            print(f"Bad element ratio: {colors['contrastRatio']} (needs {colors['expectedContrastRatio']})")

            new_color = darken_until_readable(fg, bg)
            print(f"Fixing text color: {fg} → {new_color}")

            apply_color_fix(page, bad_html, new_color)

            # Verify — axe is the judge
            if find_contrast_issue(scan(page)) is None:
                print("✅ VERIFIED — contrast problem is gone.")
            else:
                print("❌ Fix did not clear the violation.")

        browser.close()