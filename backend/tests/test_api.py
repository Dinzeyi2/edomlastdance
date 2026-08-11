from app.core.config import get_settings
from app.pipeline.geo import bounding_box_polygon

DEV_KEY = get_settings().dev_seed_tenant_key
AUTH = {"X-Tenant-Key": DEV_KEY}


async def test_leads_requires_auth(client):
    resp = await client.get("/leads")
    assert resp.status_code == 401


async def test_invalid_api_key_rejected(client):
    resp = await client.get("/leads", headers={"X-Tenant-Key": "not-a-real-key"})
    assert resp.status_code == 401


async def test_full_flow_ingest_to_lead_status_update(client):
    # 1. Register a territory covering the mock storm's default center.
    polygon = bounding_box_polygon(32.7767, -96.7970, 0.5)
    resp = await client.post(
        "/territories", json={"name": "DFW metro", "polygon_geojson": polygon}, headers=AUTH
    )
    assert resp.status_code == 201, resp.text

    # 2. Trigger ingestion -- drains synchronously, should produce leads.
    resp = await client.post("/storm-events/ingest", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["storm_events_created"]) >= 1
    assert body["jobs_processed"] > 0

    # 3. List leads for the tenant, ranked by priority_score descending.
    resp = await client.get("/leads", headers=AUTH)
    assert resp.status_code == 200
    leads = resp.json()
    assert len(leads) >= 1
    scores = [lead["priority_score"] for lead in leads]
    assert scores == sorted(scores, reverse=True)

    # 4. Fetch the evidence packet for the top lead.
    top_lead_id = leads[0]["id"]
    resp = await client.get(f"/leads/{top_lead_id}", headers=AUTH)
    assert resp.status_code == 200
    detail = resp.json()
    assert "damage_assessment" in detail
    assert detail["damage_assessment"]["provider"] == "stub"

    # 5. Update lead status -- the feedback loop.
    resp = await client.patch(f"/leads/{top_lead_id}", json={"status": "contacted"}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "contacted"

    # 6. Invalid status is rejected.
    resp = await client.patch(f"/leads/{top_lead_id}", json={"status": "bogus"}, headers=AUTH)
    assert resp.status_code == 422

    # 7. /tenants/me reflects the authenticated tenant.
    resp = await client.get("/tenants/me", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Dev Roofing Co"
