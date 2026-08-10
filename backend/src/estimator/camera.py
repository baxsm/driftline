"""Camera intrinsics and the undistortion the pose solve needs.

The essential matrix is only defined for a pinhole projection, so distorted pixels have to be
undistorted before they reach it. TUM VI ships an equidistant (fisheye) model with a wide
field of view, where treating the pixels as pinhole is not a small error: it bends straight
lines near the edge of the frame into curves and biases the recovered rotation.

`cv2.undistortPoints` and `cv2.fisheye.undistortPoints` implement different models and are
not interchangeable, so the distortion model recorded by the reader picks which one runs.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]

EQUIDISTANT_MODELS = frozenset({"equidistant", "fisheye", "kannala_brandt"})
RADTAN_MODELS = frozenset({"radtan", "plumb_bob", "radial-tangential"})


class CalibrationMissing(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Camera:
    width: int
    height: int
    matrix: Array
    distortion: Array
    distortion_model: str
    #: 4x4 transform carrying a point from the IMU body frame into this camera's frame, as
    #: kalibr's `T_cam_imu`. None when the sequence did not ship one.
    body_to_camera: Array | None = None

    @property
    def is_equidistant(self) -> bool:
        return self.distortion_model in EQUIDISTANT_MODELS

    def undistort(self, points: NDArray[np.float32]) -> Array:
        """Distorted pixels to normalized image coordinates, then back to ideal pixels.

        Reprojecting through the same intrinsic matrix keeps the RANSAC threshold in pixels,
        which is the unit the config exposes and the only one a user can reason about.
        """
        if len(points) == 0:
            return np.empty((0, 2), dtype=np.float64)
        source = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
        if self.is_equidistant:
            undistorted = cv2.fisheye.undistortPoints(
                source, self.matrix, self.distortion[:4].reshape(4, 1), P=self.matrix
            )
        else:
            undistorted = cv2.undistortPoints(
                source, self.matrix, self.distortion, P=self.matrix
            )
        return np.asarray(undistorted, dtype=np.float64).reshape(-1, 2)


def camera_from_calibration(calibration: dict[str, object], index: int = 0) -> Camera:
    """Build a camera from the reader's parsed camchain.

    Raises rather than falling back to a guessed focal length. A wrong intrinsic matrix does
    not fail loudly, it just returns a trajectory that is quietly the wrong shape.
    """
    cameras = calibration.get("cameras")
    if not isinstance(cameras, list) or len(cameras) <= index:
        raise CalibrationMissing(
            "the sequence has no camera calibration, so poses cannot be scaled"
        )

    camera = cameras[index]
    if not isinstance(camera, dict):
        raise CalibrationMissing("camera calibration is not in the expected shape")

    # the reader stores intrinsics and resolution as named mappings rather than the bare
    # lists kalibr writes, so they are read by name here
    intrinsics = camera.get("intrinsics")
    if not isinstance(intrinsics, dict) or not {"fx", "fy", "cx", "cy"} <= intrinsics.keys():
        raise CalibrationMissing("camera calibration is missing fx, fy, cx, cy")

    fx, fy, cx, cy = (float(intrinsics[key]) for key in ("fx", "fy", "cx", "cy"))
    matrix = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64)

    raw_distortion = camera.get("distortion_coeffs") or []
    distortion = np.asarray(
        [float(v) for v in raw_distortion] if isinstance(raw_distortion, list) else [],
        dtype=np.float64,
    )
    if distortion.size < 4:
        distortion = np.pad(distortion, (0, 4 - distortion.size))

    resolution = camera.get("resolution")
    width, height = (
        (int(resolution.get("width", 0)), int(resolution.get("height", 0)))
        if isinstance(resolution, dict)
        else (0, 0)
    )

    return Camera(
        width=width,
        height=height,
        matrix=matrix,
        distortion=distortion,
        distortion_model=str(camera.get("distortion_model") or "none"),
        body_to_camera=_body_to_camera(camera.get("t_cam_imu")),
    )


def _body_to_camera(raw: object) -> Array | None:
    """Parse kalibr's `T_cam_imu` into a 4x4, or None when the sequence has no extrinsic.

    This matters for scoring rather than for estimation. Ground truth is recorded in the IMU
    body frame, the estimate comes out in the camera frame, and the two are about 179 degrees
    apart on TUM VI. Comparing them without this transform reports that rotation as estimator
    error, which is how a working estimator can be made to look badly broken.
    """
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    try:
        matrix = np.array([[float(value) for value in row] for row in raw], dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if matrix.shape != (4, 4):
        return None
    return matrix
