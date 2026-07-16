# Demonstration script

## Main scenario (7–10 minutes)

| Step | Action | What to say | Expected result | Fallback |
|---:|---|---|---|---|
| 1 | `make demo-status` then open `http://localhost:8080` | one-command local environment | healthy services/home | show acceptance report |
| 2 | Open System | corpus/models/workers are measured server-side | real counts/status | explain UNKNOWN |
| 3 | Search exact identifier in BM25 | lexical relevance | exact technical match | prepared query |
| 4 | Rephrase in Vector | semantic retrieval | paraphrase match | switch query |
| 5 | Hybrid + score panel | RRF then reranker | component/final scores | diagnostics tab |
| 6 | Apply tag/code filter | payload filter plus DB visibility check | filtered results | clear filters |
| 7 | Ask answerable question | retrieval precedes generation | sources then streamed tokens | JSON fallback |
| 8 | Click citations | backend validates `[n]` mapping | highlighted source card | open source URL |
| 9 | Ask out-of-corpus question | LLM is not called without context | deterministic refusal | show metric |
| 10 | Save, history, feedback | persisted USER contour | rows appear once | refresh |
| 11 | Login EDITOR; hide/restore | server permissions and search consistency | absent then reindexed | show job event |
| 12 | Login ADMIN | source/jobs/audit/system | operational evidence | use screenshots |
| 13 | Start capped dry/smoke sync | HTTP only enqueues durable job | progress/checkpoint | cancel safely |
| 14 | Show manifests/evaluation | metrics are reproducible | hashes/timestamps | explain NOT_RUN |

Do not run full import, cleanup, restore or model pull during the defense.

## Short scenario (3 minutes)

Show System corpus/index counts, one Hybrid query with score breakdown, one streamed cited RAG
answer, an insufficient-context refusal, then ADMIN jobs/audit. End on the acceptance report.
