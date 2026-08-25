# FIX REPORT — Feature Description & Business Benefit

**Scope:** exactly two defects from HR review. Mandatory logic, the AI Business
Benefit generation flow, `main.py`, and the frontend are untouched.

---

## A. Files modified

```
backend/services/ai_enricher.py            (description scrape + benefit guarantee)
backend/services/ppt_generator.py          (blank-cell root cause)
backend/services/excel_generator.py        (defence-in-depth guard)
backend/tests/test_benefit_pipeline.py     (one assertion updated - see B4)
backend/tests/test_feature_description.py  (NEW - 9 regression tests)
backend/tests/fixtures/oracle_f43075_ai_agent_task_allocation.html   (NEW)
backend/tests/fixtures/oracle_f43073_lpn_otbi_reports.html           (NEW)
backend/tests/fixtures/oracle_f43076_robotic_multi_location.html     (NEW)
backend/tests/fixtures/oracle_f43221_b2b_message_converter.html      (NEW)
```

**Not modified:** `backend/main.py`, `backend/services/extractor.py`,
`backend/services/test_script_mapper.py`, `backend/services/test_script_excel.py`,
`backend/auth.py`, `backend/database.py`, all frontend files.

---

## B. Root cause analysis

### B1. Where the description came from (current website)

`backend/services/extractor.py` is **dead code** — nothing imports it. The live
path is `main.py` -> `services/ai_enricher.py` -> `enrich_feature()`:

```
fetch_oracle_detail_text(url)
    description_source = extract_section_text(
        soup, ["overview", "description", "feature summary", "details"]
    ) or extract_feature_body_text(soup) or intro_source
...
description_text = make_safe_description_fallback(title, oracle_detail)
```

### B2. Where the description came from (old Extension)

`Arcturus_Tool_Extension-main/backend/services/extractor.py`, lines 118-127:
find the content container, take the **first two `<p>` over 40 characters in
document order**, join, trim to ~350 chars in `executive_summary()`. It never
inspected `<strong>`/`<b>` and never fell through to whole-page text.

### B3. The regression

`extract_section_text()` scans `h1,h2,h3,h4,`**`strong,b`**. Oracle readiness
pages have no "Overview"/"Description" heading, but their *Steps to enable* and
*Tips and considerations* sections are full of inline bold labels — "On the
**Details** tab", "**Copy Template**", "**Use Template**". One of those bold
runs matches `"details"`, so a fragment of the **setup instructions** was
returned as the feature description.

Reproduced on the f43075 fixture: `extract_section_text(...)` returns
`'Prompt'` — the bold run from "On the **Details** tab, locate the **Prompt**
field."

When that produced nothing usable, `make_safe_description_fallback()` fell
through to `full_text` (the entire page) and emitted setup boilerplate or the
generic templated sentence. Measured in the shipped workbook:

| Symptom | Count |
|---|---|
| Features sharing the identical "Copy Template / Use Template" paragraph | 3 |
| Features with generic "This capability enhances ... in Oracle Cloud SCM" | 2 |
| Duplicate-description groups total | 4 |

### B4. Why Business Benefit came out blank — NOT an AI failure

The shipped Excel and PPTX come from the same run and the same
`enriched_features` list:

| Artifact | Blank Business Benefit |
|---|---|
| `outputs/oracle_26B-inventory-wn-t73741.xlsx` | **0 / 62** |
| `outputs/oracle_26B-inventory-wn-t73741.pptx` | **57 / 62** |

The AI produced a benefit for every feature. `ppt_generator.py` deleted them.

`_clean_benefit_text()` dropped any sentence containing an `IMPACT_KEYWORDS`
entry using a plain substring test. That list contained `"enable"`, `"setup"`,
`"configure"`, `"requires"` — so `"enable"` matched **"enables"** and
**"enabling"**, `"configure"` matched **"configured"**. Those words appear in
almost every well-written benefit. When every sentence was dropped,
`_benefit_cell()` returned `""` by design ("If there is truly no data, leave
blank").

Replaying that exact filter over the 62 benefits in the workbook wipes
**exactly 57** — matching the 57 blank cells byte for byte.

Groq rate limits and Gemini quota errors were a red herring for the blanks.
They are still handled (see C3), but they were not the cause.

Also found: `IMPACT_KEYWORDS`, `GENERIC_PHRASES`, `_clean_benefit_text` and
`_is_generic_benefit` were each **defined twice** in `ppt_generator.py`
(~lines 180-275 and 277-375). The duplicate block is removed.

---

## C. What changed

### C1. Feature Description — direct Oracle scrape, no AI (`ai_enricher.py`)

New `extract_oracle_feature_description(soup, title)` reproduces the
Extension's behaviour and hardens it:

- walks the document from the feature `<h1>` in **document order**, so
  paragraphs nested in Oracle's wrapper `<div>`s are found (the reason the
  sibling-based approach returned nothing);
- stops at the first **real** `h2/h3/h4` section heading — inline
  `<strong>`/`<b>` is **never** treated as a heading, which is the root cause
  fix;
- filters page furniture, image captions, `NOTE:`/`Important:` blocks, role
  code dumps and instruction-style paragraphs;
- trims at a sentence boundary. **Cleaning only — no rewriting, no
  summarising, no AI.**

Computed in `fetch_oracle_detail_text()` into a dedicated `feature_description`
key, deliberately **independent of `description_source`** (which now exists
only to feed the AI benefit prompt), so prompt tuning can never again silently
change what the customer reads.

`enrich_feature()` uses it directly; `make_safe_description_fallback()` is
retained only for pages with no scrapable body prose, and logs loudly when used.

### C2. Business Benefit — blank is now structurally impossible

Four independent layers:

1. **`ai_enricher.ensure_non_empty_benefit()`** — final guard before the value
   is written, on both the normal and the exception path.
2. **`enrich_all_features()`** — post-pass re-checks every row, plus a
   duplicate-description detector and a run summary.
3. **`ppt_generator._clean_benefit_text()`** — impact matching is now
   word-boundary based (`\b...\b`), and the filter is **non-destructive**: if
   it would remove every sentence, the original text is kept.
4. **`ppt_generator._benefit_cell()` / `excel_generator`** — last-resort
   feature-specific fallback built from the feature's own title and its scraped
   Oracle description.

### C3. Feature-specific fallback

`generate_benefit_fallback()` now derives its wording from the feature's own
title, its scraped description and its domain terms, via `_describe_capability()`
and `_infer_outcome_phrase()`. Two different features cannot produce the same
text. Acronyms are preserved ("B2B", not "b2B").

The internal note *"Business value for this feature was not generated by the AI
pipeline and requires functional review"* was being written **into the
customer-facing cell**. It now goes to the run log only, and a scrub removes it
from older saved datasets so it cannot reach a client deck on a rebuild.

Groq / Gemini failure handling is unchanged upstream (retry with corrective
feedback, then provider fallback); what changed is that a total failure now
lands on a grounded, feature-specific statement rather than a placeholder.

### C4. Mandatory column

`assess_mandatory()` verified **byte-identical** to the original. Column values
verified unchanged across a full 62-feature regeneration.

---

## D. Feature Description verification

Extracted by the new scraper from the four features named in the acceptance
criteria (fixtures mirror the live Oracle pages):

**Feature:** AI Agent: Inventory Task Allocation Assistant
> Tasking helps warehouse managers ensure that operators complete the
> activities required to keep operations running smoothly. A critical part of
> this process is ensuring tasks are assigned to the right operators.
> Currently, task assignment depends on manual allocation by managers or
> self-assignment by operators. Manual assignment is often time-consuming and
> inefficient, while self-assignment assumes all operators are equally
> proactive and responsive. ...

*(Previously: "To automatically add a suffix to all artifacts in your agent
team, you can use the Copy Template instead of Use Template button...")*

**Feature:** Create LPN Reports Using the License Plate Number Real Time Subject Area in OTBI
> License Plate Number (LPN) is a unique identifier assigned to a pallet, bin,
> or container of goods to track inventory and manage the movement of goods
> within a warehouse. Using License Plate Number Real Time Subject Area in
> Oracle Transactional Business Intelligence (OTBI), you can now create
> personalized reports on your LPNs and the contents within LPNs ...

*(Previously: "Leverage new subject area(s) by adding to existing reports...")*

**Feature:** Redwood: Deliver to Multiple Locations with Robotic Material Handling Equipment Using a Single Cart
> Healthcare providers often have multiple PAR locations in close proximity to
> each other, and delivering replenishment orders to all of these locations at
> the same time helps optimize the replenishment process. This approach reduces
> foot traffic and minimizes the number of trips required to restock supplies,
> improving overall efficiency. ...

*(Previously: "Use the Manufacturing and Supply Chain Materials Management
offering to enable Advanced Inventory Management...")*

**Feature:** AI Agent: B2B Message Converter - Enrich Workflow Features Along with Upload and Download Capabilities
> You can use the B2B Message Converter AI agent to streamline the conversion of
> B2B messages such as shipments from a Fusion Application REST resource into
> industry-standard formats. Shipments are currently supported in OAGIS 10.1. ...

Every sentence above is asserted to be **verbatim present in the source page**
(`test_description_is_not_ai_generated`).

---

## E. Business Benefit verification

Simulating total AI failure (Groq 429 + Gemini quota exhausted), all four test
features produce a non-empty, distinct, feature-specific benefit — e.g. the LPN
feature lands on *"faster reporting and clearer analysis of the underlying
data"* while the robotic-cart feature lands on *"reduced manual handling through
automated execution"*.

Full 62-feature regeneration through the patched generators:

```
EXCEL : 62 rows, blank Business Benefit = 0     (was 0)
PPTX  : 62 feature rows, blank Business Benefit = 0     (was 57)
MANDATORY unchanged: True
```

---

## F. Regression verification

| Check | Result |
|---|---|
| `assess_mandatory()` byte-identical | PASS |
| Mandatory values across 62 features | unchanged |
| Excel generation | PASS — 62 rows, all 18 columns |
| PPT generation | PASS — 62 feature rows, index + slides intact |
| AI Business Benefit flow (retry + quality gate) | unchanged, PASS |
| `backend/tests/test_benefit_pipeline.py` | 7/7 PASS |
| `backend/tests/test_feature_description.py` | 9/9 PASS |
| All modules compile and import | PASS |
| `main.py`, frontend, test-script generators | untouched |

Run the suites from the repository root:

```bash
python backend/tests/test_benefit_pipeline.py
python backend/tests/test_feature_description.py
```

---

## G. Things you should know

1. **Verification method.** The build sandbox had no outbound network, so the
   four feature pages were retrieved separately and rebuilt as local HTML
   fixtures matching Oracle's DOM. Extraction correctness is proven
   deterministically against those; the blank-benefit fix is proven against
   your real 62-feature dataset. **Please run one live job against
   `26B-inventory-wn-t73741.htm` before sending the deck to HR** and confirm
   the `[DESCRIPTION SUMMARY]` line reports `62/62 scraped directly from
   Oracle` with no duplicates.

2. **Removed from the zip:** `.venv/` (a Windows virtualenv, 275 MB),
   `frontend/node_modules/`, `__pycache__/`, and the **stale nested duplicate**
   at `Arcturus_Tool-main(IMPROVED)/Arcturus_Tool-main(IMPROVED)/`. That
   duplicate held *different* versions of `ai_enricher.py`, `extractor.py`,
   `main.py` and the tests — a genuine hazard, since editing the wrong copy
   looks like a fix that does nothing. Restore it from your original zip if you
   need it. `.git/` is preserved, so `git diff` shows every change.

3. **`.env` is still in the zip** with your API keys, exactly as you supplied
   it. Consider rotating those keys if this file is shared further.

4. **New telemetry.** Each run now prints a `[DESCRIPTION SUMMARY]` block
   (scraped vs fallback, duplicate warnings) alongside the existing
   `[BENEFIT SUMMARY]`. Two additive keys, `description_origin` and
   `benefit_origin`, are set per feature — no existing consumer is affected.

5. **`backend/services/extractor.py` is still dead code.** It was left in place
   deliberately, since removing it was outside the agreed scope, but nothing
   imports it and editing it has no effect on output.
