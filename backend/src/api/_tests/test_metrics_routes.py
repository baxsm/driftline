"""Metrics routes, driven through a real run that the worker scores.

These go through the queue, the worker, the estimator and the scorer, so they cover the
wiring the metrics unit tests deliberately leave out: that a run is scored when it finishes,
that the numbers reaching the API are the ones the scorer produced, and that a sequence with
no ground truth says so instead of reporting zeros.
"""

import pytest

from api.services import worker

# `registered_dataset` and `scorable_dataset` come from conftest.py


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    from config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _finished_run(client, session, dataset_id: str) -> dict:
    created = client.post("/api/runs", json={"dataset_id": dataset_id}).json()
    assert worker.process_one(session) is True
    run = client.get(f"/api/runs/{created['id']}").json()
    assert run["status"] == "done", run["failure_reason"]
    return run


def test_a_finished_run_is_scored(client, session, scorable_dataset, storage):
    run = _finished_run(client, session, scorable_dataset)

    body = client.get(f"/api/runs/{run['id']}/metrics").json()
    metrics = body["metrics"]

    assert body["has_ground_truth"] is True
    assert metrics is not None
    # a monocular run has no scale of its own, so it must have been Sim(3) aligned
    assert metrics["alignment"] == "sim3"
    assert metrics["aligned_pose_count"] == 24
    assert metrics["candidate_pose_count"] == 24
    assert metrics["ate_rmse"] > 0.0
    assert metrics["scale_error"] is not None


def test_metrics_are_absent_rather_than_zero_without_ground_truth(
    client, session, registered_dataset, storage
):
    """The honest shape for an unscored run. Zeros would read as a perfect estimate."""
    run = _finished_run(client, session, registered_dataset)

    body = client.get(f"/api/runs/{run['id']}/metrics").json()

    assert body["has_ground_truth"] is False
    assert body["metrics"] is None


def test_pose_errors_are_one_per_matched_pose(client, session, scorable_dataset, storage):
    run = _finished_run(client, session, scorable_dataset)

    body = client.get(f"/api/runs/{run['id']}/errors").json()

    assert body["total"] == 24
    assert len(body["errors"]) == 24
    # a 19 digit timestamp does not survive JSON.parse as a number
    assert body["errors"][0]["timestamp_ns"] == "1520530308199447626"
    assert all(error["trans_error"] >= 0.0 for error in body["errors"])


def test_pose_errors_can_be_decimated(client, session, scorable_dataset, storage):
    run = _finished_run(client, session, scorable_dataset)

    body = client.get(f"/api/runs/{run['id']}/errors?stride=4").json()

    assert body["total"] == 24
    assert len(body["errors"]) == 6
    assert body["stride"] == 4


def test_aligned_trajectory_lands_on_the_truth_frame(
    client, session, scorable_dataset, storage
):
    """Unaligned poses are in the estimator's own frame, aligned ones are in truth's.

    The truth path here runs along +x from the origin, so an aligned estimate has to as
    well. An unaligned monocular estimate is in an arbitrary frame at an arbitrary scale, so
    the two must not agree, and a route that returned the same poses either way would look
    like it worked.
    """
    run = _finished_run(client, session, scorable_dataset)

    raw = client.get(f"/api/runs/{run['id']}/trajectory").json()
    aligned = client.get(f"/api/runs/{run['id']}/trajectory?aligned=true").json()

    assert raw["aligned"] is False
    assert raw["scale_is_arbitrary"] is True
    assert aligned["aligned"] is True
    assert aligned["alignment"] == "sim3"
    # aligned onto truth, the scale is truth's, so it is no longer arbitrary
    assert aligned["scale_is_arbitrary"] is False

    travelled = aligned["poses"][-1]["tx"] - aligned["poses"][0]["tx"]
    assert travelled == pytest.approx(23 * 0.25, rel=0.15)
    assert raw["poses"][-1]["tx"] != pytest.approx(aligned["poses"][-1]["tx"], rel=1e-6)


def test_aligned_is_ignored_when_a_run_was_never_scored(
    client, session, registered_dataset, storage
):
    """Asking for alignment on an unscored run returns the raw poses, flagged as unaligned."""
    run = _finished_run(client, session, registered_dataset)

    body = client.get(f"/api/runs/{run['id']}/trajectory?aligned=true").json()

    assert body["aligned"] is False
    assert body["poses"]


def test_export_writes_a_tum_file_evo_can_read(client, session, scorable_dataset, storage):
    run = _finished_run(client, session, scorable_dataset)

    estimate = client.get(f"/api/runs/{run['id']}/export")
    truth = client.get(f"/api/runs/{run['id']}/export?kind=truth")

    assert estimate.status_code == 200
    # served as an opaque stream so a download manager cannot intercept it and return empty
    assert estimate.headers["content-type"] == "application/octet-stream"

    rows = [line for line in estimate.text.splitlines() if not line.startswith("#")]
    assert len(rows) == 24
    assert len(rows[0].split()) == 8

    truth_rows = [line for line in truth.text.splitlines() if not line.startswith("#")]
    assert len(truth_rows) > len(rows)


def test_export_rejects_truth_when_the_sequence_has_none(
    client, session, registered_dataset, storage
):
    run = _finished_run(client, session, registered_dataset)

    response = client.get(f"/api/runs/{run['id']}/export?kind=truth")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "no_ground_truth"


def test_export_rejects_an_unknown_kind(client, session, scorable_dataset, storage):
    run = _finished_run(client, session, scorable_dataset)
    assert client.get(f"/api/runs/{run['id']}/export?kind=whatever").status_code == 422


def test_deleting_a_run_removes_its_metrics(client, session, scorable_dataset, storage):
    run = _finished_run(client, session, scorable_dataset)
    assert client.get(f"/api/runs/{run['id']}/metrics").json()["metrics"]

    assert client.delete(f"/api/runs/{run['id']}").status_code == 204
    assert client.get(f"/api/runs/{run['id']}/metrics").status_code == 404


def test_metrics_require_a_session(client, session, scorable_dataset, storage):
    run = _finished_run(client, session, scorable_dataset)
    client.post("/api/auth/logout")
    assert client.get(f"/api/runs/{run['id']}/metrics").status_code == 401
    assert client.get(f"/api/runs/{run['id']}/errors").status_code == 401


def test_the_log_records_that_the_run_was_scored(client, session, scorable_dataset, storage):
    """The log is the failure inspector's record, so scoring has to leave a trace in it."""
    run = _finished_run(client, session, scorable_dataset)

    log = client.get(f"/api/runs/{run['id']}/log").text

    assert "sim3 aligned" in log
    assert "poses matched" in log
