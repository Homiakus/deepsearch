# DeepSearch Sensitivity Matrix and Discontinuity Documentation (§DS-32)

## Overview

This document defines and characterizes the sensitivity properties, thresholds, weights, and deterministic tie-break mechanisms across DeepSearch's decision components:
1. **Page Intelligence Classifier** (`scraper/acquisition/page_classifier.py`)
2. **Cost-Aware Planner & Extraction Quality Evaluator** (`scraper/control/planner.py`)
3. **Provider Selection & Health Tracker** (`scraper/discovery/provider_policy.py`)
4. **Media Discovery & Topic Image Ranker** (`scraper/discovery/media_finder.py`)
5. **Explainable Candidate Ranker** (`scraper/search/ranking/candidate_ranker.py`)

---

## 1. Page Intelligence Classifier Sensitivity Matrix

| Parameter / Feature | Value / Threshold | Rationale & Origin | Discontinuity / Behavior at Boundary | Boundary Test |
|---|---|---|---|---|
| `SCRIPT_COUNT_HEURISTIC_THRESHOLD` | `15` scripts | SPAs and heavily client-rendered pages typically include >15 `<script>` tags. | At `len(scripts) <= 15`: no JS boost (`+0.0`). At `len(scripts) > 15`: `+0.2` JS score. | `test_classifier_script_count_boundary_sensitivity` |
| `EMPTY_DOM_SHELL_MAX_BYTES` | `2000` bytes | Unrendered SPA shells containing framework roots (`#react-root`, etc.) have minimal HTML payload prior to client execution. | If framework detected and `len(html) < 2000`: `+0.3` JS score. If `>= 2000`: `+0.0`. | `test_classifier_empty_dom_shell_size_boundary` |
| `TABLE_COUNT_VISUAL_THRESHOLD` | `2` tables | Dense tabular structures (>2 tables) require visual/VLM fidelity for complex layouts. | At `tables <= 2`: `visual_score = 0.10`. At `tables > 2`: `+0.3` boost (`visual_score = 0.40`). | `test_classifier_tables_visual_score_boundary` |
| `API_DISCOVERY_MULTIPLIER` | `0.3` per API | Linear confidence boost for each detected internal API endpoint. | Scaled linearly: `min(1.0, count * 0.3)`. Capped at 1.0 (>=4 APIs). | `test_classifier_api_score_linear_scaling_and_ceiling` |
| `BOT_BLOCK_SCORE` / `JS_FLOOR` | `0.95` / `0.85` | Bot challenge pages (Cloudflare, 403, Captcha) require browser escalation and challenge solving. | Sets `block_score = 0.95`, `js_score = max(js, 0.85)`, `content_quality = 0.05`. | `test_classifier_bot_block_indicators` |
| Framework markers | Exact tokens (`__next_data__`, `data-reactroot`, `v-app`, `ng-version`, etc.) | Prevents false positives from natural language words (e.g., "reaction", "angular"). | Non-marker prose does NOT trigger framework flags. | `test_classifier_framework_markers_no_false_positives` |

---

## 2. CostPlanner & Extraction Quality Calibration

### Quality Evaluator Weights

Canonical formula for extraction quality:
$$\text{Quality} = 0.30 \cdot \text{Completeness} + 0.20 \cdot \text{Validity} + 0.20 \cdot \text{Consistency} + 0.15 \cdot \text{SchemaMatch} + 0.15 \cdot \text{ContentDensity}$$

- **Weight Sensitivity ($\pm 1\%, \pm 5\%, \pm 10\%$):** Quality score varies linearly and monotonically without discontinuous jumps.
- **Content Density Ceiling:** Normalized against `CONTENT_DENSITY_MAX_HTML_LEN = 50,000` characters, floored at `0.10` for non-empty HTML, capped at `1.00`.

### Escalation Thresholds

| Strategy Transition | Trigger Condition | Rationale |
|---|---|---|
| `CACHE -> HTTP` | `overall_score < required_quality` (`0.85`) | Cache miss or stale data requires live HTTP fetch. |
| `HTTP -> API` | `api_available == True` and `api_preference == True` | Direct API data extraction has lower compute and latency than headless browser. |
| `HTTP -> BROWSER` | `js_score >= browser_threshold` or HTTP quality failure | Dynamic JS execution required. |
| `BROWSER -> VISUAL` | `visual_score >= visual_threshold` (`0.70`) | Complex charts/canvases/tables require VLM visual extraction. |
| `BROWSER -> SEMANTIC` | `visual_score < visual_threshold` | Text-heavy extraction handled by semantic LLM parser. |

---

## 3. Provider Yield & Health Sensitivity

| Parameter | Threshold | Value / Health Factor | Description |
|---|---|---|---|
| `HEALTH_FACTOR_HEALTHY` | Error rate $< 0.50$ | `1.0` | Normal operation, full provider capacity. |
| `HEALTH_FACTOR_DEGRADED` | Error rate $\ge 0.50$ and $< 0.80$ (or calls $< 3$) | `0.6` | Provider experiencing transient failures, reduced priority. |
| `HEALTH_FACTOR_UNHEALTHY` | Error rate $\ge 0.80$ and calls $\ge 3$ | `0.2` | Persistent provider failure, penalized in routing selection. |

---

## 4. Media & Candidate Ranking Deterministic Tie-Breaks

### Invariants:
1. **Permutation Invariance:** For any candidate pool $P$ and any permutation $\pi(P)$, the ranked output list satisfies $\text{Rank}(P) = \text{Rank}(\pi(P))$.
2. **Neutral Candidate Monotonicity:** Adding a neutral/unrelated candidate $C_{\text{neutral}}$ with low relevance score to pool $P$ does not perturb the relative ordering or absolute scores of existing candidates in $P$.
3. **Deterministic Tie-Break:** When two candidates have identical relevance or ranking scores:
   - In `CandidateRanker`: tie-break by `(final_score, candidate.canonical_url or candidate.url)` descending.
   - In `score_and_rank_images`: tie-break by `(relevance_score, item["url"])` descending.
4. **Boundary Validation:** `min_count > max_count` raises `ValueError` before performing any ranking computation (`FRAG-009`).
