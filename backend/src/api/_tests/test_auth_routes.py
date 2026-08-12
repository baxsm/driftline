def test_register_returns_the_new_user(client, account):
    response = client.post("/api/auth/register", json=account)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == account["email"]
    assert "password" not in body
    assert "password_hash" not in body


def test_register_sets_a_session_cookie(client, account):
    response = client.post("/api/auth/register", json=account)
    assert "driftline_session" in response.cookies


def test_duplicate_email_is_rejected(client, account):
    client.post("/api/auth/register", json=account)
    response = client.post("/api/auth/register", json=account)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"
    assert response.json()["error"]["field"] == "email"


def test_email_is_stored_lowercase(client, account):
    shouted = {**account, "email": account["email"].upper()}
    response = client.post("/api/auth/register", json=shouted)
    assert response.json()["email"] == account["email"]


def test_short_password_names_the_field(client, account):
    response = client.post("/api/auth/register", json={**account, "password": "short"})
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "password"


def test_invalid_email_names_the_field(client):
    response = client.post(
        "/api/auth/register", json={"email": "not-an-email", "password": "testpassword123"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "email"


def test_login_with_correct_password(client, signed_in):
    client.cookies.clear()
    response = client.post("/api/auth/login", json=signed_in)
    assert response.status_code == 200
    assert response.json()["email"] == signed_in["email"]


def test_login_with_wrong_password_is_rejected(client, signed_in):
    client.cookies.clear()
    response = client.post("/api/auth/login", json={**signed_in, "password": "wrongpassword1"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_unknown_email_gives_the_same_message_as_a_wrong_password(client, signed_in):
    # the two must be indistinguishable, otherwise the endpoint reveals which emails exist
    client.cookies.clear()
    wrong_password = client.post(
        "/api/auth/login", json={**signed_in, "password": "wrongpassword1"}
    )
    unknown_email = client.post(
        "/api/auth/login", json={"email": "nobody@driftline.dev", "password": "testpassword123"}
    )
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.status_code == unknown_email.status_code


def test_me_requires_a_session(client):
    client.cookies.clear()
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_me_returns_the_signed_in_user(client, signed_in):
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == signed_in["email"]


def test_logout_clears_the_session(client, signed_in):
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401


def test_a_tampered_session_cookie_is_rejected(client, signed_in):
    client.cookies.set("driftline_session", "forged-token-value")
    response = client.get("/api/auth/me")
    assert response.status_code == 401
