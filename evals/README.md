# DeepSearch Continuous Research Evaluation Benchmark (§18, DS-A44)

## Overview
This benchmark suite provides golden query sets and metrics for evaluating DeepSearch retrieval, coverage, and claim verification quality.

## Benchmark Metrics
1. **SourceRecall**: Ratio of expected authoritative sources discovered.
2. **EvidencePrecision**: Proportion of extracted claims with valid corroboration.
3. **RetrievalRecall@10**: Quality of Top-10 dense + lexical fused chunks.
4. **NDCG@10**: Normalized Discounted Cumulative Gain for ranking quality.
5. **CostEfficiency**: Total cost and token usage per research question.

## Datasets
- `evals/datasets/golden_queries.json`: Standard research prompts across scientific, medical, and technical domains.
