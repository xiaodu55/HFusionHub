# Retrieval evaluation suite

Copy `retrieval_cases.example.jsonl` to a version-controlled JSONL file and
replace every placeholder with a representative question and one or more
relevant stable `chunk_id` values from the same knowledge base.

Run the suite against the locally configured index:

```bash
python scripts/evaluate_retrieval.py \
  --cases evaluation/retrieval_cases.jsonl \
  --top-k 5 \
  --minimum-recall 0.70 \
  --minimum-mrr 0.60 \
  --maximum-scope-violations 0
```

The command emits JSON with Recall@k, hit rate, MRR@k, nDCG@k, per-case ranks,
and knowledge-base scope violations. It exits non-zero whenever a supplied
quality threshold is not met, so the same command can be used in CI.
