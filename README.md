# SUAS — Shut Up and Serve

Daily Philippine political accountability post generator for Facebook.

## What it does

Runs 3 scheduled pipeline runs daily, fetching Philippine political news, Google Trends data, and Reddit discussions. Uses Claude API to generate Facebook posts in a confrontational accountability voice, and Gemini API to create branded images. Posts are stored in Firestore for review and published to Facebook after approval.

## Tech stack

- **Backend**: Python 3.11 + FastAPI + Poetry
- **Frontend**: React + Vite + Tailwind CSS
- **Database**: Firestore
- **Hosting**: Cloud Run

## Local development quickstart

```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys
docker-compose up --build
# Backend: http://localhost:8000
# Frontend: http://localhost:5173
# Firestore emulator: http://localhost:8080
```

## Seed test data

```bash
docker-compose exec backend python scripts/seed_firestore.py
```

## Run tests

```bash
docker-compose -f docker-compose.test.yml up --abort-on-container-exit
```

## Trigger pipeline manually

```bash
curl -X POST http://localhost:8000/api/pipeline/trigger \
  -H "Authorization: Bearer <your-firebase-id-token>"
```

## Build phases

1. **Phase 1** — Core Pipeline
2. **Phase 2** — Dashboard
3. **Phase 3** — Facebook + Reports
4. **Phase 4** — Polish + Learning
5. **Phase 5** — Scoring Model at 200 posts
