"""
Historical GDELT DOC backfill for Global Tension Monitor.

Purpose:
- Pull historical article/event-like signals from the public GDELT DOC API.
- Store each daily raw payload in S3.
- Write normalized event records into DynamoDB table `gtm_events`.

Recommended use:
- Run this as a separate Lambda named `gtm-gdelt-backfill`.
- Backfill in chunks, e.g. 7 days per invocation, not all 4 months at once.

Example Lambda test event:
{
  "start_date": "2026-05-14",
  "end_date": "2026-05-21",
  "queries": ["conflict", "war", "military"],
  "maxrecords": 100
}

Environment variables:
- GTM_EVENTS_TABLE=gtm_events
- GTM_RAW_BUCKET=gtm-raw-events-tomas
- AWS_REGION is set automatically by Lambda; defaults to eu-north-1 in code

IAM permissions:
- s3:PutObject on raw bucket
- dynamodb:PutItem / dynamodb:BatchWriteItem on gtm_events
"""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Tuple

import boto3


TABLE_NAME = os.environ.get("GTM_EVENTS_TABLE", "gtm_events")
BUCKET_NAME = os.environ["GTM_RAW_BUCKET"]
AWS_REGION = os.environ.get("AWS_REGION", "eu-north-1")

s3 = boto3.client("s3", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)

DEFAULT_QUERIES = ["conflict", "war", "military", "missile", "airstrike", "protest", "sanctions"]
MAX_DAYS_PER_RUN = 14

EVENT_KEYWORDS = {
    "missile strike": ["missile", "rocket", "ballistic", "strike", "launch"],
    "airstrike": ["airstrike", "air strike", "bombing", "warplane"],
    "drone strike": ["drone", "uav", "shahed"],
    "naval deployment": ["naval", "warship", "carrier", "fleet", "strait", "red sea"],
    "military movement": ["troops", "deployed", "convoy", "military buildup", "exercises"],
    "border clash": ["border clash", "border", "skirmish", "cross-border"],
    "diplomatic escalation": ["sanctions", "ultimatum", "ambassador", "nuclear threat", "warning"],
    "protest": ["protest", "demonstration", "unrest", "riot"],
}

REGION_KEYWORDS = {
    "Middle East": ["iran", "israel", "gaza", "lebanon", "yemen", "syria", "iraq", "houthi", "hamas", "hezbollah", "red sea", "hormuz"],
    "Eastern Europe": ["ukraine", "russia", "kyiv", "moscow", "crimea", "donbas", "kharkiv", "black sea"],
    "East Asia": ["china", "taiwan", "north korea", "south korea", "japan", "taiwan strait", "south china sea"],
    "South Asia": ["india", "pakistan", "afghanistan", "kashmir", "taliban"],
    "Horn of Africa": ["somalia", "ethiopia", "eritrea", "sudan", "red sea", "bab el-mandeb", "houthi"],
    "West Africa": ["mali", "niger", "burkina faso", "nigeria", "sahel", "boko haram"],
    "Mediterranean": ["mediterranean", "libya", "egypt", "suez"],
    "Central Asia": ["kazakhstan", "uzbekistan", "tajikistan", "kyrgyzstan", "armenia", "azerbaijan"],
    "Latin America": ["venezuela", "colombia", "haiti", "ecuador", "cartel"],
}

REGION_COORDS = {
    "Middle East": (29.5, 44.0),
    "Eastern Europe": (50.0, 30.0),
    "East Asia": (24.0, 121.0),
    "South Asia": (30.5, 68.0),
    "Horn of Africa": (10.0, 42.0),
    "West Africa": (12.0, 2.0),
    "Mediterranean": (36.0, 14.0),
    "Central Asia": (41.0, 63.0),
    "Latin America": (-15.0, -55.0),
    "Global": (0.0, 0.0),
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def daterange(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def stable_hash(value: str, length: int = 24) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def gdelt_datetime_start(day: dt.date) -> str:
    return day.strftime("%Y%m%d") + "000000"


def gdelt_datetime_end(day: dt.date) -> str:
    return day.strftime("%Y%m%d") + "235959"


def fetch_gdelt_day(query: str, day: dt.date, maxrecords: int) -> Dict[str, Any]:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(maxrecords),
        "startdatetime": gdelt_datetime_start(day),
        "enddatetime": gdelt_datetime_end(day),
        "sort": "hybridrel",
    }
    url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "global-tension-monitor-backfill/0.1"})
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read().decode("utf-8", errors="replace").strip()
    if not body:
        return {"articles": [], "_status": "empty", "_request": {"url": url, "query": query, "date": day.isoformat()}}
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {"articles": [], "_status": "non_json", "_preview": body[:300], "_request": {"url": url, "query": query, "date": day.isoformat()}}
    data["_status"] = "ok"
    data["_request"] = {"url": url, "query": query, "date": day.isoformat()}
    return data


def classify_event(text: str) -> str:
    lower = text.lower()
    for event_type, keywords in EVENT_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return event_type
    return "geopolitical signal"


def detect_region(text: str) -> Tuple[str, float, float]:
    lower = text.lower()
    for region, keywords in REGION_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            lat, lon = REGION_COORDS[region]
            return region, lat, lon
    return "Global", 0.0, 0.0


def extract_numbers(text: str) -> str:
    matches = re.findall(r"\d+[\.,]?\d*\s*(?:km|soldiers|troops|missiles|strikes|killed|wounded|dead|vessels|jets|aircraft|drones)?", text, flags=re.I)
    return ", ".join(matches[:3]) if matches else "—"


def confidence_score(article: Dict[str, Any], event_type: str, region: str) -> int:
    score = 50
    if article.get("domain"):
        score += 8
    if event_type != "geopolitical signal":
        score += 12
    if region != "Global":
        score += 10
    if article.get("sourcecountry"):
        score += 5
    return max(35, min(92, score))


def save_raw_to_s3(payload: Dict[str, Any], day: dt.date, query: str, ingested_at: str) -> str:
    safe_query = re.sub(r"[^a-zA-Z0-9_-]+", "_", query.lower()).strip("_")[:60]
    key = (
        f"source=gdelt_doc_backfill/year={day.year}/month={day.month:02d}/day={day.day:02d}/"
        f"query={safe_query}/batch-{day.strftime('%Y%m%d')}-{stable_hash(query, 8)}.json.gz"
    )
    payload = {**payload, "_backfill_ingested_at": ingested_at}
    body = gzip.compress(json.dumps(payload).encode("utf-8"))
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=body,
        ContentType="application/json",
        ContentEncoding="gzip",
    )
    return key


def normalize_article(article: Dict[str, Any], raw_s3_key: str, ingested_at: str, query: str, day: dt.date) -> Dict[str, Any]:
    title = article.get("title", "") or ""
    url = article.get("url", "") or ""
    domain = article.get("domain", "") or ""
    source_country = article.get("sourcecountry", "") or ""
    language = article.get("language", "") or ""
    seen_date = article.get("seendate", "") or day.strftime("%Y%m%d") + "120000"
    text = " ".join([title, domain, source_country])

    etype = classify_event(text)
    region, lat, lon = detect_region(text)
    event_id = stable_hash(url or f"{title}|{seen_date}|{domain}|{query}")
    confidence = confidence_score(article, etype, region)

    return {
        "pk": f"REGION#{region}",
        "sk": f"EVENT#{seen_date}#{event_id}",
        "event_id": event_id,
        "source_system": "GDELT_DOC_BACKFILL",
        "source": domain or "GDELT",
        "source_country": source_country,
        "language": language,
        "type": etype,
        "event_type": etype,
        "region": region,
        "lat": str(lat),
        "lon": str(lon),
        "confidence": confidence,
        "summary": title[:280],
        "title": title[:280],
        "url": url,
        "numbers": extract_numbers(title),
        "seen_date": seen_date,
        "time_iso": seen_date,
        "ingested_at": ingested_at,
        "backfill_query": query,
        "backfill_day": day.isoformat(),
        "raw_s3_key": raw_s3_key,
    }


def write_items(items: List[Dict[str, Any]]) -> int:
    written = 0
    with table.batch_writer(overwrite_by_pkeys=["pk", "sk"]) as batch:
        for item in items:
            batch.put_item(Item=item)
            written += 1
    return written


def lambda_handler(event: Optional[Dict[str, Any]], context: Any) -> Dict[str, Any]:
    event = event or {}
    today = dt.datetime.now(dt.timezone.utc).date()
    start = parse_date(event.get("start_date", (today - dt.timedelta(days=7)).isoformat()))
    end = parse_date(event.get("end_date", (today - dt.timedelta(days=1)).isoformat()))
    queries = event.get("queries") or DEFAULT_QUERIES
    maxrecords = int(event.get("maxrecords", 100))

    if end < start:
        raise ValueError("end_date must be >= start_date")

    days = list(daterange(start, end))
    if len(days) > MAX_DAYS_PER_RUN:
        raise ValueError(f"Backfill is capped at {MAX_DAYS_PER_RUN} days per run. Split the date range into smaller chunks.")

    ingested_at = utc_now()
    total_articles = 0
    total_written = 0
    raw_files = 0
    statuses: Dict[str, int] = {}

    for day in days:
        for query in queries:
            payload = fetch_gdelt_day(query=query, day=day, maxrecords=maxrecords)
            status = payload.get("_status", "unknown")
            statuses[status] = statuses.get(status, 0) + 1
            raw_key = save_raw_to_s3(payload, day=day, query=query, ingested_at=ingested_at)
            raw_files += 1
            articles = payload.get("articles", []) or []
            total_articles += len(articles)
            items = [normalize_article(a, raw_key, ingested_at, query, day) for a in articles]
            total_written += write_items(items) if items else 0
            time.sleep(0.2)  # gentle pacing for public API

    result = {
        "statusCode": 200,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "days_processed": len(days),
        "queries": queries,
        "raw_files_written": raw_files,
        "articles_received": total_articles,
        "items_written": total_written,
        "statuses": statuses,
        "table": TABLE_NAME,
        "bucket": BUCKET_NAME,
        "region": AWS_REGION,
        "ingested_at": ingested_at,
    }
    print(json.dumps(result))
    return result
