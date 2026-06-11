import pandas as pd
import os

def analyze_performance(csv_path):
    df = pd.read_csv(csv_path)
    rec_dist = df['recommended'].value_counts(normalize=True)
    df['is_clicked'] = df['clicked'].notnull()
    ctr = df.groupby('recommended')['is_clicked'].mean()
    return pd.concat([rec_dist, ctr], axis=1, keys=['freq', 'ctr'])

if __name__ == "__main__":
    log_path = "backend/data/simulation_logs.csv"
    if os.path.exists(log_path):
        print(analyze_performance(log_path).head(10))
    else:
        print("Log file missing.")
