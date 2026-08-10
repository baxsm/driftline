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
    max_features: int = Field(ge=50, le=2000, default=300)
    fast_threshold: int = Field(ge=1, le=100, default=20)
    min_feature_distance_px: float = Field(gt=0, le=100, default=12.0)
    ransac_threshold_px: float = Field(gt=0, le=10, default=1.0)
    redetect_below: int = Field(ge=10, le=2000, default=120)
    min_track_length: int = Field(ge=2, le=100, default=3)
    max_frames: int | None = Field(default=None, ge=2)

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))

    def hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return dict(self.model_dump())
