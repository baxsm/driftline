"""Cross check every metric against `evo`, the standard trajectory evaluation tool.

This is the verification that makes the numbers worth anything. Alignment and ATE/RPE all
produce plausible output when implemented incorrectly, and none of the ways to get them
wrong throw, so an independent implementation is the only reliable check. `evo` is used as
the oracle and never as the implementation.

Matching it to 1e-9 relative is not a coincidence of similar formulas. It means the
association rule, the Umeyama convention, the order scale and rotation are applied in, the
segment pairing for RPE, and the rotation metric all agree with a tool the literature uses.
"""

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from metrics.errors import DEFAULT_RPE_DELTA_FRAMES
from metrics.scoring import Trajectory, score

from .trajectories import transform_trajectory, wandering_trajectory, write_tum


def _find_evo(name: str) -> str | None:
    """Locate an evo console script.

    It is looked for next to the running interpreter first. `evo` is a declared dependency,
    so it is installed in this environment whether or not that environment is on PATH, and
    resolving through PATH alone makes the whole oracle skip itself the moment the tests are
    run without the venv activated. A cross check that quietly skips is worse than none,
    because the suite still reports green.
    """
    scripts = Path(sys.executable).parent
    for candidate in (scripts / f"{name}.exe", scripts / name):
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


EVO_APE = _find_evo("evo_ape")
EVO_RPE = _find_evo("evo_rpe")

pytestmark = pytest.mark.skipif(
    not EVO_APE or not EVO_RPE, reason="the evo command line was not found in this environment"
)

RELATIVE_TOLERANCE = 1e-9


def read_tum(path: Path) -> Trajectory:
    """Read back a TUM file, so our scorer sees exactly the numbers evo sees.

    Both sides must be fed identical input for a 1e-9 comparison to mean anything. The file
    carries 9 decimal places, and scoring the full precision arrays while evo scores the
    rounded file shifts the result by about 3e-9, which is the rounding rather than a
    difference in the metric. Comparing at that level without closing this gap would mean
    picking a tolerance loose enough to hide a real disagreement of the same size.
    """
    rows = [
        [float(value) for value in line.split()]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    table = np.array(rows, dtype=np.float64)
    timestamps = np.round(table[:, 0] * 1e9).astype(np.int64)
    # the file orders the quaternion (x, y, z, w) while the rest of this project is Hamilton
    quaternions = np.column_stack([table[:, 7], table[:, 4], table[:, 5], table[:, 6]])
    return Trajectory(timestamps, table[:, 1:4], quaternions)


def _run_evo(executable: str, reference: Path, estimate: Path, extra: list[str]) -> dict:
    """Run an evo app and read its statistics back.

    `--save_results` writes a zip holding `stats.json`, which is parsed rather than the
    console table. Scraping printed output would break on any formatting change and would
    silently lose precision to the printed number of digits.
    """
    results = reference.parent / f"{executable_name(executable)}.zip"
    completed = subprocess.run(
        [
            executable,
            "tum",
            str(reference),
            str(estimate),
            *extra,
            "--save_results",
            str(results),
            "--silent",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"evo failed: {completed.stdout}\n{completed.stderr}")
    with zipfile.ZipFile(results) as archive:
        return json.loads(archive.read("stats.json"))


def executable_name(executable: str) -> str:
    return Path(executable).stem


def _assert_close(ours: float, theirs: float, label: str) -> None:
    assert ours == pytest.approx(theirs, rel=RELATIVE_TOLERANCE, abs=1e-12), (
        f"{label}: ours={ours!r} evo={theirs!r}"
    )


def _mono_estimate(truth: Trajectory, noise: float = 0.01) -> Trajectory:
    """A monocular estimate: right shape, arbitrary frame, arbitrary scale, a little noise."""
    rotation = Rotation.from_euler("xyz", [0.3, -0.2, 0.7]).as_matrix()
    return transform_trajectory(
        truth,
        rotation=np.asarray(rotation, dtype=np.float64),
        translation=np.array([1.5, -2.0, 0.5]),
        scale=0.4,
        noise=noise,
    )


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Trajectory, Trajectory, Path, Path]:
    """Both trajectories, written out and read back so both sides score identical input."""
    truth_file = tmp_path / "truth.tum"
    estimate_file = tmp_path / "estimate.tum"
    truth = wandering_trajectory(seed=1, count=200)
    write_tum(truth_file, truth)
    write_tum(estimate_file, _mono_estimate(truth))
    return read_tum(truth_file), read_tum(estimate_file), truth_file, estimate_file


@pytest.mark.parametrize(
    ("mode", "flags"),
    [("se3", ["-a"]), ("sim3", ["-a", "-s"])],
)
def test_ate_matches_evo(pair, mode: str, flags: list[str]) -> None:
    truth, estimate, truth_file, estimate_file = pair
    ours = score(estimate, truth, mode)  # type: ignore[arg-type]
    theirs = _run_evo(EVO_APE, truth_file, estimate_file, flags)

    _assert_close(ours.ate_translation.rmse, theirs["rmse"], f"{mode} ate rmse")
    _assert_close(ours.ate_translation.mean, theirs["mean"], f"{mode} ate mean")
    _assert_close(ours.ate_translation.median, theirs["median"], f"{mode} ate median")
    _assert_close(ours.ate_translation.max, theirs["max"], f"{mode} ate max")
    _assert_close(ours.ate_translation.min, theirs["min"], f"{mode} ate min")
    _assert_close(ours.ate_translation.std, theirs["std"], f"{mode} ate std")


@pytest.mark.parametrize(
    ("mode", "flags"),
    [("se3", ["-a"]), ("sim3", ["-a", "-s"])],
)
def test_rpe_translation_matches_evo(pair, mode: str, flags: list[str]) -> None:
    truth, estimate, truth_file, estimate_file = pair
    ours = score(estimate, truth, mode)  # type: ignore[arg-type]
    theirs = _run_evo(
        EVO_RPE,
        truth_file,
        estimate_file,
        [*flags, "-d", str(DEFAULT_RPE_DELTA_FRAMES), "-u", "f"],
    )

    assert ours.rpe_translation is not None
    _assert_close(ours.rpe_translation.rmse, theirs["rmse"], f"{mode} rpe rmse")
    _assert_close(ours.rpe_translation.mean, theirs["mean"], f"{mode} rpe mean")
    _assert_close(ours.rpe_translation.max, theirs["max"], f"{mode} rpe max")


@pytest.mark.parametrize(
    ("mode", "flags"),
    [("se3", ["-a"]), ("sim3", ["-a", "-s"])],
)
def test_rpe_rotation_matches_evo(pair, mode: str, flags: list[str]) -> None:
    """Rotation is checked separately because it is where a convention error hides.

    A Hamilton/JPL mix up or an Euler based angle agrees with evo on translation and
    disagrees only here, so a translation-only cross check would pass with the rotation
    metric completely wrong.
    """
    truth, estimate, truth_file, estimate_file = pair
    ours = score(estimate, truth, mode)  # type: ignore[arg-type]
    theirs = _run_evo(
        EVO_RPE,
        truth_file,
        estimate_file,
        [*flags, "-d", str(DEFAULT_RPE_DELTA_FRAMES), "-u", "f", "-r", "angle_deg"],
    )

    assert ours.rpe_rotation_deg is not None
    _assert_close(ours.rpe_rotation_deg.rmse, theirs["rmse"], f"{mode} rpe rot rmse")
    _assert_close(ours.rpe_rotation_deg.mean, theirs["mean"], f"{mode} rpe rot mean")
    _assert_close(ours.rpe_rotation_deg.max, theirs["max"], f"{mode} rpe rot max")


@pytest.mark.parametrize(
    ("mode", "flags"),
    [("se3", ["-a"]), ("sim3", ["-a", "-s"])],
)
def test_ate_rotation_matches_evo(pair, mode: str, flags: list[str]) -> None:
    truth, estimate, truth_file, estimate_file = pair
    ours = score(estimate, truth, mode)  # type: ignore[arg-type]
    theirs = _run_evo(EVO_APE, truth_file, estimate_file, [*flags, "-r", "angle_deg"])

    _assert_close(ours.ate_rotation_deg.rmse, theirs["rmse"], f"{mode} ate rot rmse")
    _assert_close(ours.ate_rotation_deg.mean, theirs["mean"], f"{mode} ate rot mean")
    _assert_close(ours.ate_rotation_deg.max, theirs["max"], f"{mode} ate rot max")


def test_association_matches_evo_on_mismatched_rates(tmp_path: Path) -> None:
    """Truth at 120Hz against an estimate at 20Hz, which is the real TUM VI situation.

    Association is the step that decides which poses are compared at all, so agreeing with
    evo here means the ATE agreement above is over the same set of pairs and not a
    coincidence of two different subsets averaging out.
    """
    truth = wandering_trajectory(seed=5, count=1200)
    dense = Trajectory(
        (truth.timestamps_ns - truth.timestamps_ns[0]) // 6 + truth.timestamps_ns[0],
        truth.positions,
        truth.quaternions,
    )
    sparse_indices = np.arange(0, len(dense.timestamps_ns), 6, dtype=np.int64)

    truth_file = tmp_path / "truth.tum"
    estimate_file = tmp_path / "estimate.tum"
    write_tum(truth_file, dense)
    write_tum(estimate_file, _mono_estimate(dense.take(sparse_indices), noise=0.005))

    ours = score(read_tum(estimate_file), read_tum(truth_file), "sim3")
    theirs = _run_evo(EVO_APE, truth_file, estimate_file, ["-a", "-s"])

    _assert_close(ours.ate_translation.rmse, theirs["rmse"], "sparse ate rmse")
    assert ours.association.matched_count == len(sparse_indices)
