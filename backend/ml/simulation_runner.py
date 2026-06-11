import sys
import os
import csv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ml.simulate import VirtualUser
from ml.reranker import build_taste_space

def run_scenarios(num_agents=500):
    agents = [VirtualUser(i) for i in range(num_agents)]
    os.makedirs("backend/data", exist_ok=True)
    with open("backend/data/simulation_logs.csv", 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['user_id', 'recommended', 'clicked'])
        for agent in agents:
            recs = build_taste_space(agent.history)
            clicked = agent.interact(recs)
            writer.writerow([agent.user_id, recs[0], clicked])
    print("Simulation complete.")

if __name__ == "__main__":
    run_scenarios()
