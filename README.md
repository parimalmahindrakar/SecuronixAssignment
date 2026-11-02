# Enrichment lookup coordinator

FastAPI + Postgres + Redis backend, React (Vite) frontend. Shares a 10-lookups-a-day quota safely.

## Run (everything in Docker)
```bash
docker compose up --build      
```
Open http://localhost:5173 (API docs at http://localhost:8000/docs).

Concurrency check (200 simultaneous requests, quota 10):
```bash
docker compose --profile test run --rm loadtest
```
