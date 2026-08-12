"""Putting two runs next to each other.

Comparing runs is what turns parameter tuning into a decision rather than a guess, and the
whole value of it rests on the two sides being comparable. Two things get in the way, and both
are handled here rather than in the client.

The first is alignment. An ATE computed under Sim(3) has had its scale fitted to truth; one
computed under SE(3) has not. Subtracting one from the other produces a number that looks like
an improvement and measures nothing, so a delta is only offered when both sides were aligned
the same way.

The second is the time axis. Two runs over the same sequence can start at different frames, so
their nanosecond timestamps do not line up and their pose counts differ. Each series is sent as
seconds elapsed from its own first scored pose, which is the one axis both runs genuinely share.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from db.models import Dataset, Run

from ..errors import ApiError
from ..serializers import metrics_response
from . import metrics as metrics_service
from . import runs as service

# Every error series decimated to at most this many points. Two room runs are a few thousand
# poses each, which is far more than a plot a few hundred pixels wide can show, and the cost is
# paid on the wire and again on every redraw.
MAX_SERIES_POINTS = 600


def _config_diff(left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, Any]]:
    """The config keys that differ, and nothing else.

    Showing all of them buries the one field that changed among fifteen that did not, and the
    reason to open this screen is to find that field.
    """
    keys = sorted(set(left) | set(right))
    return [
        {"key": key, "a": left.get(key), "b": right.get(key)}
        for key in keys
        if left.get(key) != right.get(key)
    ]


# Metrics where a smaller number is a better run. Scale error is deliberately absent: it is a
# ratio around 1.0, so neither direction is an improvement and a signed delta would imply one.
LOWER_IS_BETTER = (
    "ate_rmse",
    "ate_mean",
    "ate_median",
    "ate_max",
    "ate_rot_rmse",
    "rpe_trans_rmse",
    "rpe_rot_rmse",
)


def _metric_deltas(
    left: dict[str, Any] | None, right: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Per metric deltas, stated only where subtracting the two sides is meaningful.

    A delta is withheld rather than guessed at in three cases: one side has no metrics at all,
    one side is missing that particular metric (RPE needs enough poses and is null below that),
    or the two were aligned differently. In each the row still renders with both values, and
    `delta` is null. Nulling the delta is the honest answer where a number would be a false one.
    """
    if not left or not right:
        return []

    comparable = left.get("alignment") == right.get("alignment")
    rows: list[dict[str, Any]] = []
    for key in LOWER_IS_BETTER:
        a, b = left.get(key), right.get(key)
        if a is None or b is None:
            rows.append({"key": key, "a": a, "b": b, "delta": None, "comparable": comparable})
            continue
        rows.append(
            {
                "key": key,
                "a": a,
                "b": b,
                "delta": (b - a) if comparable else None,
                "comparable": comparable,
            }
        )
    return rows


def _decimate(rows: list[Any], limit: int = MAX_SERIES_POINTS) -> list[Any]:
    if len(rows) <= limit:
        return rows
    stride = (len(rows) + limit - 1) // limit
    return rows[::stride]


def _error_series(session: Session, run_id: uuid.UUID) -> list[dict[str, Any]]:
    """One run's error series on an elapsed-seconds axis.

    Seconds from this run's own first scored pose, not wall clock and not the raw timestamp.
    Two runs starting at different frames of the same sequence have no common absolute origin,
    and plotting them against absolute nanoseconds would offset one against the other by the
    gap between their start frames rather than by anything either of them did.
    """
    rows, _ = metrics_service.pose_errors(session, run_id)
    if not rows:
        return []

    origin = rows[0].timestamp_ns
    return [
        {
            "t": (row.timestamp_ns - origin) / 1e9,
            "trans_error": row.trans_error,
            "rot_error": row.rot_error,
        }
        for row in _decimate(rows)
    ]


def _side(session: Session, run: Run) -> dict[str, Any]:
    """One run's half of the comparison."""
    dataset = session.get(Dataset, run.dataset_id)
    metrics = metrics_service.get_metrics(session, run.id)

    return {
        "id": str(run.id),
        "label": run.label,
        "dataset_id": str(run.dataset_id),
        "dataset_name": dataset.name if dataset else None,
        "config": run.config,
        "config_hash": run.config_hash,
        "status": run.status,
        "failure_reason": run.failure_reason,
        "failure_frame": run.failure_frame,
        "processed_frames": run.processed_frames,
        "total_frames": run.total_frames,
        "created_at": run.created_at.isoformat(),
        "metrics": metrics_response(metrics) if metrics else None,
        "errors": _error_series(session, run.id),
    }


def compare(
    session: Session, user_id: uuid.UUID, run_a: str, run_b: str
) -> dict[str, Any]:
    """Two runs, their config diff, their metric deltas, and both error series.

    Runs on different sequences are refused. Their trajectories would be drawn in one viewer
    and their ATEs subtracted, which reads as a comparison and is not one: the two estimates
    have no common truth to be measured against.
    """
    if run_a == run_b:
        raise ApiError("same_run", "Pick two different runs to compare.", "run_b")

    left = service.get_run(session, user_id, run_a)
    right = service.get_run(session, user_id, run_b)

    if left.dataset_id != right.dataset_id:
        raise ApiError(
            "different_datasets",
            "These runs are on different sequences, so their scores are not comparable.",
            "run_b",
        )

    a, b = _side(session, left), _side(session, right)
    return {
        "a": a,
        "b": b,
        "config_diff": _config_diff(left.config, right.config),
        "metric_deltas": _metric_deltas(a["metrics"], b["metrics"]),
        # both runs share a sequence, so one copy of the truth path serves the viewer
        "dataset_id": str(left.dataset_id),
    }
