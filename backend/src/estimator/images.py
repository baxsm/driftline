"""Locating and loading the frames of a sequence.

Images are read one at a time rather than all at once. A room sequence is 2821 frames at
512x512, which is under a gigabyte as raw greyscale, but there is no reason to hold it.

A frame listed in `data.csv` but missing from disk raises. Substituting a blank image would
let a run finish and report a trajectory that was partly estimated from nothing.
"""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from datasets.errors import SequenceUnreadable
from datasets.parsing import read_frames

CAMERA_FOLDERS = ("cam0", "cam1")


@dataclass(frozen=True, slots=True)
class FrameSource:
    camera: str
    directory: Path
    timestamps: list[int]
    filenames: list[str]

    def __len__(self) -> int:
        return len(self.timestamps)

    def path_for(self, index: int) -> Path:
        return self.directory / self.filenames[index]

    def load(self, index: int) -> NDArray[np.uint8]:
        """Read one frame as greyscale.

        The detector and KLT both work on intensity, so colour would be converted away
        immediately even if a sequence had it.
        """
        path = self.path_for(index)
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise SequenceUnreadable(f"could not read frame {path.name}", str(path))
        return np.asarray(image, dtype=np.uint8)


def open_frames(sequence_path: str | Path, camera: str = "cam0") -> FrameSource:
    """List the frames of one camera, checking the images are actually there.

    Only the first and last frame are opened here. Checking every file would mean thousands
    of stat calls before a run starts, and a frame that disappears mid-run raises anyway.
    """
    root = Path(sequence_path).expanduser()
    camera_root = root / "mav0" / camera
    csv_path = camera_root / "data.csv"
    if not csv_path.is_file():
        raise SequenceUnreadable(f"missing mav0/{camera}/data.csv", str(csv_path))

    directory = camera_root / "data"
    if not directory.is_dir():
        raise SequenceUnreadable(f"missing mav0/{camera}/data", str(directory))

    frames = read_frames(csv_path)
    if not frames:
        raise SequenceUnreadable(f"mav0/{camera}/data.csv lists no frames", str(csv_path))

    timestamps = [timestamp for timestamp, _ in frames]
    filenames = [filename for _, filename in frames]
    source = FrameSource(
        camera=camera, directory=directory, timestamps=timestamps, filenames=filenames
    )

    for index in (0, len(frames) - 1):
        path = source.path_for(index)
        if not path.is_file():
            raise SequenceUnreadable(
                f"frame {path.name} is listed in data.csv but not on disk", str(path)
            )
    return source


def available_cameras(sequence_path: str | Path) -> list[str]:
    root = Path(sequence_path).expanduser() / "mav0"
    return [name for name in CAMERA_FOLDERS if (root / name / "data").is_dir()]
