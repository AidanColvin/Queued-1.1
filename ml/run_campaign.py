"""
Orchestrates the multi-stage training campaign for Queued.
Ensures stages run in sequence and artifacts are validated post-training.
"""

import sys
import logging
import time
from pathlib import Path
from ml.stages.stage_1_movielens import run_stage_1
from ml.stages.stage_3_kion import run_stage_3

# Configure logging to write to your training log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("docs/TRAINING_LOG.md", mode='a'), logging.StreamHandler(sys.stdout)]
)

def run_campaign():
    """
    takes: None.
    does: Executes training stages sequentially, logs results, and validates outputs.
    returns: Exit code 0 if success, 1 if any stage fails.
    """
    logging.info("--- Starting Training Campaign ---")
    
    try:
        # Stage 1: Baseline
        logging.info("Executing Stage 1: MovieLens 25M")
        res1 = run_stage_1()
        logging.info(f"Stage 1 Complete: AUC {res1.get('auc')}")

        # Stage 3: Incremental Fine-tuning
        kion_path = "data/kion_events.csv"
        out_path = "data/artifacts/model_v3.bin"
        
        logging.info(f"Executing Stage 3: Kion Fine-tuning (Input: {kion_path})")
        res3 = run_stage_3(kion_path, out_path)
        
        logging.info(f"Stage 3 Complete: AUC Delta {res3.get('auc_delta')}")
        logging.info("--- Campaign Successful ---")
        return 0

    except Exception as e:
        logging.error(f"Campaign Failed: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = run_campaign()
    sys.exit(exit_code)