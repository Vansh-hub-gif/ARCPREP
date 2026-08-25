# FEATURE DESCRIPTION EXTRACTION — FIX

Scope: Feature Description only. Verified byte-identical: Business Benefit,
Mandatory, Bug IDs, Impact, Steps to Enable, Access Requirements, Priority, URL.

## Root cause

The previous implementation anchored on the feature title:

```python
heading = soup.find("h1") or soup.find("h2")
nodes = heading.find_all_next([...])
```

**On the live Oracle pages the feature title is not an `<h1>` or `<h2>`.**
The only real heading elements are the SECTION headings. So that lookup
resolved to `"Steps to enable and configure"`, and collection began *inside*
the setup section. That is precisely how these reached the deck:

| Feature | Wrong output (from Steps to enable) |
|---|---|
| AI Agent: Inventory Task Allocation Assistant | "To enable permission groups for roles, complete these steps: ..." |
| Redwood: Deliver to Multiple Locations ... | "Use the Manufacturing and Supply Chain Materials Management offering to enable ..." |
| AI Agent: B2B Message Converter ... | "To automatically add a suffix to all artifacts in your agent team ..." |

The fixtures shipped previously marked the title as `<h1>`, so the bug could
not reproduce in test. Three of the four fixtures now have **no `<h1>` at
all**, matching the live markup.

## The fix — structure-first boundary

The reliable structural signal is not the title, it is the **first section
marker**. Everything before `"Steps to enable and configure"` /
`"Tips and considerations"` / `"Key resources"` / `"Access requirements"` is
the feature explanation; everything after is setup and reference material.

`extract_oracle_feature_description()` now:

1. walks the document in order and **cuts at the first section marker**,
   recognised as a heading tag *or* a short standalone block (Oracle uses both);
2. collects `<p>`, leaf `<div>` and `<li>` — tag-tolerant, because body text is
   `<p>` on some pages and `<div class="p">` on others. `<td>` is excluded
   (table text is reference material);
3. drops page furniture, image captions, `NOTE:`/`Important:` blocks, role code
   dumps, link lists, and Oracle's own closing benefit line
   ("This feature increases operational efficiency by ...") which belongs to
   the Business Benefit column;
4. falls back to slicing the page's **flat text** on the same boundary when the
   DOM shape is unfamiliar, so an unexpected layout degrades to a slightly
   noisier description instead of to setup instructions;
5. applies a **final gate** — `_looks_like_setup_text()` — that rejects
   instruction-shaped content outright. A blank cell is recoverable; a
   confidently wrong one is not.

Keyword matching is used only to reject furniture, never as the boundary.

Length cap raised 700 -> 900 chars: longer than the gold-standard deck
(~200-500 chars per description) without overflowing a 3-row slide.

## Verified output

**AI Agent: Inventory Task Allocation Assistant**
> Tasking helps warehouse managers ensure that operators complete the
> activities required to keep operations running smoothly. A critical part of
> this process is ensuring tasks are assigned to the right operators.
> Currently, task assignment depends on manual allocation by managers or
> self-assignment by operators. ... To address this need, you can use the
> Inventory Task Allocation Assistant AI agent. ...

**Redwood: Deliver to Multiple Locations with Robotic Material Handling Equipment Using a Single Cart**
> Healthcare providers often have multiple PAR locations in close proximity to
> each other, and delivering replenishment orders to all of these locations at
> the same time helps optimize the replenishment process. ... Now, the robotic
> material handling integration can support this optimized workflow by
> delivering to multiple destinations in a single run using one cart. ...

**Create LPN Reports Using the License Plate Number Real Time Subject Area in OTBI**
> License Plate Number (LPN) is a unique identifier assigned to a pallet, bin,
> or container of goods ... Using License Plate Number Real Time Subject Area
> in Oracle Transactional Business Intelligence (OTBI), you can now create
> personalized reports on your LPNs ...

**AI Agent: B2B Message Converter ...**
> You can use the B2B Message Converter AI agent to streamline the conversion
> of B2B messages such as shipments from a Fusion Application REST resource
> into industry-standard formats. ...

Every sentence is asserted to be **verbatim present in the source page**, so
nothing is rewritten, summarised or invented.

## Tests

`backend/tests/test_feature_description.py` — 14 checks, all passing:
title-not-a-heading, `<p>` vs `<div>` markup, setup-text gate, no duplicate
descriptions, verbatim-only, detail level >= gold standard, and one case run
against **verbatim flat text from the live f43076 page**.

`backend/tests/test_benefit_pipeline.py` — unchanged, still passing.

## Regression

Regenerated Excel + PPT from the 62-feature dataset:

```
rows excel: 62 | ppt feature rows: 62
blank Business Benefit: 0 | blank Description: 0
NON-DESCRIPTION COLUMNS CHANGED: 0
```

Business Benefit is computed from `description_source` (the AI prompt input),
which is untouched — it is structurally independent of the description column,
so this change cannot move it.

Only `backend/services/ai_enricher.py` was modified. `main.py`,
`ppt_generator.py`, `excel_generator.py`, `extractor.py`, the test-script
generators and the frontend are byte-identical to your upload.

## Please confirm on one live run

The build sandbox has no outbound network, so extraction was verified against
fixtures rebuilt to the live markup plus real page text. Run one job and check
the log line:

```
[DESCRIPTION SUMMARY] 62/62 scraped directly from Oracle, 0 used the heuristic fallback.
```

Any `[DESCRIPTION] Rejected a setup/enablement block ...` line names a feature
whose page has an unusual layout and is worth eyeballing.
