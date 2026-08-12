"""Comparing two runs.

The unit tests cover the diff and delta rules on their own, because those are where a
comparison quietly becomes wrong: a delta between two differently aligned runs is a number
with no meaning, and a diff that shows every key hides the one that changed.

The integration tests drive two real runs through the worker and check that the deltas match
what each run was scored with individually, which is the claim the screen actually makes.
"""

import pytest

from api.services import worker
from api.services.compare import _config_diff, _metric_deltas

# `scorable_dataset` and `registered_dataset` come from conftest.py


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    from config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _finished_run(client, session, dataset_id: str, config: dict | None = None) -> dict:
    body: dict = {"dataset_id": dataset_id}
    if config:
        body["config"] = config
    created = client.post("/api/runs", json=body).json()
    assert worker.process_one(session) is True
    return client.get(f"/api/runs/{created['id']}").json()


def test_identical_configs_diff_to_nothing():
    config = {"mode": "mono", "max_features": 600}

    assert _config_diff(config, dict(config)) == []


def test_diff_returns_only_the_keys_that_differ():
    left = {"mode": "mono", "max_features": 600, "start_frame": 0}
    right = {"mode": "mono", "max_features": 900, "start_frame": 0}

    diff = _config_diff(left, right)

    assert diff == [{"key": "max_features", "a": 600, "b": 900}]


def test_a_key_present_on_one_side_only_is_a_difference():
    """A config that gained a field is a real difference, not a missing value to skip."""
    diff = _config_diff({"mode": "mono"}, {"mode": "mono", "enhance_contrast": True})

    assert diff == [{"key": "enhance_contrast", "a": None, "b": True}]


def test_deltas_are_withheld_when_the_alignments_differ():
    """Sim(3) fitted the scale to truth and SE(3) did not, so the difference measures nothing."""
    left = {"ate_rmse": 0.85, "rpe_trans_rmse": 0.67, "alignment": "sim3"}
    right = {"ate_rmse": 0.53, "rpe_trans_rmse": 0.34, "alignment": "se3"}

    rows = {row["key"]: row for row in _metric_deltas(left, right)}

    assert rows["ate_rmse"]["delta"] is None
    assert rows["ate_rmse"]["comparable"] is False
    # both values still render, so the reader sees the figures and why they were not subtracted
    assert rows["ate_rmse"]["a"] == 0.85
    assert rows["ate_rmse"]["b"] == 0.53


def test_deltas_are_signed_so_negative_is_an_improvement():
    left = {"ate_rmse": 0.85, "alignment": "sim3"}
    right = {"ate_rmse": 0.53, "alignment": "sim3"}

    rows = {row["key"]: row for row in _metric_deltas(left, right)}

    assert rows["ate_rmse"]["delta"] == pytest.approx(-0.32)
    assert rows["ate_rmse"]["comparable"] is True


def test_a_null_metric_on_one_side_gives_no_delta():
    """RPE is null below the pose count it needs, and null minus a number is not zero."""
    left = {"ate_rmse": 0.85, "rpe_trans_rmse": None, "alignment": "sim3"}
    right = {"ate_rmse": 0.53, "rpe_trans_rmse": 0.34, "alignment": "sim3"}

    rows = {row["key"]: row for row in _metric_deltas(left, right)}

    assert rows["rpe_trans_rmse"]["delta"] is None
    assert rows["rpe_trans_rmse"]["a"] is None
    assert rows["rpe_trans_rmse"]["b"] == 0.34
    assert rows["ate_rmse"]["delta"] == pytest.approx(-0.32)


def test_an_unscored_side_produces_no_delta_rows():
    assert _metric_deltas(None, {"ate_rmse": 0.5, "alignment": "sim3"}) == []


def test_compare_deltas_match_the_individually_scored_runs(
    client, session, scorable_dataset, storage
):
    """The end to end claim: the delta column is the difference of the two metrics panels."""
    a = _finished_run(client, session, scorable_dataset)
    b = _finished_run(client, session, scorable_dataset, {"max_features": 400})

    metrics_a = client.get(f"/api/runs/{a['id']}/metrics").json()["metrics"]
    metrics_b = client.get(f"/api/runs/{b['id']}/metrics").json()["metrics"]

    body = client.get(f"/api/compare?run_a={a['id']}&run_b={b['id']}").json()

    assert body["a"]["metrics"]["ate_rmse"] == metrics_a["ate_rmse"]
    assert body["b"]["metrics"]["ate_rmse"] == metrics_b["ate_rmse"]

    rows = {row["key"]: row for row in body["metric_deltas"]}
    assert rows["ate_rmse"]["delta"] == pytest.approx(
        metrics_b["ate_rmse"] - metrics_a["ate_rmse"]
    )


def test_compare_reports_the_config_key_that_changed(
    client, session, scorable_dataset, storage
):
    a = _finished_run(client, session, scorable_dataset)
    b = _finished_run(client, session, scorable_dataset, {"max_features": 400})

    body = client.get(f"/api/compare?run_a={a['id']}&run_b={b['id']}").json()

    assert body["config_diff"] == [{"key": "max_features", "a": 600, "b": 400}]


def test_error_series_start_at_zero_seconds(client, session, scorable_dataset, storage):
    """Both runs are placed on their own elapsed axis, which is the axis they can share."""
    a = _finished_run(client, session, scorable_dataset)
    b = _finished_run(client, session, scorable_dataset, {"max_features": 400})

    body = client.get(f"/api/compare?run_a={a['id']}&run_b={b['id']}").json()

    assert body["a"]["errors"][0]["t"] == 0.0
    assert body["b"]["errors"][0]["t"] == 0.0
    assert body["a"]["errors"][-1]["t"] > 0.0


def test_comparing_a_run_with_itself_is_refused(client, session, scorable_dataset, storage):
    a = _finished_run(client, session, scorable_dataset)

    response = client.get(f"/api/compare?run_a={a['id']}&run_b={a['id']}")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "same_run"


def test_runs_on_different_sequences_are_refused(
    client, session, scorable_dataset, registered_dataset, storage
):
    """Two estimates with no common truth cannot be scored against each other."""
    a = _finished_run(client, session, scorable_dataset)
    b = _finished_run(client, session, registered_dataset)

    response = client.get(f"/api/compare?run_a={a['id']}&run_b={b['id']}")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "different_datasets"


def test_compare_needs_a_session(client, scorable_dataset, storage):
    client.post("/api/auth/logout")

    response = client.get("/api/compare?run_a=some-id&run_b=other-id")

    assert response.status_code == 401


def test_another_users_run_is_not_comparable(client, session, scorable_dataset, storage):
    """Ownership is checked on both ids, not only the first."""
    a = _finished_run(client, session, scorable_dataset)
    b = _finished_run(client, session, scorable_dataset, {"max_features": 400})

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "other-compare@driftline.dev", "password": "testpassword123"},
    )

    response = client.get(f"/api/compare?run_a={a['id']}&run_b={b['id']}")

    assert response.status_code == 404
