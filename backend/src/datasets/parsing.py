"""Row level parsing for ASL/EuRoC and TUM VI sequence files.

Timestamps are 19 digit nanosecond integers and stay `int` for their whole life. Python
ints are arbitrary precision, so parsing with `int()` is exact. Parsing through `float`
would silently round: float64 carries about 15-16 significant decimal digits and these
values have 19, so `float("1520530308199447626")` loses the last few digits and two
distinct frames can collapse onto the same timestamp.
"""

from dataclasses import dataclass
from pathlib import Path

from .errors import SequenceUnreadable


@dataclass(frozen=True, slots=True)
class Pose:
    timestamp_ns: int
    tx: float
    ty: float
    tz: float
    qw: float
    qx: float
    qy: float
    qz: float


@dataclass(frozen=True, slots=True)
class ImuSample:
    timestamp_ns: int
    wx: float
    wy: float
    wz: float
    ax: float
    ay: float
    az: float


def parse_timestamp_ns(raw: str, *, source: str) -> int:
    """Parse a nanosecond timestamp without ever going through float."""
    text = raw.strip()
    if not text:
        raise SequenceUnreadable(f"empty timestamp in {source}", source)
    try:
        return int(text)
    except ValueError as exc:
        raise SequenceUnreadable(
            f"timestamp in {source} is not an integer: {text!r}", source
        ) from exc


def _data_lines(path: Path) -> list[str]:
    if not path.is_file():
        raise SequenceUnreadable(f"missing {path.name}", str(path))
    lines = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def _split(line: str) -> list[str]:
    """Split a row on commas, or on whitespace when the file is space separated."""
    if "," in line:
        return [part.strip() for part in line.split(",")]
    return line.split()


def read_frame_timestamps(path: Path) -> list[int]:
    """Read `timestamp,filename` rows. Returns timestamps in file order."""
    timestamps = []
    for line in _data_lines(path):
        parts = _split(line)
        if not parts:
            continue
        timestamps.append(parse_timestamp_ns(parts[0], source=str(path)))
    return timestamps


def read_poses(path: Path) -> list[Pose]:
    """Read `timestamp,tx,ty,tz,qw,qx,qy,qz` rows."""
    poses = []
    for index, line in enumerate(_data_lines(path)):
        parts = _split(line)
        if len(parts) < 8:
            raise SequenceUnreadable(
                f"{path.name} row {index + 1} has {len(parts)} columns, expected at least 8",
                str(path),
            )
        poses.append(
            Pose(
                timestamp_ns=parse_timestamp_ns(parts[0], source=str(path)),
                tx=float(parts[1]),
                ty=float(parts[2]),
                tz=float(parts[3]),
                qw=float(parts[4]),
                qx=float(parts[5]),
                qy=float(parts[6]),
                qz=float(parts[7]),
            )
        )
    return poses


def read_imu(path: Path) -> list[ImuSample]:
    """Read `timestamp,wx,wy,wz,ax,ay,az` rows."""
    samples = []
    for index, line in enumerate(_data_lines(path)):
        parts = _split(line)
        if len(parts) < 7:
            raise SequenceUnreadable(
                f"{path.name} row {index + 1} has {len(parts)} columns, expected at least 7",
                str(path),
            )
        samples.append(
            ImuSample(
                timestamp_ns=parse_timestamp_ns(parts[0], source=str(path)),
                wx=float(parts[1]),
                wy=float(parts[2]),
                wz=float(parts[3]),
                ax=float(parts[4]),
                ay=float(parts[5]),
                az=float(parts[6]),
            )
        )
    return samples
