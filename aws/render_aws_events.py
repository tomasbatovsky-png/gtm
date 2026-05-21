"""
Helper functions for reading AWS/DynamoDB events from the Render FastAPI app.

This file is intentionally optional. The existing Render app can import it when AWS
environment variables are present. If AWS is not configured, the app should keep
using its current in-memory fallback.

Required Render environment variables:
- AWS_REGION=eu-central-1
- GTM_EVENTS_TABLE=gtm_events
- AWS_ACCESS_KEY_ID=<render-readonly-access-key>
- AWS_SECRET_ACCESS_KEY=<render-readonly-secret>
"""

import os
from typing import Any, Dict, List, Optional

try:
    import boto3
    from boto3.dynamodb.conditions import Key
except Exception:  # pragma: no cover - allows safe import without boto3 installed
    boto3 = None
    Key = None


AWS_REGION = os.environ.get("AWS_REGION", "eu-central-1")
GTM_EVENTS_TABLE = os.environ.get("GTM_EVENTS_TABLE", "gtm_events")
AWS_ENABLED = os.environ.get("GTM_AWS_ENABLED", "false").lower() in {"1", "true", "yes"}


def _table():
    if not boto3 or not AWS_ENABLED:
        return None
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return dynamodb.Table(GTM_EVENTS_TABLE)


def _normalize_for_frontend(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert DynamoDB item shape into the existing frontend event shape."""
    confidence = int(item.get("confidence", 60))
    event_type = item.get("type") or item.get("event_type") or "geopolitical signal"
    color = "red" if confidence >= 82 else "orange" if confidence >= 68 else "yellow"

    def as_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    return {
        "id": item.get("event_id", item.get("sk", "")),
        "type": event_type,
        "region": item.get("region", "Global"),
        "lat": as_float(item.get("lat")),
        "lon": as_float(item.get("lon")),
        "confidence": confidence,
        "source": item.get("source", "AWS"),
        "summary": item.get("summary") or item.get("title") or "",
        "time_iso": item.get("time_iso") or item.get("seen_date") or item.get("ingested_at", ""),
        "age_minutes": 0,
        "color": color,
        "url": item.get("url", "#"),
        "numbers": item.get("numbers", "—"),
        "source_system": item.get("source_system", "AWS"),
    }


def fetch_recent_aws_events(limit_per_region: int = 20) -> List[Dict[str, Any]]:
    """
    Fetch recent events from DynamoDB across known regions.
    Returns [] if AWS is disabled or unavailable.
    """
    table = _table()
    if table is None or Key is None:
        return []

    regions = [
        "Middle East", "Eastern Europe", "East Asia", "South Asia", "Horn of Africa",
        "West Africa", "Mediterranean", "Central Asia", "Latin America", "Global",
    ]
    events: List[Dict[str, Any]] = []

    for region in regions:
        try:
            resp = table.query(
                KeyConditionExpression=Key("pk").eq(f"REGION#{region}"),
                ScanIndexForward=False,
                Limit=limit_per_region,
            )
            events.extend(_normalize_for_frontend(item) for item in resp.get("Items", []))
        except Exception as exc:
            print(f"[AWS DynamoDB] query failed for {region}: {exc}")

    events.sort(key=lambda e: e.get("time_iso", ""), reverse=True)
    return events[:100]


def aws_health() -> Dict[str, Any]:
    table = _table()
    if table is None:
        return {"enabled": False, "ok": False, "reason": "GTM_AWS_ENABLED is false or boto3 missing"}
    try:
        count = len(fetch_recent_aws_events(limit_per_region=2))
        return {"enabled": True, "ok": True, "table": GTM_EVENTS_TABLE, "region": AWS_REGION, "sample_events": count}
    except Exception as exc:
        return {"enabled": True, "ok": False, "table": GTM_EVENTS_TABLE, "region": AWS_REGION, "error": str(exc)}
