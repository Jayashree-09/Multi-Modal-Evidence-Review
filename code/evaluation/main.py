"""
Evaluation entry point for the damage claim verification system.
"""

import sys
import argparse
from pathlib import Path

# Add the evaluation directory to the path so we can import evaluate
sys.path.insert(0, str(Path(__file__).parent))
import evaluate

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", default="dataset")
    args = parser.parse_args()
    evaluate.run_evaluation(args.dataset_dir)
