"""
AWS Lambda feature builder for Global Tension Monitor ML preparation.

Purpose:
- Read normalized events from DynamoDB table `gtm_events`.
- Aggregate region/hour ML features.
- Store feature rows into DynamoDB table `gtm_region_features`.

This is NOT the ML model yet. It prepares the training/inference table:

Region | Time | Event counts | Military counts | Growth velocity | Source diversity | Label status

Required AWS resources:
- Existing table: gtm_events
- New table: gtm_region_features
  - Partition key: pk (String), e.g. REGION#Middle East
  - Sort key: sk (String), e.g. HOUR#2026-05-21T11:00:00Z

Environment variables:
- GTM_EVENTS_TABLE=gtm_events
- GTM_FEATURES_TABLE=gtm_region_features
- AWS_REGION is set automatically by Lambda; defaults to eu-north-1 in code

IAM permissions:
- dynamodb:Query on gtm_events
- dynamodb:PutItem / dynamodb:BatchWriteItem on gtm_region_features
"""

from __future__ import annotations

import datetime as dt
import json
import os
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

import boto3
from boto3.dynamodb.conditions import Key


AWS_REGION = os.environ.get("AWS_REGION", "eu-north-1")
EVENTS_TABLE = os.environ.get("GTM_EVENTS_TABLE", "gtm_events")
FEATURES_TABLE = os.environ.get("GTM_FEATURES_TABLE", "gtm_region_features")

REGIONS = [
    "Middle East",
    "Eastern Europe",
    "East Asia",
    "South Asia",
    "Horn of Africa",
    "West Africa",
    "Mediterranean",
    "Central Asia",
    "Latin America",
    "Global",
]

MILITARY_TYPES = {
    "missile strike",
    "airstrike",
    "drone strike",
    "naval deployment",
    "naval combat",
    "military movement",
    "border clash",
    "base attack",
    "shelling",
    "strategic event",
}

DIPLOMATIC_TYPES = {
    "diplomatic escalation",
    "diplomatic incident",
    "economic sanction",
    "sanction",
    "ceasefire",
}

SEVERE_TYPES = {
    "missile strike",
    "airstrike",
    "base attack",
    "shelling",
    "naval combat",
    "strategic event",
}


dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
events_table = dynamodb.Table(EVENTS_TABLE)
features_table = dynamodb.Table(FEATURES_TABLE)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def floor_to_hour(value: dt.datetime) -> dt.datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_event_time(item: Dict[str, Any]) -> Optional[dt.datetime]:
    """Parse GDELT/collector timestamps safely.

    Supported examples:
    - 2026-05-21T09:44:54.130804Z
    - 2026-05-21T09:44:54Z
    - 20260521094454
    """
    candidates = [
        item.get("time_iso"),
        item.get("seen_date"),
        item.get("ingested_at"),
    ]

    for raw in candidates:
        if not raw:
            continue
        text = str(raw).strip()
        try:
            if text.endswith("Z"):
                return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
            if len(text) == 14 and text.isdigit():
                return dt.datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc)
            return dt.datetime.fromisoformat(text).replace(tzinfo=dt.timezone.utc)
        except Exception:
            continue
    return None


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def decimalize(value: Any) -> Any:
    """Convert floats into Decimal for DynamoDB."""
    if isinstance(value, float):
        return Decimal(str(round(value, 6)))
    if isinstance(value, dict):
        return {k: decimalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decimalize(v) for v in value]
    return value


def fetch_recent_events_for_region(region: str, limit: int = 500) -> List[Dict[str, Any]]:
    """Fetch recent events by region partition.

    The current events table uses pk=REGION#<region> and sk=EVENT#<time>#<id>.
    Querying newest-first is enough for the MVP feature builder.
    """
    try:
        response = events_table.query(
            KeyConditionExpression=Key("pk").eq(f"REGION#{region}"),
            ScanIndexForward=False,
            Limit=limit,
        )
        return response.get("Items", [])
    except Exception as exc:
        print(f"[feature_builder] query failed for region={region}: {exc}")
        return []


def count_in_window(events: List[Dict[str, Any]], start: dt.datetime, end: dt.datetime) -> List[Dict[str, Any]]:
    result = []
    for event in events:
        event_time = event.get("_parsed_time")
        if event_time and start <= event_time < end:
            result.append(event)
    return result


def event_type(event: Dict[str, Any]) -> str:
    return str(event.get("type") or event.get("event_type") or "unknown").lower()


def build_region_features(region: str, now_hour: dt.datetime) -> Dict[str, Any]:
    raw_events = fetch_recent_events_for_region(region)
    events: List[Dict[str, Any]] = []
    for item in raw_events:
        parsed = parse_event_time(item)
        if parsed:
            item["_parsed_time"] = parsed
            events.append(item)

    window_1h = count_in_window(events, now_hour - dt.timedelta(hours=1), now_hour)
    window_6h = count_in_window(events, now_hour - dt.timedelta(hours=6), now_hour)
    prev_6h = count_in_window(events, now_hour - dt.timedelta(hours=12), now_hour - dt.timedelta(hours=6))
    window_24h = count_in_window(events, now_hour - dt.timedelta(hours=24), now_hour)
    window_7d = count_in_window(events, now_hour - dt.timedelta(days=7), now_hour)

    military_24h = [e for e in window_24h if event_type(e) in MILITARY_TYPES]
    diplomatic_24h = [e for e in window_24h if event_type(e) in DIPLOMATIC_TYPES]
    severe_24h = [e for e in window_24h if event_type(e) in SEVERE_TYPES]
    high_conf_24h = [e for e in window_24h if as_float(e.get("confidence")) >= 75]

    current_6h_count = len(window_6h)
    previous_6h_count = len(prev_6h)
    velocity_6h = (current_6h_count - previous_6h_count) / max(previous_6h_count, 1)

    sources = {str(e.get("source") or e.get("domain") or "unknown") for e in window_24h}
    avg_confidence = (
        sum(as_float(e.get("confidence"), 0.0) for e in window_24h) / max(len(window_24h), 1)
    )

    # Initial label is unknown. A later labeling job should fill this after 72h.
    label_due_at = now_hour + dt.timedelta(hours=72)

    return {
        "pk": f"REGION#{region}",
        "sk": f"HOUR#{iso_z(now_hour)}",
        "region": region,
        "feature_time": iso_z(now_hour),
        "event_count_1h": len(window_1h),
        "event_count_6h": current_6h_count,
        "event_count_24h": len(window_24h),
        "event_count_7d": len(window_7d),
        "military_event_count_24h": len(military_24h),
        "diplomatic_event_count_24h": len(diplomatic_24h),
        "severe_event_count_24h": len(severe_24h),
        "high_confidence_event_count_24h": len(high_conf_24h),
        "source_diversity_24h": len(sources),
        "avg_confidence_24h": round(avg_confidence, 3),
        "velocity_6h": round(velocity_6h, 4),
        "label_escalation_72h": "PENDING",
        "label_due_at": iso_z(label_due_at),
        "created_at": iso_z(utc_now()),
        "source_table": EVENTS_TABLE,
        "model_stage": "feature_store_v1",
    }


def write_feature_rows(rows: Iterable[Dict[str, Any]]) -> int:
    written = 0
    with features_table.batch_writer(overwrite_by_pkeys=["pk", "sk"]) as batch:
        for row in rows:
            batch.put_item(Item=decimalize(row))
            written += 1
    return written


def lambda_handler(event: Optional[Dict[str, Any]], context: Any) -> Dict[str, Any]:
    now_hour = floor_to_hour(utc_now())
    rows = [build_region_features(region, now_hour) for region in REGIONS]
    written = write_feature_rows(rows)

    result = {
        "statusCode": 200,
        "feature_time": iso_z(now_hour),
        "regions_processed": len(REGIONS),
        "feature_rows_written": written,
        "events_table": EVENTS_TABLE,
        "features_table": FEATURES_TABLE,
        "region": AWS_REGION,
    }
    print(json.dumps(result))
    return result
