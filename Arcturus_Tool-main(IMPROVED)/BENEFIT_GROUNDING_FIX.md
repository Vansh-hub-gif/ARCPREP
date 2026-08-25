# BUSINESS BENEFIT — SOURCE GROUNDING FIX

Scope: Business Benefit generation only. Feature Description logic is
**byte-identical** (verified function by function — see Regression below).

## Root cause of the drift

The prompt handed the model a **menu of fifteen desirable outcomes** and asked
it to pick the relevant ones:

```
The Business Benefit must explain:
  • Business value          • Productivity gains
  • Lower operational costs • Faster execution
  • Reduced business risk   • Higher inventory accuracy
  ... (15 in total)
```

That is an invitation to bolt on outcomes Oracle never documented. It is
exactly how a feature whose stated outcome was *fewer trips across the
warehouse floor* acquired "reducing labor costs and increasing throughput".

The validator had no way to catch it either: it checked length, generic
phrasing and *maximum* copy-overlap, but nothing tested whether a claimed
outcome was supported by the source.

## What changed

**1. The menu is replaced by a per-feature allow-list.**
The AI prompt also receives the complete scraped Oracle feature-page text as a source dossier, so benefit reasoning is based on the full feature information rather than only a short description.
`supported_outcomes()` reads the feature's own Oracle text and returns only the
outcomes the content actually evidences. That list is injected into the prompt:

| Feature | Allowed outcomes |
|---|---|
| Redwood: Deliver to Multiple Locations ... Single Cart | fewer trips and less material movement |
| Create LPN Reports ... in OTBI | faster reporting and analysis |
| AI Agent: Inventory Task Allocation Assistant | more balanced workloads across the team; less manual effort and intervention |

An outcome requires **two distinct pieces of evidence**, matched on word
boundaries. Both rules were necessary: with single-hit substring matching, the
token `rest` matched inside `restock` and qualified the delivery-cart feature
for "reliable data exchange with partners".

**2. The prompt now bans the invented-claim vocabulary explicitly** (labour
cost, revenue, throughput, error reduction, customer satisfaction, time
savings, compliance, ROI) unless the content supports it, and states the rule
plainly: *understating a benefit is acceptable, overstating one is not.*

**3. Validation enforces it.** `unsupported_claims()` checks each generated
line against the feature's evidence and rejects unsupported claims; the reason
is fed back to the model and it regenerates (the existing retry loop). Title
restatement is also rejected.

**4. Temperature lowered 0.7 -> 0.25** — factual accuracy over creative wording.

**5. The deterministic fallback is grounded too.** It previously picked from a
fixed keyword map that could name an outcome the source never claimed; it now
prefers `supported_outcomes()`.

## Verified against the reported case

```
Reported output:  "Optimizes warehouse logistics ... reducing labor costs and
                   increasing throughput."
  unsupported  -> ['labor cost', 'throughput']
  validation   -> REJECTED, regeneration triggered

Gold-standard:    "Supports fewer trips and less material movement on the
                   warehouse floor ..."
  unsupported  -> []
  validation   -> ACCEPTED
```

## One thing I tried and removed

A vocabulary-overlap **floor** looked like an obvious genericness test.
Measured against known-good benefits it scored **0.05-0.10** — good benefits
reword deliberately, so overlap does not separate specific from generic, and
every usable threshold rejected valid output. It is removed rather than tuned;
a note in the source records the measurement so it is not re-attempted.
Genericness is caught by the existing phrase list and title-restatement;
unsupported claims are caught by evidence, which is a precise test rather than
a proxy.

## Regression

```
rows excel: 62 | ppt feature rows: 62
blank Business Benefit: 0 | blank Description: 0
NON-DESCRIPTION COLUMNS CHANGED: 0
```

- Feature Description functions: **9 checked, 0 changed.**
- New functions are all benefit-grounding helpers; the only modified existing
  functions are `validate_benefit_lines` and `generate_benefit_fallback`.
- `main.py`, `ppt_generator.py`, `excel_generator.py`, `extractor.py`,
  `test_feature_description.py` — byte-identical to the previous delivery.
- Empty-benefit guards, fallback chain and PPT/Excel safety nets remain in place.
- Business Benefit generation now requires **exactly two** accepted statements; one or three statements trigger regeneration.
- Test suites: description 14/14, benefit pipeline 6/6, grounding 7/7 (new).
- API key, provider and model configuration unchanged.

## Please confirm on one live run

The sandbox has no outbound network, so the AI call itself could not be
exercised end to end — validation, grounding and fallback are verified against
real Oracle content offline. On your first live run, watch for:

- `[AI REJECTED] ... claims not supported by the Oracle content (...)` — the new
  gate working; a few per run is expected and healthy.
- If `[BENEFIT SUMMARY]` shows a fallback count materially higher than before,
  the gate may be too strict for some feature types. Send me the rejection
  reasons and I will widen the evidence table rather than loosen the rule.
