"""End-to-end HTTP tests, matching the exact spec: auth, POST /analyze
(sync), POST /analyze/async + GET /jobs/{id} (async, run via eager Celery --
see conftest.py), and POST /feedback.
"""
AUTH = {"Authorization": "Bearer test-key"}


async def test_health_no_auth_required(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_analyze_requires_auth(client):
    resp = await client.post("/api/v1/analyze", json={"lat": 1.0, "lng": 1.0})
    assert resp.status_code == 401


async def test_invalid_bearer_token_rejected(client):
    resp = await client.post(
        "/api/v1/analyze", json={"lat": 1.0, "lng": 1.0}, headers={"Authorization": "Bearer wrong"}
    )
    assert resp.status_code == 401


async def test_sync_analyze_returns_full_result_shape(client):
    resp = await client.post(
        "/api/v1/analyze",
        json={"lat": 40.7128, "lng": -74.0060, "address": "123 Main St", "resolution_cm": 10},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    for field in (
        "building_id", "score", "condition", "confidence", "resolution_cm",
        "footprint_masked", "imagery_date", "findings", "temporal", "image_urls",
    ):
        assert field in body

    assert body["building_id"].startswith("bld_")
    assert 0 <= body["score"] <= 100
    assert body["condition"] in ("good", "aging", "poor")
    assert body["temporal"] is None  # no compare_year requested
    assert body["image_urls"]["masked"].startswith("/storage/")
    assert len(body["image_urls"]["tiles"]) == 9  # 3x3 grid


async def test_sync_analyze_with_compare_year_populates_temporal(client):
    resp = await client.post(
        "/api/v1/analyze",
        json={"lat": 47.6062, "lng": -122.3321, "compare_year": 2020},
        headers=AUTH,
    )
    assert resp.status_code == 200
    temporal = resp.json()["temporal"]
    assert temporal is not None
    assert "previous_score" in temporal
    assert "score_delta" in temporal
    assert isinstance(temporal["change_summary"], str) and temporal["change_summary"]


async def test_async_flow_queues_then_completes(client):
    resp = await client.post(
        "/api/v1/analyze/async",
        json={"lat": 33.4484, "lng": -112.0740, "user_id": "user-1"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"
    job_id = body["job_id"]
    assert job_id.startswith("job_")

    poll = await client.get(f"/api/v1/jobs/{job_id}", headers=AUTH)
    assert poll.status_code == 200
    poll_body = poll.json()
    # Eager mode means the task has already run by the time we poll.
    assert poll_body["status"] == "completed"
    assert poll_body["progress"] == 1.0
    assert poll_body["result"] is not None
    assert 0 <= poll_body["result"]["score"] <= 100


async def test_unknown_job_id_404s(client):
    resp = await client.get("/api/v1/jobs/job_doesnotexist", headers=AUTH)
    assert resp.status_code == 404


async def test_feedback_submission(client):
    analyze_resp = await client.post(
        "/api/v1/analyze/async", json={"lat": 1.0, "lng": 1.0}, headers=AUTH
    )
    job_id = analyze_resp.json()["job_id"]

    resp = await client.post(
        "/api/v1/feedback",
        json={"job_id": job_id, "user_id": "user-1", "corrected_score": 75, "notes": "looks fine actually"},
        headers=AUTH,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "saved"


async def test_uploaded_images_are_actually_servable(client):
    resp = await client.post(
        "/api/v1/analyze", json={"lat": 12.34, "lng": 56.78}, headers=AUTH
    )
    masked_url = resp.json()["image_urls"]["masked"]
    img_resp = await client.get(masked_url)
    assert img_resp.status_code == 200
    assert img_resp.headers["content-type"] == "image/png"
