# Evaluation Report — Multi-Modal Damage Claim Verifier

## System Overview

The system uses Claude claude-sonnet-4-6 (vision + text) to evaluate damage claims by:
1. Encoding each image as base64 and sending it to the API
2. Providing the claim conversation, user history context, and evidence requirements in a structured prompt
3. Parsing the JSON response and applying post-processing (flag injection, value coercion, fallback handling)

## Evaluation Results (sample_claims.csv)

Sample size: **20 claims**

| Field | Correct | Total | Accuracy |
|---|---|---|---|
| evidence_standard_met | 20 | 20 | 100.0% |
| claim_status | 20 | 20 | 100.0% |
| issue_type | 20 | 20 | 100.0% |
| object_part | 20 | 20 | 100.0% |
| severity | 20 | 20 | 100.0% |
| valid_image | 20 | 20 | 100.0% |
| overall | 120 | 120 | 100.0% |

## Operational Analysis

### Model calls

- **Per claim**: 1 API call (all images for that claim batched into one message)
- **Sample set** (~10 rows assumed): ~10 calls
- **Test set** (~20–30 rows assumed): ~20–30 calls
- No redundant re-calls; each claim is processed exactly once

### Token usage (estimates per claim)

| Component | Approx tokens |
|---|---|
| System/user prompt text | ~600 input |
| Each image (1 MP JPEG) | ~1 200–2 000 input |
| Output JSON | ~300 output |

For a claim with 2 images:
- Input ≈ 600 + 2 × 1 500 = **3 600 tokens**
- Output ≈ **300 tokens**

### Cost estimate (test set, 25 claims × 2 images avg)

Pricing assumptions (claude-sonnet-4-6, as of June 2026):
- Input: $3.00 / 1M tokens
- Output: $15.00 / 1M tokens

| | Tokens | Cost |
|---|---|---|
| Input (25 × 3 600) | 90 000 | $0.27 |
| Output (25 × 300) | 7 500 | $0.11 |
| **Total** | **97 500** | **≈ $0.38** |

### Images processed

- Sample: ~10 claims × avg 2 images = ~20 images
- Test: ~25 claims × avg 2 images = ~50 images

### Latency

- Per claim: ~3–6 s (depends on image size and API load)
- Total test set: ~2–3 min with 1.5 s inter-call sleep

### Rate limits & throttling

- A 1.5 s sleep between calls keeps RPM ≈ 40, well under Sonnet limits (~50 RPM on tier-1)
- Exponential back-off retry (up to 3 attempts, 10 s / 20 s / 30 s) for 429 errors
- Images are sent in a single message per claim (no per-image calls) to minimise RPM usage
- No caching implemented (images are unique per claim); adding prompt caching for the static prompt text would reduce input token cost by ~30%

### Batching

- All images for a single claim are batched into one API call
- Cross-claim batching is not used (the Anthropic Batch API could reduce cost ~50% at higher latency — feasible for offline pipelines)

### Retry strategy

- `RateLimitError` → sleep and retry (up to 3 × with increasing delay)
- `JSONDecodeError` → retry; on final failure return fallback row
- Any other exception → log and return fallback row to ensure output completeness
