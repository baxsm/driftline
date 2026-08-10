"""Run routes, including a full queue-to-done execution through the worker.

The worker is driven directly rather than left to poll, so a test asserts on a finished run
instead of waiting on a thread. The estimator work itself is real: the sequence on disk is
rendered from a known camera path, so a run that completes proves the whole chain from the
route through the pipeline to the artifacts on disk.
"""

from pathlib import Path

import cv2
import pytest
import yaml

from api.services import worker
from estimator._tests.synthetic import straight_line_sequence

# matches the intrinsics the synthetic renderer projects with, so a recovered path can be
# compared against the path that generated it
CAMCHAIN = {
    "cam0": {
        "camera_model": "pinhole",
        "intrinsics": [400.0, 400.0, 320.0, 240.0],
        "distortion_model": "none",
        "distortion_coeffs": [0.0, 0.0, 0.0, 0.0],
        "resolution": [640, 480],
    }
}


@pytest.fixture
def sequence_on_disk(tmp_path: Path) -> Path:
    """Write a synthetic sequence in the ASL layout the reader expects."""
    rendered = straight_line_sequence(frames=10)
    data_dir = tmp_path / "mav0" / "cam0" / "data"
    data_dir.mkdir(parents=True)

    rows = ["#timestamp [ns],filename"]
    for index, image in enumerate(rendered.images):
        timestamp = 1520530308199447626 + index * 50_000_000
        cv2.imwrite(str(data_dir / f"{timestamp}.png"), image)
        rows.append(f"{timestamp},{timestamp}.png")
    (tmp_path / "mav0" / "cam0" / "data.csv").write_text("\n".join(rows), encoding="utf-8")

    imu_dir = tmp_path / "mav0" / "imu0"
    imu_dir.mkdir(parents=True)
    (imu_dir / "data.csv").write_text(
        "#timestamp,wx,wy,wz,ax,ay,az\n1520530308199447626,0,0,0,0,0,9.81\n",
        encoding="utf-8",
    )
    (tmp_path / "camchain.yaml").write_text(yaml.safe_dump(CAMCHAIN), encoding="utf-8")
    return tmp_path


@pytest.fixture
def registered_dataset(client, signed_in, sequence_on_disk) -> str:
    response = client.post("/api/datasets/register", json={"path": str(sequence_on_disk)})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_queue_returns_immediately_with_a_queued_run(client, registered_dataset):
    response = client.post("/api/runs", json={"dataset_id": registered_dataset})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"
    assert body["config_hash"]
    assert body["total_frames"] == 10


def test_queue_rejects_an_unknown_config_key(client, registered_dataset):
    response = client.post(
        "/api/runs",
        json={"dataset_id": registered_dataset, "config": {"max_featurs": 400}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_queue_rejects_a_config_value_out_of_range(client, registered_dataset):
    response = client.post(
        "/api/runs",
        json={"dataset_id": registered_dataset, "config": {"max_features": 5}},
    )
    assert response.status_code == 422
    assert "max_features" in (response.json()["error"].get("field") or "")


def test_queue_rejects_an_unknown_dataset(client, signed_in):
    response = client.post(
        "/api/runs", json={"dataset_id": "6f1c1f9e-0000-4000-8000-000000000000"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "dataset_not_found"


def test_runs_require_a_session(client, registered_dataset):
    client.post("/api/auth/logout")
    assert client.get("/api/runs").status_code == 401


def test_full_run_completes_and_writes_every_artifact(
    client, session, registered_dataset, tmp_path, monkeypatch
):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    from config import get_settings

    get_settings.cache_clear()

    created = client.post(
        "/api/runs",
        json={"dataset_id": registered_dataset, "label": "baseline"},
    ).json()

    assert worker.process_one(session) is True

    run = client.get(f"/api/runs/{created['id']}").json()
    assert run["status"] == "done", run["failure_reason"]
    assert run["processed_frames"] == 10
    assert run["finished_at"]

    trajectory = client.get(f"/api/runs/{created['id']}/trajectory").json()
    assert trajectory["total"] == 10
    assert trajectory["scale_is_arbitrary"] is True
    # timestamps must survive as strings, because a 19 digit integer does not fit a float64
    assert trajectory["poses"][0]["timestamp_ns"] == "1520530308199447626"
    assert all(pose["tracked_features"] > 0 for pose in trajectory["poses"])

    tracks = client.get(f"/api/runs/{created['id']}/tracks?from=0&to=3").json()
    assert len(tracks["frames"]) == 4
    assert tracks["frames"][0]["features"]

    log = client.get(f"/api/runs/{created['id']}/log").text
    assert "done" in log

    get_settings.cache_clear()


def test_tracks_range_is_bounded(client, registered_dataset):
    created = client.post("/api/runs", json={"dataset_id": registered_dataset}).json()
    response = client.get(f"/api/runs/{created['id']}/tracks?from=0&to=500")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "range_too_large"


def test_a_run_over_a_deleted_sequence_fails_with_a_reason(
    client, session, registered_dataset, sequence_on_disk, tmp_path, monkeypatch
):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    from config import get_settings

    get_settings.cache_clear()

    created = client.post("/api/runs", json={"dataset_id": registered_dataset}).json()
    for image in (sequence_on_disk / "mav0" / "cam0" / "data").glob("*.png"):
        image.unlink()

    assert worker.process_one(session) is True

    run = client.get(f"/api/runs/{created['id']}").json()
    assert run["status"] == "failed"
    assert run["failure_reason"]

    get_settings.cache_clear()


def test_list_filters_by_dataset(client, registered_dataset):
    client.post("/api/runs", json={"dataset_id": registered_dataset, "label": "one"})
    body = client.get(f"/api/runs?dataset_id={registered_dataset}").json()
    assert body["total"] == 1
    assert body["runs"][0]["label"] == "one"
    assert body["runs"][0]["dataset_name"]


def test_delete_removes_the_run(client, registered_dataset):
    created = client.post("/api/runs", json={"dataset_id": registered_dataset}).json()
    assert client.delete(f"/api/runs/{created['id']}").status_code == 204
    assert client.get(f"/api/runs/{created['id']}").status_code == 404


def test_one_users_run_is_invisible_to_another(client, registered_dataset, account):
    created = client.post("/api/runs", json={"dataset_id": registered_dataset}).json()
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": f"other-{account['email']}", "password": "testpassword123"},
    )
    assert client.get(f"/api/runs/{created['id']}").status_code == 404
