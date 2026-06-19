# Multi-Modal Damage Claim Verifier
**HackerRank Orchestrate June '26**

## Quick Start

```bash
# 1. Clone the hackathon repo (if you haven't already)
git clone git@github.com:interviewstreet/hackerrank-orchestrate-june26.git
cd hackerrank-orchestrate-june26

# 2. Copy this solution's code/ folder into the repo
cp -r /path/to/this/code ./code

# 3. Install dependencies
pip install anthropic

# 4. Set your Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-..."

# 5. Run evaluation on labeled sample first
python code/evaluation/evaluate.py --dataset-dir dataset

# 6. Run on the full test set → produces output.csv
python code/main.py --dataset-dir dataset --output-csv output.csv
```

## Architecture

```
main.py
├── load_csv()               # reads all CSVs
├── encode_image()           # base64-encodes images
├── get_user_risk_context()  # builds risk text from user_history.csv
├── get_evidence_requirements() # selects relevant rules from evidence_requirements.csv
├── build_prompt()           # composes the full multimodal prompt
├── call_claude()            # calls Claude claude-sonnet-4-6 with retry/back-off
├── process_row()            # orchestrates one claim end-to-end
└── write_output()           # writes output.csv

evaluation/
├── evaluate.py              # runs sample set, computes accuracy, writes report
└── evaluation_report.md     # auto-generated operational analysis
```

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **One API call per claim** | Batches all images in a single message → minimises RPM, lowers latency |
| **JSON-only output prompt** | Structured output avoids parsing ambiguity |
| **Post-processing coercion** | Ensures all fields stay within allowed value lists |
| **User-history flag injection** | Adds `user_history_risk` / `manual_review_required` flags when rejection count or 90-day volume is high |
| **Fallback rows** | Any failure (network, JSON, missing images) returns a safe `not_enough_information` row rather than crashing |
| **1.5 s inter-call sleep** | Keeps RPM ≈ 40, well within Sonnet tier-1 limits |
| **Exponential back-off retry** | Handles transient 429 rate-limit errors gracefully |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Your Anthropic API key |

## Output Schema

See `problem_statement.md` for full schema. The system produces `output.csv` with these columns:

`user_id, image_paths, user_claim, claim_object, evidence_standard_met, evidence_standard_met_reason, risk_flags, issue_type, object_part, claim_status, claim_status_justification, supporting_image_ids, valid_image, severity`

## Cost Estimate

~$0.38 for a 25-claim test set with avg 2 images/claim using claude-sonnet-4-6.
See `evaluation/evaluation_report.md` for full breakdown.
