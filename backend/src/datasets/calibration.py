"""Calibration parsing for kalibr `camchain.yaml` and TUM VI `imu_config.yaml`.

Shapes here were read off the real `dataset-room1_512_16` archive rather than reconstructed
from the format description. TUM VI ships `camera_model: pinhole` with
`distortion_model: equidistant`, which maps to the `pinhole-equi` camera model in the
schema. EuRoC ships `radtan`, which maps to `pinhole-radtan`.
"""

from pathlib import Path
from typing import Any

import yaml

from .errors import SequenceUnreadable

_DISTORTION_TO_CAMERA_MODEL = {
    "equidistant": "pinhole-equi",
    "equi": "pinhole-equi",
    "radtan": "pinhole-radtan",
    "plumb_bob": "pinhole-radtan",
    "none": "pinhole",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SequenceUnreadable(f"{path.name} is not valid yaml", str(path)) from exc
    if not isinstance(loaded, dict):
        raise SequenceUnreadable(f"{path.name} does not contain a yaml mapping", str(path))
    return loaded


def parse_camchain(path: Path) -> dict[str, Any]:
    """Parse a kalibr camchain into the calibration json stored on the dataset row."""
    raw = _load_yaml(path)
    cameras = []
    for key in sorted(k for k in raw if k.startswith("cam")):
        entry = raw[key]
        if not isinstance(entry, dict):
            continue
        intrinsics = entry.get("intrinsics")
        resolution = entry.get("resolution")
        if not intrinsics or not resolution:
            raise SequenceUnreadable(
                f"{path.name} camera {key} is missing intrinsics or resolution", str(path)
            )
        cameras.append(
            {
                "name": key,
                "camera_model": entry.get("camera_model", "pinhole"),
                "distortion_model": entry.get("distortion_model", "none"),
                "distortion_coeffs": [float(v) for v in entry.get("distortion_coeffs", [])],
                "intrinsics": {
                    "fx": float(intrinsics[0]),
                    "fy": float(intrinsics[1]),
                    "cx": float(intrinsics[2]),
                    "cy": float(intrinsics[3]),
                },
                "resolution": {"width": int(resolution[0]), "height": int(resolution[1])},
                "t_cam_imu": entry.get("T_cam_imu"),
                "t_cn_cnm1": entry.get("T_cn_cnm1"),
            }
        )

    if not cameras:
        raise SequenceUnreadable(f"{path.name} contains no camera entries", str(path))

    return {"cameras": cameras}


def camera_model_from_calibration(calibration: dict[str, Any]) -> str | None:
    """Map the first camera's distortion model onto the schema's camera_model values."""
    cameras = calibration.get("cameras") or []
    if not cameras:
        return None
    distortion = str(cameras[0].get("distortion_model", "")).lower()
    return _DISTORTION_TO_CAMERA_MODEL.get(distortion)


def parse_imu_config(path: Path) -> dict[str, float]:
    """Parse TUM VI `imu_config.yaml` noise parameters.

    These override the EuRoC defaults in the estimator config. The two differ by enough to
    matter: TUM VI ships an accelerometer random walk of 8.6e-4 against the EuRoC 3.0e-3.
    """
    raw = _load_yaml(path)
    fields = {
        "gyro_noise": "gyroscope_noise_density",
        "accel_noise": "accelerometer_noise_density",
        "gyro_bias_rw": "gyroscope_random_walk",
        "accel_bias_rw": "accelerometer_random_walk",
    }
    parsed = {name: float(raw[key]) for name, key in fields.items() if key in raw}
    if "update_rate" in raw:
        parsed["update_rate_hz"] = float(raw["update_rate"])
    return parsed
