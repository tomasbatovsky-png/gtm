"""
AWS Lambda collector for Global Tension Monitor.

Purpose:
- Fetch live public geopolitical/news signals from GDELT DOC API.
- Store the complete raw batch in S3 as compressed JSON.
- Store normalized event records in DynamoDB.

Environment variables required in AWS Lambda:
- GTM_EVENTS_TABLE=gtm_events
- GTM_RAW_BUCKET=<your-s3-bucket-name>
- AWS_REGION is set automatically by Lambda; defaults to eu-north-1 in code

IAM permissions required:
- s3:PutObject on the raw bucket
- dynamodb:PutItem / dynamodb:BatchWriteItem on the events table
- logs:* basic Lambda logging permissions
"""

import gzip
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import boto3


TABLE_NAME = os.environ.get("GTM_EVENTS_TABLE", "gtm_events")
BUCKET_NAME = os.environ["GTM_RAW_BUCKET"]
AWS_REGION = os.environ.get("AWS_REGION", "eu-north-1")

s3 = boto3.client("s3", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)


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
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_hash(value: str, length: int = 24) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _fetch_gdelt_url(query: str, timespan: str, maxrecords: str = "75") -> Dict[str, Any]:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": maxrecords,
        "timespan": timespan,
        "sort": "hybridrel",
    }
    url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "global-tension-monitor-aws-lambda/0.2"})
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read().decode("utf-8", errors="replace").strip()

    if not body:
        raise ValueError(f"GDELT returned empty response for query={query!r}, timespan={timespan!r}")

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        preview = body[:300].replace("\n", " ")
        raise ValueError(f"GDELT returned non-JSON response. Preview: {preview}") from exc

    if not isinstance(data, dict):
        raise ValueError("GDELT returned JSON, but not an object")

    data["_request"] = {"query": query, "timespan": timespan, "url": url}
    return data


def fetch_gdelt_articles() -> Dict[str, Any]:
    """Fetch GDELT data with safe fallbacks.

    GDELT occasionally returns an empty body for strict/complex queries. This function
    retries with broader query/time windows instead of failing the whole Lambda.
    """
    attempts = [
        ("war OR conflict OR escalation OR military OR sanctions OR missile OR border OR protest OR naval OR airstrike OR drone", "15min", "75"),
        ("war conflict escalation military sanctions missile border protest", "1hour", "75"),
        ("conflict military", "6hours", "50"),
    ]
    errors: List[str] = []

    for query, timespan, maxrecords in attempts:
        try:
            data = _fetch_gdelt_url(query=query, timespan=timespan, maxrecords=maxrecords)
            data.setdefault("articles", [])
            data["_collector_status"] = "ok"
            if errors:
                data["_collector_previous_errors"] = errors
            return data
        except Exception as exc:
            errors.append(str(exc))
            print(f"[GDELT retry] {exc}")

    # Still return a valid payload so S3/CloudWatch show the failure cleanly.
    return {
        "articles": [],
        "_collector_status": "gdelt_fetch_failed",
        "_collector_errors": errors,
        "_request": {"attempts": len(attempts)},
    }


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
    lat, lon = REGION_COORDS["Global"]
    return "Global", lat, lon


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


def normalize_article(article: Dict[str, Any], raw_s3_key: str, ingested_at: str) -> Dict[str, Any]:
    title = article.get("title", "") or ""
    url = article.get("url", "") or ""
    domain = article.get("domain", "") or ""
    source_country = article.get("sourcecountry", "") or ""
    language = article.get("language", "") or ""
    seen_date = article.get("seendate", "") or ingested_at
    text = " ".join([title, domain, source_country])

    event_type = classify_event(text)
    region, lat, lon = detect_region(text)
    event_id = stable_hash(url or f"{title}|{seen_date}|{domain}")
    confidence = confidence_score(article, event_type, region)

    return {
        "pk": f"REGION#{region}",
        "sk": f"EVENT#{seen_date}#{event_id}",
        "event_id": event_id,
        "source_system": "GDELT_DOC",
        "source": domain or "GDELT",
        "source_country": source_country,
        "language": language,
        "type": event_type,
        "event_type": event_type,
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
        "raw_s3_key": raw_s3_key,
    }


def save_raw_to_s3(payload: Dict[str, Any], ingested_at: str) -> str:
    dt = datetime.fromisoformat(ingested_at.replace("Z", "+00:00"))
    key = (
        f"source=gdelt_doc/year={dt.year}/month={dt.month:02d}/day={dt.day:02d}/"
        f"hour={dt.hour:02d}/batch-{dt.strftime('%Y%m%dT%H%M%SZ')}.json.gz"
    )
    body = gzip.compress(json.dumps(payload).encode("utf-8"))
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=body,
        ContentType="application/json",
        ContentEncoding="gzip",
    )
    return key


def write_items(items: List[Dict[str, Any]]) -> int:
    written = 0
    with table.batch_writer(overwrite_by_pkeys=["pk", "sk"]) as batch:
        for item in items:
            batch.put_item(Item=item)
            written += 1
    return written


def lambda_handler(event: Optional[Dict[str, Any]], context: Any) -> Dict[str, Any]:
    ingested_at = utc_now()
    payload = fetch_gdelt_articles()
    raw_s3_key = save_raw_to_s3(payload, ingested_at)

    articles = payload.get("articles", [])
    items = [normalize_article(article, raw_s3_key, ingested_at) for article in articles]
    written = write_items(items) if items else 0

    result = {
        "statusCode": 200,
        "source": "GDELT_DOC",
        "collector_status": payload.get("_collector_status", "unknown"),
        "raw_s3_key": raw_s3_key,
        "articles_received": len(articles),
        "items_written": written,
        "ingested_at": ingested_at,
        "table": TABLE_NAME,
        "bucket": BUCKET_NAME,
        "region": AWS_REGION,
    }
    if payload.get("_collector_errors"):
        result["collector_errors"] = payload["_collector_errors"]
    if payload.get("_collector_previous_errors"):
        result["collector_previous_errors"] = payload["_collector_previous_errors"]
    print(json.dumps(result))
    return result
