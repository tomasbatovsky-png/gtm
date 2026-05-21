"""
AWS-enabled entrypoint for Global Tension Monitor on Render.

Use this instead of app:app when you want Render to serve the dashboard/API
while AWS Lambda + DynamoDB provide the live data layer.

Render start command:
    uvicorn app_aws:app --host 0.0.0.0 --port $PORT

Required Render environment variables:
    GTM_AWS_ENABLED=true
    AWS_REGION=eu-north-1
    GTM_EVENTS_TABLE=gtm_events
    AWS_ACCESS_KEY_ID=<readonly-render-access-key>
    AWS_SECRET_ACCESS_KEY=<readonly-render-secret>

This wrapper deliberately disables the original Render-side refresh loop from
app.py, so the web process no longer performs RSS ingestion in RAM.
"""

import datetime
from contextlib import asynccontextmanager
from typing import Any, Dict, List

import app as base_app
from aws.render_aws_events import aws_health, fetch_recent_aws_events


app = base_app.app

# Preserve the original fallback function from app.py.
_original_gevents = base_app.gevents

_aws_runtime_cache: Dict[str, Any] = {
    "events": [],
    "last_fetch": None,
    "last_sync": None,
    "ttl_seconds": 60,
}


@asynccontextmanager
async def aws_only_lifespan(_app):
    """Disable the original app.py background refresh_loop on Render.

    AWS Lambda + EventBridge now own ingestion. Render should only read and serve.
    """
    print("[GTM AWS] Render-side ingestion disabled. Using AWS/DynamoDB data layer.")
    yield


# Replace original FastAPI lifespan before ASGI startup.
app.router.lifespan_context = aws_only_lifespan


def _utc_now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _should_refresh_aws_cache() -> bool:
    last_fetch = _aws_runtime_cache.get("last_fetch")
    if not last_fetch:
        return True
    age = (datetime.datetime.utcnow() - last_fetch).total_seconds()
    return age >= int(_aws_runtime_cache.get("ttl_seconds", 60))


def _fallback_forecast(gti: float) -> Dict[str, Any]:
    if gti < 3:
        return {"low_pct": 55, "moderate_pct": 35, "high_pct": 10, "reasoning": "AWS/DynamoDB signals show low current tension."}
    if gti < 5:
        return {"low_pct": 35, "moderate_pct": 45, "high_pct": 20, "reasoning": "AWS/DynamoDB signals show moderate regional tension."}
    if gti < 7:
        return {"low_pct": 20, "moderate_pct": 45, "high_pct": 35, "reasoning": "AWS/DynamoDB signals show elevated escalation risk."}
    return {"low_pct": 10, "moderate_pct": 35, "high_pct": 55, "reasoning": "AWS/DynamoDB signals show high multi-region escalation risk."}


def _sync_base_cache_from_aws(events: List[Dict[str, Any]]) -> None:
    """Populate app.py's existing _cache so old endpoints keep working."""
    if not events:
        return

    now = _utc_now()
    gti_data = base_app.calc_gti(events)
    regional = base_app.calc_regional(events)
    strategic = base_app.detect_strategic(events)
    supply = base_app.calc_supply_chain(events, strategic)
    velocity = base_app.calc_velocity(events)
    alerts = base_app.check_alerts(gti_data["gti"], base_app._cache.get("prev_gti"), events)
    forecast = _fallback_forecast(gti_data["gti"])

    snapshot = {
        "ts": now,
        "gti": gti_data["gti"],
        "event_count": len(events),
        "events": [{k: v for k, v in e.items() if k != "full_text"} for e in events[:100]],
    }
    history = (base_app._cache.get("history", []) + [snapshot])[-144:]

    base_app._cache.update({
        "events": events,
        "history": history,
        "gti_data": gti_data,
        "regional": regional,
        "strategic": strategic,
        "supply_chain": supply,
        "alerts": alerts,
        "prev_gti": gti_data["gti"],
        "last_refresh": now,
        "forecast": forecast,
        "velocity": velocity,
        "source": "aws_dynamodb",
    })
    _aws_runtime_cache["last_sync"] = now


def _get_aws_events_or_fallback() -> List[Dict[str, Any]]:
    if _should_refresh_aws_cache():
        events = fetch_recent_aws_events(limit_per_region=25)
        _aws_runtime_cache["events"] = events
        _aws_runtime_cache["last_fetch"] = datetime.datetime.utcnow()
        if events:
            _sync_base_cache_from_aws(events)
            print(f"[GTM AWS] Loaded {len(events)} events from DynamoDB")
        else:
            print("[GTM AWS] No DynamoDB events available; using original fallback")

    events = _aws_runtime_cache.get("events") or []
    if events:
        return events
    return _original_gevents()


# Monkey-patch app.py's gevents() global so existing route handlers use AWS data.
base_app.gevents = _get_aws_events_or_fallback


@app.middleware("http")
async def aws_cache_middleware(request, call_next):
    """Refresh AWS cache before API calls so legacy endpoints read current data."""
    if request.url.path.startswith("/api/"):
        try:
            _get_aws_events_or_fallback()
        except Exception as exc:
            print(f"[GTM AWS] Cache sync failed: {exc}")
    return await call_next(request)


@app.get("/api/aws-health")
async def api_aws_health():
    health = aws_health()
    return {
        **health,
        "runtime_cache_events": len(_aws_runtime_cache.get("events") or []),
        "runtime_cache_last_sync": _aws_runtime_cache.get("last_sync"),
        "render_ingestion_disabled": True,
        "data_source": base_app._cache.get("source", "fallback"),
    }
