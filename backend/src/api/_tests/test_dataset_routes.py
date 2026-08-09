import pytest

FRAMES = (
    "#timestamp [ns],filename\n"
    "1520530308199447626,1520530308199447626.png\n"
    "1520530308249448626,1520530308249448626.png\n"
)
GROUND_TRUTH = (
    "# timestamp[ns],tx,ty,tz,qw,qx,qy,qz\n"
    "1520530308189679351,0.84,-0.21,1.24,0.9996498117,0.0037,0.0097,-0.0243\n"
    "1520530308198012351,0.85,-0.22,1.25,0.9996655192,0.0038,0.0094,-0.0237\n"
)
CAMCHAIN = """cam0:
  camera_model: pinhole
  distortion_model: equidistant
  distortion_coeffs: [0.0034, 0.0007, -0.0020, 0.0002]
  intrinsics: [190.97, 190.97, 254.93, 256.89]
  resolution: [512, 512]
"""


@pytest.fixture
def sequence_path(tmp_path):
    cam0 = tmp_path / "mav0" / "cam0"
    cam0.mkdir(parents=True)
    (cam0 / "data.csv").write_text(FRAMES, encoding="utf-8")
    dso = tmp_path / "dso"
    dso.mkdir()
    (dso / "gt_imu.csv").write_text(GROUND_TRUTH, encoding="utf-8")
    (dso / "camchain.yaml").write_text(CAMCHAIN, encoding="utf-8")
    return str(tmp_path)


def register(client, path, name=None):
    payload = {"path": path}
    if name:
        payload["name"] = name
    return client.post("/api/datasets/register", json=payload)


def test_listing_requires_a_session(client):
    client.cookies.clear()
    assert client.get("/api/datasets").status_code == 401


def test_empty_list_for_a_new_account(client, signed_in):
    assert client.get("/api/datasets").json()["datasets"] == []


def test_register_reports_what_the_reader_found(client, signed_in, sequence_path):
    body = register(client, sequence_path).json()
    assert body["source"] == "tum_vi"
    assert body["frame_count"] == 2
    assert body["has_ground_truth"] is True
    assert body["camera_model"] == "pinhole-equi"


def test_register_rejects_a_folder_that_is_not_a_sequence(client, signed_in, tmp_path):
    response = register(client, str(tmp_path / "nothing-here"))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "sequence_unreadable"


def test_the_error_names_the_missing_file(client, signed_in, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    response = register(client, str(empty))
    assert "mav0/cam0/data.csv" in response.json()["error"]["message"]


def test_registering_the_same_path_twice_is_rejected(client, signed_in, sequence_path):
    register(client, sequence_path)
    response = register(client, sequence_path)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "path_already_registered"


def test_a_supplied_name_wins_over_the_folder_name(client, signed_in, sequence_path):
    assert register(client, sequence_path, "my label").json()["name"] == "my label"


def test_ground_truth_timestamps_are_strings(client, signed_in, sequence_path):
    # json numbers are float64 in the browser, which cannot hold a 19 digit nanosecond value
    dataset_id = register(client, sequence_path).json()["id"]
    poses = client.get(f"/api/datasets/{dataset_id}/ground-truth").json()["poses"]
    assert poses[0]["timestamp_ns"] == "1520530308189679351"
    assert isinstance(poses[0]["timestamp_ns"], str)


def test_ground_truth_is_ordered_by_timestamp(client, signed_in, sequence_path):
    dataset_id = register(client, sequence_path).json()["id"]
    poses = client.get(f"/api/datasets/{dataset_id}/ground-truth").json()["poses"]
    assert [pose["timestamp_ns"] for pose in poses] == sorted(
        pose["timestamp_ns"] for pose in poses
    )


def test_stride_decimates_the_ground_truth(client, signed_in, sequence_path):
    dataset_id = register(client, sequence_path).json()["id"]
    poses = client.get(f"/api/datasets/{dataset_id}/ground-truth?stride=2").json()["poses"]
    assert len(poses) == 1


def test_stride_below_one_is_rejected(client, signed_in, sequence_path):
    dataset_id = register(client, sequence_path).json()["id"]
    assert client.get(f"/api/datasets/{dataset_id}/ground-truth?stride=0").status_code == 422


def test_unknown_dataset_id_is_a_404(client, signed_in):
    missing = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/api/datasets/{missing}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "dataset_not_found"


def test_a_malformed_dataset_id_is_a_404_not_a_500(client, signed_in):
    assert client.get("/api/datasets/not-a-uuid").status_code == 404


def test_delete_unregisters_the_sequence(client, signed_in, sequence_path):
    dataset_id = register(client, sequence_path).json()["id"]
    assert client.delete(f"/api/datasets/{dataset_id}").status_code == 204
    assert client.get("/api/datasets").json()["datasets"] == []


def test_delete_leaves_the_files_alone(client, signed_in, sequence_path, tmp_path):
    dataset_id = register(client, sequence_path).json()["id"]
    client.delete(f"/api/datasets/{dataset_id}")
    assert (tmp_path / "mav0" / "cam0" / "data.csv").is_file()


def test_a_dataset_is_not_visible_to_another_account(client, signed_in, sequence_path):
    dataset_id = register(client, sequence_path).json()["id"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    client.post(
        "/api/auth/register",
        json={"email": "someone-else@driftline.dev", "password": "testpassword123"},
    )
    assert client.get(f"/api/datasets/{dataset_id}").status_code == 404
    assert client.get("/api/datasets").json()["datasets"] == []
