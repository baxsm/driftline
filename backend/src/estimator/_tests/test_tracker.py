import numpy as np

from estimator.config import EstimatorConfig
from estimator.motion import MotionUnrecoverable, estimate_motion
from estimator.tracker import TrackerState, advance, detect, track_forward

from .synthetic import straight_line_sequence


def _config() -> EstimatorConfig:
    return EstimatorConfig()


def test_detects_corners_on_a_textured_frame():
    sequence = straight_line_sequence(frames=2)
    assert len(detect(sequence.images[0], 300, 0.01, 12.0)) > 50


def test_detects_nothing_on_a_flat_frame():
    flat = np.full((240, 320), 100, dtype=np.uint8)
    assert len(detect(flat, 300, 0.01, 12.0)) == 0


def test_forward_backward_check_drops_mistracks():
    """Tracking into an unrelated frame must not report confident matches."""
    sequence = straight_line_sequence(frames=2)
    points = detect(sequence.images[0], 200, 0.01, 12.0)
    noise = np.random.default_rng(3).integers(0, 255, sequence.images[0].shape, dtype=np.uint8)
    _, good = track_forward(sequence.images[0], noise, points)
    assert int(good.sum()) < len(points) * 0.5


def test_first_frame_detects_and_assigns_ids_from_zero():
    sequence = straight_line_sequence(frames=2)
    state, previous, current = advance(
        TrackerState(), None, sequence.images[0], 300, 0.01, 12.0, 120
    )
    assert len(state.points) > 50
    assert state.track_ids[0] == 0
    assert all(age == 0 for age in state.ages)
    # nothing has been seen twice yet, so there are no pairs to solve a pose from
    assert len(previous) == 0 and len(current) == 0


def test_surviving_tracks_keep_their_id_and_age():
    sequence = straight_line_sequence(frames=3)
    state, _, _ = advance(TrackerState(), None, sequence.images[0], 300, 0.01, 12.0, 120)
    first_ids = set(state.track_ids)

    state, previous, current = advance(
        state, sequence.images[0], sequence.images[1], 300, 0.01, 12.0, 120
    )
    survivors = [tid for tid, age in zip(state.track_ids, state.ages, strict=True) if age > 0]
    assert survivors, "no track survived a single frame"
    assert set(survivors).issubset(first_ids)
    assert len(previous) == len(current) == len(survivors)


def test_a_redetected_feature_gets_a_new_id_not_the_old_one():
    """A track lost across a gap must not be reported as having survived it."""
    sequence = straight_line_sequence(frames=3)
    state, _, _ = advance(TrackerState(), None, sequence.images[0], 300, 0.01, 12.0, 120)
    highest_first_pass = max(state.track_ids)

    # tracking into pure noise loses every track, forcing a full redetection
    noise = np.random.default_rng(5).integers(0, 255, sequence.images[0].shape, dtype=np.uint8)
    state, _, _ = advance(state, sequence.images[0], noise, 300, 0.01, 12.0, 120)

    assert all(tid > highest_first_pass for tid in state.track_ids)


def test_redetection_tops_up_below_the_floor():
    sequence = straight_line_sequence(frames=2)
    sparse = TrackerState(
        points=np.array([[100.0, 100.0]], dtype=np.float32),
        track_ids=[0],
        ages=[4],
        next_track_id=1,
    )
    state, _, _ = advance(
        sparse, sequence.images[0], sequence.images[1], 300, 0.01, 12.0, redetect_below=120
    )
    assert len(state.points) > 1


def test_ransac_rejects_injected_outliers():
    """Half the correspondences are garbage; the pose must still come from the good half."""
    sequence = straight_line_sequence(frames=2)
    points = detect(sequence.images[0], 200, 0.01, 12.0)
    tracked, good = track_forward(sequence.images[0], sequence.images[1], points)
    clean_previous = points[good].astype(np.float64)
    clean_current = tracked[good].astype(np.float64)

    rng = np.random.default_rng(9)
    outlier_count = len(clean_previous) // 2
    corrupted = clean_current.copy()
    corrupted[:outlier_count] += rng.uniform(-60, 60, (outlier_count, 2))

    estimate = estimate_motion(clean_previous, corrupted, sequence.camera_matrix, 1.0)
    assert estimate.inlier_count >= outlier_count * 0.6
    # the true motion is +x, and it must survive half the points being wrong
    assert estimate.motion.translation[0] > 0.8


def test_too_few_correspondences_raises_with_a_reason():
    try:
        estimate_motion(
            np.zeros((4, 2)), np.zeros((4, 2)), straight_line_sequence(frames=2).camera_matrix, 1.0
        )
    except MotionUnrecoverable as exc:
        assert "need" in exc.reason
    else:
        raise AssertionError("expected MotionUnrecoverable")


def test_config_defaults_are_in_range():
    config = _config()
    assert 50 <= config.max_features <= 2000
    assert config.redetect_below <= config.max_features
