from pathlib import Path

OUT = Path(__file__).parent / "pages"
OUT.mkdir(exist_ok=True)

def page(body):
    return f"""<!DOCTYPE html>
<html lang="en">
<head><title>Test</title></head>
<body><main>
{body}
</main></body>
</html>"""

PAGES = {
    # heading-order problems
    "h1.html": "<h1>Recipes</h1>\n<h4>Soup</h4><p>Warm.</p>",
    "h2.html": "<h1>Guide</h1>\n<h2>Setup</h2>\n<h5>Step one</h5><p>Do it.</p>",
    "h3.html": "<h1>Docs</h1>\n<h3>Intro</h3>\n<h2>Usage</h2>\n<h6>Notes</h6><p>Text.</p>",

    # contrast problems
    "c1.html": '<h1>Page</h1>\n<p style="color:#999999;background:#ffffff">Faint text here.</p>',
    "c2.html": '<h1>Page</h1>\n<p style="color:#aaaaaa;background:#ffffff">Also faint text.</p>',

    # missing alt text
    "a1.html": '<h1>Gallery</h1>\n<img src="../fox.jpeg" width="300">',
    "a2.html": '<h1>Photos</h1>\n<img src="../fox.jpeg" width="200">\n<p>A caption.</p>',

    # missing labels
    "l1.html": '<h1>Login</h1>\n<input type="email" name="email">',
    "l2.html": '<h1>Signup</h1>\n<input type="text" name="username">\n<input type="password" name="pw">',
}

for name, body in PAGES.items():
    (OUT / name).write_text(page(body))

print(f"Created {len(PAGES)} pages in {OUT}")