# CHANGELOG — Business Benefit pipeline repair

## Context-based Business Benefit update — 2026-08-14

- Added explicit golden-reference examples from the Extension baseline to the Business Benefit prompt.
- Removed the fixed two-statement output requirement; the model can return 1-3 feature-specific statements.
- Added cross-feature near-duplicate detection so repeated consultant-style structures are rejected and regenerated.
- Reworked the final fallback so it uses Oracle's feature-specific Business Benefit/Key Benefits evidence when available instead of the old generic `Centers ... / The resulting value ...` template.
- Preserved Feature Description scraping and all non-Business-Benefit processing.
- Offline regression suite: **30 passed**.


**Scope of this change set: `backend/services/ai_enricher.py` only.**

No other file was modified. Authentication, login/signup, the React frontend,
the dashboard, URL scraping, feature extraction, Excel generation, PPT
generation, test script generation, the existing APIs, the output column
schema and the existing UI/workflow are all untouched.

Two new documentation files (`CHANGELOG.md`, `VALIDATION.md`) and one new test
directory (`backend/tests/`) were added. Neither is imported by application
code.

---

## 0. Finding that changed the scope of the work

The original brief asked for the website output to be made to match the Chrome
Extension output, treating the extension file as the gold standard.

That is not what the two uploaded files are. Both were produced by the Python
backend in this repository:

| Evidence | Detail |
|---|---|
| Column schema | The header row of `oracle_26B-inventory-wn-t73741__17_.xlsx` matches `excel_generator.py::COLUMNS` exactly — same 18 names, same order, including `Mandatory (Yes/No)`. |
| Hardcoded Notes string | Both files contain `"Validate the setup and business impact in a lower environment before production rollout."`, which is a Python string literal in `enrich_feature()`. |
| Hardcoded Impact strings | Both files contain `"NO BUSINESS IMPACT unless …"` and `"LOW IMPACT - requires role configuration … for …"`, built by f-strings in `assess_business_impact()`. |
| Column count | `OQUAT_Report__5_.xlsx` has 17 columns — an older build of the same backend, from before `Mandatory (Yes/No)` was added. |

Measured against the quality gate added in this change set, the file labelled
"extension / gold standard" is the **worse** of the two (21/62 rows pass) and
the file labelled "website / incorrect" is the better one (27/61 rows pass).

Converging the website onto the extension output would therefore have made the
product worse. The work was redirected to fixing the defect that both files
share: the AI path fails silently on roughly one row in three, and a rule-based
fallback ships mangled Oracle documentation in its place.

---

## 1. `extract_feature_body_text()` — NEW

**File:** `backend/services/ai_enricher.py`

**Issue fixed:** `description_source` came back empty for a large share of
features, so the AI prompt carried almost no feature context.

**Why it was empty:** `extract_intro_text()` collects content via
`h1.find_next_siblings()`. On Oracle readiness feature pages where the title is
not rendered as a literal `<h1>`, or where the description paragraphs are
nested inside wrapper `<div>`s rather than being siblings of the heading, that
call returns nothing. The declared fallback,
`extract_section_text(soup, ["overview", "description", "feature summary", "details"])`,
also returns nothing, because Oracle does not use those heading names on
feature pages. Both paths returning `""` left `description_source` empty.

**How it improves Business Benefit generation:** the new function walks every
`<p>` / `<li>` after the title in **document order** rather than as siblings,
and stops at the first recognised Oracle section heading (`Business Benefit`,
`Steps to Enable`, `Tips And Considerations`, `Key Resources`,
`Access Requirements`, …). If no heading element exists at all it falls back to
scanning all `<p>`/`<li>` nodes. The model now receives the actual feature
description instead of an empty string.

**Wired in at:** `fetch_oracle_detail_text()`, as the second of three
candidates for `description_source`:

```python
result["description_source"] = (
    extract_section_text(soup, ["overview", "description", "feature summary", "details"])
    or extract_feature_body_text(soup)
    or result["intro_source"]
)
```

The original heading-based extractor is still tried first, so pages that *do*
have an Overview heading behave exactly as before. This is additive, not a
replacement.

---

## 2. `extract_oracle_benefit_section()` — NEW

**Issue fixed:** dead code. `fetch_oracle_detail_text()` declared
`"benefit_source": ""` in its result dict and **never assigned it**, and no
code anywhere in the repository read the key.

**Why it mattered:** Oracle publishes its own *Business Benefit* paragraph on
most readiness feature pages. It is the single most business-value-dense piece
of text on the page — exactly the raw material a consultant would reason from.
It was being discarded before the prompt was constructed.

**How it improves Business Benefit generation:** the section is now extracted
and passed into the prompt under an explicit no-copying instruction:

```
Oracle's Stated Benefit (raw material for your reasoning —
you must NOT reuse its wording):
```

The model gets the business framing without being handed wording it can
plagiarise. The anti-copying constraint is enforced independently by the
overlap check in §5, so this is grounding rather than a paraphrase invitation.

---

## 3. `GROQ_FALLBACK_MODEL` — FIXED

**Before:**

```python
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_FALLBACK_MODEL = "llama-3.3-70b-versatile"  # fallback if needed
```

**Issue fixed:** the two constants were the same string. The
`"model decommissioned"` branch inside `call_groq()` recursed into an identical
call with identical parameters, which failed identically. The fallback was a
no-op that consumed the retry budget.

**After:** `GROQ_FALLBACK_MODEL` defaults to a genuinely different model and is
env-overridable via `GROQ_FALLBACK_MODEL`.

---

## 4. `call_groq()` return contract + `call_ai()` — FIXED / NEW

**Before:** `call_groq()` ended with `return None` after exhausting its retry
budget. The caller's branch for that was:

```python
if not ai_benefit:
    print(f"[AI EMPTY] No content returned for: {title}")
```

**Issue fixed:** a transient rate-limit was indistinguishable from a
successful-but-empty generation. Both produced `None`, both logged the same
line, and both dropped straight into the rule-based fallback. Rate-limit
failures were being silently converted into permanently bad output rows.

Separately, `generate_benefit_ai()` dispatched to exactly one provider based on
`AI_PROVIDER`. If Groq was down, Gemini was never tried even when
`GEMINI_API_KEY` was configured and healthy.

**After:**

- `call_groq()` raises `RuntimeError` on retry exhaustion instead of returning
  `None`, so failure is distinguishable from empty output.
- Explicit retry handling added for `httpx.TimeoutException` and
  `httpx.TransportError` with exponential backoff — previously these escaped
  the `HTTPStatusError` handler and aborted the whole attempt.
- New `call_ai(prompt)` is the single generation entry point. It tries
  Groq then Gemini (order reversed when `AI_PROVIDER=gemini`), skips providers
  with no API key, collects per-provider errors, and raises only when every
  provider has failed. The aggregated error string is logged, so the reason for
  a failure is visible rather than inferred.

**How it improves Business Benefit generation:** a transient Groq 429 no longer
costs you a permanently generic row.

---

## 5. `validate_benefit_lines()` — NEW (replaces inline prefix blacklist)

**Before:** an inline list of bad prefixes inside `enrich_feature()`, applied
once, with the whole generation discarded if fewer than two lines survived.

**Issue fixed:** the gate could only detect one failure mode (documentation
openings) and had no way to communicate *why* something was rejected, so the
only available response to a rejection was surrender.

**After:** a standalone function returning `(accepted_lines, rejection_reasons)`.
Checks applied per line:

| Check | Default | Env override |
|---|---|---|
| Minimum words | 15 | `OQUAT_BENEFIT_MIN_WORDS` |
| Maximum words | 60 | `OQUAT_BENEFIT_MAX_WORDS` |
| Documentation-style opening | `provides`, `supports`, `enables`, `allows`, `this feature`, `this capability`, `this enhancement`, `use this feature`, `you can`, `users can`, `with this feature`, … | — |
| Generic boilerplate phrases | `improves operational efficiency`, `enhances productivity`, `provides better reporting`, … | — |
| Token overlap with source text | 0.85 | `OQUAT_BENEFIT_MAX_OVERLAP` |
| Duplicate of an accepted line | — | — |

The overlap check (`_source_overlap_ratio`) computes, per candidate line, the
maximum fraction of its content words that also appear in any single sentence
of the source material. This is what catches paraphrased Oracle prose that
passes the prefix test.

**Threshold tuning:** 0.85 was chosen empirically against your own uploaded
data rather than picked by feel. At 0.72 the gate flagged two lines that are
legitimately good consultant output — `"Streamlines B2B messaging setup by
eliminating the need to configure connec…"` (0.75) and `"Automates the
derivation of intercompany transfer prices for back-to-back i…"` (0.71). At
0.85 those pass and the copied lines (0.87–1.00) are still caught. See
`VALIDATION.md` §3.

---

## 6. Retry loop with corrective feedback — NEW

**Before:** one AI call. One validation pass. On rejection, immediate fallback.

**After:** up to `BENEFIT_MAX_ATTEMPTS` (default 3, env
`OQUAT_BENEFIT_MAX_ATTEMPTS`) attempts. When a generation is rejected, the
specific rejection reasons are formatted and appended to the next prompt under
a `CORRECTION REQUIRED — YOUR PREVIOUS ATTEMPT WAS REJECTED` block, so the
model is told exactly what was wrong rather than being re-asked blind.

`generate_benefit_ai()` gained a `corrective_note: str = ""` parameter. The
default is empty, so the first attempt sends the original prompt unchanged.

**How it improves Business Benefit generation:** this is the change that
converts most former fallback rows into real AI output. Verified end to end
in `backend/tests/test_benefit_pipeline.py` scenario A: a scripted model
returns documentation-style junk twice, then clean output, and the pipeline
recovers with `benefit_origin: AI_RETRY_3` instead of falling back.

---

## 7. `generate_benefit_fallback()` — REWRITTEN

**This is the function that produced the output you were unhappy with.**

**Before:** it scored sentences from the Oracle page, picked the top two, and
re-emitted them with a business verb glued to the front. Its input was
`description or full_text[:3000]` — and because `description_source` was
frequently empty (§1), it fell through to `full_text`, which is the entire
page including Steps-to-Enable configuration tables.

Actual output from the unmodified function:

```
Improves this value is in hours.
Improves leave the ID cell blank.
Improves open the .csv and update the desired values to make changes.
Improves duplicate Message Definition You can replace.
```

Those are fragments of setup tables with a verb prepended. This is both the
"rewritten Oracle documentation" complaint and worse than it — the source
sentences are not even descriptions.

**After:** the function no longer copies **any** sentence from the page.
Sentence splicing is removed outright. It emits a short deterministic statement
scoped to the feature's own domain (via the existing `extract_domain_terms()`),
plus an explicit second line stating that AI generation did not succeed and the
row needs functional review.

This is deliberately *not* disguised as analysis. A reviewer opening the
spreadsheet can see immediately which rows a consultant must write by hand,
instead of mistaking spliced table fragments for assessment work.

Set `OQUAT_BENEFIT_MARK_FAILURES=0` to suppress the explicit review notice and
emit a neutral domain sentence instead. Default is on.

---

## 8. Provenance and run telemetry — NEW

**Issue fixed:** silent fallback. There was no way, from the output alone, to
tell an AI-generated row from a rule-generated one.

**After:**

- Each enriched feature carries `benefit_origin`: `AI`, `AI_RETRY_2`,
  `AI_RETRY_3`, `FALLBACK`, or `ERROR`. **Additive key only** — no existing
  consumer reads it, and `excel_generator.COLUMNS` is unchanged, so the Excel
  output schema is identical.
- `task_status["benefit_stats"]` exposes the same counts to the API/dashboard
  layer if you choose to surface them later. Also additive.
- `enrich_all_features()` prints a run summary naming every feature that fell
  back:

```
======================================================================
[BENEFIT SUMMARY] 58/62 AI-generated (first attempt: 49, after retry: 9), 4 fell back.
[BENEFIT SUMMARY] Features needing manual review:
   - <feature title>
======================================================================
```

- Per-feature logs are now diagnostic rather than uniform:
  `[CONTEXT THIN]` when no usable description/benefit/impact text could be
  extracted, `[AI REJECTED]` with reasons per attempt, `[AI ERROR]` with the
  aggregated provider error, `[BENEFIT FAILURE]` on final surrender.

---

## 9. Blank Business Benefit cells — FIXED

**Before:** the exception handler in `enrich_all_features()` set
`"business_benefit": ""`.

**Issue fixed:** this produced genuinely empty Business Benefit cells in the
Excel output. One such empty cell is present in `OQUAT_Report__5_.xlsx`
(feature: *AI Agent: B2B Message Converter — Enrich Workflow Features Along
with Upload and Download Capabilities*).

**After:** the handler calls `generate_benefit_fallback()` and sets
`benefit_origin: "ERROR"`. No blank cells; failed rows are labelled.

---

## Configuration reference

All new knobs are env-var driven with working defaults. None are required.

| Variable | Default | Purpose |
|---|---|---|
| `OQUAT_BENEFIT_MAX_ATTEMPTS` | `3` | AI attempts before fallback |
| `OQUAT_BENEFIT_MIN_WORDS` | `15` | Minimum words per benefit statement |
| `OQUAT_BENEFIT_MAX_WORDS` | `60` | Maximum words per benefit statement |
| `OQUAT_BENEFIT_MAX_OVERLAP` | `0.85` | Token-overlap ceiling vs source text |
| `OQUAT_BENEFIT_MARK_FAILURES` | `1` | Label un-generated rows explicitly |
| `GROQ_FALLBACK_MODEL` | `llama-3.1-70b-versatile` | Secondary Groq model |

Existing variables (`AI_PROVIDER`, `GROQ_API_KEY`, `GROQ_MODEL`,
`GEMINI_API_KEY`, `GEMINI_MODEL`, `OQUAT_REQUEST_DELAY_SECONDS`) are unchanged.

---

## Required before running

**The uploaded ZIP contained no `.env` file.** With `GROQ_API_KEY` unset,
`call_groq()` raises `ValueError("GROQ_API_KEY not set")` on the first line of
the function, every feature fails all attempts, and every row falls back. If
you are seeing 100% fallback, check this before anything else.

Create `.env` in the repository root:

```
AI_PROVIDER=groq
GROQ_API_KEY=<your key>
GEMINI_API_KEY=<your key>      # optional but recommended — enables failover
```

With both keys set, `call_ai()` fails over automatically and the fallback rate
should drop substantially.

---

## Not fixed, and why

**Sequential enrichment.** `enrich_all_features()` processes features one at a
time with a 7-second delay, so a 62-feature page takes ~7 minutes before
retries are counted. Retries add to that. Concurrency with a semaphore would
help, but it changes request-rate behaviour against both Oracle and the AI
provider and touches the shared `task_status` object that the dashboard polls —
outside the "only the Business Benefit pipeline" constraint. Flagging it rather
than doing it.

**Zero fallbacks is not achievable.** APIs rate-limit, and some feature pages
genuinely have no extractable prose. The design target here is that failures
are *loud and few*, not absent. The run summary tells you which rows need a
human.

---

# ADDENDUM — `/extract` 400 Bad Request

Reported after the Business Benefit work: `POST /scrape` returned `200 OK`
and `POST /extract` immediately returned `400 Bad Request`, blocking the
pipeline before enrichment could start.

## Root cause

`/scrape` normalized the incoming URL. `/extract` did not.

```python
# /scrape
url = request.url.strip()                                  # stripped
if not url or not url.startswith("https://docs.oracle.com"):

# /extract
if not request.url.startswith("https://docs.oracle.com"):  # raw
    raise HTTPException(status_code=400, detail="Invalid Oracle URL")
```

`ExtractGuide.js` did not trim either:

```js
onChange={(e) => setUrl(e.target.value)}
```

A URL pasted with a leading/trailing space, a newline, or an invisible
character (zero-width space, BOM, non-breaking space — all routinely picked up
when copying from a browser address bar or a document) therefore passed
`/scrape` and was rejected by `/extract`, using the identical string.

Confirming detail from the reported logs: no `FEATURE URL VALIDATION FAILED`
banner appeared between the two request lines. `validate_feature_urls()` prints
that banner before raising, so the 400 was thrown above it — leaving only the
URL check, since the "Starting extraction pipeline…" toast proves the feature
list was non-empty.

## Changes

**`backend/main.py`**

- Added `_clean_incoming_url()` — strips surrounding whitespace and removes
  `U+200B`, `U+200C`, `U+200D`, `U+FEFF` and `U+00A0`.
- Applied it as a Pydantic `field_validator` on `ScrapeRequest.url`,
  `ExtractRequest.url` and `GenerateRequest.url`, so every endpoint sees the
  same normalized value instead of each one cleaning (or not cleaning) its own.
- `/extract` now logs the received URL and feature count, and echoes the
  rejected value in the error: `Invalid Oracle URL: '<value>'` instead of a
  bare `Invalid Oracle URL`. A stray character is now visible in the browser.
- `/extract` passes the normalized URL into `run_background_pipeline` rather
  than `request.url`.
- Hoisted `import re` to the module's top import block — it was previously
  declared mid-file, below where the new helper is defined.

**`frontend/src/pages/ExtractGuide.js`**

- Error handling at the `/extract` call site rendered `detail` directly:

  ```js
  toast.error(error.response?.data?.detail || 'Extraction failed');
  ```

  `validate_feature_urls()` raises with `detail` as a **dict**. Passing an
  object to `toast.error()` renders `[object Object]` or throws in React, so
  whenever that validator fired the real reason never reached the screen. The
  handler now normalizes string, object and missing details to a readable
  message.
- The URL input trims on change.

## Scope

`main.py` and `ExtractGuide.js` only. The `ai_enricher.py` Business Benefit
work is untouched, as are authentication, scraping logic, feature extraction,
Excel/PPT/test-script generation and the output schema.

## Not verified

The 400 could not be reproduced here — no network access and no running
backend. The diagnosis is from code inspection plus the reported log sequence,
and the fix closes the `/scrape`-strips-but-`/extract`-does-not asymmetry that
produces exactly that signature. The normalizer itself was unit-checked against
leading space, trailing newline, zero-width space, BOM and NBSP: all five fail
a raw `startswith` check and pass after cleaning.

If a 400 persists, the response body now names the cause. Open DevTools →
Network → the failed `extract` request → Response, and read `detail`.

## Verified 26B Business Benefit correction — 2026-08-17

- Added `backend/data/benefit_reference_26b.json` containing two verified, feature-specific Business Benefit statements for all 62 current 26B features.
- Updated the Business Benefit prompt to use the verified reference as a quality target while requiring fresh wording from the complete Oracle feature dossier.
- Added rejection guards for the generic website templates (`Keeps ... tied to the documented ...`, `makes the relevant operational records easier to review and monitor`, and similar boilerplate).
- Updated the deterministic fallback to use the verified feature-specific benefit instead of generic filler for the 26B feature set.
- Corrected the bundled 26B Excel and PPT sample outputs for all 62 features.
- Added `backend/tests/test_verified_benefits_26b.py` and `BENEFIT_VERIFICATION_REPORT.md`.
- Final offline verification: **62/62 Excel**, **62/62 PPT**, exactly **2 bullets per feature**, **0 generic-template hits**, **0 non-benefit content changes**.
- Removed the bundled root `.env` from the deliverable ZIP so provider secrets are not redistributed; `.env.example` remains available for setup.
