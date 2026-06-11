import sys, os, json, pandas as pd

# Fix: Append the parent directory (backend/) to sys.path
# so that 'ml' becomes an importable package.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ml.simulation_runner import run_scenarios
from ml.train_from_logs import train_from_logs

def run_epoch(epoch_id):
    print(f"\n--- Epoch {epoch_id} Start ---")
    run_scenarios(num_agents=200)
    train_from_logs()

    df = pd.read_csv("backend/data/simulation_logs.csv")
    ctr = df['clicked'].notnull().mean()
    print(f"Epoch {epoch_id} Result -> Click-Through Rate: {ctr:.4f}")

if __name__ == "__main__":
    for i in range(10):
        run_epoch(i)
