import sys
import os
import logging

# Ensure backend modules are discoverable
sys.path.append(os.path.join(os.path.dirname(__file__), '../backend'))

from ml.stages.stage_1_movielens import run_stage_1
from ml.stages.stage_3_kion import run_stage_3

def run_campaign():
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting Multi-Stage Training Campaign...")
    
    # Stage 1: Baseline
    res1 = run_stage_1()
    logging.info(f"Stage 1 AUC: {res1.get('auc')}")
    
    # Stage 3: Kion Fine-tuning
    res3 = run_stage_3("data/kion_events.csv", "data/artifacts/model_v3.bin")
    logging.info(f"Stage 3 AUC Delta: {res3.get('auc_delta')}")

if __name__ == "__main__":
    run_campaign()