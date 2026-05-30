import pytest
from datetime import datetime, timedelta
from services.consumer.src.anomaly_engine import AnomalyEngine, AnomalyType, Severity


@pytest.fixture
def anomaly_engine():
    return AnomalyEngine()


def test_crowd_surge_triggers(anomaly_engine):
    """Inject 16 concurrent ENTRY events → anomaly created"""
    # Simulate 16 people in store simultaneously
    zone_counts = {
        "entrance": 2,
        "makeup": 5,
        "skincare": 4,
        "hair": 3,
        "fragrance": 1,
        "personal_care": 0,
        "checkout": 1
    }
    
    total = sum(zone_counts.values())
    assert total == 16
    
    # Anomaly should trigger when > 15 customers
    anomalies = anomaly_engine.check_crowd_surge(zone_counts)
    assert len(anomalies) == 1
    assert anomalies[0].type == AnomalyType.CROWD_SURGE
    assert anomalies[0].severity == Severity.HIGH


def test_crowd_surge_no_trigger(anomaly_engine):
    """14 concurrent ENTRY events → no anomaly"""
    zone_counts = {
        "entrance": 2,
        "makeup": 4,
        "skincare": 3,
        "hair": 3,
        "fragrance": 1,
        "personal_care": 0,
        "checkout": 1
    }
    
    total = sum(zone_counts.values())
    assert total == 14
    
    anomalies = anomaly_engine.check_crowd_surge(zone_counts)
    assert len(anomalies) == 0


def test_dwell_outlier(anomaly_engine):
    """Session dwell_seconds > 5400 (90 min) → anomaly created"""
    # Session with 100 minute dwell time
    session_data = {
        "session_id": "sess_001",
        "person_id": "track_001",
        "started_at": datetime.now() - timedelta(seconds=6000),
        "dwell_seconds": 6000
    }
    
    anomalies = anomaly_engine.check_dwell_outlier(session_data)
    assert len(anomalies) == 1
    assert anomalies[0].type == AnomalyType.DWELL_OUTLIER
    assert anomalies[0].severity == Severity.MEDIUM


def test_dwell_outlier_no_trigger(anomaly_engine):
    """Session dwell_seconds < 5400 → no anomaly"""
    session_data = {
        "session_id": "sess_002",
        "person_id": "track_002",
        "started_at": datetime.now() - timedelta(seconds=3000),
        "dwell_seconds": 3000
    }
    
    anomalies = anomaly_engine.check_dwell_outlier(session_data)
    assert len(anomalies) == 0


def test_low_conversion_window(anomaly_engine):
    """9 entries in 30 min, 0 purchases → anomaly created"""
    # Simulate 9 entries and 0 purchases in last 30 minutes
    recent_sessions = [
        {"state": "ENTERED", "created_at": datetime.now() - timedelta(minutes=i)}
        for i in range(9)
    ]
    
    anomalies = anomaly_engine.check_low_conversion_window(recent_sessions)
    assert len(anomalies) == 1
    assert anomalies[0].type == AnomalyType.LOW_CONVERSION_WINDOW
    assert anomalies[0].severity == Severity.MEDIUM


def test_low_conversion_no_trigger(anomaly_engine):
    """9 entries, 2 purchases → no anomaly"""
    recent_sessions = [
        {"state": "PURCHASED", "created_at": datetime.now() - timedelta(minutes=1)},
        {"state": "PURCHASED", "created_at": datetime.now() - timedelta(minutes=2)},
    ] + [
        {"state": "ENTERED", "created_at": datetime.now() - timedelta(minutes=i)}
        for i in range(3, 10)
    ]
    
    anomalies = anomaly_engine.check_low_conversion_window(recent_sessions)
    assert len(anomalies) == 0
