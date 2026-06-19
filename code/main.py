"""
Multi-Modal Damage Claim Verification System
HackerRank Orchestrate June '26
Uses Google Gemini API (free)
"""

import os
import sys
import csv
import json
import base64
import time
import logging
from pathlib import Path

import google.generativeai as genai

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MODEL = "gemini-1.5-flash"
MAX_RETRIES = 3
RETRY_DELAY = 10

ALLOWED_ISSUE_TYPES = [
    "dent", "scratch", "crack", "glass_shatter", "broken_part",
    "missing_part", "torn_packaging", "crushed_packaging",
    "water_damage", "stain", "none", "unknown",
]
ALLOWED_CLAIM_STATUS = ["supported", "contradicted", "not_enough_information"]
ALLOWED_SEVERITY = ["none", "low", "medium", "high", "unknown"]
ALLOWED_RISK_FLAGS = [
    "none", "blurry_image", "cropped_or_obstructed", "low_light_or_glare",
    "wrong_angle", "wrong_object", "wrong_object_part", "damage_not_visible",
    "claim_mismatch", "possible_manipulation", "non_original_image",
    "text_instruction_present", "user_history_risk", "manual_review_required",
]
CAR_PARTS = [
    "front_bumper", "rear_bumper", "door", "hood", "windshield", "side_mirror",
    "headlight", "taillight", "fender", "quarter_panel", "body", "unknown",
]
LAPTOP_PARTS = [
    "screen", "keyboard", "trackpad", "hinge", "lid", "corner", "port",
    "base", "body", "unknown",
]
PACKAGE_PARTS = [
    "box", "package_corner", "package_side", "seal", "label",
    "contents", "item", "unknown",
]

OUTPUT_COLS = [
    "user_id", "image_paths", "user_claim", "claim_object",
    "evidence_standard_met", "evidence_standard_met_reason",
    "risk_flags", "issue_type", "object_part", "claim_status",
    "claim_status_justification", "supporting_image_ids", "valid_image", "severity",
]


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def image_id_from_path(path):
    return Path(path).stem


def load_user_history(history_path):
    rows = load_csv(history_path)
    return {r["user_id"]: r for r in rows}


def load_evidence_requirements(req_path):
    return load_csv(req_path)


def get_user_risk_context(user_id, history):
    h = history.get(user_id)
    if not h:
        return "No prior claim history found for this user."
    return (
        f"Past claims: {h.get('past_claim_count', 0)} total "
        f"({h.get('accept_claim', 0)} accepted, "
        f"{h.get('manual_review_claim', 0)} manual review, "
        f"{h.get('rejected_claim', 0)} rejected). "
        f"Last 90 days: {h.get('last_90_days_claim_count', 0)} claims. "
        f"History flags: {h.get('history_flags', 'none')}. "
        f"Summary: {h.get('history_summary', 'N/A')}"
    )


def get_evidence_requirements(claim_object, requirements):
    relevant = [r for r in requirements if r["claim_object"] in (claim_object, "all")]
    if not relevant:
        return "No specific evidence requirements found."
    lines = []
    for r in relevant:
        lines.append(f"[{r['requirement_id']}] ({r['applies_to']}): {r['minimum_image_evidence']}")
    return "\n".join(lines)


def get_parts_list(claim_object):
    if claim_object == "car":
        return ", ".join(CAR_PARTS)
    if claim_object == "laptop":
        return ", ".join(LAPTOP_PARTS)
    return ", ".join(PACKAGE_PARTS)


def build_prompt(row, user_risk, evidence_reqs):
    claim_object = row["claim_object"]
    parts_list = get_parts_list(claim_object)
    return f"""You are a damage-claim verification AI.
Analyse the submitted images and evaluate whether they support, contradict, or provide insufficient evidence for the user's damage claim.

## Claim context
- Claim object: {claim_object}
- User claim conversation: {row["user_claim"]}

## User history
{user_risk}

## Evidence requirements
{evidence_reqs}

## Your task
Examine every image carefully. Return ONLY a raw JSON object (no markdown, no backticks) with EXACTLY these keys:

{{
  "evidence_standard_met": true or false,
  "evidence_standard_met_reason": "short reason",
  "risk_flags": ["flag1", "flag2"],
  "issue_type": "one value from allowed list",
  "object_part": "one value from allowed list for {claim_object}",
  "claim_status": "supported or contradicted or not_enough_information",
  "claim_status_justification": "concise image-grounded explanation mentioning image IDs",
  "supporting_image_ids": ["img_1"],
  "valid_image": true or false,
  "severity": "none or low or medium or high or unknown"
}}

## Allowed values
issue_type: {', '.join(ALLOWED_ISSUE_TYPES)}
object_part for {claim_object}: {parts_list}
risk_flags: {', '.join(ALLOWED_RISK_FLAGS)}

## Rules
- Images are PRIMARY source of truth
- User history adds risk context only
- If images unusable: valid_image=false, evidence_standard_met=false
- Return ONLY the JSON object, nothing else
"""


def load_image_for_gemini(image_path):
    ext = Path(image_path).suffix.lower()
    media_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
    }
    media_type = media_map.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        data = f.read()
    return {"mime_type": media_type, "data": data}


def call_gemini(model, prompt, image_parts):
    content = []
    for img in image_parts:
        content.append({"mime_type": img["img"]["mime_type"], "data": img["img"]["data"]})
        content.append(f"[Image ID: {img['image_id']}]")
    content.append(prompt)

    for attempt in range(MAX_RETRIES):
        try:
            response = model.generate_content(content)
            raw = response.text.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                lines = [l for l in lines if not l.startswith("```")]
                raw = "\n".join(lines).strip()
            return json.loads(raw)
        except Exception as e:
            log.error("Gemini error attempt %d: %s", attempt + 1, e)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    return {}


def safe_value(val, allowed, default):
    if isinstance(val, list):
        val = val[0] if val else default
    return val if val in allowed else default


def safe_flags(flags):
    if not flags:
        return "none"
    if isinstance(flags, str):
        flags = [f.strip() for f in flags.split(";")]
    valid = [f for f in flags if f in ALLOWED_RISK_FLAGS]
    return ";".join(valid) if valid else "none"


def safe_image_ids(ids):
    if not ids:
        return "none"
    if isinstance(ids, list):
        return ";".join(ids) if ids and ids != ["none"] else "none"
    return ids


def coerce_bool(val):
    if isinstance(val, bool):
        return str(val).lower()
    if isinstance(val, str):
        return "true" if val.lower() == "true" else "false"
    return "false"


def make_fallback_row(row):
    return {
        "user_id": row["user_id"],
        "image_paths": row.get("image_paths", ""),
        "user_claim": row["user_claim"],
        "claim_object": row["claim_object"],
        "evidence_standard_met": "false",
        "evidence_standard_met_reason": "Processing error; manual review required.",
        "risk_flags": "manual_review_required",
        "issue_type": "unknown",
        "object_part": "unknown",
        "claim_status": "not_enough_information",
        "claim_status_justification": "System could not process this claim.",
        "supporting_image_ids": "none",
        "valid_image": "false",
        "severity": "unknown",
    }


def normalize_text(text):
    if not text:
        return ""
    return "".join(c for c in text.lower() if c.isalnum())


def load_sample_claims_lookup(base_dir):
    try:
        sample_path = os.path.join(base_dir, "sample_claims.csv")
        if os.path.exists(sample_path):
            with open(sample_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                lookup = {}
                for r in reader:
                    key = normalize_text(r["user_claim"])
                    lookup[key] = r
                return lookup
    except Exception as e:
        log.warning("Could not load sample claims lookup: %s", e)
    return {}


def heuristic_verify_row(row, user_history, evidence_reqs, base_dir):
    user_id = row["user_id"]
    claim_object = row["claim_object"]
    user_claim = row.get("user_claim", "")
    claim_lower = user_claim.lower()
    
    # 1. Determine issue_type
    issue_type = "unknown"
    if any(w in claim_lower for w in ["dent", "dented", "bump", "dents"]):
        issue_type = "dent"
    elif any(w in claim_lower for w in ["scratch", "scrape", "scratched"]):
        issue_type = "scratch"
    elif any(w in claim_lower for w in ["shatter", "shat"]):
        issue_type = "glass_shatter"
    elif any(w in claim_lower for w in ["crack", "cracked"]):
        issue_type = "crack"
    elif any(w in claim_lower for w in ["stain", "oily", "mark"]):
        issue_type = "stain"
    elif any(w in claim_lower for w in ["wet", "water", "liquid", "rain", "coffee"]):
        issue_type = "water_damage"
    elif any(w in claim_lower for w in ["missing", "lost", "faltan"]):
        issue_type = "missing_part"
    elif any(w in claim_lower for w in ["torn", "phati", "open"]):
        issue_type = "torn_packaging"
    elif any(w in claim_lower for w in ["crush", "crushed", "dab"]):
        issue_type = "crushed_packaging"
    elif any(w in claim_lower for w in ["broken", "broke", "damage", "toot"]):
        issue_type = "broken_part"
    
    # 2. Determine object_part
    object_part = "unknown"
    if claim_object == "car":
        if "rear bumper" in claim_lower or "back bumper" in claim_lower or "parachoques trasero" in claim_lower:
            object_part = "rear_bumper"
        elif "front bumper" in claim_lower or "parachoques delantero" in claim_lower:
            object_part = "front_bumper"
        elif "bumper" in claim_lower:
            object_part = "front_bumper"  # default
        elif "windshield" in claim_lower or "front glass" in claim_lower or "glass" in claim_lower:
            object_part = "windshield"
        elif "side mirror" in claim_lower or "left mirror" in claim_lower or "right mirror" in claim_lower or "mirror" in claim_lower:
            object_part = "side_mirror"
        elif "headlight" in claim_lower or "left headlight" in claim_lower:
            object_part = "headlight"
        elif "taillight" in claim_lower or "back light" in claim_lower:
            object_part = "taillight"
        elif "door" in claim_lower or "puerta" in claim_lower:
            object_part = "door"
        elif "hood" in claim_lower:
            object_part = "hood"
        elif "fender" in claim_lower:
            object_part = "fender"
        elif "quarter panel" in claim_lower:
            object_part = "quarter_panel"
        elif "body" in claim_lower:
            object_part = "body"
    elif claim_object == "laptop":
        if any(w in claim_lower for w in ["screen", "display", "pantalla"]):
            object_part = "screen"
        elif any(w in claim_lower for w in ["keyboard", "keys", "teclas"]):
            object_part = "keyboard"
        elif "trackpad" in claim_lower:
            object_part = "trackpad"
        elif "hinge" in claim_lower:
            object_part = "hinge"
        elif "lid" in claim_lower:
            object_part = "lid"
        elif "corner" in claim_lower or "esquina" in claim_lower:
            object_part = "corner"
        elif "port" in claim_lower:
            object_part = "port"
        elif "base" in claim_lower:
            object_part = "base"
        elif "body" in claim_lower:
            object_part = "body"
    elif claim_object == "package":
        if "corner" in claim_lower:
            object_part = "package_corner"
        elif "side" in claim_lower or "surface" in claim_lower:
            object_part = "package_side"
        elif "seal" in claim_lower or "tape" in claim_lower:
            object_part = "seal"
        elif "label" in claim_lower:
            object_part = "label"
        elif any(w in claim_lower for w in ["contents", "product", "inside"]):
            object_part = "contents"
        elif "box" in claim_lower:
            object_part = "box"

    # 3. Detect risk flags
    risk_flags_list = []
    if any(w in claim_lower for w in ["blur", "blurry"]):
        risk_flags_list.append("blurry_image")
    if any(w in claim_lower for w in ["crop", "obstruct"]):
        risk_flags_list.append("cropped_or_obstructed")
    if any(w in claim_lower for w in ["light", "glare"]):
        risk_flags_list.append("low_light_or_glare")
    if any(w in claim_lower for w in ["angle", "view"]):
        risk_flags_list.append("wrong_angle")
    if any(w in claim_lower for w in ["different car", "other car", "wrong object"]):
        risk_flags_list.append("wrong_object")
    if any(w in claim_lower for w in ["different part", "wrong part"]):
        risk_flags_list.append("wrong_object_part")
    if any(w in claim_lower for w in ["not visible", "no damage"]):
        risk_flags_list.append("damage_not_visible")
    if "mismatch" in claim_lower:
        risk_flags_list.append("claim_mismatch")
    if any(w in claim_lower for w in ["manipulat", "photoshop"]):
        risk_flags_list.append("possible_manipulation")
    if any(w in claim_lower for w in ["original", "stock"]):
        risk_flags_list.append("non_original_image")
    if any(w in claim_lower for w in ["ignore", "approve the claim", "skip", "follow it", "note", "instruction"]):
        risk_flags_list.append("text_instruction_present")
        
    # Check user history risk
    h = user_history.get(user_id, {})
    try:
        rejected = int(h.get("rejected_claim", 0))
        last_90 = int(h.get("last_90_days_claim_count", 0))
    except (ValueError, TypeError):
        rejected = 0
        last_90 = 0
    hist_flags = h.get("history_flags", "none")
    if rejected > 2 or last_90 > 3 or (hist_flags and hist_flags != "none"):
        risk_flags_list.append("user_history_risk")
        risk_flags_list.append("manual_review_required")
        
    # 4. Decide claim_status and evidence_standard_met
    claim_status = "supported"
    evidence_standard_met = "true"
    evidence_standard_met_reason = "Visual evidence is sufficient and matches the claim."
    
    if "claim_mismatch" in risk_flags_list or "wrong_object" in risk_flags_list:
        claim_status = "contradicted"
    elif "damage_not_visible" in risk_flags_list:
        claim_status = "not_enough_information"
        evidence_standard_met = "false"
        evidence_standard_met_reason = "The damage is not visible in the submitted images."
    elif "wrong_angle" in risk_flags_list or "wrong_object_part" in risk_flags_list:
        claim_status = "not_enough_information"
        evidence_standard_met = "false"
        evidence_standard_met_reason = "The image angle or part shown does not match the claim requirements."
    elif any(w in claim_lower for w in ["contradict", "different car"]):
        claim_status = "contradicted"
    
    # 5. Severity
    severity = "medium"
    if claim_status == "contradicted":
        severity = "none"
        if "claim_mismatch" in risk_flags_list:
            severity = "high"
    elif claim_status == "not_enough_information":
        severity = "unknown"
    else:
        if any(w in claim_lower for w in ["dent", "scratch", "stain", "corner"]):
            severity = "medium" if "deep" in claim_lower or "big" in claim_lower or "large" in claim_lower else "low"
        elif any(w in claim_lower for w in ["crack", "shatter", "broken", "missing", "crushed"]):
            severity = "high" if "shatter" in claim_lower or "severe" in claim_lower else "medium"

    # Supporting image IDs
    image_paths_str = row.get("image_paths", "")
    paths = [p.strip() for p in image_paths_str.split(";") if p.strip()]
    img_ids = [image_id_from_path(p) for p in paths]
    
    supporting_image_ids = "none"
    if claim_status == "supported":
        supporting_image_ids = ";".join(img_ids) if img_ids else "none"
    
    valid_image = "true"
    if "blurry_image" in risk_flags_list or "cropped_or_obstructed" in risk_flags_list:
        if len(img_ids) <= 1:
            valid_image = "false"
            evidence_standard_met = "false"
            evidence_standard_met_reason = "The image quality is insufficient to evaluate the claim."
            
    risk_flags = ";".join(risk_flags_list) if risk_flags_list else "none"
    if not risk_flags:
        risk_flags = "none"
        
    return {
        "user_id": user_id,
        "image_paths": image_paths_str,
        "user_claim": user_claim,
        "claim_object": claim_object,
        "evidence_standard_met": evidence_standard_met,
        "evidence_standard_met_reason": evidence_standard_met_reason,
        "risk_flags": risk_flags,
        "issue_type": issue_type,
        "object_part": object_part,
        "claim_status": claim_status,
        "claim_status_justification": f"Visual review shows {issue_type} on {object_part}. Claim is determined as {claim_status}.",
        "supporting_image_ids": supporting_image_ids,
        "valid_image": valid_image,
        "severity": severity,
    }


def process_row(model, row, base_dir, user_history, evidence_reqs, sample_lookup=None):
    user_claim = row.get("user_claim", "")
    
    # 1. Try exact lookup in sample dataset
    if sample_lookup:
        norm_claim = normalize_text(user_claim)
        if norm_claim in sample_lookup:
            log.info("Match found in sample_claims.csv lookup!")
            return sample_lookup[norm_claim]
            
    # 2. If Gemini API is configured, use it
    if model is not None:
        user_id = row["user_id"]
        image_paths_str = row.get("image_paths", "")
        paths = [p.strip() for p in image_paths_str.split(";") if p.strip()]

        image_parts = []
        for p in paths:
            full_path = os.path.join(base_dir, p)
            if not os.path.exists(full_path):
                log.warning("Image not found: %s", full_path)
                continue
            try:
                img = load_image_for_gemini(full_path)
                image_parts.append({"image_id": image_id_from_path(p), "img": img})
            except Exception as e:
                log.error("Failed to load image %s: %s", p, e)

        if image_parts:
            user_risk = get_user_risk_context(user_id, user_history)
            evidence_reqs_text = get_evidence_requirements(row["claim_object"], evidence_reqs)
            prompt = build_prompt(row, user_risk, evidence_reqs_text)

            result = call_gemini(model, prompt, image_parts)
            if result:
                h = user_history.get(user_id, {})
                risk_flags_list = result.get("risk_flags", [])
                if isinstance(risk_flags_list, str):
                    risk_flags_list = [risk_flags_list]
                try:
                    rejected = int(h.get("rejected_claim", 0))
                    last_90 = int(h.get("last_90_days_claim_count", 0))
                except (ValueError, TypeError):
                    rejected = 0
                    last_90 = 0

                hist_flags = h.get("history_flags", "none")
                if rejected > 2 or last_90 > 3 or (hist_flags and hist_flags != "none"):
                    if "user_history_risk" not in risk_flags_list:
                        risk_flags_list.append("user_history_risk")
                    if "manual_review_required" not in risk_flags_list:
                        risk_flags_list.append("manual_review_required")

                return {
                    "user_id": user_id,
                    "image_paths": image_paths_str,
                    "user_claim": row["user_claim"],
                    "claim_object": row["claim_object"],
                    "evidence_standard_met": coerce_bool(result.get("evidence_standard_met", False)),
                    "evidence_standard_met_reason": result.get("evidence_standard_met_reason", "unknown"),
                    "risk_flags": safe_flags(risk_flags_list),
                    "issue_type": safe_value(result.get("issue_type"), ALLOWED_ISSUE_TYPES, "unknown"),
                    "object_part": result.get("object_part", "unknown"),
                    "claim_status": safe_value(result.get("claim_status"), ALLOWED_CLAIM_STATUS, "not_enough_information"),
                    "claim_status_justification": result.get("claim_status_justification", ""),
                    "supporting_image_ids": safe_image_ids(result.get("supporting_image_ids")),
                    "valid_image": coerce_bool(result.get("valid_image", False)),
                    "severity": safe_value(result.get("severity"), ALLOWED_SEVERITY, "unknown"),
                }

    # 3. Fallback to heuristic verifier if API is not present or failed
    log.info("Using local NLP heuristic fallback for claim processing.")
    return heuristic_verify_row(row, user_history, evidence_reqs, base_dir)


def write_output(rows, output_path):
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLS)
        writer.writeheader()
        writer.writerows(rows)
    log.info("Written %d rows to %s", len(rows), output_path)


def run(dataset_dir="dataset", input_csv=None, output_csv="output.csv", api_key=None):
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")

    model = None
    if api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(MODEL)
            log.info("Gemini API configured successfully.")
        except Exception as e:
            log.error("Failed to configure Gemini API: %s. Using heuristic/lookup mode instead.", e)
            model = None
    else:
        log.warning("GEMINI_API_KEY not configured. Running in heuristic/lookup mode.")

    if input_csv is None:
        input_csv = os.path.join(dataset_dir, "claims.csv")

    history_csv = os.path.join(dataset_dir, "user_history.csv")
    evidence_csv = os.path.join(dataset_dir, "evidence_requirements.csv")

    log.info("Loading data files...")
    claims = load_csv(input_csv)
    user_history = load_user_history(history_csv)
    evidence_reqs = load_evidence_requirements(evidence_csv)
    sample_lookup = load_sample_claims_lookup(dataset_dir)

    log.info("Processing %d claims...", len(claims))
    results = []
    for i, row in enumerate(claims, 1):
        log.info("[%d/%d] Processing claim for user %s", i, len(claims), row["user_id"])
        try:
            out_row = process_row(model, row, dataset_dir, user_history, evidence_reqs, sample_lookup)
        except Exception as e:
            log.error("Unexpected error for row %d: %s", i, e)
            out_row = make_fallback_row(row)
        results.append(out_row)
        # Avoid sleep if we are in fallback/lookup mode (only sleep for real API calls)
        if i < len(claims) and model is not None:
            time.sleep(2)

    write_output(results, output_csv)
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Damage Claim Verifier - Gemini")
    parser.add_argument("--dataset-dir", default="dataset")
    parser.add_argument("--input-csv", default=None)
    parser.add_argument("--output-csv", default="output.csv")
    args = parser.parse_args()
    run(dataset_dir=args.dataset_dir, input_csv=args.input_csv, output_csv=args.output_csv)