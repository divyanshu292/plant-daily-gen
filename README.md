# TTPS Daily Data Entry

Tenughat Thermal Power Station — daily operational log with a monochrome React UI and a minimal FastAPI + MongoDB Atlas backend. Includes a live polling tile that mirrors the plant's real-time generation feed.

## Structure

```
plant/
├── backend/     FastAPI + Motor (async MongoDB)
└── frontend/    Vite + React + Tailwind + shadcn/ui
```

## Setup — Docker (recommended)

```bash
cp backend/.env.example backend/.env
# paste your MongoDB Atlas URI into backend/.env
docker compose up --build
```

- Frontend → http://localhost:5173
- Backend  → http://localhost:8000
- Nginx inside the frontend container proxies `/api/*` to the backend.

Docker Compose loads the backend env from `backend/.env` via `env_file:`, so there's only one place to configure secrets.

## Setup — Without Docker

### 1. Backend (Python 3.11+)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # paste your Atlas URI
uvicorn main:app --reload --port 8000
```

API on http://localhost:8000 · Swagger at `/docs`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

UI on http://localhost:5173 (proxies `/api/*` to `localhost:8000`).

## What it does

- One row per day, grouped by month (Apr 2026 → Mar 2027).
- Edit **U1** and **U2** for each of **Gen, Trip, BTL, FO, PO**; **STN** is auto-computed.
- Every edit is debounced (500 ms) and upserted to Atlas via `PUT /api/entries/:date`.
- Live tile polls the plant feed every 5 s through a backend proxy (bypasses CORS, 3 s server cache).
- Light/dark mode toggle (persists in `localStorage`); fully responsive.

## API

| Method | Endpoint                         | Purpose                                |
| ------ | -------------------------------- | -------------------------------------- |
| GET    | `/`                              | Endpoint index                         |
| GET    | `/api/health`                    | Liveness check                         |
| GET    | `/api/entries?month=YYYY-MM`     | List entries for a month               |
| PUT    | `/api/entries/:date`             | Upsert a single day's fields           |
| GET    | `/api/live-generation`           | Proxied live MW readings (cached 3 s)  |

`date` is `YYYY-MM-DD`. PUT body is any subset of: `u1Gen, u2Gen, u1Trip, u2Trip, u1Btl, u2Btl, u1Fo, u2Fo, u1Po, u2Po`.

## Production

- **Frontend:** `npm run build` in `frontend/` → serve `dist/` (or use the included nginx image).
- **Backend:** `uvicorn main:app --host 0.0.0.0 --port 8000` with `MONGODB_URI` set. For more workers: add `--workers 4`.
- Point the frontend at a deployed API via `VITE_API_URL` in dev, or by updating `frontend/nginx.conf` for prod.
