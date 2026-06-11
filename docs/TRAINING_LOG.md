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

## Stage 2 — Netflix Prize pretrain (+ML25M, 25% user subsample)

- 3,026/17,770 Netflix titles mapped by normalized title+year (±1)
- full-Netflix variant (75.6M ratings) REGRESSED AUC 0.7936 -> 0.7643 (2005-era data swamps modern signal); retried at 25% user parity
- Netflix adds 18,834,398 ratings on catalog titles (119,550 users)
- ratings: 42,100,611 rows / 282,085 users (86,103 holdout judgments, 2,541 eval users)
- old factors: shipped AUC 0.7936, P@5 0.8586, P@10 0.8594 (cf-only AUC 0.7593)
- new factors: shipped AUC 0.7895, P@5 0.8534, P@10 0.8549 (cf-only AUC 0.7548)
- verdict: REJECTED (regression — old factors kept)

## Stage 3 — MTS Kion implicit watch events (+ML25M)

- 1,788/12,002 Kion films mapped via title_orig/title + year (±1)
- completion-as-signal: >=70% watched -> 4.5, <=20% -> 1.5 (middle dropped)
- adds 840,528 pseudo-ratings from 298,334 real streaming users
- ratings: 24,106,741 rows / 460,869 users (86,103 holdout judgments, 2,541 eval users)
- old factors: shipped AUC 0.7936, P@5 0.8586, P@10 0.8594 (cf-only AUC 0.7593)
- new factors: shipped AUC 0.7937, P@5 0.8573, P@10 0.8594 (cf-only AUC 0.7594)
- verdict: ADOPTED

## Stage 4 — recent ratings only (2015+, HF recent-ratings equivalent)

- HF pinecone/movielens-recent-ratings is a loader over ml-25m.zip; the slice is reproduced locally
- hypothesis: dropping pre-2015 preferences sharpens modern like/dislike prediction
- ratings: 6,755,713 rows / 45,043 users (86,103 holdout judgments, 2,541 eval users)
- old factors: shipped AUC 0.7937, P@5 0.8573, P@10 0.8594 (cf-only AUC 0.7594)
- new factors: shipped AUC 0.7619, P@5 0.8555, P@10 0.8569 (cf-only AUC 0.7310)
- verdict: REJECTED (regression — old factors kept)

## Stage 5 — Kaggle "movie rating data" (20M + tags)

- not trained: the dataset is GroupLens MovieLens 20M (2016) repackaged — a
  strict predecessor of the 25M release Stage 1 already trains on in full,
  including the tag-genome our content signal consumes from 25M's newer cut.
  Nothing in it is new to the corpus; also requires Kaggle credentials.
- verdict: REDUNDANT (documented, skipped)

## Catalog collision repair (post-campaign)

- 135 wrong-film overviews (year-less CMU fallback collisions: Inside Out
  2015 carried the 2011 crime film's plot, Ex Machina carried Appleseed,
  Arrival carried The Arrival 1996...) — re-fetched year-verified Wikipedia
  summaries (Inside Out/Whiplash/Arrival fixed; unverifiable ones cleared);
  all 135 rows re-embedded with MiniLM so the semantic space is clean.
- 1,251 trailer keys nulled: 19 YouTube ids had fanned out over hundreds of
  films each (consent-page scrape bug); the runtime YouTube-search fallback
  serves those titles. Both enrichment scripts hardened (year-aware CMU
  lookup; same-id dedup guard).

## Constant re-sweep on Stage-3 factors (post-campaign tuning)

- the shipped POP_BETA/W_SEMANTIC_ENERGY were tuned against the old
  10%-sample factors; re-swept jointly (beta x w_semantic grid) on the
  adopted Stage-3 factors.
- w_semantic: flat within noise across 0.10-0.20 — kept at 0.15.
- POP_BETA 0.6 -> 0.75: AUC improves on every seed tested
  (42: 0.8019 -> 0.8031; 7: 0.7817 -> 0.7832; 1234: 0.7682 -> 0.7702),
  P@5 neutral-to-positive. ADOPTED.
