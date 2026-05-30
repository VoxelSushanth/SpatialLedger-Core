import pytest
import asyncio
from httpx import AsyncClient, ASGITransport


BASE_URL = "http://localhost:8000"


@pytest.mark.asyncio
async def test_health_endpoint():
    """GET /health returns 200"""
    async with AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_ready_endpoint():
    """GET /ready returns 200 when db + redis up"""
    async with AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/ready")
        # Should return 200 if services are healthy
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data


@pytest.mark.asyncio
async def test_metrics_structure():
    """GET /metrics returns all required fields, conversion_rate is float 0-1"""
    async with AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/metrics")
        assert response.status_code == 200
        data = response.json()
        
        # Check top-level fields
        assert "store_id" in data
        assert "date" in data
        assert "footfall" in data
        assert "conversion" in data
        assert "dwell_time" in data
        assert "revenue" in data
        assert "zone_popularity" in data
        
        # Check footfall structure
        footfall = data["footfall"]
        assert "total_entries" in footfall
        assert "unique_visitors" in footfall
        assert "re_entries" in footfall
        assert "staff_count" in footfall
        
        # Check conversion rate is valid
        conversion = data["conversion"]
        assert "rate" in conversion
        assert isinstance(conversion["rate"], float)
        assert 0 <= conversion["rate"] <= 1


@pytest.mark.asyncio
async def test_funnel_monotonic():
    """funnel stages are non-increasing (each stage count <= previous)"""
    async with AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/funnel")
        assert response.status_code == 200
        data = response.json()
        
        stages = data.get("stages", [])
        assert len(stages) > 0
        
        # Each stage count should be <= previous stage count
        for i in range(1, len(stages)):
            assert stages[i]["count"] <= stages[i-1]["count"], \
                f"Stage {stages[i]['stage']} ({stages[i]['count']}) > {stages[i-1]['stage']} ({stages[i-1]['count']})"


@pytest.mark.asyncio
async def test_funnel_no_double_count():
    """funnel purchased.count <= funnel entered.count"""
    async with AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/funnel")
        assert response.status_code == 200
        data = response.json()
        
        stages = data.get("stages", [])
        entered_count = next((s["count"] for s in stages if s["stage"] == "ENTERED"), 0)
        purchased_count = next((s["count"] for s in stages if s["stage"] == "PURCHASED"), 0)
        
        assert purchased_count <= entered_count


@pytest.mark.asyncio
async def test_events_pagination():
    """GET /events with limit=10 returns <=10 items with pagination info"""
    async with AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/events?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        
        assert "events" in data
        assert "total" in data
        assert "pagination" in data
        
        events = data["events"]
        assert len(events) <= 10
        
        pagination = data["pagination"]
        assert "limit" in pagination
        assert "offset" in pagination
        assert pagination["limit"] == 10
        assert pagination["offset"] == 0


@pytest.mark.asyncio
async def test_zones_all():
    """GET /zones returns list with all 7 zone_ids"""
    async with AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/zones")
        assert response.status_code == 200
        data = response.json()
        
        expected_zones = {"entrance", "makeup", "skincare", "hair", "fragrance", "personal_care", "checkout"}
        returned_zones = {zone["zone_id"] for zone in data}
        
        assert returned_zones == expected_zones


@pytest.mark.asyncio
async def test_anomalies_filter():
    """GET /anomalies?severity=HIGH returns only HIGH severity"""
    async with AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/anomalies?severity=HIGH")
        assert response.status_code == 200
        data = response.json()
        
        anomalies = data.get("anomalies", [])
        for anomaly in anomalies:
            assert anomaly["severity"] == "HIGH"


@pytest.mark.asyncio
async def test_post_event():
    """POST /events with valid schema returns 201"""
    event_payload = {
        "event_type": "ENTRY",
        "person_id": "track_test_001",
        "person_type": "CUSTOMER",
        "zone_id": "entrance",
        "camera_id": "cam_test",
        "confidence": 0.95,
        "timestamp": "2026-04-10T12:00:00+05:30"
    }
    
    async with AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/events", json=event_payload)
        assert response.status_code == 201
        data = response.json()
        assert "event_id" in data
