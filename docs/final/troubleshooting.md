# Troubleshooting

| Symptom | Diagnosis | Safe action | Never delete |
|---|---|---|---|
| Docker/Compose missing | `docker --version`; `docker-compose version` | install supported engine/plugin | volumes |
| PostgreSQL unhealthy | `make demo-logs`; `pg_isready` | verify `.env`, port and disk; restart | `postgres_data` |
| Migration failed | `alembic current/history` | restore backup; fix migration; retry | corpus tables |
| Qdrant unavailable/alias missing | system/index report | start Qdrant; run validated full reindex | active collection |
| Ollama/model missing | `make models-check` | explicit `make models-pull`; CPU fallback | model volume |
| NVIDIA/VRAM issue | toolkit and `nvidia-smi` | use base CPU compose; reduce context | data volumes |
| Worker offline/stuck job | heartbeat, lease, job events | restart worker; allow stale recovery | checkpoint |
| API quota exhausted/page 25 | source/job events | wait; anonymous import rolls to a new `todate` window | checkpoint |
| Search index empty | eligible chunks and active alias | start indexer/full reindex | PostgreSQL chunks |
| RAG stream delayed/502 | Nginx buffering/timeouts, Ollama | use `/api/ask` fallback; inspect request ID | responses DB |
| CSRF/session error | fetch `/api/auth/csrf`, cookie settings | re-login/rotate token | security middleware |
| Disk warning | `make disk-report` | confirmed `make cleanup-safe` for caches/logs only | DB, Qdrant, models, backups |
| Backup failed | container health and permissions | retry without changing primary data | last good backup |
| Restore check failed | checksums/versions | reject bundle and create new backup | primary environment |
