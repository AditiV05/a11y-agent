# a11y-agent

An agent that runs a **detect → fix → verify** loop on web page accessibility
problems. It finds real issues with axe-core, proposes context-aware fixes, and
confirms its own fixes actually cleared — with verification honest enough to
distinguish _"a fix was applied"_ from _"the fix is good."_

```
Resolves 76% of axe-detected violations of the four supported types
(34/45 across 4 live sites), confirmed by re-scan.
Of alt text applied, 80% rated adequate by an independent LLM judge
(probabilistic — not a deterministic check).
```

[See a full report →](output/report-real.html)

---

## The design rule

The whole project rests on one constraint:

> **The language model does judgment only. It never decides what is broken, and
> never decides whether its own fix worked.**

- **Detection** is deterministic — axe-core scans the page and names the exact
  element at fault.
- **Verification** is deterministic — axe-core re-scans the patched page. The
  model does not get to declare success.
- **The model** writes only the _content_ of a fix: what heading level fits here,
  what alt text describes this image, what label suits this input.

The test: remove the model entirely, and axe still detects, Playwright still
renders, and verification still runs. What is left is a working scanner. That is
the difference between a system and a wrapper.

---

## Verification tiers

Not all "fixed" means the same thing, so the agent reports three tiers separately
rather than collapsing them into one flattering number.

| Tier                                 | What it proves                                                                        | Applies to              |
| ------------------------------------ | ------------------------------------------------------------------------------------- | ----------------------- |
| **Tier 1 — deterministic**           | The violation is provably gone; axe re-scan confirms                                  | heading order, contrast |
| **Tier 2 — presence**                | A required attribute now exists; axe cannot judge its quality                         | alt text, form labels   |
| **Tier 3 — quality (probabilistic)** | A separate vision-model pass judged whether the alt text actually describes the image | alt text only           |

The trap this refuses: letting _"axe went green"_ inflate into _"accessibility
solved."_ axe confirms a presence or structure fix. It does not confirm that alt
text is any good. Those are different claims and this project keeps them apart.

---

## What it fixes

Four issue types. Deliberately four — the win condition is a narrow thing that
works, not a broad thing that half-works.

| Issue            | Fix engine                                   | Verified as     |
| ---------------- | -------------------------------------------- | --------------- |
| `heading-order`  | LLM judgment (which level _should_ this be?) | Tier 1          |
| `color-contrast` | Pure math — WCAG ratio, no model involved    | Tier 1          |
| `image-alt`      | Vision model writes the description          | Tier 2 + Tier 3 |
| `label`          | LLM judgment (what does this input want?)    | Tier 2          |

**Contrast is the control case.** Its fix is computed to satisfy exactly what axe
measures, and no model touches it. So if contrast ever fails verification, the
bug is in the harness, not the model. It caught two real bugs during development.

---

## Results

**Controlled corpus** (9 hand-built pages with known planted problems):
11/11 resolved. This is a sanity check on the pipeline, not a result.

**Live sites** (4 real, unaudited sites — single run):

| Issue type       | Resolved        | Verification           |
| ---------------- | --------------- | ---------------------- |
| heading-order    | 8/8 (100%)      | Tier 1 — deterministic |
| color-contrast   | 9/20 (45%)      | Tier 1 — deterministic |
| image-alt        | 15/15 (100%)    | Tier 2 — presence      |
| label            | 2/2 (100%)      | Tier 2 — presence      |
| **Overall**      | **34/45 (76%)** |                        |
| Alt-text quality | 12/15 (80%)     | Tier 3 — probabilistic |

The denominator is violations **of the four supported types only**. A real page
throws 14+ distinct axe rules; this agent claims four of them and counts nothing
else.

---

## Known limitations

These are the honest edges, not a to-do list.

**Contrast can't fix light text on a mid-tone background.** Changing the text
colour in either direction either fails to reach 4.5:1 or destroys the design
(white caption on red → near-black). The correct fix is adjusting the
_background_, which is out of scope. Those cases are skipped and reported as
skipped. An earlier version "solved" them by darkening blindly and scored 89% —
that number was partly earned by fixes a developer would reject.

**Tier 3 is a floor, not a certificate.** The judge reliably fails lazy or
off-topic alt text ("image", "a dog running in a park" for a fox). It does _not_
catch confident errors: the X logo was described once as a cat and once as a
spider, and the judge passed both. Tier 3 catches sloppiness, not hallucination.

**Tier 3 is also non-deterministic.** The same alt text can pass one run and fail
the next. Any quality figure needs a real sample size behind it.

**Live-site numbers move between runs.** Pages render differently on each load —
carousels, lazy content, conditional forms — so even the denominator shifts. Quote
a single run with a date, or average several.

**Sampling cap.** Five nodes per issue type per page. One test page had 142 images
missing alt text; fixing every one would mean hundreds of API calls for a single
page. The cap keeps runs fast and is stated in every report.

**Unreadable images are skipped.** SVGs, data URIs, and blocked or cross-origin
images that fail to fetch cannot be sent to the vision model.

**Static / server-rendered pages only.** Fixes are applied to the rendered DOM.
On a static or SSR page that maps cleanly to a real source change. On a React app
where an `<img>` is generated three components up, "patched the DOM, axe passes"
does not translate to a pull request.

**Copilot, not autopilot.** The agent suggests diffs. It never writes to the live
site — all patching happens on an in-memory copy of the page.

---

## Setup

Requires Python 3.9+ and an OpenAI API key.

```bash
git clone https://github.com/AditiV05/a11y-agent.git
cd a11y-agent

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium        # ~150 MB, one time
```

Create a `.env` file in the project root:

```
OPENAI_API_KEY=sk-your-key-here
```

Set a hard spend cap on your OpenAI account before running anything. A full eval
run costs well under a dollar with `gpt-4o-mini`, but the cap should exist anyway.

## Usage

```bash
# Detect only — no model, no fixes. The deterministic spine.
python detect.py https://example.com
python detect.py pages/h2.html

# Full detect → fix → verify across the controlled corpus
python evaluate.py

# ...and across the live sites listed in evaluate.py
python evaluate.py --real
```

Each run prints a per-page diff and a tiered summary, and writes an HTML
before/after report to `output/`.

Regenerate the controlled test corpus with `python make_pages.py`.

## Layout

```
a11y-agent/
├── agent.py           # the four fixers + the shared detect/verify loop
├── detect.py          # detection only — the no-LLM spine
├── evaluate.py        # eval harness, tiered metrics, HTML report
├── make_pages.py      # generates the controlled test corpus
├── pages/             # 9 controlled test pages
├── vendor/axe.min.js  # pinned axe-core 4.12.1
└── output/            # generated reports
```

## Built with

Playwright (headless Chromium) · axe-core 4.12.1 · OpenAI `gpt-4o-mini` · Python

## Future work (v2)

- Framework-aware source diffs — map a DOM fix back to the component that
  generated it, and open a real pull request
- Background-colour adjustment for the contrast cases v1 skips
- A web UI
- A larger, versioned eval corpus so the headline number is an average rather
  than a single run
