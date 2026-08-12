"""Trajectory builders shared by the metrics tests."""

import numpy as np
from numpy.typing import NDArray
from scipy.spatial.transform import Rotation

from metrics.scoring import Trajectory

Array = NDArray[np.float64]

FRAME_INTERVAL_NS = 50_000_000
# a plausible TUM VI start time, so the tests exercise the 19 digit values the real data has
EPOCH_NS = 1_520_530_000_000_000_000


def wandering_trajectory(seed: int = 1, count: int = 200) -> Trajectory:
    """A smooth random walk with orientation, standing in for a handheld camera path."""
    rng = np.random.default_rng(seed)
    positions = np.column_stack(
        [
            np.cumsum(rng.normal(0.05, 0.02, count)),
            np.cumsum(rng.normal(0.0, 0.02, count)),
            np.cumsum(rng.normal(0.01, 0.01, count)),
        ]
    )
    rotation_vectors = np.cumsum(rng.normal(0.0, 0.02, (count, 3)), axis=0)
    quaternions = Rotation.from_rotvec(rotation_vectors).as_quat(scalar_first=True)
    timestamps = (np.arange(count) * FRAME_INTERVAL_NS + EPOCH_NS).astype(np.int64)
    return Trajectory(timestamps, positions, np.asarray(quaternions, dtype=np.float64))


def transform_trajectory(
    trajectory: Trajectory,
    rotation: Array,
    translation: Array,
    scale: float = 1.0,
    noise: float = 0.0,
    seed: int = 99,
) -> Trajectory:
    """Apply the inverse of a known alignment, so scoring should recover it.

    The result is what an estimator would have produced if it were perfect apart from the
    arbitrary frame and scale: aligning it back onto the input returns the transform given
    here, and the ATE is whatever `noise` was injected.
    """
    positions = (rotation.T @ (trajectory.positions - translation).T).T / scale
    rotations = np.einsum("ij,njk->nik", rotation.T, trajectory.rotations)
    if noise > 0.0:
        positions = positions + np.random.default_rng(seed).normal(0.0, noise, positions.shape)
    quaternions = Rotation.from_matrix(rotations).as_quat(scalar_first=True)
    return Trajectory(
        trajectory.timestamps_ns.copy(),
        np.asarray(positions, dtype=np.float64),
        np.asarray(quaternions, dtype=np.float64),
    )


def write_tum(path, trajectory: Trajectory) -> None:
    """TUM format: seconds, position, then a quaternion with the scalar part last."""
    lines = []
    for timestamp, position, quaternion in zip(
        trajectory.timestamps_ns, trajectory.positions, trajectory.quaternions, strict=True
    ):
        w, x, y, z = quaternion
        tx, ty, tz = position
        lines.append(
            f"{timestamp / 1e9:.9f} {tx:.9f} {ty:.9f} {tz:.9f} "
            f"{x:.9f} {y:.9f} {z:.9f} {w:.9f}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
