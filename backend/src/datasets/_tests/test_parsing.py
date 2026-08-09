import pytest

from datasets.errors import SequenceUnreadable
from datasets.parsing import parse_timestamp_ns, read_frame_timestamps, read_imu, read_poses

FRAME_CSV = "#timestamp [ns],filename\n1520530308199447626,1520530308199447626.png\n"
POSE_CSV = (
    "# timestamp[ns],tx,ty,tz,qw,qx,qy,qz\n"
    "1520530308189679351,0.8417820384,-0.2193354118,1.2499749141,"
    "0.9996498117,0.0037373093,0.0097169635,-0.0243283190\n"
)
IMU_TXT = (
    "# timestamp[ns] w.x w.y w.z a.x a.y a.z\n"
    "1520530308181901469 0.1045577128 -0.0792420275 0.0178416359 "
    "-0.3522450410 0.0000321145 9.9237603029\n"
)


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_keeps_full_nanosecond_precision():
    assert parse_timestamp_ns("1520530308199447626", source="t") == 1520530308199447626


def test_float_parsing_would_lose_precision():
    # guards the reason the parser never uses float: this is the value that would be stored
    assert int(float("1520530308199447626")) != 1520530308199447626


def test_rejects_non_integer_timestamp():
    with pytest.raises(SequenceUnreadable):
        parse_timestamp_ns("1520530308.199447626", source="t")


def test_rejects_empty_timestamp():
    with pytest.raises(SequenceUnreadable):
        parse_timestamp_ns("   ", source="t")


def test_reads_frame_timestamps_as_int(tmp_path):
    timestamps = read_frame_timestamps(write(tmp_path, "data.csv", FRAME_CSV))
    assert timestamps == [1520530308199447626]
    assert isinstance(timestamps[0], int)


def test_skips_comments_and_blank_lines(tmp_path):
    text = FRAME_CSV + "\n# trailing comment\n"
    assert len(read_frame_timestamps(write(tmp_path, "data.csv", text))) == 1


def test_reads_pose_row(tmp_path):
    pose = read_poses(write(tmp_path, "gt.csv", POSE_CSV))[0]
    assert pose.timestamp_ns == 1520530308189679351
    assert pose.tx == pytest.approx(0.8417820384)
    assert pose.qw == pytest.approx(0.9996498117)


def test_reads_whitespace_separated_imu(tmp_path):
    sample = read_imu(write(tmp_path, "imu.txt", IMU_TXT))[0]
    assert sample.timestamp_ns == 1520530308181901469
    assert sample.az == pytest.approx(9.9237603029)


def test_pose_row_with_too_few_columns_names_the_file(tmp_path):
    path = write(tmp_path, "gt.csv", "# h\n1520530308189679351,1.0,2.0\n")
    with pytest.raises(SequenceUnreadable) as excinfo:
        read_poses(path)
    assert "gt.csv" in str(excinfo.value)


def test_missing_file_raises_named_error(tmp_path):
    with pytest.raises(SequenceUnreadable) as excinfo:
        read_frame_timestamps(tmp_path / "absent.csv")
    assert "absent.csv" in str(excinfo.value)
