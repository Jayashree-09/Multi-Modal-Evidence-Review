"""
Evaluation pipeline for the damage claim verification system.
Runs the system on dataset/sample_claims.csv (which has labels),
then computes accuracy metrics for each output field.

Usage:
    python evaluation/evaluate.py [--dataset-dir dataset]
"""

import os
import sys
import csv
import json
import argparse
import logging
from pathlib import Path

# Add parent directory to path so we can import main
sys.path.insert(0, str(Path(__file__).parent.parent))
import main as verifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SCORED_FIELDS = [
    "evidence_standard_met",
    "claim_status",
    "issue_type",
    "object_part",
    "severity",
    "valid_image",
]


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def score_predictions(predictions: list[dict], labels: list[dict]) -> dict:
    """
    Compare predictions vs labels row-by-row for SCORED_FIELDS.
    Returns per-field accuracy and overall accuracy.
    """
    if len(predictions) != len(labels):
        log.warning(
            "Prediction count (%d) != label count (%d)", len(predictions), len(labels)
        )

    field_correct = {f: 0 for f in SCORED_FIELDS}
    field_total = {f: 0 for f in SCORED_FIELDS}

    for pred, label in zip(predictions, labels):
        for field in SCORED_FIELDS:
            pred_val = str(pred.get(field, "")).strip().lower()
            label_val = str(label.get(field, "")).strip().lower()
            if label_val:  # only score when label exists
                field_total[field] += 1
                if pred_val == label_val:
                    field_correct[field] += 1

    results = {}
    total_correct = 0
    total_scored = 0
    for field in SCORED_FIELDS:
        total = field_total[field]
        correct = field_correct[field]
        accuracy = correct / total if total > 0 else 0.0
        results[field] = {
            "correct": correct,
            "total": total,
            "accuracy": round(accuracy, 4),
        }
        total_correct += correct
        total_scored += total

    overall = total_correct / total_scored if total_scored > 0 else 0.0
    results["overall"] = {
        "correct": total_correct,
        "total": total_scored,
        "accuracy": round(overall, 4),
    }
    return results


def print_report(scores: dict):
    print("\n" + "=" * 50)
    print("EVALUATION RESULTS")
    print("=" * 50)
    for field, data in scores.items():
        print(
            f"  {field:<30} {data['correct']:>3}/{data['total']:<3}  "
            f"accuracy={data['accuracy']:.1%}"
        )
    print("=" * 50 + "\n")


def run_evaluation(dataset_dir: str = "dataset"):
    sample_csv = os.path.join(dataset_dir, "sample_claims.csv")
    eval_output_csv = os.path.join(dataset_dir, "eval_predictions.csv")
    report_path = os.path.join(os.path.dirname(__file__), "evaluation_report.md")

    if not os.path.exists(sample_csv):
        sys.exit(f"sample_claims.csv not found at {sample_csv}")

    log.info("Running verifier on sample_claims.csv…")
    predictions = verifier.run(
        dataset_dir=dataset_dir,
        input_csv=sample_csv,
        output_csv=eval_output_csv,
    )

    labels = load_csv(sample_csv)
    scores = score_predictions(predictions, labels)
    print_report(scores)

    # Save JSON scores
    scores_path = os.path.join(os.path.dirname(__file__), "scores.json")
    with open(scores_path, "w") as f:
        json.dump(scores, f, indent=2)
    log.info("Scores saved to %s", scores_path)

    # Write markdown report
    write_report(report_path, scores, len(labels))
    log.info("Report saved to %s", report_path)


def write_report(path: str, scores: dict, n_samples: int):
    lines = [
        "# Evaluation Report — Multi-Modal Damage Claim Verifier",
        "",
        "## System Overview",
        "",
        "The system uses Claude claude-sonnet-4-6 (vision + text) to evaluate damage claims by:",
        "1. Encoding each image as base64 and sending it to the API",
        "2. Providing the claim conversation, user history context, and evidence requirements in a structured prompt",
        "3. Parsing the JSON response and applying post-processing (flag injection, value coercion, fallback handling)",
        "",
        "## Evaluation Results (sample_claims.csv)",
        "",
        f"Sample size: **{n_samples} claims**",
        "",
        "| Field | Correct | Total | Accuracy |",
        "|---|---|---|---|",
    ]
    for field, data in scores.items():
        lines.append(
            f"| {field} | {data['correct']} | {data['total']} | {data['accuracy']:.1%} |"
        )

    lines += [
        "",
        "## Operational Analysis",
        "",
        "### Model calls",
        "",
        "- **Per claim**: 1 API call (all images for that claim batched into one message)",
        "- **Sample set** (~10 rows assumed): ~10 calls",
        "- **Test set** (~20–30 rows assumed): ~20–30 calls",
        "- No redundant re-calls; each claim is processed exactly once",
        "",
        "### Token usage (estimates per claim)",
        "",
        "| Component | Approx tokens |",
        "|---|---|",
        "| System/user prompt text | ~600 input |",
        "| Each image (1 MP JPEG) | ~1 200–2 000 input |",
        "| Output JSON | ~300 output |",
        "",
        "For a claim with 2 images:",
        "- Input ≈ 600 + 2 × 1 500 = **3 600 tokens**",
        "- Output ≈ **300 tokens**",
        "",
        "### Cost estimate (test set, 25 claims × 2 images avg)",
        "",
        "Pricing assumptions (claude-sonnet-4-6, as of June 2026):",
        "- Input: $3.00 / 1M tokens",
        "- Output: $15.00 / 1M tokens",
        "",
        "| | Tokens | Cost |",
        "|---|---|---|",
        "| Input (25 × 3 600) | 90 000 | $0.27 |",
        "| Output (25 × 300) | 7 500 | $0.11 |",
        "| **Total** | **97 500** | **≈ $0.38** |",
        "",
        "### Images processed",
        "",
        "- Sample: ~10 claims × avg 2 images = ~20 images",
        "- Test: ~25 claims × avg 2 images = ~50 images",
        "",
        "### Latency",
        "",
        "- Per claim: ~3–6 s (depends on image size and API load)",
        "- Total test set: ~2–3 min with 1.5 s inter-call sleep",
        "",
        "### Rate limits & throttling",
        "",
        "- A 1.5 s sleep between calls keeps RPM ≈ 40, well under Sonnet limits (~50 RPM on tier-1)",
        "- Exponential back-off retry (up to 3 attempts, 10 s / 20 s / 30 s) for 429 errors",
        "- Images are sent in a single message per claim (no per-image calls) to minimise RPM usage",
        "- No caching implemented (images are unique per claim); adding prompt caching for the static prompt text would reduce input token cost by ~30%",
        "",
        "### Batching",
        "",
        "- All images for a single claim are batched into one API call",
        "- Cross-claim batching is not used (the Anthropic Batch API could reduce cost ~50% at higher latency — feasible for offline pipelines)",
        "",
        "### Retry strategy",
        "",
        "- `RateLimitError` → sleep and retry (up to 3 × with increasing delay)",
        "- `JSONDecodeError` → retry; on final failure return fallback row",
        "- Any other exception → log and return fallback row to ensure output completeness",
    ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", default="dataset")
    args = parser.parse_args()
    run_evaluation(args.dataset_dir)
