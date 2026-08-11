"""
Stages the profile the README screenshots are taken from.

Registers the real TUM VI room1 sequence and runs the estimator over all 2,821 frames, so
every figure in the README comes from a real sequence rather than a synthetic one.

The visual runs happen wherever this is pointed. The inertial run needs gtsam, which
publishes no Windows wheel, so on Windows it has to be executed by the container built from
backend/Dockerfile. Only one worker may poll at a time: two of them race for the same queued
row, and the native one fails any inertial run it wins.

    # native backend running, worker enabled
    python scripts/stage-readme-demo.py

    # then, for the inertial run, with the native backend stopped
    docker run -d --name driftline-fusion-demo \
      --add-host=host.docker.internal:host-gateway -p 8000:8000 \
      -v "<absolute path to data>:/data" \
      -e DATABASE_URL="postgresql+psycopg://driftline:driftline@host.docker.internal:5435/driftline" \
      -e SESSION_SECRET="<32 chars or more>" -e CORS_ORIGINS="<frontend origin>" \
      -e STORAGE_DIR="/app/storage" driftline-fusion
    python scripts/stage-readme-demo.py --inertial --sequence /data/dataset-room1_512_16

A run registered from the container records the path it saw, so the two passes register the
sequence under different paths. Point the second pass at the first one's dataset with
--dataset-id, or repoint its run afterwards, so the profile holds one sequence and not two.
"""

import argparse
import sys
import time
from pathlib import Path

import httpx

API = "http://localhost:8000/api"
EMAIL = "demo@driftline.dev"
PASSWORD = "driftline-demo-2026"
NAME = "TUM VI room1"

VISUAL_RUNS = [
    ("baseline, 600 features", {"mode": "mono", "max_features": 600}),
    (
        "1200 features, tighter keyframes",
        {
            "mode": "mono",
            "max_features": 1200,
            "keyframe_parallax_px": 6.0,
            "redetect_below": 500,
        },
    ),
]
INERTIAL_RUN = ("visual inertial, metric scale", {"mode": "mono_inertial", "max_features": 600})

session = httpx.Client(timeout=60.0, follow_redirects=True)


def sign_in() -> None:
    created = session.post(f"{API}/auth/register", json={"email": EMAIL, "password": PASSWORD})
    if created.status_code == 409:
        session.post(
            f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD}
        ).raise_for_status()
    else:
        created.raise_for_status()
    print(f"signed in as {EMAIL}")


def register(path: str) -> str:
    registered = session.post(f"{API}/datasets/register", json={"path": path, "name": NAME})
    if registered.status_code == 409:
        for dataset in session.get(f"{API}/datasets").json()["datasets"]:
            if dataset["name"] == NAME:
                return dataset["id"]
    registered.raise_for_status()
    body = registered.json()
    print(
        f"{body['name']}: {body['frame_count']} frames, "
        f"ground truth {'yes' if body['has_ground_truth'] else 'no'}"
    )
    return body["id"]


def run(dataset_id: str, label: str, config: dict) -> None:
    queued = session.post(
        f"{API}/runs", json={"dataset_id": dataset_id, "config": config, "label": label}
    )
    queued.raise_for_status()
    run_id = queued.json()["id"]

    started = time.monotonic()
    while time.monotonic() - started < 1800:
        current = session.get(f"{API}/runs/{run_id}").json()
        if current["status"] in ("done", "failed"):
            break
        print(
            f"  {label}: {current.get('processed_frames') or 0}"
            f"/{current.get('total_frames') or 0}",
            end="\r",
        )
        time.sleep(2)
    else:
        raise TimeoutError(f"{label} did not finish")

    if current["status"] == "failed":
        print(f"  {label}: failed, {current.get('failure_reason')}")
        return

    scored = session.get(f"{API}/runs/{run_id}/metrics").json()
    metrics = scored.get("metrics")
    if not metrics:
        print(f"  {label}: done, not scored")
        return
    print(
        f"  {label}: done, ATE {metrics['ate_rmse'] * 100:.1f} cm "
        f"({metrics.get('alignment')})"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sequence",
        default=str(Path(__file__).resolve().parent.parent / "data" / "dataset-room1_512_16"),
        help="the sequence folder, as the runtime executing the run will see it",
    )
    parser.add_argument(
        "--inertial",
        action="store_true",
        help="queue the visual inertial run instead of the visual ones",
    )
    parser.add_argument("--dataset-id", help="use an already registered sequence")
    args = parser.parse_args()

    sign_in()
    dataset_id = args.dataset_id or register(args.sequence)

    if args.inertial:
        label, config = INERTIAL_RUN
        run(dataset_id, label, config)
    else:
        for label, config in VISUAL_RUNS:
            run(dataset_id, label, config)

    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
