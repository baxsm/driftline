"""Hamilton quaternion helpers.

Every quaternion in this project is Hamilton convention, ordered (w, x, y, z), matching
GTSAM and the dataset ground truth files. Any component that speaks JPL must convert at its
own boundary. `scipy` stores quaternions as (x, y, z, w), so the ordering is swapped at the
edge of this module and nowhere else.
"""

import numpy as np
from numpy.typing import NDArray
from scipy.spatial.transform import Rotation

Array = NDArray[np.float64]


class QuaternionError(ValueError):
    pass


def normalize(quaternion: Array) -> Array:
    """Return the unit quaternion. Raises when the input is too close to zero to normalize."""
    q = np.asarray(quaternion, dtype=np.float64)
    if q.shape[-1] != 4:
        raise QuaternionError(f"quaternion must have 4 components, got shape {q.shape}")
    norm = np.linalg.norm(q, axis=-1, keepdims=True)
    if np.any(norm < 1e-12):
        raise QuaternionError("cannot normalize a zero length quaternion")
    return np.asarray(q / norm, dtype=np.float64)


def to_matrix(quaternion: Array) -> Array:
    """Hamilton (w, x, y, z) to a 3x3 rotation matrix."""
    return np.asarray(
        Rotation.from_quat(normalize(quaternion), scalar_first=True).as_matrix(),
        dtype=np.float64,
    )


def from_matrix(matrix: Array) -> Array:
    """3x3 rotation matrix to Hamilton (w, x, y, z), canonical sign (w >= 0)."""
    m = np.asarray(matrix, dtype=np.float64)
    if m.shape != (3, 3):
        raise QuaternionError(f"rotation matrix must be 3x3, got shape {m.shape}")
    return canonical(np.asarray(Rotation.from_matrix(m).as_quat(scalar_first=True)))


def canonical(quaternion: Array) -> Array:
    """Pick one of the two representations of a rotation.

    q and -q are the same rotation, so comparing raw components without fixing the sign
    produces false mismatches. Normally the sign is chosen so w >= 0, but a 180 degree
    rotation has w == 0 and that rule cannot decide between q and -q. In that case the
    first component that is not zero picks the sign instead.
    """
    q = normalize(quaternion)
    for component in q:
        if abs(component) > 1e-12:
            return np.asarray(-q if component < 0.0 else q, dtype=np.float64)
    return np.asarray(q, dtype=np.float64)


def geodesic_angle(left: Array, right: Array) -> float:
    """Angle in radians on SO(3) between two rotations.

    Uses the quaternion inner product rather than differencing Euler angles, which is
    unstable near gimbal singularities.
    """
    a = normalize(left)
    b = normalize(right)
    dot = float(np.clip(abs(np.dot(a, b)), -1.0, 1.0))
    return float(2.0 * np.arccos(dot))
