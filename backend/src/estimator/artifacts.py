"""Run outputs that do not belong in Postgres.

    storage/runs/{run_id}/
      tracks.parquet     per frame feature observations, for the tracking view
      trajectory.tum     the estimate in TUM format, for the phase 3 evo cross check
      log.txt            what the estimator did, for the failure inspector

Feature observations are far larger than poses: a few hundred points on every frame over a
few thousand frames is millions of rows, which is a file, not a table.

`trajectory.tum` exists so the metrics computed in phase 3 can be re-derived by running the
`evo` command line against the same file. A stored number that cannot be independently
reproduced is not a check on anything.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .pipeline import FrameResult

TUM_HEADER = "# timestamp tx ty tz qx qy qz qw\n"


@dataclass(frozen=True, slots=True)
class RunArtifacts:
    root: Path

    @property
    def tracks_path(self) -> Path:
        return self.root / "tracks.parquet"

    @property
    def trajectory_path(self) -> Path:
        return self.root / "trajectory.tum"

    @property
    def log_path(self) -> Path:
        return self.root / "log.txt"


def artifacts_for(storage_dir: str | Path, run_id: str) -> RunArtifacts:
    return RunArtifacts(Path(storage_dir) / "runs" / run_id)


def prepare(artifacts: RunArtifacts) -> None:
    artifacts.root.mkdir(parents=True, exist_ok=True)


def write_tracks(artifacts: RunArtifacts, frames: list[FrameResult]) -> int:
    """Flatten every frame's observations into one table. Returns the row count."""
    rows = [
        {
            "frame_index": frame.frame_index,
            "timestamp_ns": frame.timestamp_ns,
            "track_id": observation.track_id,
            "x": observation.x,
            "y": observation.y,
            "age": observation.age,
        }
        for frame in frames
        for observation in frame.observations
    ]
    frame_table = pd.DataFrame(
        rows,
        columns=["frame_index", "timestamp_ns", "track_id", "x", "y", "age"],
    )
    frame_table.to_parquet(artifacts.tracks_path, index=False)
    return len(rows)


def read_tracks(artifacts: RunArtifacts, first_frame: int, last_frame: int) -> pd.DataFrame:
    """Read one frame range back. Returns an empty frame when the run wrote no tracks."""
    if not artifacts.tracks_path.is_file():
        return pd.DataFrame(columns=["frame_index", "timestamp_ns", "track_id", "x", "y", "age"])
    table = pd.read_parquet(artifacts.tracks_path)
    selected = table[
        (table["frame_index"] >= first_frame) & (table["frame_index"] <= last_frame)
    ]
    return selected.sort_values(["frame_index", "track_id"])


def tum_line(
    timestamp_ns: int,
    position: tuple[float, float, float],
    quaternion: tuple[float, float, float, float],
) -> str:
    """One TUM row: timestamp in seconds, position, then an (x, y, z, w) quaternion.

    TUM puts the scalar part last while the rest of this project uses Hamilton (w, x, y, z).
    The swap lives here alone, so the file written during a run and the file served by the
    export route cannot disagree about the ordering.
    """
    w, x, y, z = quaternion
    tx, ty, tz = position
    return f"{timestamp_ns / 1e9:.9f} {tx:.9f} {ty:.9f} {tz:.9f} {x:.9f} {y:.9f} {z:.9f} {w:.9f}\n"


def write_trajectory(artifacts: RunArtifacts, frames: list[FrameResult]) -> None:
    lines = [TUM_HEADER]
    for frame in frames:
        w, x, y, z = frame.pose.quaternion()
        tx, ty, tz = frame.pose.translation
        lines.append(
            tum_line(frame.timestamp_ns, (float(tx), float(ty), float(tz)), (w, x, y, z))
        )
    artifacts.trajectory_path.write_text("".join(lines), encoding="utf-8")


def append_log(artifacts: RunArtifacts, message: str) -> None:
    with artifacts.log_path.open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


def read_log(artifacts: RunArtifacts) -> str:
    if not artifacts.log_path.is_file():
        return ""
    return artifacts.log_path.read_text(encoding="utf-8")
