"""API tests using FastAPI TestClient against an isolated sqlite DB."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(isolated_settings):  # type: ignore[no-untyped-def]
    from finunderwrite.api.app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


_SBI_CSV = (
    "Txn Date,Description,Debit,Credit,Balance\n"
    "15/01/2025,UPI-SWIGGY,250.00,,4750.00\n"
    "16/01/2025,NEFT-SALARY,,50000.00,54750.00\n"
    "17/01/2025,ATM-WITHDRAWAL,2000.00,,52750.00\n"
)


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "X-Request-ID" in resp.headers


def test_ui_index_and_static_assets(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "FinUnderWrite" in resp.text
    assert "text/html" in resp.headers.get("content-type", "")

    css = client.get("/static/styles.css")
    assert css.status_code == 200
    assert "Newsreader" in css.text

    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert "/statements" in js.text


def test_root_head_and_favicon(client: TestClient) -> None:
    head = client.head("/")
    assert head.status_code == 200

    favicon = client.get("/favicon.ico")
    assert favicon.status_code == 204


def test_health_includes_upload_limit_mb(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["max_upload_mb"] >= 1


def test_upload_csv_and_list_transactions(client: TestClient) -> None:
    files = {"file": ("sbi.csv", io.BytesIO(_SBI_CSV.encode()), "text/csv")}
    resp = client.post("/statements", files=files, data={"customer_id": "cust-1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "processed"
    assert body["transactions_ingested"] == 3

    resp = client.get("/transactions", params={"customer_id": "cust-1"})
    assert resp.status_code == 200
    listing = resp.json()
    assert listing["count"] == 3
    assert listing["transactions"][0]["customer_id"] == "cust-1"


def test_unsupported_file_type_rejected(client: TestClient) -> None:
    files = {"file": ("note.txt", io.BytesIO(b"hello"), "text/plain")}
    resp = client.post("/statements", files=files, data={"customer_id": "c"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "http_error"


def test_upload_size_limit(client: TestClient, isolated_settings) -> None:  # type: ignore[no-untyped-def]
    isolated_settings.max_upload_bytes = 10
    files = {"file": ("big.csv", io.BytesIO(b"x" * 100), "text/csv")}
    resp = client.post("/statements", files=files, data={"customer_id": "c"})
    assert resp.status_code == 413
    assert "bytes" in resp.json()["detail"]


def test_upload_size_limit_reported_in_mb(client: TestClient, isolated_settings) -> None:  # type: ignore[no-untyped-def]
    isolated_settings.max_upload_bytes = 2 * 1024 * 1024
    files = {"file": ("big.csv", io.BytesIO(b"x" * (2 * 1024 * 1024 + 1)), "text/csv")}
    resp = client.post("/statements", files=files, data={"customer_id": "c"})
    assert resp.status_code == 413
    assert resp.json()["detail"] == "Upload exceeds limit of 2 MB"
    assert "bytes" not in resp.json()["detail"]


def test_profile_and_features_after_upload(client: TestClient) -> None:
    files = {"file": ("sbi.csv", io.BytesIO(_SBI_CSV.encode()), "text/csv")}
    client.post("/statements", files=files, data={"customer_id": "cust-2"})

    resp = client.get("/profile/cust-2")
    assert resp.status_code == 200
    assert resp.json()["customer_id"] == "cust-2"

    resp = client.get("/features/cust-2")
    assert resp.status_code == 200
    assert resp.json()["customer_id"] == "cust-2"
    assert "features" in resp.json()


def test_profile_404_when_no_data(client: TestClient) -> None:
    resp = client.get("/profile/ghost")
    assert resp.status_code == 404


def test_synthetic_404_when_none(client: TestClient) -> None:
    resp = client.get("/synthetic", params={"n": 100})
    assert resp.status_code == 404


def test_synthetic_invalid_n(client: TestClient) -> None:
    resp = client.get("/synthetic", params={"n": 777})
    assert resp.status_code == 400


def test_synthetic_served_from_registry(client: TestClient, isolated_settings, tmp_path) -> None:  # type: ignore[no-untyped-def]
    csv_path = tmp_path / "syn.csv"
    csv_path.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    from finunderwrite.persistence import repository

    repository.register_synthetic_dataset(
        name="gaussian_copula_100",
        n=100,
        method="gaussian_copula",
        path=str(csv_path),
        metrics={"fidelity": {"overall_quality_score": 0.9}},
    )
    resp = client.get("/synthetic", params={"n": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["method"] == "gaussian_copula"
    assert body["count"] == 2
