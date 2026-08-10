"""The camera is built from whatever the dataset reader stored, so these go through the real
parser rather than a hand written dict. A shape mismatch between the two is invisible until a
run fails, and it fails on every frame at once.
"""

from pathlib import Path

import numpy as np
import pytest
import yaml

from datasets.calibration import parse_camchain
from estimator.camera import CalibrationMissing, camera_from_calibration

TUM_VI_CAMCHAIN = {
    "cam0": {
        "camera_model": "pinhole",
        "intrinsics": [190.978, 190.973, 254.932, 256.897],
        "distortion_model": "equidistant",
        "distortion_coeffs": [0.00348, 0.000715, -0.00205, 0.000202],
        "resolution": [512, 512],
    }
}


def _camera_from_yaml(tmp_path: Path, raw: dict) -> dict:
    path = tmp_path / "camchain.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return parse_camchain(path)


def test_builds_from_what_the_reader_actually_stores(tmp_path: Path):
    camera = camera_from_calibration(_camera_from_yaml(tmp_path, TUM_VI_CAMCHAIN))
    assert camera.width == 512
    assert camera.height == 512
    assert camera.matrix[0][0] == pytest.approx(190.978)
    assert camera.matrix[1][2] == pytest.approx(256.897)
    assert camera.is_equidistant


def test_radtan_is_not_treated_as_fisheye(tmp_path: Path):
    raw = {"cam0": dict(TUM_VI_CAMCHAIN["cam0"], distortion_model="radtan")}
    assert not camera_from_calibration(_camera_from_yaml(tmp_path, raw)).is_equidistant


def test_missing_calibration_raises_rather_than_guessing():
    with pytest.raises(CalibrationMissing):
        camera_from_calibration({})


def test_undistort_moves_points_under_a_fisheye_model(tmp_path: Path):
    """A real equidistant model must actually change the pixels it is given."""
    camera = camera_from_calibration(_camera_from_yaml(tmp_path, TUM_VI_CAMCHAIN))
    edge = np.array([[20.0, 20.0]], dtype=np.float32)
    moved = camera.undistort(edge)
    assert float(np.linalg.norm(moved - edge)) > 1.0


def test_undistort_is_a_no_op_without_distortion(tmp_path: Path):
    raw = {
        "cam0": dict(
            TUM_VI_CAMCHAIN["cam0"],
            distortion_model="none",
            distortion_coeffs=[0.0, 0.0, 0.0, 0.0],
        )
    }
    camera = camera_from_calibration(_camera_from_yaml(tmp_path, raw))
    points = np.array([[100.0, 120.0], [300.0, 260.0]], dtype=np.float32)
    assert np.allclose(camera.undistort(points), points, atol=1e-6)


def test_empty_input_returns_empty(tmp_path: Path):
    camera = camera_from_calibration(_camera_from_yaml(tmp_path, TUM_VI_CAMCHAIN))
    assert len(camera.undistort(np.empty((0, 2), dtype=np.float32))) == 0
