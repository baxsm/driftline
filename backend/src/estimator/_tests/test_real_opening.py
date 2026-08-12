"""The opening of a real sequence must be solvable from frame 0.

For three sessions this was recorded as a known limitation: room1 was said to open with the
camera held still, and `start_frame` existed to skip past it. That reading was wrong twice
over, and both halves are worth pinning here because the run that proves it takes a real
sequence and cannot be fixtured.

**The opening is not static.** Ground truth has the device travelling 20 cm over the first 120
frames while the gyro reads 0.06 to 0.12 rad/s. It is being turned, not held. Near pure
rotation is a harder case for monocular geometry than stillness, because there is real feature
motion to fit and almost no parallax behind it, so a solver that trusts its correspondence
count will happily fit an essential matrix to it.

**It is solvable anyway**, and it stopped being solvable only because of the miscount that
`motion.py` describes. Once the four decompositions are scored directly, the opening yields
keyframes and the run completes.

Checked against the code before that fix rather than assumed to guard it: reverting
`motion.py` fails `test_the_opening_runs_to_completion_from_frame_zero` at frame 553 with
"only 6 points passed the chirality check". A 200 frame window passes either way, which is
why the window here is 600.
"""

import numpy as np
import pytest

from datasets._tests.sequences import sequence_path
from datasets.reader import read_sequence
from estimator.camera import camera_from_calibration
from estimator.config import EstimatorConfig
from estimator.images import open_frames
from estimator.pipeline import run_pipeline

pytestmark = pytest.mark.integration

# Frames of the opening to run over. This is not a round number chosen for tidiness: the
# window has to reach frame 553, which is where the old miscount killed a run started at frame
# 0. Stopping at 200 or 400 passes against the broken code too, so a shorter window would make
# these tests decorative.
OPENING_FRAMES = 600

# The frame the pre-fix code died on, kept as the thing this file is really guarding.
KNOWN_REGRESSION_FRAME = 553


@pytest.fixture(scope="module")
def opening():
    root = sequence_path()
    info = read_sequence(root)
    frames = open_frames(root)
    camera = camera_from_calibration(info.calibration)
    outcome = run_pipeline(
        timestamps=frames.timestamps[:OPENING_FRAMES],
        load_image=frames.load,
        camera=camera,
        config=EstimatorConfig(max_frames=OPENING_FRAMES),
    )
    return outcome


def test_the_opening_runs_to_completion_from_frame_zero(opening):
    assert not opening.failed, opening.failure_reason
    assert len(opening.frames) == OPENING_FRAMES


def test_the_run_passes_the_frame_the_old_solver_died_on(opening):
    """The specific frame the miscount killed, named so a future failure is recognisable.

    A run that stops here is the old bug returning rather than a new one, and the reason on it
    will say points failed the chirality check.
    """
    assert opening.failure_frame != KNOWN_REGRESSION_FRAME
    solved_past = [
        frame for frame in opening.frames if frame.frame_index > KNOWN_REGRESSION_FRAME
    ]
    assert solved_past, f"the run did not get past frame {KNOWN_REGRESSION_FRAME}"


def test_the_opening_solves_real_geometry_rather_than_coasting(opening):
    """Completing is not enough: a run that solved nothing also reaches the last frame.

    Every pose would be the identity carried forward, which the pipeline only catches when
    there are fewer than two keyframes. Asserting on the keyframe count is what separates a
    solved opening from a coasted one.
    """
    assert opening.keyframe_count > 10


def test_the_opening_moves_and_stays_finite(opening):
    positions = np.array([frame.pose.translation for frame in opening.frames])
    assert np.all(np.isfinite(positions))

    steps = np.linalg.norm(np.diff(positions, axis=0), axis=1)
    # a stalled path is the failure this guards: the estimator holding the identity for the
    # whole opening and reporting it as a successful run whose trajectory is a point
    assert float(steps.sum()) > 0.0
    assert np.count_nonzero(steps > 0) > OPENING_FRAMES // 2


def test_low_parallax_frames_are_bridged_rather_than_solved_one_by_one(opening):
    """Keyframes must be spaced by parallax, not taken on every frame.

    The opening is where this matters most. If the pipeline took a keyframe per frame it would
    be solving 0.7 px of motion, which is the degenerate case the keyframe threshold exists to
    avoid, and the trajectory would be noise rather than an estimate.
    """
    keyframes = [frame.frame_index for frame in opening.frames if frame.is_keyframe]
    assert keyframes[0] == 0
    assert len(keyframes) < OPENING_FRAMES
