# Training log

One entry per dataset stage. Metric = ml.evaluate temporal holdout (AUC / P@k), same protocol every stage.

## Stage 1 — MovieLens 25M (full)

- previous factors were trained on a 10% user sample (2.33M ratings)
- ratings: 23,266,213 rows / 162,535 users (86,103 holdout judgments, 2,541 eval users)
- old factors: shipped AUC 0.7861, P@5 0.8646, P@10 0.8647 (cf-only AUC 0.7609)
- new factors: shipped AUC 0.7893, P@5 0.8632, P@10 0.8639 (cf-only AUC 0.7593)
- verdict: ADOPTED
