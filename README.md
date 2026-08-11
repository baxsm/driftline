# driftline

Estimate camera trajectories from video and IMU data, and measure the drift against ground truth.

Register a recorded sequence, run a visual-inertial estimator over it, and score the estimate
against hardware-measured ground truth. The trajectory viewer overlays the estimate on truth
and colours it by per-pose error, so a parameter change is judged by its effect on drift
rather than by eye.

## Requirements

- Python 3.13 or newer
- Node 20 or newer
- PostgreSQL 16 or newer

## Setup

Start the database:

```bash
docker compose up -d
```

Backend:

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
cp .env.example .env
.venv/Scripts/alembic upgrade head
.venv/Scripts/uvicorn main:app --app-dir src --reload
```

Frontend:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

The app runs at `http://localhost:3000` and the API at `http://localhost:8000`.

## Sequences

driftline reads sequences in the ASL folder layout, which TUM VI and EuRoC both use. Download
one, extract it into `data/`, and register the folder that contains `mav0`:

```
https://cdn3.vision.in.tum.de/tumvi/exported/euroc/512_16/dataset-room1_512_16.tar
```

The `room` sequences carry ground truth for the full trajectory, so estimates run against them
can be scored. Sequences are read in place and are never copied into the database.

## Tests

```bash
cd backend && .venv/Scripts/pytest
cd frontend && npm test && npm run e2e
```

Tests that need a real sequence read `data/dataset-room1_512_16`, and skip when it is not
there. Point them somewhere else with `DRIFTLINE_TEST_SEQUENCE` (backend) or
`E2E_SEQUENCE_PATH` (end to end).

Inertial runs need GTSAM, which publishes no Windows wheel, so they run in the container:

```bash
cd backend && docker build -t driftline-fusion .
```
