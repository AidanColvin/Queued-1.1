import numpy as n
class TrajectoryPredictor:
 def __init__(self, d=384):
  self.d = d
  self.w = {"liked":1.0,"saved":0.65,"skip":0.0,"dismissed":-0.55}
 def predict_future_affinity(self, c, s, cand):
  v_pref = n.array(c, dtype=float)
  v_cand = n.array(cand, dtype=float)
  for swipe in s:
   v_pref += self.w.get(swipe["action"], 0.0) * n.array(swipe["embedding"], dtype=float)
  np_norm = n.linalg.norm(v_pref)
  nc_norm = n.linalg.norm(v_cand)
  return float(n.dot(v_pref, v_cand) / (np_norm * nc_norm)) if np_norm and nc_norm else 0.0
