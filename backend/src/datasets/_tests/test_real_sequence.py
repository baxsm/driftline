"""Integration checks against a real sequence on disk.

Set `DRIFTLINE_TEST_SEQUENCE` to the folder holding `mav0` and `dso`. Skipped when unset so
the suite still runs on a machine without the dataset, but these are the assertions that
catch what fixtures cannot: real column layouts, real precision, and real rates.
"""

import os
from itertools import pairwise
from pathlib import Path

import pytest

from datasets.parsing import read_frame_timestamps, read_poses
from datasets.reader import read_sequence

SEQUENCE_ENV = "DRIFTLINE_TEST_SEQUENCE"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sequence_root() -> Path:
    raw = os.getenv(SEQUENCE_ENV)
    if not raw:
        pytest.skip(f"{SEQUENCE_ENV} is not set")
    root = Path(raw)
    if not root.is_dir():
        pytest.skip(f"{SEQUENCE_ENV} does not point at a directory: {root}")
    return root


def test_reports_ground_truth_present(sequence_root):
    info = read_sequence(sequence_root)
    assert info.has_ground_truth is True
    assert info.ground_truth_count > 1000


def test_frame_count_is_plausible(sequence_root):
    info = read_sequence(sequence_root)
    assert 500 < info.frame_count < 20000


def test_camera_and_imu_rates_are_plausible(sequence_root):
    info = read_sequence(sequence_root)
    assert info.duration_seconds > 10.0
    frame_rate = info.frame_count / info.duration_seconds
    assert 5.0 < frame_rate < 60.0
    if info.imu_sample_count:
        imu_rate = info.imu_sample_count / info.duration_seconds
        assert imu_rate > frame_rate


def test_ground_truth_is_denser_than_frames(sequence_root):
    info = read_sequence(sequence_root)
    assert info.ground_truth_count > info.frame_count


def test_real_timestamps_stay_integers_and_increase(sequence_root):
    timestamps = read_frame_timestamps(sequence_root / "mav0" / "cam0" / "data.csv")
    assert all(isinstance(value, int) for value in timestamps)
    assert all(later > earlier for earlier, later in pairwise(timestamps))
    assert len(str(timestamps[0])) == 19


def test_real_ground_truth_quaternions_are_unit_norm(sequence_root):
    poses = read_poses(sequence_root / "dso" / "gt_imu.csv")
    for pose in poses[:500]:
        norm = (pose.qw**2 + pose.qx**2 + pose.qy**2 + pose.qz**2) ** 0.5
        assert norm == pytest.approx(1.0, abs=1e-6)


def test_calibration_is_parsed_from_real_camchain(sequence_root):
    info = read_sequence(sequence_root)
    assert info.camera_model in {"pinhole-equi", "pinhole-radtan"}
    cameras = info.calibration["cameras"]
    assert cameras
    intrinsics = cameras[0]["intrinsics"]
    assert intrinsics["fx"] > 0.0
    assert intrinsics["cx"] > 0.0
