"""The estimator config a user changes between runs.

`extra="forbid"` is deliberate. A typo in a config key must fail loudly rather than be
silently dropped and run with the default, because a run that silently used defaults would
then be compared against one that did not.
"""

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EstimatorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["mono"] = "mono"
    max_features: int = Field(ge=50, le=2000, default=600)
    # corner strength relative to the strongest corner in the frame. Lower finds more, and
    # weaker, corners. This replaced `fast_threshold`, which the pipeline never read: the
    # detector is Shi-Tomasi and takes a quality level, not a corner threshold.
    corner_quality: float = Field(gt=0.0, le=1.0, default=0.01)
    min_feature_distance_px: float = Field(gt=0, le=100, default=12.0)
    ransac_threshold_px: float = Field(gt=0, le=10, default=1.0)
    redetect_below: int = Field(ge=10, le=2000, default=300)
    min_track_length: int = Field(ge=2, le=100, default=3)
    max_frames: int | None = Field(default=None, ge=2)
    start_frame: int = Field(ge=0, default=0)

    # Contrast limited histogram equalisation before detection. The TUM VI room frames average
    # 32.8 of 255, and equalising raises the corner count on frame 0 from 108 to 287.
    enhance_contrast: bool = True

    # A frame is only used for geometry once the median feature has moved this far from the
    # last keyframe. Consecutive frames at 20Hz move about 0.7 px, which is far below what the
    # essential matrix can separate rotation from translation with, so solving every frame
    # against its predecessor fails on any sequence that is not moving quickly.
    keyframe_parallax_px: float = Field(gt=0.0, le=200.0, default=8.0)
    # Give up on finding parallax after this many frames. A camera held still never reaches
    # the threshold, and the run should say so rather than tracking to the end of the sequence.
    max_frames_without_keyframe: int = Field(ge=2, le=2000, default=120)

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))

    def hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return dict(self.model_dump())
