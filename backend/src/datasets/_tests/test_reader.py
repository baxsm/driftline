import pytest

from datasets.errors import SequenceUnreadable
from datasets.reader import read_sequence

FRAMES = (
    "#timestamp [ns],filename\n"
    "1520530308199447626,1520530308199447626.png\n"
    "1520530308249448626,1520530308249448626.png\n"
)
GROUND_TRUTH = (
    "# timestamp[ns],tx,ty,tz,qw,qx,qy,qz\n"
    "1520530308189679351,0.84,-0.21,1.24,0.9996498117,0.0037,0.0097,-0.0243\n"
    "1520530308198012351,0.84,-0.21,1.25,0.9996655192,0.0038,0.0094,-0.0237\n"
)
IMU = (
    "# timestamp[ns] w.x w.y w.z a.x a.y a.z\n"
    "1520530308181901469 0.10 -0.07 0.01 -0.35 0.00 9.92\n"
    "1520530308186917469 0.09 -0.08 0.01 -0.30 0.00 9.95\n"
)
CAMCHAIN = """cam0:
  camera_model: pinhole
  distortion_model: equidistant
  distortion_coeffs: [0.0034, 0.0007, -0.0020, 0.0002]
  intrinsics: [190.97, 190.97, 254.93, 256.89]
  resolution: [512, 512]
"""
IMU_CONFIG = """rostopic: /imu0
update_rate: 200.0
accelerometer_noise_density: 0.0028
accelerometer_random_walk: 0.00086
gyroscope_noise_density: 0.00016
gyroscope_random_walk: 0.000022
"""


def build_sequence(root, *, ground_truth=True, imu=True, calibration=True):
    cam0 = root / "mav0" / "cam0"
    cam0.mkdir(parents=True)
    (cam0 / "data.csv").write_text(FRAMES, encoding="utf-8")
    dso = root / "dso"
    dso.mkdir()
    if ground_truth:
        (dso / "gt_imu.csv").write_text(GROUND_TRUTH, encoding="utf-8")
    if imu:
        (dso / "imu.txt").write_text(IMU, encoding="utf-8")
    if calibration:
        (dso / "camchain.yaml").write_text(CAMCHAIN, encoding="utf-8")
        (dso / "imu_config.yaml").write_text(IMU_CONFIG, encoding="utf-8")
    return root


def test_reads_tum_vi_layout(tmp_path):
    info = read_sequence(build_sequence(tmp_path / "room1"))
    assert info.source == "tum_vi"
    assert info.frame_count == 2
    assert info.imu_sample_count == 2
    assert info.has_ground_truth is True
    assert info.ground_truth_count == 2
    assert info.camera_model == "pinhole-equi"


def test_reads_euroc_ground_truth_location(tmp_path):
    root = build_sequence(tmp_path / "euroc", ground_truth=False)
    truth_dir = root / "mav0" / "state_groundtruth_estimate0"
    truth_dir.mkdir(parents=True)
    (truth_dir / "data.csv").write_text(GROUND_TRUTH, encoding="utf-8")
    info = read_sequence(root)
    assert info.has_ground_truth is True
    assert info.ground_truth_count == 2


def test_sequence_without_ground_truth_is_honest(tmp_path):
    info = read_sequence(build_sequence(tmp_path / "no-truth", ground_truth=False))
    assert info.has_ground_truth is False
    assert info.ground_truth_count == 0


def test_duration_uses_integer_nanosecond_span(tmp_path):
    info = read_sequence(build_sequence(tmp_path / "room1"))
    # frame span 1520530308249448626 - 1520530308199447626 = 50001000 ns, and it is the
    # widest of the streams, so it is the reported duration
    assert info.duration_seconds == pytest.approx(0.050001)


def test_missing_frames_csv_names_the_file(tmp_path):
    root = tmp_path / "broken"
    (root / "mav0" / "cam0").mkdir(parents=True)
    with pytest.raises(SequenceUnreadable) as excinfo:
        read_sequence(root)
    assert "mav0/cam0/data.csv" in str(excinfo.value)


def test_empty_frames_csv_is_rejected(tmp_path):
    root = tmp_path / "empty"
    cam0 = root / "mav0" / "cam0"
    cam0.mkdir(parents=True)
    (cam0 / "data.csv").write_text("#timestamp [ns],filename\n", encoding="utf-8")
    with pytest.raises(SequenceUnreadable) as excinfo:
        read_sequence(root)
    assert "no frames" in str(excinfo.value)


def test_path_that_is_not_a_directory_is_rejected(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(SequenceUnreadable):
        read_sequence(target)


def test_calibration_carries_real_imu_noise(tmp_path):
    info = read_sequence(build_sequence(tmp_path / "room1"))
    assert info.calibration["imu"]["accel_bias_rw"] == pytest.approx(0.00086)
    assert info.calibration["cameras"][0]["intrinsics"]["fx"] == pytest.approx(190.97)
