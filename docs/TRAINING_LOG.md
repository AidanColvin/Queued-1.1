# Training log

One entry per dataset stage. Metric = ml.evaluate temporal holdout (AUC / P@k), same protocol every stage.

## Stage 1 — MovieLens 25M (full)

- previous factors were trained on a 10% user sample (2.33M ratings)
- ratings: 23,266,213 rows / 162,535 users (86,103 holdout judgments, 2,541 eval users)
- old factors: shipped AUC 0.7954, P@5 0.8603, P@10 0.8626 (cf-only AUC 0.7609)
- new factors: shipped AUC 0.7959, P@5 0.8602, P@10 0.8612 (cf-only AUC 0.7593)
- verdict: ADOPTED — small but real AUC gain; the catalog's 5,462 titles were
  already well-covered by the 10% sample, so 10x data moves the needle only
  slightly. Popularity prior refreshed from the full 25M counts.
- incident: an interim "force commit" regenerated all artifacts from the 10%
  sample WITHOUT enrichment (catalog shrank to 5,400; zero posters/trailers —
  the production deck went empty). Restored the enriched 5,462-title artifacts
  from git (2b77796) and retrained on top; numbers above are post-restore.

## Stage 2 — Netflix Prize pretrain (+ML25M)

- 3,026/17,770 Netflix titles mapped by normalized title+year (±1)
- Netflix adds 75,591,925 ratings on catalog titles (478,625 users)
- ratings: 98,858,138 rows / 641,160 users (86,103 holdout judgments, 2,541 eval users)
- old factors: shipped AUC 0.7936, P@5 0.8586, P@10 0.8594 (cf-only AUC 0.7593)
- new factors: shipped AUC 0.7643, P@5 0.8416, P@10 0.8452 (cf-only AUC 0.7320)
- verdict: REJECTED (regression — old factors kept)
