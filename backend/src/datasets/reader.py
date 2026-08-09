"""Read a sequence folder and report what is actually in it.

Both TUM VI and EuRoC use the ASL `mav0` layout for images and IMU, but they put ground
truth in different places, and TUM VI keeps its calibration in a sibling `dso` folder:

    mav0/cam0/data.csv                              frames, both
    mav0/imu0/data.csv                              imu, EuRoC
    mav0/state_groundtruth_estimate0/data.csv       ground truth, EuRoC
    dso/gt_imu.csv                                  ground truth, TUM VI
    dso/imu.txt                                     imu, TUM VI
    dso/camchain.yaml                               calibration, TUM VI

Checking only the EuRoC ground truth path reports "no ground truth" for every TUM VI
sequence, which silently disables all scoring, so both locations are checked.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .calibration import camera_model_from_calibration, parse_camchain, parse_imu_config
from .errors import SequenceUnreadable
from .parsing import Pose, read_frame_timestamps, read_imu, read_poses

GROUND_TRUTH_CANDIDATES = (
    Path("dso") / "gt_imu.csv",
    Path("mav0") / "state_groundtruth_estimate0" / "data.csv",
)
IMU_CANDIDATES = (
    Path("mav0") / "imu0" / "data.csv",
    Path("dso") / "imu.txt",
)
CAMCHAIN_CANDIDATES = (
    Path("dso") / "camchain.yaml",
    Path("camchain.yaml"),
)
IMU_CONFIG_CANDIDATES = (
    Path("dso") / "imu_config.yaml",
    Path("imu_config.yaml"),
)


@dataclass(frozen=True, slots=True)
class SequenceInfo:
    name: str
    source: str
    path: str
    frame_count: int
    imu_sample_count: int
    duration_seconds: float
    has_ground_truth: bool
    ground_truth_count: int
    camera_model: str | None
    calibration: dict[str, Any] = field(default_factory=dict)


def _first_existing(root: Path, candidates: tuple[Path, ...]) -> Path | None:
    for relative in candidates:
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return None


def _detect_source(root: Path, calibration: dict[str, Any]) -> str:
    if (root / "dso").is_dir():
        return "tum_vi"
    if (root / "mav0" / "state_groundtruth_estimate0").is_dir():
        return "euroc"
    cameras = calibration.get("cameras") or []
    if cameras and cameras[0].get("distortion_model") == "equidistant":
        return "tum_vi"
    return "custom"


def _span_seconds(timestamps: list[int]) -> float:
    """Duration in seconds from integer nanosecond bounds.

    The subtraction happens in integer space and only the small difference becomes a float,
    so no precision is lost off the 19 digit endpoints.
    """
    if len(timestamps) < 2:
        return 0.0
    return (max(timestamps) - min(timestamps)) / 1e9


def read_ground_truth(root: Path) -> list[Pose]:
    """Read ground truth poses, or return an empty list when the sequence has none."""
    path = _first_existing(root, GROUND_TRUTH_CANDIDATES)
    return read_poses(path) if path else []


def read_sequence(path: str | Path) -> SequenceInfo:
    """Inspect a sequence folder. Raises SequenceUnreadable naming the first missing file."""
    root = Path(path).expanduser()
    if not root.is_dir():
        raise SequenceUnreadable(f"path is not a directory: {root}", str(root))

    frames_csv = root / "mav0" / "cam0" / "data.csv"
    if not frames_csv.is_file():
        raise SequenceUnreadable(
            "missing mav0/cam0/data.csv, so this is not an ASL or TUM VI sequence",
            str(frames_csv),
        )

    frame_timestamps = read_frame_timestamps(frames_csv)
    if not frame_timestamps:
        raise SequenceUnreadable("mav0/cam0/data.csv contains no frames", str(frames_csv))

    imu_path = _first_existing(root, IMU_CANDIDATES)
    imu_samples = read_imu(imu_path) if imu_path else []

    ground_truth = read_ground_truth(root)

    calibration: dict[str, Any] = {}
    camchain_path = _first_existing(root, CAMCHAIN_CANDIDATES)
    if camchain_path:
        calibration = parse_camchain(camchain_path)

    imu_config_path = _first_existing(root, IMU_CONFIG_CANDIDATES)
    if imu_config_path:
        calibration["imu"] = parse_imu_config(imu_config_path)

    spans = [_span_seconds(frame_timestamps)]
    if imu_samples:
        spans.append(_span_seconds([sample.timestamp_ns for sample in imu_samples]))

    return SequenceInfo(
        name=root.name,
        source=_detect_source(root, calibration),
        path=str(root.resolve()),
        frame_count=len(frame_timestamps),
        imu_sample_count=len(imu_samples),
        duration_seconds=max(spans),
        has_ground_truth=bool(ground_truth),
        ground_truth_count=len(ground_truth),
        camera_model=camera_model_from_calibration(calibration),
        calibration=calibration,
    )
