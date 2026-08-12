"""Run routes, including a full queue-to-done execution through the worker.

The worker is driven directly rather than left to poll, so a test asserts on a finished run
instead of waiting on a thread. The estimator work itself is real: the sequence on disk is
rendered from a known camera path, so a run that completes proves the whole chain from the
route through the pipeline to the artifacts on disk.
"""

from api.services import worker

# `sequence_on_disk`, `registered_dataset`, `scorable_sequence` and `scorable_dataset` come
# from conftest.py, so the metrics route tests can use the same ones without importing them


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


def test_an_unexpected_crash_names_what_went_wrong(
    client, session, registered_dataset, monkeypatch
):
    """A crash the estimator did not anticipate must still say what happened.

    This is not hypothetical. A missing parquet engine in the fusion image crashed a run after
    the estimate had already been computed, and the panel said only "the estimator stopped
    unexpectedly", which sends the reader to the container logs to learn that the trajectory
    was fine and only writing it out had failed.
    """

    def explode(*args, **kwargs):
        raise ImportError("Unable to find a usable engine; tried using: 'pyarrow'")

    monkeypatch.setattr(worker, "write_tracks", explode)

    created = client.post("/api/runs", json={"dataset_id": registered_dataset}).json()
    assert worker.process_one(session) is True

    run = client.get(f"/api/runs/{created['id']}").json()
    assert run["status"] == "failed"
    assert "ImportError" in run["failure_reason"]
    assert "pyarrow" in run["failure_reason"]


def test_a_crash_reason_stays_short_enough_to_read(
    client, session, registered_dataset, monkeypatch
):
    def explode(*args, **kwargs):
        raise RuntimeError("x" * 5000)

    monkeypatch.setattr(worker, "write_tracks", explode)

    created = client.post("/api/runs", json={"dataset_id": registered_dataset}).json()
    assert worker.process_one(session) is True

    reason = client.get(f"/api/runs/{created['id']}").json()["failure_reason"]
    assert len(reason) < 400
    assert reason.endswith("...")


def test_list_carries_ate_so_the_list_can_rank_runs(
    client, session, scorable_dataset, tmp_path, monkeypatch
):
    """The list shows and sorts on ATE, so the summary has to carry it and its alignment."""
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    from config import get_settings

    get_settings.cache_clear()

    client.post("/api/runs", json={"dataset_id": scorable_dataset})
    assert worker.process_one(session) is True

    row = client.get(f"/api/runs?dataset_id={scorable_dataset}").json()["runs"][0]

    assert row["ate_rmse"] > 0.0
    # a bare ATE is not comparable to another ATE without knowing how each was aligned
    assert row["alignment"] == "sim3"

    get_settings.cache_clear()


def test_an_unscored_run_reports_a_null_ate_rather_than_zero(client, registered_dataset):
    """Zero would sort to the top as the best run in the list."""
    client.post("/api/runs", json={"dataset_id": registered_dataset})

    row = client.get(f"/api/runs?dataset_id={registered_dataset}").json()["runs"][0]

    assert row["ate_rmse"] is None
    assert row["alignment"] is None


def test_sorting_by_ate_puts_the_best_run_first(
    client, session, scorable_dataset, tmp_path, monkeypatch
):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    from config import get_settings

    get_settings.cache_clear()

    for features in (600, 400, 300):
        client.post(
            "/api/runs",
            json={"dataset_id": scorable_dataset, "config": {"max_features": features}},
        )
        assert worker.process_one(session) is True

    rows = client.get(f"/api/runs?dataset_id={scorable_dataset}&sort=ate").json()["runs"]
    scores = [row["ate_rmse"] for row in rows]

    assert len(scores) == 3
    assert scores == sorted(scores)

    get_settings.cache_clear()


def test_an_unscored_run_sorts_last_rather_than_disappearing(
    client, session, scorable_dataset, registered_dataset, tmp_path, monkeypatch
):
    """A run that was never scored is a state worth seeing, so it sorts last, not away."""
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    from config import get_settings

    get_settings.cache_clear()

    client.post("/api/runs", json={"dataset_id": scorable_dataset})
    assert worker.process_one(session) is True
    client.post("/api/runs", json={"dataset_id": registered_dataset})
    assert worker.process_one(session) is True

    rows = client.get("/api/runs?sort=ate").json()["runs"]

    assert len(rows) == 2
    assert rows[0]["ate_rmse"] is not None
    assert rows[1]["ate_rmse"] is None

    get_settings.cache_clear()


def test_list_filters_by_status(client, registered_dataset):
    client.post("/api/runs", json={"dataset_id": registered_dataset, "label": "waiting"})

    assert client.get("/api/runs?status=queued").json()["total"] == 1
    assert client.get("/api/runs?status=done").json()["total"] == 0


def test_an_unknown_sort_is_rejected_rather_than_silently_ignored(client, registered_dataset):
    """Falling back to the default would return a list that looks sorted and is not."""
    assert client.get("/api/runs?sort=whatever").status_code == 422
