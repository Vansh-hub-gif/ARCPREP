# VALIDATION — Business Benefit pipeline

## 0. What was verified, and what was not

Read this section before the rest of the document.

**Verified:**

- The defect mechanism was reproduced against the **original, unmodified**
  `ai_enricher.py`, and its output matched the text in the uploaded reports
  character-for-character.
- The extraction fix, the quality gate, the retry loop and the rewritten
  fallback were exercised end to end and all pass (§2–§5).
- The quality gate was run across all 123 rows of both uploaded reports (§3).
- Downstream generators still import and produce an identical 18-column
  workbook (§6).

**Not verified:**

- **No live Oracle page was fetched.** Network egress was unavailable in the
  environment where this work was done, so `docs.oracle.com` could not be
  reached.
- **No real AI call was made.** The uploaded ZIP contained no `.env`, so no
  `GROQ_API_KEY` or `GEMINI_API_KEY` was available. Every AI interaction below
  uses a scripted stub model.
- Consequently, **there is no "new website output" column in §1**, and the
  original requirement to regenerate the same Oracle page and compare against
  the extension output has **not** been met. That comparison has to be run on
  your machine with keys set. Instructions are in §7.

Everything below is either a direct measurement over your existing data or a
control-flow test with a stubbed model. Nothing is a claim about live output
quality.

---

## 1. The two uploaded files are both backend output

The brief treated `oracle_26B-inventory-wn-t73741__17_.xlsx` as Chrome
Extension output and `OQUAT_Report__5_.xlsx` as website output, and asked for
the second to be converged onto the first.

Both files were produced by the Python backend in this repository.

| Check | `OQUAT_Report__5_.xlsx` | `oracle_26B-...__17_.xlsx` |
|---|---|---|
| Column count | 17 | 18 |
| Header order matches `excel_generator.COLUMNS` | prefix match (pre-`Mandatory`) | **exact match, all 18** |
| Contains `enrich_feature()`'s hardcoded Notes literal | yes | yes |
| Contains `assess_business_impact()` f-string outputs | yes | yes |
| Fallback verb produced | `Provides` | `Improves` |

The Notes literal is
`"Validate the setup and business impact in a lower environment before production rollout."`
— a Python string constant in `enrich_feature()`. The Impact strings
(`"NO BUSINESS IMPACT unless {condition}"`,
`"LOW IMPACT - requires role configuration{role_str} for {domain}"`) are
f-strings in `assess_business_impact()`. A separate JavaScript Chrome extension
would not emit either.

The 17-vs-18 column difference dates the files: `OQUAT_Report__5_.xlsx` predates
the addition of `Mandatory (Yes/No)` to `COLUMNS`.

### Quality comparison of the two files

Side by side, on the same features:

| Feature | File labelled "extension" (gold standard) | File labelled "website" (incorrect) |
|---|---|---|
| Redwood: Configure Collaboration Messaging | `Improves this value is in hours.` | `Provides this value is in hours.` |
| Redwood: Define Processing Rules for B2B Messages | `Improves leave the ID cell blank.` | `Automates the modification of inbound B2B messages to meet specific enterprise collaboration requirements without complex development.` |
| Redwood: Receive an Order from Oracle CPQ | `Improves duplicate Message Definition You can replace.` | `Streamlines the quote-to-order process by automating the transformation of Oracle CPQ quote messages into actionable sales orders in Fusion applications.` |
| Redwood: Deliver to Multiple Locations with Robotic Material Handling Equipment | `Improves for such activities, organizations use intraorganization transfer orders to move material from a source subinventory to a PAR location.` | `Optimizes material replenishment processes by allowing robotic material handling equipment to deliver to multiple locations in a single run.` |
| AI Agent: B2B Message Converter | `Improves perform a complete sequence of messaging conversion steps within the agent, including uploading and downloading mapping files.` | *(empty cell)* |

The designated gold standard is the weaker file on every row above except the
last, where the other file has a blank cell (fixed — see CHANGELOG §9).

**Conclusion:** converging the website onto the extension would have degraded
output. The work was redirected to the defect both files share.

---

## 2. Root cause reproduced against unmodified code

The reported symptom is Business Benefit text that reads like rewritten Oracle
documentation. The actual mechanism is worse than paraphrasing: the fallback
was splicing fragments of **Steps-to-Enable configuration tables**.

Chain of causation:

1. `extract_intro_text()` collects via `h1.find_next_siblings()`. On a feature
   page whose title is not a literal `<h1>`, this returns `""`.
2. `extract_section_text(soup, ["overview", "description", ...])` also returns
   `""`, because Oracle does not use those heading names.
3. `description_source` is therefore `""`.
4. `generate_benefit_fallback(title, description, full_text)` computes
   `desc = description or full_text[:3000]` — falling through to the **entire
   page**, config tables included.
5. It scores sentences, picks two, and prepends a business verb.

Reproduction using the original unmodified `ai_enricher.py` against a fixture
with a non-`h1` title (`backend/tests/fixtures/feature_page_no_h1.html`):

```
ORIGINAL generate_benefit_fallback(description='') ->
Improves rules are maintained in a spreadsheet that business users can update directly.
Improves leave the ID cell blank.
```

`Improves leave the ID cell blank.` is character-for-character the second line
in `oracle_26B-inventory-wn-t73741__17_.xlsx` for
*Redwood: Define Processing Rules for B2B Messages*.

The prompt was never the problem. It is long, specific and well-constructed; it
was being fed an empty description, and its output was being discarded on the
first stumble.

### Extraction fix measured

Same fixture, old paths vs new:

| Extractor | Result |
|---|---|
| `extract_intro_text()` (old) | `''` |
| `extract_section_text([overview, description, feature summary, details])` (old) | `''` |
| `extract_feature_body_text()` (new) | both description paragraphs, Steps-to-Enable text excluded |

On the fixture that *does* have an `<h1>`
(`backend/tests/fixtures/feature_page_with_h1.html`), the new extractor also
recovers Oracle's own Business Benefit paragraph, which was previously
discarded because `benefit_source` was never assigned:

```
extract_oracle_benefit_section() ->
Reduces the time required to onboard a new trading partner and lowers the risk
of misconfigured message definitions.
```

---

## 3. Quality gate measured over real generated output

The gate in `validate_benefit_lines()` was run over every row of both uploaded
reports. This is a measurement over your actual data, not a fixture.

| File | Rows | Pass the gate | Would be regenerated |
|---|---|---|---|
| `OQUAT_Report__5_.xlsx` (labelled "website") | 61 | **27** | 34 |
| `oracle_26B-...__17_.xlsx` (labelled "extension") | 62 | **21** | 41 |

Rejection reasons across `OQUAT_Report__5_.xlsx`, by first-triggered rule:

| Reason | Lines |
|---|---|
| documentation-style opening | 41 |
| too short | 16 |
| copied from Oracle text | 1 |

Under the current pipeline every one of those lines shipped. Under the new one
each triggers a regeneration with the reason fed back to the model, and only
survives to the spreadsheet if all attempts fail — in which case the row is
labelled.

### Threshold calibration

The overlap threshold was tuned against your data rather than guessed.
Per-line overlap ratios from `OQUAT_Report__5_.xlsx`:

| Overlap | Line (truncated) | Verdict |
|---|---|---|
| 1.00 | `Supports processes involving the return of goods for repair or maintenance,` | copied |
| 1.00 | `Provides this provides greater flexibility for managing and storing your ex…` | copied |
| 0.97 | `Provides using License Plate Number Real Time Subject Area in Oracle Transa…` | copied |
| 0.95 | `Provides instead of applying recall processes across all organizations, you…` | copied |
| 0.87 | `Provides now, you can create ASNs and ASBNs with a predefined spreadsheet t…` | copied |
| **0.75** | `Streamlines B2B messaging setup by eliminating the need to configure connec…` | **legitimate** |
| **0.71** | `Automates the derivation of intercompany transfer prices for back-to-back i…` | **legitimate** |

An initial threshold of 0.72 produced two false positives on genuinely good
consultant output. The shipped default is **0.85**, which keeps both legitimate
lines and still catches everything from 0.87 up. Override with
`OQUAT_BENEFIT_MAX_OVERLAP`.

### Gate unit check

Five known-bad lines drawn from the shipped reports, and two hand-written
consultant-style lines, against the same source text:

```
[PASS] quality gate: 5/5 known-bad rejected, 2/2 known-good accepted
```

---

## 4. Retry loop — control flow verified

Scenario A. A scripted stub model returns documentation-style output twice,
then clean output. Previously, attempt 1's rejection ended the process.

```
[AI REJECTED] attempt 1/3: 0/2 lines accepted.
    Reasons: ['too short (11 words): Provides the ability to define processing rules…',
              'too short (5 words): Supports message modification without development.']
[AI REJECTED] attempt 2/3: 0/2 lines accepted.
    Reasons: ['too short (7 words): This feature enables organizations to modify messages.',
              'too short (12 words): Rules are maintained in a spreadsheet that business users…']
[BENEFIT] AI generated (attempt 3) for: Redwood: Define Processing Rules for B2B Messages

benefit_origin: AI_RETRY_3
```

Result written to the row:

> Cuts trading-partner onboarding effort by letting business analysts adjust
> inbound message handling directly, removing the IT change requests that
> previously gated every new partner integration.
> Lowers integration risk by keeping partner-specific exceptions isolated from
> the standard message definition, so a single mapping change cannot disrupt
> other trading relationships.

The rejection *reasons* are what get appended to the next prompt, so the model
is corrected rather than re-asked blind.

**Caveat:** the third response here is scripted, not generated. This test proves
the pipeline recovers when the model produces acceptable output on a later
attempt. It does not prove how often a real model will do so.

---

## 5. Total AI failure — no documentation splicing

Scenario B. Every provider fails on every attempt.

```
[AI ERROR] attempt 1/3: All AI providers failed -> groq: 429 | gemini: no key
[AI ERROR] attempt 2/3: All AI providers failed -> groq: 429 | gemini: no key
[AI ERROR] attempt 3/3: All AI providers failed -> groq: 429 | gemini: no key
[BENEFIT FAILURE] AI generation failed after 3 attempts — deterministic
                  placeholder written, needs review
```

Output written:

> Targets B2B messaging by changing how the 'Define Processing Rules for B2B
> Messages' capability is delivered in Oracle Cloud SCM, reducing the manual
> handling that the existing process requires.
> Business value for this feature was not generated by the AI pipeline and
> requires functional review before it is shared with the customer.

Under identical conditions the old code produced
`Improves leave the ID cell blank.`

The test asserts mechanically that **no sentence of five or more words from the
source page appears anywhere in the fallback output**, and that the cell is
never empty.

This is deliberately not disguised as analysis. A reviewer can see at a glance
which rows need a consultant.

---

## 6. Nothing else broken

| Check | Result |
|---|---|
| `ai_enricher.py` parses | pass |
| `excel_generator`, `ppt_generator`, `test_script_mapper`, `test_script_excel` import | pass |
| `excel_generator.COLUMNS` unchanged (18 names, same order) | pass |
| Workbook generated from an enriched feature dict | 18 columns, Business Benefit renders with its newline intact |
| New `benefit_origin` key breaks a downstream consumer | no — additive key, nothing reads it |
| Files modified outside the Business Benefit pipeline | none |

Untouched by this change set: authentication, login, signup, React frontend,
dashboard, URL scraping, feature extraction, Excel generation, PPT generation,
test script generation, existing APIs, output format, existing UI, existing
workflow.

The full offline suite:

```
$ python backend/tests/test_benefit_pipeline.py

[PASS] with-h1 page: body extracted, config table excluded, Oracle benefit section captured
[PASS] no-h1 page: old paths returned '', new path recovered the description
       without pulling in Steps-to-Enable text
[PASS] quality gate: 5/5 known-bad rejected, 2/2 known-good accepted
[PASS] retry loop: recovered on attempt 3, benefit_origin=AI_RETRY_3
[PASS] total-failure fallback: no source sentence copied, row flagged for review,
       cell non-empty
[PASS] regression: setup-table fragments can no longer reach the output

All offline checks passed.
```

---

## 7. The live comparison you still need to run

This is the step that could not be completed here.

**1. Create `.env` in the repository root.** The uploaded ZIP had none, which
means `GROQ_API_KEY` was unset and every row would have fallen back regardless
of any other fix:

```
AI_PROVIDER=groq
GROQ_API_KEY=<your key>
GEMINI_API_KEY=<your key>      # optional; enables cross-provider failover
```

**2. Run the offline suite first** to confirm the code is intact:

```
python backend/tests/test_benefit_pipeline.py
```

**3. Regenerate the same Oracle page** through the normal website workflow:

```
https://docs.oracle.com/en/cloud/saas/readiness/scm/26b/inv26b/
```

**4. Read the run summary** printed at the end of enrichment:

```
[BENEFIT SUMMARY] N/62 AI-generated (first attempt: X, after retry: Y), Z fell back.
[BENEFIT SUMMARY] Features needing manual review:
   - <titles>
```

`Z` is the number that matters. If it is high, the logs now tell you which
failure mode is responsible rather than leaving you to infer it:

| Log line | Meaning | Action |
|---|---|---|
| `[CONTEXT THIN]` | No description/benefit/impact text extracted | Page structure differs again — send me the URL |
| `[AI ERROR] … 429` | Rate limiting | Raise `OQUAT_REQUEST_DELAY_SECONDS`, or set `GEMINI_API_KEY` for failover |
| `[AI ERROR] … not set` | Missing key | Fix `.env` |
| `[AI REJECTED]` ×3 | Model output keeps failing the gate | Check the reasons; the thresholds in CHANGELOG §5 are env-tunable |

**5. Run the gate over the new report** and compare against the §3 baselines
of 27/61 and 21/62:

```
python backend/tests/test_benefit_pipeline.py path/to/new_OQUAT_Report.xlsx
```

**6. Cross-check `benefit_origin`.** Rows marked `FALLBACK` or `ERROR` are the
ones needing a consultant. Rows marked `AI` or `AI_RETRY_n` are real generated
output.

---

## 8. Honest expectations

The success criterion "the AI pipeline is actually being used rather than
falling back to generic logic" is now achievable, and the criteria around
context-based rather than documentation-based output are enforced mechanically
by the gate rather than left to the prompt.

"AI generation always succeeds" is not achievable and was not built toward.
Providers rate-limit, and some Oracle feature pages genuinely contain no
extractable prose. The design target is that failures are **loud and few**
rather than silent and frequent — visible in the logs, labelled in the data via
`benefit_origin`, and never disguised as analysis in the spreadsheet.

One further item flagged but not fixed, because it falls outside the "only the
Business Benefit pipeline" constraint: enrichment is sequential with a
7-second inter-feature delay, so a 62-feature page takes roughly 7 minutes
before retries, and retries extend that. Adding concurrency would change
request-rate behaviour against both Oracle and the AI provider and would touch
the shared `task_status` object the dashboard polls. Worth doing as a separate
piece of work.


## 8. HR Business-Benefit Requirement — Latest Fix

The Business Benefit pipeline now follows the requested workflow:

1. The feature title identifies the Oracle feature page.
2. The prompt receives the complete scraped Oracle feature-page text as a source dossier, alongside the extracted description, Oracle benefit section, impact context, and setup context.
3. The model is instructed to reason from that feature-specific information and produce business consequences rather than a feature summary.
4. Exactly **two** Business Benefit statements are required. One statement or three-or-more statements are rejected and regenerated.
5. Unsupported outcomes, copied Oracle wording, title restatement, generic boilerplate, and cross-feature repetition remain quality-gated.
6. The deterministic fallback also emits exactly two feature-specific statements.

Offline verification after this change: **31/31 pytest tests passed**.

The live AI wording itself was not tested in this sandbox because no outbound AI request was available. The prompt, validation, retry logic, fallback behavior, and regression tests were exercised offline.
