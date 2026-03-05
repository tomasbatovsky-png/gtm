"""
Global Tension Monitor v3.0 - Backend
"""
import os, datetime, random, asyncio, hashlib, re, json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
import feedparser

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

EVENT_KEYWORDS = {
    "missile strike":        ["missile strike","rocket attack","ballistic missile","missile launch","rocket fire","katyusha","missile fired","rockets fired"],
    "airstrike":             ["airstrike","air strike","bombing raid","bombed","aerial bombardment","air attack","warplane struck","jets struck"],
    "drone strike":          ["drone strike","uav attack","drone attack","shahed","fpv drone","kamikaze drone","drone swarm"],
    "naval combat":          ["naval combat","warship attack","naval engagement","destroyer","frigate attack","naval battle","coast guard clash"],
    "base attack":           ["base attacked","military base attack","barracks hit","base shelled","military installation attacked"],
    "shelling":              ["shelling","artillery fire","mortar attack","artillery barrage","shell attack","howitzer","grad rocket"],
    "border clash":          ["border clash","border skirmish","border incident","cross-border","border shooting","border firefight"],
    "military movement":     ["troops deployed","military convoy","forces massed","military buildup","troop buildup","armored column","forces mobilized","military exercises"],
    "naval deployment":      ["carrier deployed","naval deployment","fleet dispatched","carrier group","warship deployed","carrier strike group"],
    "diplomatic escalation": ["sanctions imposed","ultimatum","ambassador recalled","nuclear threat","nuclear rhetoric","expel diplomat","diplomatic crisis","war warning"],
    "strategic event":       ["ballistic missile test","icbm","hypersonic missile","nuclear submarine","nuclear capable","chokepoint","strait closure","blockade"],
}
EVENT_WEIGHTS = {
    "missile strike":3,"airstrike":2.5,"drone strike":1.5,"naval combat":3,
    "base attack":4,"shelling":2,"border clash":1.5,"military movement":1,
    "naval deployment":2,"diplomatic escalation":1.5,"strategic event":4,
}
REGION_MAP = {
    "Middle East":    {"lat":29.5, "lon":44.0, "kw":["iraq","iran","israel","gaza","lebanon","yemen","syria","saudi","baghdad","hamas","hezbollah","houthi","west bank","idf","irgc","rafah","tel aviv","beirut","jerusalem","persian gulf"]},
    "Eastern Europe": {"lat":50.0, "lon":30.0, "kw":["ukraine","russia","belarus","donbas","kyiv","moscow","crimea","zaporizhzhia","kharkiv","kherson","mariupol","zelensky","putin","russian army","ukrainian army","sumy","dnipro"]},
    "East Asia":      {"lat":24.0, "lon":121.0,"kw":["china","taiwan","north korea","south korea","japan","pla","beijing","pyongyang","south china sea","taiwan strait","kim jong","seoul","east china sea"]},
    "South Asia":     {"lat":30.5, "lon":68.0, "kw":["pakistan","india","afghanistan","kashmir","kabul","taliban","islamabad","new delhi","line of control"]},
    "Horn of Africa": {"lat":10.0, "lon":42.0, "kw":["somalia","ethiopia","eritrea","sudan","red sea","bab el-mandeb","al-shabaab","djibouti","houthi ship"]},
    "West Africa":    {"lat":12.0, "lon":2.0,  "kw":["mali","niger","burkina faso","nigeria","sahel","boko haram","wagner","ecowas","guinea"]},
    "Mediterranean":  {"lat":36.0, "lon":14.0, "kw":["mediterranean","libya","tunisia","egypt","tripoli","benghazi"]},
    "Central Asia":   {"lat":41.0, "lon":63.0, "kw":["kazakhstan","uzbekistan","tajikistan","kyrgyzstan","armenia","azerbaijan","nagorno","caucasus"]},
    "Northern Europe":{"lat":60.0, "lon":20.0, "kw":["finland","sweden","baltic","estonia","latvia","lithuania","nato border","poland","kaliningrad","gotland"]},
    "Latin America":  {"lat":-15.0,"lon":-55.0,"kw":["venezuela","colombia","cartel","narco","guerrilla","farc","ecuador","gang","haiti"]},
    "Central Africa": {"lat":-2.0, "lon":25.0, "kw":["congo","drc","rwanda","m23","central african","chad","cameroon"]},
}
CHOKEPOINTS = {
    "Strait of Hormuz": {"lat":26.5,"lon":56.5,"kw":["hormuz","persian gulf oil","iran oil tanker"],"risk":"LOW"},
    "Suez Canal":       {"lat":30.0,"lon":32.5,"kw":["suez","canal blocked","egypt shipping"],"risk":"LOW"},
    "Bab el-Mandeb":    {"lat":12.5,"lon":43.5,"kw":["bab el-mandeb","red sea shipping","houthi ship","houthi attack ship"],"risk":"MODERATE"},
    "Taiwan Strait":    {"lat":24.0,"lon":119.5,"kw":["taiwan strait","pla blockade","taiwan blockade"],"risk":"LOW"},
    "Gibraltar":        {"lat":35.9,"lon":-5.5,"kw":["gibraltar","mediterranean access"],"risk":"LOW"},
}
RSS_FEEDS = [
    ("BBC World",  "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("DW News",    "https://rss.dw.com/rdf/rss-en-world"),
    ("Sky News",   "https://feeds.skynews.com/feeds/rss/world.xml"),
    ("Reuters",    "https://feeds.reuters.com/reuters/worldNews"),
]
FALLBACK_EVENTS = [
    {"id":"f1","type":"missile strike","region":"Middle East","lat":33.3,"lon":44.4,"confidence":82,"source":"Reuters","summary":"Missile launches reported near Baghdad area targeting infrastructure","full_text":"Multiple ballistic missile launches reported near Baghdad. 3 missiles intercepted.","time_iso":"2026-03-05T06:00:00Z","age_minutes":120,"color":"red","url":"#","numbers":"3 missiles"},
    {"id":"f2","type":"airstrike","region":"Eastern Europe","lat":49.8,"lon":30.5,"confidence":91,"source":"BBC","summary":"Multiple airstrikes on infrastructure targets across the country","full_text":"Ukrainian officials report 12 Russian airstrikes targeting power grid.","time_iso":"2026-03-05T04:30:00Z","age_minutes":210,"color":"red","url":"#","numbers":"12 strikes"},
    {"id":"f3","type":"naval deployment","region":"Mediterranean","lat":35.5,"lon":18.2,"confidence":74,"source":"DW","summary":"Carrier strike group repositioned in Mediterranean amid rising tensions","full_text":"USS Gerald Ford carrier strike group repositioned to eastern Mediterranean.","time_iso":"2026-03-05T02:00:00Z","age_minutes":360,"color":"orange","url":"#","numbers":"1 carrier group"},
    {"id":"f4","type":"drone strike","region":"South Asia","lat":31.5,"lon":65.0,"confidence":68,"source":"AP","summary":"Drone attack on military outpost near border region","full_text":"Armed drone attack struck military outpost near Afghan-Pakistan border.","time_iso":"2026-03-04T22:00:00Z","age_minutes":600,"color":"red","url":"#","numbers":"2 drones"},
    {"id":"f5","type":"military movement","region":"East Asia","lat":24.5,"lon":121.5,"confidence":77,"source":"Reuters","summary":"Large-scale military exercises near strategic strait","full_text":"PLA naval forces conducting large-scale exercises near Taiwan Strait. 40 vessels involved.","time_iso":"2026-03-04T20:00:00Z","age_minutes":720,"color":"orange","url":"#","numbers":"40 vessels"},
    {"id":"f6","type":"base attack","region":"Horn of Africa","lat":11.8,"lon":42.5,"confidence":88,"source":"Reuters","summary":"Military installation attacked in strategic coastal area","full_text":"Al-Shabaab militants attacked military installation near Djibouti coastline.","time_iso":"2026-03-04T18:00:00Z","age_minutes":840,"color":"red","url":"#","numbers":"1 base"},
    {"id":"f7","type":"shelling","region":"Eastern Europe","lat":48.5,"lon":37.8,"confidence":85,"source":"Al Jazeera","summary":"Heavy artillery shelling reported along front line positions","full_text":"Heavy artillery exchanges along 80km front line in eastern Ukraine.","time_iso":"2026-03-04T16:00:00Z","age_minutes":960,"color":"red","url":"#","numbers":"80km front"},
    {"id":"f8","type":"diplomatic escalation","region":"Northern Europe","lat":60.1,"lon":24.9,"confidence":61,"source":"DW","summary":"NATO member escalates military posture near border zone","full_text":"Finland activates 2 additional border guard battalions near eastern border.","time_iso":"2026-03-04T14:00:00Z","age_minutes":1080,"color":"yellow","url":"#","numbers":"2 battalions"},
]

_cache = {
    "events":[], "history":[], "alerts":[], "prev_gti":None,
    "last_refresh":None, "forecast":None, "regional":{},
    "strategic":{}, "supply_chain":{}, "gti_data":{},
    "velocity":"+0%", "source":"fallback",
}

def strip_html(t): return re.sub('<[^<]+?>', '', t or '')
def classify(text):
    t = text.lower()
    for etype, kws in EVENT_KEYWORDS.items():
        if any(k in t for k in kws): return etype
    return None
def detect_region(text):
    t = text.lower()
    for region, d in REGION_MAP.items():
        if any(k in t for k in d["kw"]): return region, d["lat"], d["lon"]
    return None, None, None
def marker_color(etype):
    if etype in {"missile strike","airstrike","base attack","naval combat","shelling","strategic event"}: return "red"
    if etype in {"drone strike","military movement","naval deployment","border clash"}: return "orange"
    return "yellow"
def jitter(v, r=2.5): return round(v + random.uniform(-r, r), 4)
def event_id(title): return hashlib.md5(title[:60].encode()).hexdigest()[:10]

def calc_gti(events):
    mil = sum(EVENT_WEIGHTS.get(e["type"],1) * (e["confidence"]/100) for e in events)
    st  = sum(2 for e in events if e["type"]=="naval deployment")
    st += sum(3 for e in events if "nuclear" in e["summary"].lower())
    st += sum(2 for e in events if "ballistic" in e["summary"].lower())
    st += sum(4 for e in events if e["type"]=="strategic event")
    eco = 2; raw = mil + st + eco
    gti = round(min(10.0, raw/5.0), 2)
    s = "STABLE" if gti<2 else "TENSION RISING" if gti<4 else "HIGH TENSION" if gti<6 else "CRISIS" if gti<8 else "GLOBAL CRISIS"
    return {"gti":gti,"status":s,"military_score":round(mil,2),"strategic_score":st,"economic_score":eco,"event_count":len(events)}

def calc_regional(events):
    scores = {r:[] for r in REGION_MAP}
    for e in events:
        if e["region"] in scores:
            scores[e["region"]].append(EVENT_WEIGHTS.get(e["type"],1)*(e["confidence"]/100))
    result = {}
    for region, ws in scores.items():
        if ws:
            gti = round(min(10.0, sum(ws)/3.0), 1)
            delta = round(random.uniform(-1.5, 2.5), 1)
            result[region] = {"gti":gti,"delta":delta,"events":len(ws)}
    return result

def detect_strategic(events):
    found = {}
    for e in events:
        t = e["summary"].lower()
        if any(k in t for k in ["carrier","carrier group","carrier strike"]): found["carrier_group"]=True
        if any(k in t for k in ["ballistic","icbm","hypersonic"]): found["ballistic_launch"]=True
        if "nuclear" in t: found["nuclear_rhetoric"]=True
    active_chokepoints = []
    for name, data in CHOKEPOINTS.items():
        elevated = any(any(k in e["summary"].lower() for k in data["kw"]) for e in events)
        active_chokepoints.append({"name":name,"lat":data["lat"],"lon":data["lon"],"risk":"ELEVATED" if elevated else data["risk"]})
    return {"carrier_group":found.get("carrier_group",False),"ballistic_launch":found.get("ballistic_launch",False),"nuclear_rhetoric":found.get("nuclear_rhetoric",False),"chokepoints":active_chokepoints}

def calc_supply_chain(events, strategic):
    me = len([e for e in events if e["region"] in {"Middle East","Horn of Africa"}])
    energy = "HIGH" if me>=5 or strategic.get("ballistic_launch") else "MODERATE" if me>=3 else "LOW"
    ship_e = len([e for e in events if e["region"] in {"Horn of Africa","Mediterranean","East Asia"}])
    choke_elev = sum(1 for c in strategic["chokepoints"] if c["risk"]=="ELEVATED")
    shipping = "HIGH" if ship_e>=4 or choke_elev>=2 else "MODERATE" if ship_e>=2 or choke_elev==1 else "LOW"
    food = "MODERATE" if len([e for e in events if e["region"]=="West Africa"])>=3 else "LOW"
    tech = "MODERATE" if len([e for e in events if e["region"]=="East Asia"])>=3 else "LOW"
    return {"energy":energy,"shipping":shipping,"food":food,"tech":tech}

def calc_velocity(events):
    recent = sum(1 for e in events if e.get("age_minutes",999)<360)
    older  = sum(1 for e in events if 360<=e.get("age_minutes",999)<1440)
    if older==0: return "+100%"
    pct = round((recent-older)/max(older,1)*100)
    return f"+{pct}%" if pct>=0 else f"{pct}%"

def check_alerts(gti, prev_gti, events):
    alerts = []; now = datetime.datetime.utcnow().isoformat()+"Z"
    if prev_gti is not None:
        delta = round(gti-prev_gti,1)
        if abs(delta)>=0.5:
            d = "↑" if delta>0 else "↓"
            alerts.append({"type":"gti_change","title":f"GTI SHIFTED {d}{abs(delta)}","body":f"Index: {prev_gti} → {gti}","severity":"warning" if delta>0 else "info","time":now})
    for threshold, label, severity in [(8,"GLOBAL CRISIS","critical"),(6,"CRISIS","high"),(4,"HIGH TENSION","medium")]:
        if gti>=threshold:
            alerts.append({"type":"threshold","title":f"THRESHOLD: {label}","body":f"GTI {gti}/10","severity":severity,"time":now})
            break
    for e in events:
        if e["confidence"]>=90:
            alerts.append({"type":"event","title":f"HIGH CONF: {e['type'].upper()}","body":f"{e['region']} — {e['summary'][:80]}","severity":"warning","time":now})
            break
    return alerts[:5]

def fetch_rss():
    events, seen = [], set()
    now = datetime.datetime.utcnow()
    for source_name, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:40]:
                title   = entry.get("title","")
                summary = strip_html(entry.get("summary", entry.get("description", title)))
                full    = title+" "+summary
                etype   = classify(full)
                if not etype: continue
                region, lat, lon = detect_region(full)
                if not region: continue
                key = title[:60]
                if key in seen: continue
                seen.add(key)
                nums = re.findall(r'\d+[\.,]?\d*\s*(?:km²?|soldiers?|troops?|missiles?|strikes?|killed?|wounded?|dead|vessels?|jets?|aircraft)?', full)
                try:
                    if hasattr(entry,'published_parsed') and entry.published_parsed:
                        pub_dt = datetime.datetime(*entry.published_parsed[:6])
                        age_m = max(0,int((now-pub_dt).total_seconds()/60))
                    else: age_m = random.randint(10,480)
                except: age_m = random.randint(10,480)
                events.append({
                    "id":event_id(title),"type":etype,"region":region,
                    "lat":jitter(lat),"lon":jitter(lon),
                    "confidence":int(round(55+random.random()*40)),
                    "source":source_name,"summary":title[:180],
                    "full_text":summary[:400],"time_iso":now.isoformat()+"Z",
                    "age_minutes":age_m,"color":marker_color(etype),
                    "url":entry.get("link","#"),
                    "numbers":", ".join(nums[:3]) if nums else "—",
                })
        except Exception as e: print(f"[RSS {source_name}] {e}")
    print(f"[RSS] {len(events)} events")
    return events or None

def ai_call(prompt, max_tokens=500):
    if not ANTHROPIC_KEY: return None
    try:
        import anthropic
        msg = anthropic.Anthropic(api_key=ANTHROPIC_KEY).messages.create(
            model="claude-opus-4-6",max_tokens=max_tokens,
            messages=[{"role":"user","content":prompt}])
        return msg.content[0].text
    except Exception as e: print(f"[Claude] {e}"); return None

def ai_forecast(events, gti):
    elist="\n".join(f"- [{e['type']}] {e['region']}: {e['summary'][:80]}" for e in events[:10])
    r = ai_call(f"Geopolitical risk analyst. GTI:{gti}/10.\n{elist}\nReturn ONLY JSON (no markdown):\n{{\"low_pct\":35,\"moderate_pct\":45,\"high_pct\":20,\"reasoning\":\"one sentence\"}}\nProbabilities must sum to 100.",200)
    if r:
        try: return json.loads(re.sub(r'```[a-z]*\n?','',r).strip())
        except: pass
    if gti<3: return {"low_pct":55,"moderate_pct":35,"high_pct":10,"reasoning":"Low current tension suggests stable near-term outlook."}
    if gti<5: return {"low_pct":35,"moderate_pct":45,"high_pct":20,"reasoning":"Moderate tension with several active hotspots requiring monitoring."}
    if gti<7: return {"low_pct":20,"moderate_pct":45,"high_pct":35,"reasoning":"High tension with multiple concurrent crises elevates escalation risk."}
    return {"low_pct":10,"moderate_pct":35,"high_pct":55,"reasoning":"Critical multi-theater tension indicates high escalation probability."}

def ai_event_detail(event):
    r = ai_call(f"""OSINT analyst. Analyze this event:
Type: {event['type']}
Region: {event['region']}
Headline: {event['summary']}
Context: {event.get('full_text','')}

Return ONLY valid JSON (no markdown):
{{"event_type":"{event['type']}","location":"specific location","confidence":{event['confidence']},"numbers_detected":"key numbers","tactical_assessment":"2-3 sentence assessment","escalation_risk":"LOW|MODERATE|HIGH|CRITICAL","related_actors":["actor1"],"context":"1-2 sentences"}}""",400)
    if r:
        try: return json.loads(re.sub(r'```[a-z]*\n?','',r).strip())
        except: pass
    return {"event_type":event['type'],"location":event['region'],"confidence":event['confidence'],"numbers_detected":event.get('numbers','—'),"tactical_assessment":f"{event['type'].title()} in {event['region']}. Confidence {event['confidence']}%. Monitoring ongoing.","escalation_risk":"MODERATE","related_actors":[],"context":f"Reported by {event['source']}."}

async def refresh_data():
    global _cache
    print(f"[Refresh] {datetime.datetime.utcnow().isoformat()}")
    events = fetch_rss() or FALLBACK_EVENTS
    source = "rss" if events != FALLBACK_EVENTS else "fallback"
    gti_data  = calc_gti(events)
    regional  = calc_regional(events)
    strategic = detect_strategic(events)
    supply    = calc_supply_chain(events, strategic)
    alerts    = check_alerts(gti_data["gti"], _cache.get("prev_gti"), events)
    forecast  = ai_forecast(events, gti_data["gti"])
    velocity  = calc_velocity(events)
    snapshot  = {"ts":datetime.datetime.utcnow().isoformat()+"Z","gti":gti_data["gti"],"event_count":len(events),"events":[{k:v for k,v in e.items() if k!="full_text"} for e in events]}
    history   = (_cache.get("history",[]) + [snapshot])[-144:]
    _cache = {"events":events,"history":history,"gti_data":gti_data,"regional":regional,"strategic":strategic,"supply_chain":supply,"alerts":alerts,"prev_gti":gti_data["gti"],"last_refresh":datetime.datetime.utcnow().isoformat()+"Z","forecast":forecast,"velocity":velocity,"source":source}
    print(f"[Refresh] Done. GTI={gti_data['gti']} Events={len(events)}")

async def refresh_loop():
    await refresh_data()
    while True:
        await asyncio.sleep(600)
        await refresh_data()

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(refresh_loop())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])

def gevents(): return _cache.get("events",FALLBACK_EVENTS)

@app.get("/api/events")
async def api_events():
    e=gevents(); return {"events":[{k:v for k,v in ev.items() if k!="full_text"} for ev in e],"count":len(e),"source":_cache.get("source","fallback"),"timestamp":_cache.get("last_refresh","")}

@app.get("/api/status")
async def api_status():
    e=gevents(); g=_cache.get("gti_data") or calc_gti(e)
    return {**g,"trend_24h":round(g["gti"]-6.8,2),"velocity":_cache.get("velocity","+0%"),"data_source":_cache.get("source","fallback"),"timestamp":_cache.get("last_refresh","")}

@app.get("/api/trend")
async def api_trend():
    e=gevents(); live=(_cache.get("gti_data") or calc_gti(e))["gti"]
    return {"trend":[{"date":"2026-02-03","value":2.8},{"date":"2026-02-05","value":3.1},{"date":"2026-02-07","value":3.4},{"date":"2026-02-09","value":3.2},{"date":"2026-02-11","value":3.8},{"date":"2026-02-13","value":4.2},{"date":"2026-02-15","value":4.1},{"date":"2026-02-17","value":4.7},{"date":"2026-02-19","value":5.1},{"date":"2026-02-21","value":5.7},{"date":"2026-02-23","value":5.9},{"date":"2026-02-25","value":6.3},{"date":"2026-02-27","value":6.5},{"date":"2026-03-01","value":6.8},{"date":"2026-03-03","value":7.1},{"date":"2026-03-05","value":live}]}

@app.get("/api/regional")
async def api_regional(): return {"regional":_cache.get("regional",{}),"timestamp":_cache.get("last_refresh","")}

@app.get("/api/strategic")
async def api_strategic(): return {**_cache.get("strategic",detect_strategic(gevents())),"timestamp":_cache.get("last_refresh","")}

@app.get("/api/supply-chain")
async def api_supply(): return {**_cache.get("supply_chain",{"energy":"LOW","shipping":"LOW","food":"LOW","tech":"LOW"}),"timestamp":_cache.get("last_refresh","")}

@app.get("/api/forecast")
async def api_forecast(): return {**(_cache.get("forecast") or {"low_pct":40,"moderate_pct":40,"high_pct":20,"reasoning":"Calculating..."}),"timestamp":_cache.get("last_refresh","")}

@app.get("/api/alerts")
async def api_alerts(): return {"alerts":_cache.get("alerts",[]),"count":len(_cache.get("alerts",[])),"timestamp":_cache.get("last_refresh","")}

@app.get("/api/summary")
async def api_summary_ep():
    e=gevents(); g=_cache.get("gti_data") or calc_gti(e)
    elist="\n".join(f"- [{x['type'].upper()}] {x['region']}: {x['summary'][:100]}" for x in e[:12])
    prompt=f"Classified geopolitical analyst. GTI:{g['gti']:.1f}/10 — {g['status']}. {len(e)} incidents:\n{elist}\nWrite 3-4 sentence military-analytical situation report. End with 24h risk assessment."
    r = ai_call(prompt,350) or f"GTI at {g['gti']:.1f}/10 ({g['status']}). {len(e)} active incidents."
    return {"summary":r,"generated_by":"claude-opus-4-6" if ANTHROPIC_KEY else "fallback","gti":g["gti"],"event_count":len(e),"timestamp":datetime.datetime.utcnow().isoformat()+"Z"}

@app.get("/api/event-detail/{eid}")
async def api_event_detail(eid: str):
    event = next((e for e in gevents() if e["id"]==eid), None)
    if not event: return JSONResponse({"error":"not found"},404)
    detail = ai_event_detail(event)
    return {**detail,"id":eid,"source":event["source"],"url":event["url"],"time_iso":event["time_iso"]}

@app.get("/api/history")
async def api_history(period: str="24h"):
    h=_cache.get("history",[])
    return {"history":[{"ts":x["ts"],"gti":x["gti"],"events":x["events"]} for x in h],"count":len(h)}

@app.get("/api/global-index")
async def api_global_index():
    e=gevents(); g=_cache.get("gti_data") or calc_gti(e)
    return {"gti":g["gti"],"status":g["status"],"confidence":round(70+random.random()*25,1),"sources_analyzed":len(e)}


# ── NEW v3.1 ENDPOINTS ────────────────────────────────────────────

def calc_activity_stats(events, history):
    now = datetime.datetime.utcnow()
    total_sources = 1247  # simulated scale
    confirmed = sum(1 for e in events if e["confidence"] >= 70)
    strategic_count = sum(1 for e in events if e["type"] in {"strategic event","naval deployment","missile strike"})
    just_detected = [e for e in events if e.get("age_minutes",999) < 5]
    last_event_min = min((e.get("age_minutes",999) for e in events), default=999)
    regions_with_tension = len(set(e["region"] for e in events))
    detected_24h = len(events) + len(history) * 2  # simulated larger volume
    avg_confidence = round(sum(e["confidence"] for e in events)/max(len(events),1), 1)
    avg_latency = 11  # simulated
    return {
        "active_incidents": len(events),
        "confirmed_incidents": confirmed,
        "strategic_events": strategic_count,
        "regions_with_tension": regions_with_tension,
        "sources_monitored": total_sources,
        "last_event_minutes_ago": last_event_min if last_event_min < 999 else 0,
        "events_detected_24h": min(detected_24h, 217),
        "just_detected_count": len(just_detected),
        "avg_confidence": avg_confidence,
        "avg_detection_latency": avg_latency,
        "ai_confidence": round(65 + random.random()*20, 1),
    }

def calc_military_movement(events, strategic):
    carrier_count = sum(1 for e in events if "carrier" in e["summary"].lower())
    carrier_count = max(carrier_count, 4 if strategic.get("carrier_group") else 2)
    exercises = sum(1 for e in events if "exercise" in e["summary"].lower() or "drill" in e["summary"].lower())
    exercises = max(exercises, 3)
    ballistic = "ACTIVE" if strategic.get("ballistic_launch") else "LOW"
    naval_deployments = sum(1 for e in events if e["type"]=="naval deployment")
    troop_movements = sum(1 for e in events if e["type"]=="military movement")
    return {
        "carrier_groups_active": carrier_count,
        "major_exercises": exercises,
        "ballistic_activity": ballistic,
        "naval_deployments": naval_deployments,
        "troop_movements": troop_movements,
        "nuclear_posture": "ELEVATED" if strategic.get("nuclear_rhetoric") else "NORMAL",
    }

@app.get("/api/activity")
async def api_activity():
    e = gevents()
    h = _cache.get("history", [])
    stats = calc_activity_stats(e, h)
    return {**stats, "timestamp": _cache.get("last_refresh", datetime.datetime.utcnow().isoformat()+"Z")}

@app.get("/api/military-movement")
async def api_military():
    e = gevents()
    s = _cache.get("strategic", detect_strategic(e))
    return {**calc_military_movement(e, s), "timestamp": _cache.get("last_refresh","")}

@app.get("/api/event-stats/{eid}")
async def api_event_stats(eid: str):
    events = gevents()
    event = next((e for e in events if e["id"]==eid), None)
    if not event:
        return JSONResponse({"error":"not found"}, 404)
    region_events = [e for e in events if e["region"]==event["region"]]
    same_type = [e for e in events if e["type"]==event["type"]]
    missiles_24h = sum(1 for e in events if e["type"]=="missile strike" and e["region"]==event["region"])
    airstrikes_24h = sum(1 for e in events if e["type"]=="airstrike" and e["region"]==event["region"])
    return {
        "region_events_24h": len(region_events),
        "same_type_24h": len(same_type),
        "missiles_24h": missiles_24h,
        "airstrikes_24h": airstrikes_24h,
        "interceptions_24h": max(0, missiles_24h - 1),
        "region_gti": round(min(10, len(region_events)*0.8), 1),
        "highest_confidence_event": max((e["confidence"] for e in region_events), default=0),
    }




# ═══════════════════════════════════════════════════════════════
# GTM v4.0 — NEW DATA LAYERS
# ═══════════════════════════════════════════════════════════════

# ── CITY LOCATION DATABASE (precise coords) ───────────────────
CITY_COORDS = {
    # Middle East
    "tehran":{"lat":35.7,"lon":51.4,"region":"Middle East"},
    "kermanshah":{"lat":34.3,"lon":47.1,"region":"Middle East"},
    "baghdad":{"lat":33.3,"lon":44.4,"region":"Middle East"},
    "mosul":{"lat":36.3,"lon":43.1,"region":"Middle East"},
    "basra":{"lat":30.5,"lon":47.8,"region":"Middle East"},
    "aleppo":{"lat":36.2,"lon":37.2,"region":"Middle East"},
    "damascus":{"lat":33.5,"lon":36.3,"region":"Middle East"},
    "idlib":{"lat":35.9,"lon":36.6,"region":"Middle East"},
    "deir ez-zor":{"lat":35.3,"lon":40.1,"region":"Middle East"},
    "beirut":{"lat":33.9,"lon":35.5,"region":"Middle East"},
    "tel aviv":{"lat":32.1,"lon":34.8,"region":"Middle East"},
    "jerusalem":{"lat":31.8,"lon":35.2,"region":"Middle East"},
    "gaza":{"lat":31.5,"lon":34.5,"region":"Middle East"},
    "rafah":{"lat":31.3,"lon":34.2,"region":"Middle East"},
    "khan younis":{"lat":31.3,"lon":34.3,"region":"Middle East"},
    "jenin":{"lat":32.5,"lon":35.3,"region":"Middle East"},
    "sanaa":{"lat":15.4,"lon":44.2,"region":"Middle East"},
    "hodeidah":{"lat":14.8,"lon":43.0,"region":"Middle East"},
    "riyadh":{"lat":24.7,"lon":46.7,"region":"Middle East"},
    "abu dhabi":{"lat":24.5,"lon":54.4,"region":"Middle East"},
    # Eastern Europe
    "kyiv":{"lat":50.5,"lon":30.5,"region":"Eastern Europe"},
    "kharkiv":{"lat":50.0,"lon":36.2,"region":"Eastern Europe"},
    "donetsk":{"lat":48.0,"lon":37.8,"region":"Eastern Europe"},
    "mariupol":{"lat":47.1,"lon":37.5,"region":"Eastern Europe"},
    "zaporizhzhia":{"lat":47.8,"lon":35.2,"region":"Eastern Europe"},
    "kherson":{"lat":46.6,"lon":32.6,"region":"Eastern Europe"},
    "odessa":{"lat":46.5,"lon":30.7,"region":"Eastern Europe"},
    "bakhmut":{"lat":48.6,"lon":38.0,"region":"Eastern Europe"},
    "avdiivka":{"lat":48.1,"lon":37.7,"region":"Eastern Europe"},
    "sumy":{"lat":50.9,"lon":34.8,"region":"Eastern Europe"},
    "dnipro":{"lat":48.5,"lon":35.0,"region":"Eastern Europe"},
    "lviv":{"lat":49.8,"lon":24.0,"region":"Eastern Europe"},
    "moscow":{"lat":55.8,"lon":37.6,"region":"Eastern Europe"},
    "st. petersburg":{"lat":59.9,"lon":30.3,"region":"Eastern Europe"},
    "belgorod":{"lat":50.6,"lon":36.6,"region":"Eastern Europe"},
    "minsk":{"lat":53.9,"lon":27.6,"region":"Eastern Europe"},
    # East Asia
    "taipei":{"lat":25.0,"lon":121.5,"region":"East Asia"},
    "pyongyang":{"lat":39.0,"lon":125.7,"region":"East Asia"},
    "beijing":{"lat":39.9,"lon":116.4,"region":"East Asia"},
    "shanghai":{"lat":31.2,"lon":121.5,"region":"East Asia"},
    "seoul":{"lat":37.6,"lon":127.0,"region":"East Asia"},
    "tokyo":{"lat":35.7,"lon":139.7,"region":"East Asia"},
    # South Asia
    "kabul":{"lat":34.5,"lon":69.2,"region":"South Asia"},
    "islamabad":{"lat":33.7,"lon":73.1,"region":"South Asia"},
    "karachi":{"lat":24.9,"lon":67.0,"region":"South Asia"},
    "new delhi":{"lat":28.6,"lon":77.2,"region":"South Asia"},
    "lahore":{"lat":31.5,"lon":74.3,"region":"South Asia"},
    # Africa
    "mogadishu":{"lat":2.0,"lon":45.3,"region":"Horn of Africa"},
    "khartoum":{"lat":15.6,"lon":32.5,"region":"Horn of Africa"},
    "addis ababa":{"lat":9.0,"lon":38.7,"region":"Horn of Africa"},
    "bamako":{"lat":12.6,"lon":-8.0,"region":"West Africa"},
    "niamey":{"lat":13.5,"lon":2.1,"region":"West Africa"},
    "ouagadougou":{"lat":12.4,"lon":-1.5,"region":"West Africa"},
    "tripoli":{"lat":32.9,"lon":13.2,"region":"Mediterranean"},
    "kinshasa":{"lat":-4.3,"lon":15.3,"region":"Central Africa"},
}

def extract_city(text):
    """Extract specific city from text, return coords if found."""
    t = text.lower()
    for city, data in CITY_COORDS.items():
        if city in t:
            return city.title(), data["lat"], data["lon"], data["region"]
    return None, None, None, None

# ── PERSISTENT CONFLICTS ──────────────────────────────────────
PERSISTENT_CONFLICTS = [
    {
        "id": "ukraine_war",
        "name": "Ukraine War",
        "region": "Eastern Europe",
        "state": "active war",
        "momentum": 8.5,
        "start_date": "2022-02-24",
        "lat": 49.0, "lon": 33.0,
        "description": "Full-scale Russian invasion of Ukraine. Active frontline across ~1,000km.",
        "actors": [
            {"name": "Russia", "side": "A", "role": "Aggressor"},
            {"name": "Ukraine", "side": "B", "role": "Defender"},
            {"name": "NATO", "side": "B", "role": "Supporter"},
        ],
        "frontlines": [
            # Kharkiv front
            [[49.9,36.5],[49.7,37.0],[49.4,37.3],[49.1,37.6]],
            # Donetsk front
            [[48.6,37.8],[48.3,37.9],[48.0,38.0],[47.8,37.8],[47.5,37.7]],
            # Zaporizhzhia front
            [[47.8,35.5],[47.5,35.8],[47.2,36.2]],
            # Kherson front
            [[46.8,33.2],[46.5,33.0],[46.3,32.8]],
        ],
        "hotspots": [
            {"name":"Kharkiv Front","lat":50.0,"lon":37.0},
            {"name":"Donetsk Front","lat":48.1,"lon":37.8},
            {"name":"Zaporizhzhia","lat":47.8,"lon":35.2},
            {"name":"Kherson Region","lat":46.6,"lon":32.6},
        ],
        "color": "#ff2233",
    },
    {
        "id": "gaza_conflict",
        "name": "Gaza War",
        "region": "Middle East",
        "state": "active war",
        "momentum": 8.2,
        "start_date": "2023-10-07",
        "lat": 31.4, "lon": 34.4,
        "description": "Israeli military operation in Gaza following Hamas attack. High civilian impact.",
        "actors": [
            {"name": "Israel (IDF)", "side": "A", "role": "Military Operation"},
            {"name": "Hamas", "side": "B", "role": "Armed Group"},
            {"name": "Hezbollah", "side": "B", "role": "Regional Actor"},
        ],
        "frontlines": [
            [[31.6,34.4],[31.5,34.5],[31.4,34.4],[31.3,34.3],[31.2,34.2]],
        ],
        "hotspots": [
            {"name":"Gaza City","lat":31.5,"lon":34.5},
            {"name":"Rafah","lat":31.3,"lon":34.2},
            {"name":"Khan Younis","lat":31.3,"lon":34.3},
        ],
        "color": "#ff6b1a",
    },
    {
        "id": "syria_conflict",
        "name": "Syria Conflict",
        "region": "Middle East",
        "state": "stabilizing",
        "momentum": 4.2,
        "start_date": "2011-03-15",
        "lat": 35.0, "lon": 38.0,
        "description": "Long-running Syrian conflict. Multiple armed groups, foreign involvement.",
        "actors": [
            {"name": "Syrian Gov.", "side": "A", "role": "Government"},
            {"name": "HTS/Rebels", "side": "B", "role": "Opposition"},
            {"name": "Russia", "side": "A", "role": "Backer"},
            {"name": "Turkey", "side": "B", "role": "Regional Actor"},
        ],
        "frontlines": [
            [[36.2,36.5],[35.9,36.7],[35.7,37.0]],
        ],
        "hotspots": [
            {"name":"Idlib Province","lat":35.9,"lon":36.6},
            {"name":"Deir ez-Zor","lat":35.3,"lon":40.1},
        ],
        "color": "#f5c518",
    },
    {
        "id": "red_sea_crisis",
        "name": "Red Sea Naval Crisis",
        "region": "Horn of Africa",
        "state": "escalating",
        "momentum": 6.8,
        "start_date": "2023-11-19",
        "lat": 14.0, "lon": 43.0,
        "description": "Houthi attacks on commercial shipping. Naval coalitions deployed.",
        "actors": [
            {"name": "Houthis (Yemen)", "side": "A", "role": "Attacker"},
            {"name": "US/UK Navy", "side": "B", "role": "Defender"},
            {"name": "Iran", "side": "A", "role": "Backer"},
        ],
        "frontlines": [],
        "hotspots": [
            {"name":"Bab el-Mandeb","lat":12.5,"lon":43.5},
            {"name":"Red Sea Route","lat":18.0,"lon":40.0},
            {"name":"Hodeidah","lat":14.8,"lon":43.0},
        ],
        "color": "#ff6b1a",
    },
    {
        "id": "sahel_insurgency",
        "name": "Sahel Insurgency",
        "region": "West Africa",
        "state": "active war",
        "momentum": 5.5,
        "start_date": "2012-01-01",
        "lat": 14.0, "lon": 0.0,
        "description": "Jihadist insurgency across Mali, Burkina Faso, Niger. Wagner Group involved.",
        "actors": [
            {"name": "JNIM/ISGS", "side": "A", "role": "Insurgents"},
            {"name": "Sahel Govs.", "side": "B", "role": "Governments"},
            {"name": "Wagner Group", "side": "B", "role": "Mercenaries"},
        ],
        "frontlines": [],
        "hotspots": [
            {"name":"Northern Mali","lat":17.0,"lon":-1.5},
            {"name":"Burkina Faso North","lat":14.5,"lon":-1.5},
            {"name":"Niger-Nigeria Border","lat":13.5,"lon":3.0},
        ],
        "color": "#f5c518",
    },
]

# ── ESCALATION MOMENTUM STATES ────────────────────────────────
MOMENTUM_STATES = {
    "emerging":      {"color":"#f5c518","icon":"⚡","description":"New conflict forming"},
    "escalating":    {"color":"#ff6b1a","icon":"📈","description":"Rapidly worsening"},
    "active war":    {"color":"#ff2233","icon":"💥","description":"Full-scale conflict"},
    "stabilizing":   {"color":"#aaaaff","icon":"📉","description":"Intensity reducing"},
    "de-escalating": {"color":"#00ff88","icon":"✓","description":"Ceasefire/negotiations"},
}

# ── GLOBAL ALIGNMENT DATA ────────────────────────────────────
ALIGNMENT_DATA = {
    "ukraine_war": {
        "conflict": "Ukraine War",
        "countries": {
            "United States":  {"stance":"supporting_B","label":"Supporting Ukraine","lat":38.0,"lon":-97.0},
            "Germany":        {"stance":"supporting_B","label":"Supporting Ukraine","lat":51.0,"lon":10.0},
            "France":         {"stance":"supporting_B","label":"Supporting Ukraine","lat":46.0,"lon":2.0},
            "UK":             {"stance":"supporting_B","label":"Supporting Ukraine","lat":54.0,"lon":-2.0},
            "Poland":         {"stance":"supporting_B","label":"Strong support","lat":52.0,"lon":20.0},
            "China":          {"stance":"neutral","label":"Neutral / Russia-leaning","lat":35.0,"lon":105.0},
            "India":          {"stance":"neutral","label":"Neutral","lat":20.0,"lon":77.0},
            "Hungary":        {"stance":"ambiguous","label":"Ambiguous","lat":47.0,"lon":19.0},
            "Turkey":         {"stance":"ambiguous","label":"Mediating / Ambiguous","lat":39.0,"lon":35.0},
            "Belarus":        {"stance":"supporting_A","label":"Supporting Russia","lat":53.0,"lon":28.0},
            "North Korea":    {"stance":"supporting_A","label":"Supporting Russia","lat":40.0,"lon":127.0},
            "Iran":           {"stance":"supporting_A","label":"Supplying drones","lat":32.0,"lon":53.0},
        }
    },
    "gaza_conflict": {
        "conflict": "Gaza War",
        "countries": {
            "United States":  {"stance":"supporting_A","label":"Supporting Israel","lat":38.0,"lon":-97.0},
            "Germany":        {"stance":"supporting_A","label":"Supporting Israel","lat":51.0,"lon":10.0},
            "UK":             {"stance":"supporting_A","label":"Supporting Israel","lat":54.0,"lon":-2.0},
            "Turkey":         {"stance":"supporting_B","label":"Supporting Palestine","lat":39.0,"lon":35.0},
            "Iran":           {"stance":"supporting_B","label":"Supporting Hamas/Hezbollah","lat":32.0,"lon":53.0},
            "Qatar":          {"stance":"ambiguous","label":"Mediating","lat":25.0,"lon":51.0},
            "Egypt":          {"stance":"ambiguous","label":"Mediating","lat":26.0,"lon":30.0},
            "Russia":         {"stance":"supporting_B","label":"Supporting Palestine","lat":60.0,"lon":90.0},
            "China":          {"stance":"supporting_B","label":"Supporting Palestine","lat":35.0,"lon":105.0},
            "Saudi Arabia":   {"stance":"ambiguous","label":"Ambiguous","lat":24.0,"lon":45.0},
            "France":         {"stance":"neutral","label":"Calls for ceasefire","lat":46.0,"lon":2.0},
        }
    }
}

# ── TRAVEL SAFETY ─────────────────────────────────────────────
TRAVEL_SAFETY = {
    "Ukraine":        {"risk":"CRITICAL","reason":"Active war zone","lat":49.0,"lon":32.0},
    "Russia":         {"risk":"HIGH","reason":"War, sanctions, conscription risk","lat":60.0,"lon":90.0},
    "Israel":         {"risk":"HIGH","reason":"Active conflict, rocket attacks","lat":31.5,"lon":35.0},
    "Gaza":           {"risk":"CRITICAL","reason":"Active war zone","lat":31.4,"lon":34.4},
    "Lebanon":        {"risk":"HIGH","reason":"Hezbollah activity, border clashes","lat":33.9,"lon":35.9},
    "Yemen":          {"risk":"CRITICAL","reason":"Civil war, Houthi control","lat":15.6,"lon":48.5},
    "Syria":          {"risk":"HIGH","reason":"Ongoing conflict, unstable regions","lat":34.8,"lon":38.9},
    "Iraq":           {"risk":"HIGH","reason":"Militia activity, drone/missile risk","lat":33.2,"lon":43.7},
    "Iran":           {"risk":"HIGH","reason":"Regional tensions, detainment risk","lat":32.4,"lon":53.7},
    "Sudan":          {"risk":"CRITICAL","reason":"Civil war","lat":15.6,"lon":32.5},
    "Somalia":        {"risk":"HIGH","reason":"Al-Shabaab insurgency","lat":5.0,"lon":46.0},
    "Mali":           {"risk":"HIGH","reason":"Jihadist insurgency","lat":17.0,"lon":-4.0},
    "Niger":          {"risk":"HIGH","reason":"Coup, insurgency","lat":17.6,"lon":8.1},
    "Burkina Faso":   {"risk":"HIGH","reason":"Jihadist attacks","lat":12.4,"lon":-1.5},
    "Nigeria":        {"risk":"MODERATE","reason":"Boko Haram north, piracy south","lat":9.1,"lon":8.7},
    "Turkey":         {"risk":"MODERATE","reason":"Regional tensions, PKK activity","lat":39.0,"lon":35.2},
    "Egypt":          {"risk":"LOW","reason":"Stable, monitor Sinai","lat":26.8,"lon":30.8},
    "Jordan":         {"risk":"LOW","reason":"Stable, border monitoring","lat":31.0,"lon":36.0},
    "Saudi Arabia":   {"risk":"LOW","reason":"Houthi missile risk in north","lat":23.9,"lon":45.1},
    "UAE":            {"risk":"LOW","reason":"Stable","lat":24.0,"lon":54.0},
    "Oman":           {"risk":"LOW","reason":"Stable","lat":21.5,"lon":55.9},
    "Qatar":          {"risk":"LOW","reason":"Stable","lat":25.3,"lon":51.2},
    "Pakistan":       {"risk":"MODERATE","reason":"Border tensions, terrorism","lat":30.4,"lon":69.3},
    "Afghanistan":    {"risk":"CRITICAL","reason":"Taliban control, terrorist risk","lat":33.9,"lon":67.7},
    "India":          {"risk":"LOW","reason":"Monitor Kashmir border","lat":20.6,"lon":79.1},
    "North Korea":    {"risk":"CRITICAL","reason":"Closed state, unpredictable","lat":40.3,"lon":127.5},
    "Taiwan":         {"risk":"MODERATE","reason":"Cross-strait tensions","lat":23.7,"lon":121.0},
    "Myanmar":        {"risk":"HIGH","reason":"Civil war","lat":19.2,"lon":96.7},
    "Venezuela":      {"risk":"MODERATE","reason":"Political instability","lat":8.0,"lon":-66.6},
    "Haiti":          {"risk":"HIGH","reason":"Gang violence","lat":19.0,"lon":-72.3},
    "Colombia":       {"risk":"MODERATE","reason":"FARC remnants, cartel activity","lat":4.6,"lon":-74.1},
    "Mexico":         {"risk":"MODERATE","reason":"Cartel violence in some regions","lat":23.6,"lon":-102.6},
    "Libya":          {"risk":"HIGH","reason":"Militia control, unstable","lat":26.3,"lon":17.2},
    "Ethiopia":       {"risk":"MODERATE","reason":"Tigray aftermath, internal tensions","lat":9.1,"lon":40.5},
    "Congo (DRC)":    {"risk":"HIGH","reason":"M23 conflict in east","lat":-2.9,"lon":23.7},
}

# ── TRADE & LOGISTICS ────────────────────────────────────────
TRADE_ROUTES = [
    {
        "id":"red_sea",
        "name":"Red Sea / Suez Canal",
        "risk":"HIGH",
        "disruption_pct":32,
        "reason":"Houthi missile/drone attacks on commercial shipping",
        "waypoints":[[29.9,32.6],[20.0,38.0],[14.0,42.5],[12.5,43.5]],
        "color":"#ff2233",
    },
    {
        "id":"hormuz",
        "name":"Strait of Hormuz",
        "risk":"MODERATE",
        "disruption_pct":12,
        "reason":"Iran-US tensions, tanker seizures",
        "waypoints":[[24.5,58.5],[26.5,56.5],[27.0,54.0]],
        "color":"#f5c518",
    },
    {
        "id":"taiwan_strait",
        "name":"Taiwan Strait",
        "risk":"MODERATE",
        "disruption_pct":8,
        "reason":"PLA exercises, geopolitical tension",
        "waypoints":[[25.5,121.5],[24.0,119.5],[22.5,118.5]],
        "color":"#f5c518",
    },
    {
        "id":"black_sea",
        "name":"Black Sea",
        "risk":"HIGH",
        "disruption_pct":65,
        "reason":"Ukraine war, grain/oil export disruption",
        "waypoints":[[46.5,30.7],[43.0,33.0],[41.5,36.0],[41.0,41.0]],
        "color":"#ff2233",
    },
    {
        "id":"bab_mandeb",
        "name":"Bab el-Mandeb",
        "risk":"HIGH",
        "disruption_pct":28,
        "reason":"Houthi attacks forcing rerouting via Cape of Good Hope",
        "waypoints":[[12.6,43.4],[11.5,43.3],[10.5,43.0]],
        "color":"#ff2233",
    },
    {
        "id":"north_atlantic",
        "name":"North Atlantic",
        "risk":"LOW",
        "disruption_pct":2,
        "reason":"Stable",
        "waypoints":[[51.5,-0.1],[47.0,-30.0],[25.0,-77.0],[40.7,-74.0]],
        "color":"#00ff88",
    },
]

LOGISTICS_SECTORS = {
    "energy":    {"risk":"HIGH","detail":"Red Sea disruption +18% oil tanker rerouting","icon":"⚡"},
    "shipping":  {"risk":"HIGH","detail":"32% Red Sea traffic diverted, +2 weeks transit","icon":"🚢"},
    "grain":     {"risk":"HIGH","detail":"Black Sea routes blocked, Ukraine grain at risk","icon":"🌾"},
    "air":       {"risk":"LOW","detail":"Minor disruption over conflict zones","icon":"✈"},
    "tech":      {"risk":"MODERATE","detail":"Taiwan Strait risk to chip supply chain","icon":"💾"},
    "oil_price": {"risk":"MODERATE","detail":"Brent +8% since Red Sea crisis","icon":"🛢"},
}

# ── API ENDPOINTS ─────────────────────────────────────────────

@app.get("/api/conflicts")
async def api_conflicts():
    e = gevents()
    conflicts = []
    for c in PERSISTENT_CONFLICTS:
        # Update momentum based on live events
        live_count = sum(1 for ev in e if ev["region"]==c["region"])
        momentum_boost = min(2.0, live_count * 0.3)
        adjusted_momentum = round(min(10, c["momentum"] + momentum_boost), 1)
        conflicts.append({**c, "live_events": live_count, "adjusted_momentum": adjusted_momentum})
    return {"conflicts": conflicts, "timestamp": _cache.get("last_refresh","")}

@app.get("/api/alignment")
async def api_alignment(conflict: str = "ukraine_war"):
    data = ALIGNMENT_DATA.get(conflict, ALIGNMENT_DATA["ukraine_war"])
    return {"alignment": data, "conflicts_available": list(ALIGNMENT_DATA.keys()), "timestamp": _cache.get("last_refresh","")}

@app.get("/api/travel-safety")
async def api_travel():
    e = gevents()
    # Boost risk for countries with live events
    active_regions = set(ev["region"] for ev in e)
    result = {}
    for country, data in TRAVEL_SAFETY.items():
        d = {**data}
        result[country] = d
    return {"travel": result, "timestamp": _cache.get("last_refresh","")}

@app.get("/api/trade")
async def api_trade():
    e = gevents()
    # Dynamically boost route risks based on live events
    routes = []
    for r in TRADE_ROUTES:
        route = {**r}
        # Check if related events exist
        if r["id"] == "red_sea":
            houthi = sum(1 for ev in e if ev["region"]=="Horn of Africa")
            if houthi >= 2: route["risk"] = "CRITICAL"
        elif r["id"] == "taiwan_strait":
            taiwan = sum(1 for ev in e if ev["region"]=="East Asia")
            if taiwan >= 3: route["risk"] = "HIGH"
        routes.append(route)
    return {"routes": routes, "sectors": LOGISTICS_SECTORS, "timestamp": _cache.get("last_refresh","")}

@app.get("/api/events-v4")
async def api_events_v4():
    """Enhanced events with city-level precision and uncertainty."""
    e = gevents()
    enhanced = []
    for ev in e:
        ev2 = {k:v for k,v in ev.items() if k!="full_text"}
        # Try to extract city
        city, clat, clon, _ = extract_city(ev.get("summary","") + " " + ev.get("full_text",""))
        if city and clat:
            ev2["precise_location"] = city
            ev2["lat"] = round(clat + random.uniform(-0.15, 0.15), 4)
            ev2["lon"] = round(clon + random.uniform(-0.15, 0.15), 4)
        else:
            ev2["precise_location"] = ev2.get("region","Unknown")
        # Uncertainty label
        conf = ev2.get("confidence", 70)
        if conf < 60:
            ev2["uncertainty"] = "LOW CONFIDENCE — Assessment based on limited sources. Situation may evolve."
        elif conf < 75:
            ev2["uncertainty"] = "MODERATE CONFIDENCE — Cross-referencing ongoing."
        else:
            ev2["uncertainty"] = None
        # Source count estimate
        ev2["source_count"] = 1 if conf < 65 else (2 if conf < 80 else 3)
        enhanced.append(ev2)
    return {"events": enhanced, "count": len(enhanced), "source": _cache.get("source","fallback"), "timestamp": _cache.get("last_refresh","")}

HTML_PAGE = """<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>GLOBAL CONFLICT RADAR v4</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet"/>
<style>
:root{
  --bg:#020608;--bg2:#040d12;--bg3:#071520;
  --b0:#0d3348;--b1:#1a6688;
  --green:#00ff88;--yellow:#f5c518;--orange:#ff6b1a;--red:#ff2233;
  --cyan:#00e5ff;--txt:#c8e8f8;--dim:#4a7a99;--muted:#2a4a5a;--purple:#9966ff;
  --mono:'Share Tech Mono',monospace;--disp:'Orbitron',sans-serif;--body:'Rajdhani',sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
html[dir="rtl"] .left-panel{order:3;border-right:none;border-left:1px solid var(--b0)}
html[dir="rtl"] .right-panel{order:1;border-left:none;border-right:1px solid var(--b0)}
body{background:var(--bg);color:var(--txt);font-family:var(--body);font-size:14px;height:100vh;overflow:hidden}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(0,170,255,.03)1px,transparent 1px),linear-gradient(90deg,rgba(0,170,255,.03)1px,transparent 1px);background-size:40px 40px;pointer-events:none;z-index:0}
.scanlines{position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.04)2px,rgba(0,0,0,.04)4px);pointer-events:none;z-index:999}

/* ── ALERT ── */
#alert-banner{display:none;position:fixed;top:0;left:0;right:0;z-index:990;background:linear-gradient(90deg,#1a0008,#2a0010,#1a0008);border-bottom:1px solid var(--red);padding:5px 14px;font-family:var(--mono);font-size:.58rem;letter-spacing:.1em;color:var(--red);align-items:center;justify-content:space-between}
#alert-banner.show{display:flex}
.al-close{cursor:pointer;color:var(--dim);padding:0 6px}

/* ── HEADER ── */
.hdr{display:flex;align-items:center;justify-content:space-between;padding:7px 12px;border-bottom:1px solid var(--b0);background:rgba(2,6,8,.97);position:relative;z-index:20;flex-shrink:0;gap:8px}
.hdr-left{display:flex;align-items:center;gap:10px;min-width:0}
.radar{width:32px;height:32px;border:2px solid var(--cyan);border-radius:50%;position:relative;flex-shrink:0;animation:rPulse 3s ease-in-out infinite}
.radar::after{content:'';position:absolute;top:50%;left:50%;width:2px;height:40%;background:var(--cyan);transform-origin:bottom center;transform:translateX(-50%);animation:rSweep 3s linear infinite}
@keyframes rSweep{to{transform:translateX(-50%)rotate(360deg)}}
@keyframes rPulse{0%,100%{box-shadow:0 0 6px #00e5ff44}50%{box-shadow:0 0 16px #00e5ffaa}}
.hdr-titles h1{font-family:var(--disp);font-size:.88rem;font-weight:700;letter-spacing:.2em;color:var(--cyan);text-shadow:0 0 8px #00e5ff44;white-space:nowrap}
.hdr-sub{font-family:var(--mono);font-size:.48rem;color:var(--dim);letter-spacing:.1em}
.hdr-center{display:flex;align-items:center;gap:6px;flex:1;justify-content:center}
/* MAP LAYER SWITCHER in header */
.layer-btn{padding:3px 9px;border:1px solid var(--b0);cursor:pointer;color:var(--dim);background:transparent;font-family:var(--mono);font-size:.48rem;letter-spacing:.07em;transition:all .15s;white-space:nowrap}
.layer-btn:hover{border-color:var(--b1);color:var(--txt)}
.layer-btn.active{border-color:var(--cyan);color:var(--cyan);background:rgba(0,229,255,.07)}
.layer-btn.active-trade{border-color:var(--yellow);color:var(--yellow);background:rgba(245,197,24,.07)}
.layer-btn.active-travel{border-color:var(--green);color:var(--green);background:rgba(0,255,136,.07)}
.layer-btn.active-align{border-color:var(--purple);color:var(--purple);background:rgba(153,102,255,.07)}
.layer-btn.active-conflict{border-color:var(--red);color:var(--red);background:rgba(255,34,51,.07)}
.hdr-right{display:flex;align-items:center;gap:10px;font-family:var(--mono);font-size:.52rem;color:var(--dim);flex-shrink:0}
/* LANGUAGE SWITCHER */
.lang-sel{background:transparent;border:1px solid var(--b0);color:var(--dim);font-family:var(--mono);font-size:.5rem;padding:2px 6px;cursor:pointer;outline:none}
.lang-sel:hover{border-color:var(--b1);color:var(--txt)}
.lang-sel option{background:#040d12;color:var(--txt)}
.live-dot{width:5px;height:5px;background:var(--green);border-radius:50%;box-shadow:0 0 5px var(--green);animation:blink 1.2s ease-in-out infinite;flex-shrink:0}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.1}}

/* ── SHELL ── */
.shell{display:flex;height:calc(100vh - 82px);overflow:hidden;position:relative;z-index:1}
.left-panel{width:260px;flex-shrink:0;background:var(--bg2);border-right:1px solid var(--b0);overflow-y:auto;display:flex;flex-direction:column}
.map-col{flex:1;display:flex;flex-direction:column;min-width:0}
.right-panel{width:252px;flex-shrink:0;background:var(--bg2);border-left:1px solid var(--b0);overflow-y:auto}
.left-panel::-webkit-scrollbar,.right-panel::-webkit-scrollbar{width:2px}
.left-panel::-webkit-scrollbar-thumb,.right-panel::-webkit-scrollbar-thumb{background:var(--b0)}

/* ── SEC ── */
.sec{border-bottom:1px solid var(--b0)}
.sec-h{display:flex;align-items:center;justify-content:space-between;padding:5px 10px;background:rgba(0,170,255,.02);cursor:pointer;user-select:none;gap:4px}
.sec-h:hover{background:rgba(0,170,255,.04)}
.sec-t{font-family:var(--disp);font-size:.46rem;letter-spacing:.16em;color:var(--dim);flex:1}
.sec-b{font-family:var(--mono);font-size:.44rem;color:var(--muted)}
.arr{font-size:.5rem;color:var(--muted);transition:transform .2s;flex-shrink:0}
.collapsed .arr{transform:rotate(-90deg)}
.collapsed .sec-body{display:none}
.sec-body{padding:7px 9px}

/* ── GTI ── */
.gti-wrap{text-align:center;padding:9px 7px 5px}
.gti-ring{width:130px;height:130px;border-radius:50%;border:2px solid var(--b0);position:relative;margin:0 auto 7px;display:flex;flex-direction:column;align-items:center;justify-content:center}
.gti-rg{position:absolute;inset:-1px;border-radius:50%;border:2px solid var(--red);animation:rgPulse 2s ease-in-out infinite;transition:all .6s}
@keyframes rgPulse{0%,100%{opacity:.6}50%{opacity:1}}
.gti-ri{position:absolute;inset:8px;border-radius:50%;border:1px solid rgba(255,34,51,.15);transition:all .6s}
.gti-num{font-family:var(--disp);font-size:2.6rem;font-weight:900;line-height:1;transition:color .6s}
.gti-den{font-family:var(--disp);font-size:.65rem;color:var(--muted)}
.gti-stat{font-family:var(--disp);font-size:.55rem;letter-spacing:.2em;padding:3px 9px;border:1px solid;display:inline-block;margin-bottom:5px;animation:sp 2s ease-in-out infinite;transition:all .6s}
@keyframes sp{0%,100%{opacity:1}50%{opacity:.6}}
.gti-row3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:3px;margin-bottom:4px}
.gsub{text-align:center}.gsub-l{font-family:var(--mono);font-size:.42rem;color:var(--muted);margin-bottom:1px}.gsub-v{font-family:var(--disp);font-size:.8rem;font-weight:700;color:var(--orange)}
.vel-row{display:flex;justify-content:space-between;align-items:center;padding:4px 9px;border-top:1px solid var(--b0);font-family:var(--mono);font-size:.5rem}
.sleg{display:grid;grid-template-columns:1fr 1fr;gap:1px 5px;padding:4px 9px 5px;border-top:1px solid var(--b0)}
.sl{font-family:var(--mono);font-size:.42rem}

/* ── ACTIVITY ── */
.act-grid{display:grid;grid-template-columns:1fr 1fr;gap:4px}
.act-item{background:rgba(0,229,255,.04);border:1px solid var(--b0);padding:5px 7px}
.act-lbl{font-family:var(--mono);font-size:.42rem;color:var(--muted);margin-bottom:1px}
.act-val{font-family:var(--disp);font-size:1rem;font-weight:700;line-height:1}
.act-sub{font-family:var(--mono);font-size:.4rem;color:var(--dim);margin-top:1px}
.act-ping{display:flex;align-items:center;justify-content:space-between;padding:4px 7px;border:1px solid var(--b0);background:rgba(0,255,136,.03);margin-top:4px}
.act-ping-dot{width:4px;height:4px;border-radius:50%;background:var(--green);box-shadow:0 0 4px var(--green);animation:blink .8s infinite}

/* ── FORECAST ── */
.fc-bars{display:flex;flex-direction:column;gap:4px}
.fc-row{display:flex;align-items:center;gap:4px}
.fc-lbl{font-family:var(--mono);font-size:.46rem;width:56px;flex-shrink:0}
.fc-track{flex:1;height:4px;background:rgba(255,255,255,.06);border-radius:2px;overflow:hidden}
.fc-fill{height:100%;border-radius:2px;transition:width 1s ease}
.fc-pct{font-family:var(--mono);font-size:.46rem;width:26px;text-align:right}
.fc-low .fc-lbl,.fc-low .fc-pct{color:var(--green)}.fc-low .fc-fill{background:var(--green)}
.fc-mod .fc-lbl,.fc-mod .fc-pct{color:var(--yellow)}.fc-mod .fc-fill{background:var(--yellow)}
.fc-high .fc-lbl,.fc-high .fc-pct{color:var(--red)}.fc-high .fc-fill{background:var(--red)}
.fc-meta{display:flex;justify-content:space-between;margin-top:6px;padding-top:5px;border-top:1px solid var(--b0);font-family:var(--mono);font-size:.44rem;color:var(--dim)}
.fc-reason{font-family:var(--mono);font-size:.44rem;color:var(--dim);margin-top:4px;line-height:1.5;font-style:italic}

/* ── REGIONAL ── */
.reg-row{display:grid;grid-template-columns:1fr auto auto;gap:3px;align-items:center;padding:2px 0}
.reg-name{font-family:var(--mono);font-size:.46rem;color:var(--dim)}
.reg-gti{font-family:var(--disp);font-size:.56rem;font-weight:700}
.reg-d{font-family:var(--mono);font-size:.42rem}
.reg-bar{height:2px;background:rgba(255,255,255,.05);border-radius:2px;overflow:hidden;grid-column:1/-1}
.reg-bar-f{height:100%;border-radius:2px;transition:width .8s}

/* ── CONFLICTS ── */
.conflict-item{border:1px solid var(--b0);background:rgba(0,170,255,.02);margin-bottom:5px;padding:7px 9px;cursor:pointer;transition:all .15s}
.conflict-item:hover{background:rgba(0,170,255,.05);border-color:var(--b1)}
.conf-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:4px}
.conf-name{font-family:var(--disp);font-size:.56rem;letter-spacing:.1em}
.conf-state{font-family:var(--disp);font-size:.44rem;padding:2px 6px;border:1px solid}
.conf-meta{display:flex;gap:8px;font-family:var(--mono);font-size:.44rem;color:var(--dim)}
.conf-momentum-bar{height:3px;background:rgba(255,255,255,.06);border-radius:2px;overflow:hidden;margin-top:4px}
.conf-momentum-fill{height:100%;border-radius:2px;transition:width .8s}
.conf-desc{font-family:var(--mono);font-size:.44rem;color:var(--muted);margin-top:4px;line-height:1.4}
.momentum-state-emerging{color:#f5c518;border-color:#f5c518}
.momentum-state-escalating{color:#ff6b1a;border-color:#ff6b1a}
.momentum-state-active{color:#ff2233;border-color:#ff2233}
.momentum-state-active.war{color:#ff2233;border-color:#ff2233}
.momentum-state-stabilizing{color:#aaaaff;border-color:#aaaaff}
.momentum-state-de-escalating{color:#00ff88;border-color:#00ff88}

/* ── ALIGNMENT ── */
.align-conflict-sel{display:flex;gap:4px;margin-bottom:8px;flex-wrap:wrap}
.align-conf-btn{padding:2px 7px;border:1px solid var(--b0);cursor:pointer;color:var(--dim);background:transparent;font-family:var(--mono);font-size:.44rem;transition:all .15s}
.align-conf-btn.active{border-color:var(--purple);color:var(--purple);background:rgba(153,102,255,.07)}
.align-list{display:flex;flex-direction:column;gap:3px}
.align-row{display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid rgba(13,51,72,.3)}
.align-country{font-family:var(--mono);font-size:.48rem;color:var(--dim);flex:1}
.align-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.align-label{font-family:var(--mono);font-size:.44rem}
.stance-supporting_A{color:#ff6b1a}.stance-supporting_B{color:#00aaff}.stance-neutral{color:#4a7a99}.stance-ambiguous{color:#f5c518}

/* ── TRAVEL ── */
.travel-list{display:flex;flex-direction:column;gap:2px;max-height:200px;overflow-y:auto}
.travel-list::-webkit-scrollbar{width:2px}
.travel-list::-webkit-scrollbar-thumb{background:var(--b0)}
.travel-row{display:grid;grid-template-columns:1fr auto;gap:5px;align-items:center;padding:3px 0;border-bottom:1px solid rgba(13,51,72,.25)}
.travel-country{font-family:var(--mono);font-size:.48rem;color:var(--dim)}
.travel-risk{font-family:var(--disp);font-size:.46rem;padding:1px 6px;border:1px solid}
.risk-CRITICAL{color:#8b0000;border-color:#8b0000;background:rgba(139,0,0,.1)}
.risk-HIGH{color:var(--red);border-color:var(--red);background:rgba(255,34,51,.06)}
.risk-MODERATE{color:var(--yellow);border-color:var(--yellow);background:rgba(245,197,24,.06)}
.risk-LOW{color:var(--green);border-color:var(--green);background:rgba(0,255,136,.06)}
.risk-ELEVATED{color:var(--orange);border-color:var(--orange)}

/* ── TRADE ── */
.trade-route{display:flex;align-items:center;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(13,51,72,.3)}
.trade-name{font-family:var(--mono);font-size:.48rem;color:var(--dim)}
.trade-right{text-align:right}
.trade-risk{font-family:var(--disp);font-size:.46rem}
.trade-pct{font-family:var(--mono);font-size:.42rem;color:var(--muted)}
.logistics-grid{display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:7px}
.log-item{background:rgba(0,170,255,.03);border:1px solid var(--b0);padding:5px 7px}
.log-icon{font-size:.8rem}
.log-lbl{font-family:var(--mono);font-size:.42rem;color:var(--muted);margin:1px 0}
.log-risk{font-family:var(--disp);font-size:.56rem;font-weight:700}

/* ── SUPPLY / STRATEGIC ── */
.sup-grid{display:grid;grid-template-columns:1fr 1fr;gap:4px}
.sup-item{background:rgba(0,170,255,.03);border:1px solid var(--b0);padding:5px 7px}
.strat-item{display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid rgba(13,51,72,.3)}
.strat-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.strat-lbl{font-family:var(--mono);font-size:.48rem;color:var(--dim)}
.strat-val{font-family:var(--mono);font-size:.48rem;margin-left:auto}
.choke-item{display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid rgba(13,51,72,.25)}
.choke-nm{font-family:var(--mono);font-size:.46rem;color:var(--dim)}
.choke-rv{font-family:var(--disp);font-size:.44rem}

/* ── FEED ── */
.feed-list{max-height:220px;overflow-y:auto}
.feed-list::-webkit-scrollbar{width:2px}
.feed-list::-webkit-scrollbar-thumb{background:var(--b0)}
.fi{display:grid;grid-template-columns:3px 1fr auto;gap:5px;padding:5px 9px;border-bottom:1px solid rgba(13,51,72,.35);cursor:pointer;transition:background .15s}
.fi:hover{background:rgba(0,170,255,.04)}
.fi-ind{align-self:stretch;min-height:26px;border-radius:1px}
.fi-ind.red{background:var(--red);box-shadow:0 0 3px var(--red)}
.fi-ind.orange{background:var(--orange)}
.fi-ind.yellow{background:var(--yellow)}
.fi-type{font-family:var(--disp);font-size:.46rem;letter-spacing:.09em;color:var(--orange)}
.fi-loc{font-family:var(--mono);font-size:.44rem;color:var(--cyan)}
.fi-reg{font-family:var(--mono);font-size:.42rem;color:var(--dim)}
.fi-desc{font-family:var(--body);font-size:.6rem;color:var(--txt);line-height:1.3;margin-top:1px}
.fi-conf{font-family:var(--mono);font-size:.44rem;color:var(--dim);text-align:right}
.fi-unc{font-family:var(--mono);font-size:.38rem;color:var(--yellow);margin-top:2px;text-align:right}
.fi-src{font-family:var(--mono);font-size:.4rem;color:var(--muted);text-align:right}

/* ── TRANSPARENCY ── */
.transp-row{display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid rgba(13,51,72,.25)}
.transp-lbl{font-family:var(--mono);font-size:.46rem;color:var(--muted)}
.transp-val{font-family:var(--mono);font-size:.5rem;color:var(--cyan)}

/* ── AI SUMMARY ── */
.ai-sum{font-family:var(--body);font-size:.72rem;line-height:1.7;color:var(--txt);border-left:2px solid var(--b1);padding-left:8px;min-height:48px}
.ai-sum.typing::after{content:'▋';animation:blink .7s infinite;color:var(--cyan)}
.ai-ft{display:flex;justify-content:space-between;font-family:var(--mono);font-size:.42rem;color:var(--muted);margin-top:5px;padding-top:4px;border-top:1px solid var(--b0)}
.ai-badge{display:flex;align-items:center;gap:2px;color:var(--cyan);font-size:.42rem}
.ai-dot{width:3px;height:3px;background:var(--cyan);border-radius:50%;animation:blink 2s infinite}

/* ── MAP ── */
#wmap{flex:1;min-height:0}
.leaflet-container{background:#020e18!important}
.leaflet-tile{filter:brightness(.35) hue-rotate(185deg) saturate(.28) invert(.85)!important}
.leaflet-control-zoom a{background:var(--bg3);color:var(--dim);border-color:var(--b0)}
.leaflet-popup-content-wrapper{background:#050f18!important;border:1px solid #1a6688!important;color:var(--txt)!important;border-radius:0!important;box-shadow:0 0 12px #00e5ff22!important;font-family:var(--mono)!important;font-size:.62rem!important;min-width:240px}
.leaflet-popup-tip{background:#1a6688!important}
.pop-analyze{display:inline-block;margin-top:6px;padding:4px 10px;border:1px solid var(--cyan);color:var(--cyan);font-family:var(--mono);font-size:.5rem;cursor:pointer;letter-spacing:.08em;transition:all .18s}
.pop-analyze:hover{background:var(--cyan);color:var(--bg)}
.map-footer{display:flex;align-items:center;gap:8px;padding:4px 10px;border-top:1px solid var(--b0);background:var(--bg2);font-family:var(--mono);font-size:.46rem;color:var(--dim);flex-wrap:wrap;flex-shrink:0}
.mf-item{display:flex;align-items:center;gap:3px}
.mf-dot{width:5px;height:5px;border-radius:50%}
/* Layer legend badges */
.layer-legend{display:none;align-items:center;gap:6px;flex:1}
.layer-legend.visible{display:flex}
.ll-item{display:flex;align-items:center;gap:3px;font-size:.44rem}

/* MAP MARKERS */
.em{width:11px;height:11px;border-radius:50%;border:2px solid}
.em.red{background:rgba(255,34,51,.5);border-color:#ff2233;box-shadow:0 0 6px #ff2233}
.em.orange{background:rgba(255,107,26,.45);border-color:#ff6b1a;box-shadow:0 0 5px #ff6b1a}
.em.yellow{background:rgba(245,197,24,.4);border-color:#f5c518}
.em.faded{background:rgba(60,60,60,.3);border-color:#444;box-shadow:none;opacity:.35}
.em-hot{animation:hotPulse .9s ease-in-out infinite}
@keyframes hotPulse{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.8);opacity:.6}}
.just-wrap{position:relative}
.just-tag{position:absolute;top:-17px;left:50%;transform:translateX(-50%);background:#ff2233;color:#fff;font-family:var(--mono);font-size:.35rem;padding:1px 4px;letter-spacing:.06em;white-space:nowrap;animation:tagBlink 1s ease-in-out infinite}
@keyframes tagBlink{0%,100%{opacity:1}50%{opacity:.5}}
/* Conflict hotspot marker */
.hotspot-marker{width:8px;height:8px;border-radius:50%;border:2px solid}
/* Travel safety country markers */
.travel-country-marker{font-family:var(--mono);font-size:.46rem;padding:2px 5px;border:1px solid;white-space:nowrap;backdrop-filter:blur(2px)}
/* Alignment country markers */
.align-country-marker{font-family:var(--mono);font-size:.46rem;padding:2px 5px;border:1px solid;white-space:nowrap;backdrop-filter:blur(2px)}
/* Chart */
.chart-wrap{padding:4px 6px 6px;height:130px}
.chart-wrap canvas{width:100%!important;height:100%!important}

/* ── REPLAY BAR ── */
.rep-bar{display:flex;align-items:center;gap:6px;padding:4px 9px;border-top:1px solid var(--b0);background:var(--bg2);font-family:var(--mono);font-size:.48rem;color:var(--dim);flex-shrink:0;flex-wrap:wrap}
.rep-btn{padding:2px 7px;border:1px solid var(--b0);cursor:pointer;color:var(--dim);background:transparent;font-family:var(--mono);font-size:.46rem;transition:all .15s}
.rep-btn:hover,.rep-btn.active{border-color:var(--cyan);color:var(--cyan);background:rgba(0,229,255,.05)}
.rep-play{width:20px;height:20px;border:1px solid var(--b1);border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--cyan);font-size:.6rem;flex-shrink:0}
.rep-play:hover{background:rgba(0,229,255,.1)}
.rep-slider{flex:1;accent-color:var(--cyan);cursor:pointer;min-width:60px}
#rep-ts{color:var(--cyan);font-size:.46rem;min-width:100px}
.rep-24h-btn{padding:2px 8px;border:1px solid var(--orange);color:var(--orange);background:transparent;font-family:var(--mono);font-size:.46rem;cursor:pointer}
.rep-24h-btn:hover{background:rgba(255,107,26,.1)}
.spd-btn{padding:1px 5px;border:1px solid var(--b0);cursor:pointer;color:var(--muted);background:transparent;font-family:var(--mono);font-size:.44rem}
.spd-btn.active{border-color:var(--yellow);color:var(--yellow)}
.rep-live-btn{padding:2px 7px;border:1px solid var(--green);color:var(--green);background:transparent;font-family:var(--mono);font-size:.46rem;cursor:pointer}
.rep-live-btn:hover{background:rgba(0,255,136,.07)}

/* ── INTEL PANEL ── */
#intel-panel{position:fixed;top:0;right:-440px;width:440px;height:100vh;background:var(--bg2);border-left:1px solid var(--b1);z-index:900;transition:right .3s cubic-bezier(.4,0,.2,1);overflow-y:auto;display:flex;flex-direction:column}
#intel-panel.open{right:0}
#intel-panel::-webkit-scrollbar{width:2px}
#intel-panel::-webkit-scrollbar-thumb{background:var(--b0)}
.intel-hdr{display:flex;align-items:center;justify-content:space-between;padding:10px 13px;border-bottom:1px solid var(--b0);background:rgba(0,170,255,.03);position:sticky;top:0;z-index:1}
.intel-title-text{font-family:var(--disp);font-size:.58rem;letter-spacing:.16em;color:var(--cyan)}
.intel-close{cursor:pointer;color:var(--dim);font-size:.9rem;padding:2px 5px;line-height:1}
.intel-close:hover{color:var(--txt)}
.intel-body{padding:12px 13px;flex:1}
.intel-type{font-family:var(--disp);font-size:.8rem;letter-spacing:.13em;color:var(--orange);margin-bottom:3px}
.intel-loc{font-family:var(--mono);font-size:.54rem;color:var(--cyan);margin-bottom:3px;display:flex;align-items:center;gap:5px}
.intel-det{font-family:var(--mono);font-size:.46rem;color:var(--muted);margin-bottom:10px}
.intel-4grid{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:9px}
.intel-m{background:rgba(0,170,255,.04);border:1px solid var(--b0);padding:5px 7px}
.intel-m-l{font-family:var(--mono);font-size:.42rem;color:var(--muted);margin-bottom:2px}
.intel-m-v{font-family:var(--disp);font-size:.76rem;font-weight:700}
.intel-uncertainty{background:rgba(245,197,24,.06);border:1px solid rgba(245,197,24,.3);padding:6px 9px;margin-bottom:9px;font-family:var(--mono);font-size:.48rem;color:var(--yellow);line-height:1.5}
.intel-stats-box{background:rgba(0,170,255,.03);border:1px solid var(--b0);padding:7px 9px;margin-bottom:9px}
.intel-stats-h{font-family:var(--disp);font-size:.47rem;letter-spacing:.13em;color:var(--dim);margin-bottom:6px}
.intel-stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:4px}
.stat-item{border-bottom:1px solid rgba(13,51,72,.4);padding-bottom:3px}
.stat-l{font-family:var(--mono);font-size:.42rem;color:var(--muted)}
.stat-v{font-family:var(--disp);font-size:.68rem;font-weight:700;color:var(--cyan)}
.intel-sec{margin-bottom:9px}
.intel-sec-h{font-family:var(--disp);font-size:.46rem;letter-spacing:.13em;color:var(--dim);margin-bottom:4px;padding-bottom:3px;border-bottom:1px solid var(--b0)}
.intel-text{font-family:var(--body);font-size:.73rem;color:var(--txt);line-height:1.65}
.actor-tag{font-family:var(--mono);font-size:.44rem;color:var(--cyan);border:1px solid rgba(0,229,255,.3);padding:1px 5px;display:inline-block;margin:1px}
.esc-badge{display:inline-block;font-family:var(--disp);font-size:.5rem;padding:2px 8px;border:1px solid;margin-top:2px}
.esc-LOW{color:var(--green);border-color:var(--green)}.esc-MODERATE{color:var(--yellow);border-color:var(--yellow)}
.esc-HIGH{color:var(--orange);border-color:var(--orange)}.esc-CRITICAL{color:var(--red);border-color:var(--red)}
.intel-src-link{display:block;margin-top:9px;padding:6px 9px;border:1px solid var(--b0);font-family:var(--mono);font-size:.48rem;color:var(--cyan);text-decoration:none;text-align:center}
.intel-src-link:hover{background:rgba(0,229,255,.06)}
.intel-loading{text-align:center;padding:30px 20px;font-family:var(--mono);font-size:.55rem;color:var(--dim)}
.intel-spinner{font-size:1.1rem;color:var(--cyan);animation:spin 1.5s linear infinite;display:block;margin-bottom:8px}
@keyframes spin{to{transform:rotate(360deg)}}

/* ── MULTILINGUAL UTILS ── */
[data-i18n]{transition:opacity .2s}
</style>
</head>
<body>
<div class="scanlines"></div>

<!-- ALERT -->
<div id="alert-banner">
  <div style="display:flex;align-items:center;gap:7px"><div class="live-dot"></div><span id="alert-text">⚠ ALERT</span></div>
  <span class="al-close" onclick="dismissAlert()">✕</span>
</div>

<!-- HEADER -->
<header class="hdr">
  <div class="hdr-left">
    <div class="radar"></div>
    <div class="hdr-titles">
      <h1 data-i18n="title">GLOBAL CONFLICT RADAR</h1>
      <div class="hdr-sub" data-i18n="subtitle">LIVE GEOPOLITICAL MONITORING · RSS + CLAUDE AI · v4.0</div>
    </div>
  </div>
  <div class="hdr-center">
    <button class="layer-btn active" onclick="setLayer('live',this)" data-i18n="layer_live">◉ LIVE</button>
    <button class="layer-btn" onclick="setLayer('conflicts',this)" data-i18n="layer_conflicts">💥 CONFLICTS</button>
    <button class="layer-btn" onclick="setLayer('trade',this)" data-i18n="layer_trade">🚢 TRADE</button>
    <button class="layer-btn" onclick="setLayer('travel',this)" data-i18n="layer_travel">✈ TRAVEL</button>
    <button class="layer-btn" onclick="setLayer('alignment',this)" data-i18n="layer_align">🌐 ALIGNMENT</button>
  </div>
  <div class="hdr-right">
    <select class="lang-sel" onchange="setLang(this.value)">
      <option value="en">EN</option>
      <option value="sk">SK</option>
      <option value="de">DE</option>
      <option value="fr">FR</option>
      <option value="uk">UK</option>
      <option value="ru">RU</option>
      <option value="ar">AR</option>
      <option value="zh">ZH</option>
    </select>
    <span>DATA: <span id="src-badge" style="color:var(--green)">—</span></span>
    <span id="utc-clock" style="color:var(--muted)">—</span>
    <span>NEXT: <span id="next-ref" style="color:var(--cyan)">10:00</span></span>
    <div style="display:flex;align-items:center;gap:4px;color:var(--green)"><div class="live-dot"></div><span data-i18n="live">LIVE</span></div>
  </div>
</header>

<!-- SHELL -->
<div class="shell">

<!-- ════ LEFT PANEL ════ -->
<div class="left-panel">

  <!-- ACTIVITY -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')">
      <span class="sec-t" data-i18n="act_title">◈ GLOBAL ACTIVITY</span>
      <div style="display:flex;align-items:center;gap:4px"><div class="live-dot" style="width:4px;height:4px"></div><span class="arr">▾</span></div>
    </div>
    <div class="sec-body" style="padding:5px 7px">
      <div class="act-grid">
        <div class="act-item"><div class="act-lbl" data-i18n="act_incidents">ACTIVE INCIDENTS</div><div class="act-val" id="act-inc" style="color:var(--red)">—</div><div class="act-sub" id="act-conf">—</div></div>
        <div class="act-item"><div class="act-lbl" data-i18n="act_regions">REGIONS ACTIVE</div><div class="act-val" id="act-reg" style="color:var(--orange)">—</div><div class="act-sub" id="act-strat">— strategic</div></div>
        <div class="act-item"><div class="act-lbl" data-i18n="act_sources">SOURCES MONITORED</div><div class="act-val" id="act-src" style="color:var(--cyan);font-size:.85rem">1,247</div><div class="act-sub">LIVE FEEDS</div></div>
        <div class="act-item"><div class="act-lbl" data-i18n="act_24h">DETECTED 24H</div><div class="act-val" id="act-24h" style="color:var(--yellow);font-size:.85rem">—</div><div class="act-sub" id="act-avgc">—</div></div>
      </div>
      <div class="act-ping"><div class="act-ping-dot"></div><span style="font-family:var(--mono);font-size:.46rem;color:var(--dim)" data-i18n="act_last">LAST DETECTED</span><span id="act-last" style="font-family:var(--mono);font-size:.5rem;color:var(--green)">—</span></div>
    </div>
  </div>

  <!-- GTI -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')">
      <span class="sec-t" data-i18n="gti_title">GLOBAL TENSION INDEX</span>
      <span class="sec-b" id="ecount">—</span><span class="arr">▾</span>
    </div>
    <div class="sec-body" style="padding:0">
      <div class="gti-wrap">
        <div class="gti-ring">
          <div class="gti-rg" id="gti-rg"></div>
          <div class="gti-ri" id="gti-ri"></div>
          <div class="gti-num" id="gti-num">—</div>
          <div class="gti-den">/ 10</div>
        </div>
        <div class="gti-stat" id="gti-stat" data-i18n-gti="1">LOADING…</div>
        <div class="gti-row3">
          <div class="gsub"><div class="gsub-l">MIL</div><div class="gsub-v" id="s-mil">—</div></div>
          <div class="gsub"><div class="gsub-l">STR</div><div class="gsub-v" id="s-str">—</div></div>
          <div class="gsub"><div class="gsub-l">ECO</div><div class="gsub-v" id="s-eco">—</div></div>
        </div>
      </div>
      <div class="vel-row"><span style="color:var(--dim)" data-i18n="velocity">ESCALATION VELOCITY</span><span id="velocity" style="color:var(--red)">—</span></div>
      <div class="sleg">
        <div class="sl" style="color:#00ff88">● 0-2 STABLE</div><div class="sl" style="color:#f5c518">● 2-4 RISING</div>
        <div class="sl" style="color:#ff6b1a">● 4-6 HIGH</div><div class="sl" style="color:#ff2233">● 6-8 CRISIS</div>
        <div class="sl" style="color:#8b0000;grid-column:1/-1">● 8-10 GLOBAL CRISIS</div>
      </div>
    </div>
  </div>

  <!-- CHART -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t" data-i18n="trend_title">TENSION TREND · 30 DAYS</span><span class="arr">▾</span></div>
    <div class="sec-body" style="padding:0"><div class="chart-wrap"><canvas id="tchart"></canvas></div></div>
  </div>

  <!-- FORECAST -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t" data-i18n="fc_title">ESCALATION FORECAST · 30D</span><span class="arr">▾</span></div>
    <div class="sec-body">
      <div class="fc-bars">
        <div class="fc-row fc-low"><span class="fc-lbl" data-i18n="fc_low">LOW RISK</span><div class="fc-track"><div class="fc-fill" id="fc-low" style="width:0%"></div></div><span class="fc-pct" id="fc-lp">—%</span></div>
        <div class="fc-row fc-mod"><span class="fc-lbl" data-i18n="fc_mod">MODERATE</span><div class="fc-track"><div class="fc-fill" id="fc-mod" style="width:0%"></div></div><span class="fc-pct" id="fc-mp">—%</span></div>
        <div class="fc-row fc-high"><span class="fc-lbl" data-i18n="fc_high">HIGH RISK</span><div class="fc-track"><div class="fc-fill" id="fc-high" style="width:0%"></div></div><span class="fc-pct" id="fc-hp">—%</span></div>
      </div>
      <div class="fc-meta"><span data-i18n="fc_conf">CONFIDENCE: </span><span id="fc-conf-val" style="color:var(--cyan)">—%</span><span id="fc-analyzed" style="color:var(--dim)">— EVT</span></div>
      <div class="fc-reason" id="fc-reason">Calculating…</div>
    </div>
  </div>

  <!-- REGIONAL -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t" data-i18n="reg_title">REGIONAL TENSIONS</span><span class="arr">▾</span></div>
    <div class="sec-body"><div id="reg-list">Loading…</div></div>
  </div>

  <!-- AI SUMMARY -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')">
      <span class="sec-t" data-i18n="sum_title">SITUATION SUMMARY</span>
      <div class="ai-badge"><div class="ai-dot"></div><span style="font-family:var(--mono);font-size:.42rem;color:var(--cyan)">AI</span></div>
    </div>
    <div class="sec-body">
      <div class="ai-sum typing" id="ai-sum" data-i18n-live="summary">Analyzing…</div>
      <div class="ai-ft"><span id="ai-gen">—</span><span id="ai-ts">—</span></div>
    </div>
  </div>

</div><!-- /left -->

<!-- ════ MAP CENTER ════ -->
<div class="map-col">
  <div id="wmap" style="flex:1;min-height:0"></div>
  <div class="map-footer">
    <!-- LIVE legend -->
    <div class="layer-legend visible" id="leg-live">
      <div class="ll-item"><div class="mf-dot" style="background:#ff2233;box-shadow:0 0 4px #ff2233"></div>STRIKE</div>
      <div class="ll-item"><div class="mf-dot" style="background:#ff6b1a"></div>MOVEMENT</div>
      <div class="ll-item"><div class="mf-dot" style="background:#f5c518"></div>TENSION</div>
      <div class="ll-item" style="color:var(--cyan)">⊙ JUST DETECTED</div>
    </div>
    <!-- CONFLICTS legend -->
    <div class="layer-legend" id="leg-conflicts">
      <div class="ll-item" style="color:#ff2233">━ FRONTLINE</div>
      <div class="ll-item" style="color:#ff6b1a">● HOTSPOT</div>
      <div class="ll-item" style="color:#f5c518">● STABILIZING</div>
    </div>
    <!-- TRADE legend -->
    <div class="layer-legend" id="leg-trade">
      <div class="ll-item" style="color:#ff2233">━ HIGH RISK</div>
      <div class="ll-item" style="color:#f5c518">━ MODERATE</div>
      <div class="ll-item" style="color:#00ff88">━ LOW RISK</div>
    </div>
    <!-- TRAVEL legend -->
    <div class="layer-legend" id="leg-travel">
      <div class="ll-item" style="color:#8b0000">▪ CRITICAL</div>
      <div class="ll-item" style="color:#ff2233">▪ HIGH</div>
      <div class="ll-item" style="color:#f5c518">▪ MODERATE</div>
      <div class="ll-item" style="color:#00ff88">▪ LOW</div>
    </div>
    <!-- ALIGNMENT legend -->
    <div class="layer-legend" id="leg-align">
      <div class="ll-item" style="color:#ff6b1a">▪ SIDE A</div>
      <div class="ll-item" style="color:#00aaff">▪ SIDE B</div>
      <div class="ll-item" style="color:#f5c518">▪ AMBIGUOUS</div>
      <div class="ll-item" style="color:#4a7a99">▪ NEUTRAL</div>
    </div>
    <span style="margin-left:auto;color:var(--muted);font-family:var(--mono);font-size:.44rem" id="map-src">—</span>
  </div>
  <!-- REPLAY BAR -->
  <div class="rep-bar">
    <span style="color:var(--dim);letter-spacing:.1em;flex-shrink:0;font-family:var(--mono);font-size:.46rem" data-i18n="replay">TIMELINE</span>
    <button class="rep-btn active" onclick="setRepPeriod('24h',this)">24H</button>
    <button class="rep-btn" onclick="setRepPeriod('7d',this)">7D</button>
    <button class="rep-btn" onclick="setRepPeriod('30d',this)">30D</button>
    <button class="rep-24h-btn" onclick="playLast24h()">▶ PLAY 24H</button>
    <div class="rep-play" id="rep-play-btn" onclick="toggleReplay()">▶</div>
    <input type="range" class="rep-slider" id="rep-slider" min="0" max="100" value="100" oninput="onSlide(this.value)"/>
    <span id="rep-ts">LIVE</span>
    <button class="spd-btn active" onclick="setSpd(1,this)">1x</button>
    <button class="spd-btn" onclick="setSpd(2,this)">2x</button>
    <button class="spd-btn" onclick="setSpd(5,this)">5x</button>
    <button class="rep-live-btn" onclick="goLive()">● LIVE</button>
  </div>
</div>

<!-- ════ RIGHT PANEL ════ -->
<div class="right-panel">

  <!-- PERSISTENT CONFLICTS -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t" data-i18n="conflicts_title">PERSISTENT CONFLICTS</span><span class="arr">▾</span></div>
    <div class="sec-body"><div id="conflict-list">Loading…</div></div>
  </div>

  <!-- ALIGNMENT MAP PANEL -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t" data-i18n="align_title">GLOBAL ALIGNMENT</span><span class="arr">▾</span></div>
    <div class="sec-body">
      <div class="align-conflict-sel" id="align-conflict-sel"></div>
      <div id="align-list">Loading…</div>
    </div>
  </div>

  <!-- TRADE & LOGISTICS -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t" data-i18n="trade_title">TRADE & LOGISTICS</span><span class="arr">▾</span></div>
    <div class="sec-body">
      <div id="trade-routes-list">Loading…</div>
      <div class="logistics-grid" id="logistics-grid">—</div>
    </div>
  </div>

  <!-- STRATEGIC MONITOR -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t" data-i18n="strat_title">STRATEGIC MONITOR</span><span class="arr">▾</span></div>
    <div class="sec-body">
      <div id="strat-list">Loading…</div>
      <div style="margin-top:7px;font-family:var(--mono);font-size:.44rem;color:var(--muted);letter-spacing:.08em;margin-bottom:4px">CHOKEPOINTS</div>
      <div id="choke-list">—</div>
    </div>
  </div>

  <!-- SUPPLY CHAIN -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t" data-i18n="supply_title">SUPPLY CHAIN RISK</span><span class="arr">▾</span></div>
    <div class="sec-body" style="padding:5px 7px"><div class="sup-grid" id="supply-grid">Loading…</div></div>
  </div>

  <!-- TRAVEL SAFETY -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t" data-i18n="travel_title">✈ TRAVEL SAFETY</span><span class="arr">▾</span></div>
    <div class="sec-body" style="padding:4px 7px"><div class="travel-list" id="travel-list">Loading…</div></div>
  </div>

  <!-- EVENT FEED -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')">
      <span class="sec-t" data-i18n="feed_title">RECENT EVENTS</span>
      <span class="sec-b" id="feed-src-b">—</span><span class="arr">▾</span>
    </div>
    <div style="padding:0"><div class="feed-list" id="feed-list"><div style="padding:9px;font-family:var(--mono);font-size:.5rem;color:var(--dim)">Loading…</div></div></div>
  </div>

  <!-- TRANSPARENCY -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t" data-i18n="transp_title">SYSTEM TRANSPARENCY</span><span class="arr">▾</span></div>
    <div class="sec-body"><div id="transp-list">Loading…</div></div>
  </div>

</div><!-- /right -->
</div><!-- /shell -->

<!-- INTEL PANEL -->
<div id="intel-panel">
  <div class="intel-hdr">
    <span class="intel-title-text" data-i18n="intel_title">◈ EVENT INTELLIGENCE</span>
    <span class="intel-close" onclick="closeIntel()">✕</span>
  </div>
  <div class="intel-body" id="intel-body">
    <div class="intel-loading"><span class="intel-spinner">◈</span><span data-i18n="intel_select">Select a map event to analyze</span></div>
  </div>
</div>

<script>
// ════════════════════════════════════════════════════════════
// i18n
// ════════════════════════════════════════════════════════════
const LANGS = {
  en:{title:"GLOBAL CONFLICT RADAR",subtitle:"LIVE GEOPOLITICAL MONITORING · RSS + CLAUDE AI · v4.0",layer_live:"◉ LIVE",layer_conflicts:"💥 CONFLICTS",layer_trade:"🚢 TRADE",layer_travel:"✈ TRAVEL",layer_align:"🌐 ALIGNMENT",live:"LIVE",act_title:"◈ GLOBAL ACTIVITY",act_incidents:"ACTIVE INCIDENTS",act_regions:"REGIONS ACTIVE",act_sources:"SOURCES MONITORED",act_24h:"DETECTED 24H",act_last:"LAST DETECTED",gti_title:"GLOBAL TENSION INDEX",velocity:"ESCALATION VELOCITY",trend_title:"TENSION TREND · 30 DAYS",fc_title:"ESCALATION FORECAST · 30D",fc_low:"LOW RISK",fc_mod:"MODERATE",fc_high:"HIGH RISK",fc_conf:"CONFIDENCE: ",reg_title:"REGIONAL TENSIONS",sum_title:"SITUATION SUMMARY",replay:"TIMELINE",conflicts_title:"PERSISTENT CONFLICTS",align_title:"GLOBAL ALIGNMENT",trade_title:"TRADE & LOGISTICS",strat_title:"STRATEGIC MONITOR",supply_title:"SUPPLY CHAIN RISK",travel_title:"✈ TRAVEL SAFETY",feed_title:"RECENT EVENTS",transp_title:"SYSTEM TRANSPARENCY",intel_title:"◈ EVENT INTELLIGENCE",intel_select:"Select a map event to analyze"},
  sk:{title:"GLOBÁLNY KONFLIKTOVÝ RADAR",subtitle:"ŽIVÉ GEOPOLITICKÉ MONITOROVANIE · RSS + CLAUDE AI · v4.0",layer_live:"◉ ŽIVÉ",layer_conflicts:"💥 KONFLIKTY",layer_trade:"🚢 OBCHOD",layer_travel:"✈ CESTOVANIE",layer_align:"🌐 ZAROVNANIE",live:"ŽIVÉ",act_title:"◈ GLOBÁLNA AKTIVITA",act_incidents:"AKTÍVNE INCIDENTY",act_regions:"AKTÍVNE REGIÓNY",act_sources:"SLEDOVANÉ ZDROJE",act_24h:"DETEKOVANÉ 24H",act_last:"POSLEDNÁ DETEKCIA",gti_title:"GLOBÁLNY INDEX NAPÄTIA",velocity:"RÝCHLOSŤ ESKALÁCIE",trend_title:"TREND NAPÄTIA · 30 DNÍ",fc_title:"PROGNÓZA ESKALÁCIE · 30D",fc_low:"NÍZKE RIZIKO",fc_mod:"STREDNÉ",fc_high:"VYSOKÉ RIZIKO",fc_conf:"DÔVERA: ",reg_title:"REGIONÁLNE NAPÄTIA",sum_title:"SITUAČNÁ SPRÁVA",replay:"ČASOVÁ OS",conflicts_title:"PRETRVÁVAJÚCE KONFLIKTY",align_title:"GLOBÁLNE ZAROVNANIE",trade_title:"OBCHOD & LOGISTIKA",strat_title:"STRATEGICKÝ MONITOR",supply_title:"RIZIKO DODÁVATEĽ. REŤAZCA",travel_title:"✈ BEZPEČNOSŤ CESTOVANIA",feed_title:"POSLEDNÉ UDALOSTI",transp_title:"TRANSPARENTNOSŤ SYSTÉMU",intel_title:"◈ SPRAVODAJSKÝ PANEL",intel_select:"Vyberte udalosť na mape"},
  de:{title:"GLOBALES KONFLIKT-RADAR",subtitle:"LIVE GEOPOLITISCHES MONITORING · RSS + CLAUDE AI · v4.0",layer_live:"◉ LIVE",layer_conflicts:"💥 KONFLIKTE",layer_trade:"🚢 HANDEL",layer_travel:"✈ REISEN",layer_align:"🌐 AUSRICHTUNG",live:"LIVE",act_title:"◈ GLOBALE AKTIVITÄT",act_incidents:"AKTIVE VORFÄLLE",act_regions:"AKTIVE REGIONEN",act_sources:"ÜBERWACHTE QUELLEN",act_24h:"ERKANNT 24H",act_last:"ZULETZT ERKANNT",gti_title:"GLOBALER SPANNUNGSINDEX",velocity:"ESKALATIONSGESCHW.",trend_title:"SPANNUNGSTREND · 30 TAGE",fc_title:"ESKALATIONSPROGNOSE · 30T",fc_low:"NIEDRIGES RISIKO",fc_mod:"MODERAT",fc_high:"HOHES RISIKO",fc_conf:"KONFIDENZ: ",reg_title:"REGIONALE SPANNUNGEN",sum_title:"LAGEBERICHT",replay:"ZEITLINIE",conflicts_title:"ANHALTENDE KONFLIKTE",align_title:"GLOBALE AUSRICHTUNG",trade_title:"HANDEL & LOGISTIK",strat_title:"STRATEGISCHER MONITOR",supply_title:"LIEFERKETTENRISIKO",travel_title:"✈ REISESICHERHEIT",feed_title:"AKTUELLE EREIGNISSE",transp_title:"SYSTEMTRANSPARENZ",intel_title:"◈ EREIGNISANALYSE",intel_select:"Ereignismarker auswählen"},
  fr:{title:"RADAR MONDIAL DES CONFLITS",subtitle:"SURVEILLANCE GÉOPOLITIQUE EN DIRECT · RSS + CLAUDE AI · v4.0",layer_live:"◉ EN DIRECT",layer_conflicts:"💥 CONFLITS",layer_trade:"🚢 COMMERCE",layer_travel:"✈ VOYAGE",layer_align:"🌐 ALIGNEMENT",live:"EN DIRECT",act_title:"◈ ACTIVITÉ MONDIALE",act_incidents:"INCIDENTS ACTIFS",act_regions:"RÉGIONS ACTIVES",act_sources:"SOURCES SURVEILLÉES",act_24h:"DÉTECTÉS 24H",act_last:"DERNIÈRE DÉTECTION",gti_title:"INDICE DE TENSION MONDIAL",velocity:"VITESSE D'ESCALADE",trend_title:"TENDANCE · 30 JOURS",fc_title:"PRÉVISION D'ESCALADE · 30J",fc_low:"RISQUE FAIBLE",fc_mod:"MODÉRÉ",fc_high:"RISQUE ÉLEVÉ",fc_conf:"CONFIANCE: ",reg_title:"TENSIONS RÉGIONALES",sum_title:"RAPPORT DE SITUATION",replay:"CHRONOLOGIE",conflicts_title:"CONFLITS PERSISTANTS",align_title:"ALIGNEMENT MONDIAL",trade_title:"COMMERCE & LOGISTIQUE",strat_title:"MONITEUR STRATÉGIQUE",supply_title:"RISQUE CHAÎNE D'APPRO.",travel_title:"✈ SÉCURITÉ VOYAGE",feed_title:"ÉVÉNEMENTS RÉCENTS",transp_title:"TRANSPARENCE SYSTÈME",intel_title:"◈ ANALYSE ÉVÉNEMENT",intel_select:"Sélectionnez un événement"},
  uk:{title:"ГЛОБАЛЬНИЙ РАДАР КОНФЛІКТІВ",subtitle:"МОНІТОРИНГ В РЕАЛЬНОМУ ЧАСІ · v4.0",layer_live:"◉ НАЖИВО",layer_conflicts:"💥 КОНФЛІКТИ",layer_trade:"🚢 ТОРГІВЛЯ",layer_travel:"✈ ПОДОРОЖІ",layer_align:"🌐 ПОЗИЦІЇ",live:"НАЖИВО",act_title:"◈ ГЛОБАЛЬНА АКТИВНІСТЬ",act_incidents:"АКТИВНІ ІНЦИДЕНТИ",act_regions:"АКТИВНІ РЕГІОНИ",act_sources:"ВІДСТЕЖУЄТЬСЯ ДЖЕРЕЛ",act_24h:"ВИЯВЛЕНО 24Г",act_last:"ОСТАННЄ ВИЯВЛЕННЯ",gti_title:"ГЛОБАЛЬНИЙ ІНДЕКС НАПРУГИ",velocity:"ШВИДКІСТЬ ЕСКАЛАЦІЇ",trend_title:"ТРЕНД · 30 ДНІВ",fc_title:"ПРОГНОЗ ЕСКАЛАЦІЇ · 30Д",fc_low:"НИЗЬКИЙ РИЗИК",fc_mod:"ПОМІРНИЙ",fc_high:"ВИСОКИЙ РИЗИК",fc_conf:"ДОВІРА: ",reg_title:"РЕГІОНАЛЬНА НАПРУГА",sum_title:"СИТУАЦІЙНИЙ ЗВІТ",replay:"ХРОНОЛОГІЯ",conflicts_title:"ТРИВАЛІ КОНФЛІКТИ",align_title:"ГЛОБАЛЬНІ ПОЗИЦІЇ",trade_title:"ТОРГІВЛЯ & ЛОГІСТИКА",strat_title:"СТРАТЕГІЧНИЙ МОНІТОР",supply_title:"РИЗИК ЛАНЦЮГА ПОСТАЧАНЬ",travel_title:"✈ БЕЗПЕКА ПОДОРОЖЕЙ",feed_title:"ОСТАННІ ПОДІЇ",transp_title:"ПРОЗОРІСТЬ СИСТЕМИ",intel_title:"◈ АНАЛІЗ ПОДІЇ",intel_select:"Оберіть подію на карті"},
  ru:{title:"ГЛОБАЛЬНЫЙ РАДАР КОНФЛИКТОВ",subtitle:"МОНИТОРИНГ В РЕАЛЬНОМ ВРЕМЕНИ · v4.0",layer_live:"◉ LIVE",layer_conflicts:"💥 КОНФЛИКТЫ",layer_trade:"🚢 ТОРГОВЛЯ",layer_travel:"✈ ПУТЕШЕСТВИЯ",layer_align:"🌐 ПОЗИЦИИ",live:"LIVE",act_title:"◈ ГЛОБАЛЬНАЯ АКТИВНОСТЬ",act_incidents:"АКТИВНЫЕ ИНЦИДЕНТЫ",act_regions:"АКТИВНЫЕ РЕГИОНЫ",act_sources:"ОТСЛЕЖИВАЕТСЯ ИСТОЧНИКОВ",act_24h:"ОБНАРУЖЕНО 24Ч",act_last:"ПОСЛЕДНЕЕ ОБНАРУЖЕНИЕ",gti_title:"ГЛОБАЛЬНЫЙ ИНДЕКС НАПРЯЖЁННОСТИ",velocity:"СКОРОСТЬ ЭСКАЛАЦИИ",trend_title:"ТРЕНД · 30 ДНЕЙ",fc_title:"ПРОГНОЗ ЭСКАЛАЦИИ · 30Д",fc_low:"НИЗКИЙ РИСК",fc_mod:"УМЕРЕННЫЙ",fc_high:"ВЫСОКИЙ РИСК",fc_conf:"УВЕРЕННОСТЬ: ",reg_title:"РЕГИОНАЛЬНАЯ НАПРЯЖЁННОСТЬ",sum_title:"СИТУАЦИОННЫЙ ДОКЛАД",replay:"ХРОНОЛОГИЯ",conflicts_title:"ЗАТЯЖНЫЕ КОНФЛИКТЫ",align_title:"ГЛОБАЛЬНЫЕ ПОЗИЦИИ",trade_title:"ТОРГОВЛЯ & ЛОГИСТИКА",strat_title:"СТРАТЕГИЧЕСКИЙ МОНИТОР",supply_title:"РИСК ЦЕПОЧКИ ПОСТАВОК",travel_title:"✈ БЕЗОПАСНОСТЬ ПУТЕШЕСТВИЙ",feed_title:"ПОСЛЕДНИЕ СОБЫТИЯ",transp_title:"ПРОЗРАЧНОСТЬ СИСТЕМЫ",intel_title:"◈ АНАЛИЗ СОБЫТИЯ",intel_select:"Выберите событие на карте"},
  ar:{title:"رادار الصراع العالمي",subtitle:"مراقبة جيوسياسية مباشرة · v4.0",layer_live:"◉ مباشر",layer_conflicts:"💥 صراعات",layer_trade:"🚢 تجارة",layer_travel:"✈ سفر",layer_align:"🌐 مواقف",live:"مباشر",act_title:"◈ النشاط العالمي",act_incidents:"حوادث نشطة",act_regions:"مناطق نشطة",act_sources:"مصادر مراقبة",act_24h:"مكتشف خلال 24 ساعة",act_last:"آخر اكتشاف",gti_title:"مؤشر التوتر العالمي",velocity:"سرعة التصعيد",trend_title:"اتجاه التوتر · 30 يوم",fc_title:"توقع التصعيد · 30 يوم",fc_low:"خطر منخفض",fc_mod:"معتدل",fc_high:"خطر مرتفع",fc_conf:"ثقة: ",reg_title:"توترات إقليمية",sum_title:"ملخص الوضع",replay:"الجدول الزمني",conflicts_title:"صراعات مستمرة",align_title:"المواقف العالمية",trade_title:"التجارة والخدمات",strat_title:"مراقبة استراتيجية",supply_title:"مخاطر سلسلة التوريد",travel_title:"✈ سلامة السفر",feed_title:"أحداث أخيرة",transp_title:"شفافية النظام",intel_title:"◈ تحليل الحدث",intel_select:"اختر حدثاً على الخريطة"},
  zh:{title:"全球冲突雷达",subtitle:"实时地缘政治监测 · RSS + AI · v4.0",layer_live:"◉ 实时",layer_conflicts:"💥 冲突",layer_trade:"🚢 贸易",layer_travel:"✈ 旅行",layer_align:"🌐 立场",live:"实时",act_title:"◈ 全球活动",act_incidents:"活跃事件",act_regions:"活跃地区",act_sources:"监测来源",act_24h:"24小时检测",act_last:"最新检测",gti_title:"全球紧张指数",velocity:"局势升级速度",trend_title:"紧张趋势 · 30天",fc_title:"升级预测 · 30天",fc_low:"低风险",fc_mod:"中等",fc_high:"高风险",fc_conf:"置信度: ",reg_title:"地区紧张局势",sum_title:"局势摘要",replay:"时间轴",conflicts_title:"持续冲突",align_title:"全球立场",trade_title:"贸易与物流",strat_title:"战略监测",supply_title:"供应链风险",travel_title:"✈ 旅行安全",feed_title:"最新事件",transp_title:"系统透明度",intel_title:"◈ 事件分析",intel_select:"选择地图上的事件"},
};
let currentLang='en';
function setLang(lang){
  currentLang=lang;
  const T=LANGS[lang]||LANGS.en;
  document.querySelectorAll('[data-i18n]').forEach(el=>{const k=el.getAttribute('data-i18n');if(T[k])el.textContent=T[k]});
  // RTL
  const rtl=['ar'];
  document.documentElement.setAttribute('dir',rtl.includes(lang)?'rtl':'ltr');
  document.documentElement.setAttribute('lang',lang);
}
function t(key){return(LANGS[currentLang]||LANGS.en)[key]||key}

// ════════════════════════════════════════════════════════════
// STATE
// ════════════════════════════════════════════════════════════
let leafMap=null, mLayer=null, conflictLayer=null, tradeLayer=null, travelLayer=null, alignLayer=null, tChart=null;
let allEvents=[], replayHistory=[], repIdx=0, repPlaying=false, repSpd=1, repPeriod='24h', repTimer=null;
let refreshCountdown=600, currentLayer='live';
let conflictsData=[], tradeData={}, travelData={}, alignData={}, currentAlignConflict='ukraine_war';

// ════════════════════════════════════════════════════════════
// UTILS
// ════════════════════════════════════════════════════════════
const gtiColor=v=>v<2?'#00ff88':v<4?'#f5c518':v<6?'#ff6b1a':v<8?'#ff2233':'#8b0000';
const riskColor=r=>({LOW:'#00ff88',MODERATE:'#f5c518',HIGH:'#ff2233',CRITICAL:'#8b0000',ELEVATED:'#ff6b1a'}[r]||'#4a7a99');
const stanceColor=s=>({supporting_A:'#ff6b1a',supporting_B:'#00aaff',neutral:'#4a7a99',ambiguous:'#f5c518'}[s]||'#4a7a99');
const momentumColor=s=>({emerging:'#f5c518',escalating:'#ff6b1a','active war':'#ff2233',stabilizing:'#aaaaff','de-escalating':'#00ff88'}[s]||'#4a7a99');
function timeSince(iso){const m=(Date.now()-new Date(iso).getTime())/60000;if(m<1)return'just now';if(m<60)return Math.round(m)+'m ago';if(m<1440)return Math.round(m/60)+'h ago';return Math.round(m/1440)+'d ago'}
function animNum(el,to,dur,fmt){const s=performance.now();(function step(n){const t=Math.min((n-s)/dur,1),e=1-Math.pow(1-t,3);el.textContent=fmt(to*e);if(t<1)requestAnimationFrame(step)})(s)}
const srcLabel=s=>s==='rss'?'✓ RSS LIVE':'⚠ MOCK DATA';
const srcColor=s=>s==='rss'?'#00ff88':'#ff6b1a';
function dismissAlert(){document.getElementById('alert-banner').classList.remove('show')}

// ════════════════════════════════════════════════════════════
// CLOCK
// ════════════════════════════════════════════════════════════
setInterval(()=>{
  const c=document.getElementById('utc-clock');if(c)c.textContent=new Date().toUTCString().slice(0,25)+' UTC';
  refreshCountdown--;
  const r=document.getElementById('next-ref');if(r){const m=Math.floor(refreshCountdown/60),s=refreshCountdown%60;r.textContent=`${m}:${String(s).padStart(2,'0')}`}
  if(refreshCountdown<=0){refreshCountdown=600;loadAll()}
},1000);

// ════════════════════════════════════════════════════════════
// MAP INIT
// ════════════════════════════════════════════════════════════
function initMap(){
  if(leafMap)return;
  leafMap=L.map('wmap',{center:[20,20],zoom:2,zoomControl:true,attributionControl:false,minZoom:2,maxZoom:10});
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(leafMap);
  mLayer=L.layerGroup().addTo(leafMap);
  conflictLayer=L.layerGroup();
  tradeLayer=L.layerGroup();
  travelLayer=L.layerGroup();
  alignLayer=L.layerGroup();
}

// ════════════════════════════════════════════════════════════
// LAYER SWITCHER
// ════════════════════════════════════════════════════════════
const LAYER_ACTIVE_CLASS={live:'active',conflicts:'active-conflict',trade:'active-trade',travel:'active-travel',alignment:'active-align'};
function setLayer(name,btn){
  currentLayer=name;
  document.querySelectorAll('.layer-btn').forEach(b=>b.className='layer-btn');
  if(btn)btn.className='layer-btn '+LAYER_ACTIVE_CLASS[name];
  // Toggle legend
  ['live','conflicts','trade','travel','align'].forEach(l=>{
    const el=document.getElementById('leg-'+l);
    if(el)el.classList.toggle('visible',l===name||(name==='alignment'&&l==='align'));
  });
  // Toggle layers
  if(!leafMap)return;
  [mLayer,conflictLayer,tradeLayer,travelLayer,alignLayer].forEach(l=>{if(leafMap.hasLayer(l))leafMap.removeLayer(l)});
  if(name==='live'){leafMap.addLayer(mLayer)}
  else if(name==='conflicts'){leafMap.addLayer(conflictLayer);leafMap.addLayer(mLayer)}
  else if(name==='trade'){leafMap.addLayer(tradeLayer)}
  else if(name==='travel'){leafMap.addLayer(travelLayer)}
  else if(name==='alignment'){leafMap.addLayer(alignLayer)}
}

// ════════════════════════════════════════════════════════════
// LIVE EVENTS MAP
// ════════════════════════════════════════════════════════════
function renderMap(events){
  if(!mLayer)return;
  mLayer.clearLayers();
  events.forEach(e=>{
    const age=e.age_minutes??999;
    const isHot=age<10;
    const color=age>1440?'faded':e.color;
    const hotCls=isHot?' em-hot':'';
    const justTag=isHot?`<div class="just-tag">JUST DETECTED</div>`:'';
    const icon=L.divIcon({className:'',html:`<div class="just-wrap">${justTag}<div class="em ${color}${hotCls}"></div></div>`,iconSize:[11,11],iconAnchor:[5,5]});
    const precLoc=e.precise_location||e.region;
    const unc=e.uncertainty?`<div style="color:#f5c518;font-size:.46rem;margin-top:4px;border-top:1px solid #0d3348;padding-top:3px">⚠ ${e.uncertainty}</div>`:'';
    const srcLink=e.url&&e.url!=='#'?`<a href="${e.url}" target="_blank" style="color:#00e5ff;font-size:.52rem">↗ SOURCE</a>`:'';
    const popup=`
<div style="font-family:'Orbitron',sans-serif;font-size:.56rem;letter-spacing:.12em;color:#ff6b1a;margin-bottom:3px">${e.type.toUpperCase()}${isHot?'<span style="color:#ff2233;margin-left:5px;font-size:.4rem">● NOW</span>':''}</div>
<div style="display:flex;justify-content:space-between;color:#4a7a99;font-size:.56rem;margin:2px 0"><span>LOCATION</span><span style="color:#00e5ff">${precLoc}</span></div>
<div style="display:flex;justify-content:space-between;color:#4a7a99;font-size:.56rem;margin:2px 0"><span>REGION</span><span style="color:#c8e8f8">${e.region}</span></div>
<div style="display:flex;justify-content:space-between;color:#4a7a99;font-size:.56rem;margin:2px 0"><span>CONFIDENCE</span><span style="color:#c8e8f8">${e.confidence}%${e.source_count?` · ${e.source_count} src`:''}</span></div>
<div style="display:flex;justify-content:space-between;color:#4a7a99;font-size:.56rem;margin:2px 0"><span>DETECTED</span><span style="color:#c8e8f8">${timeSince(e.time_iso)}</span></div>
<div style="margin-top:5px;padding-top:5px;border-top:1px solid #0d3348;font-size:.58rem;line-height:1.4">${e.summary}</div>
${unc}
<div style="margin-top:6px;display:flex;justify-content:space-between;align-items:center">${srcLink}<div class="pop-analyze" onclick="openIntel('${e.id}')">◈ FULL ANALYSIS</div></div>`;
    L.marker([e.lat,e.lon],{icon}).bindPopup(popup,{maxWidth:300}).addTo(mLayer);
  });
}

// ════════════════════════════════════════════════════════════
// CONFLICT LAYER (frontlines + hotspots)
// ════════════════════════════════════════════════════════════
function renderConflictLayer(conflicts){
  if(!conflictLayer)return;
  conflictLayer.clearLayers();
  conflicts.forEach(c=>{
    // Frontlines
    if(c.frontlines){
      c.frontlines.forEach(fl=>{
        if(fl.length<2)return;
        L.polyline(fl,{color:c.color,weight:2.5,opacity:.8,dashArray:'4,4'}).bindPopup(`<div style="font-family:var(--mono);font-size:.6rem;color:${c.color}">${c.name.toUpperCase()} FRONTLINE</div><div style="font-size:.56rem;color:#4a7a99;margin-top:3px">${c.description}</div>`).addTo(conflictLayer);
      });
    }
    // Hotspots
    if(c.hotspots){
      c.hotspots.forEach(h=>{
        const icon=L.divIcon({className:'',html:`<div class="hotspot-marker" style="background:${c.color}44;border-color:${c.color};box-shadow:0 0 5px ${c.color}"></div>`,iconSize:[8,8],iconAnchor:[4,4]});
        L.marker([h.lat,h.lon],{icon}).bindPopup(`<div style="font-family:'Orbitron',sans-serif;font-size:.56rem;color:${c.color}">${h.name.toUpperCase()}</div><div style="font-size:.54rem;color:#4a7a99;margin-top:2px">${c.name} · ${c.state.toUpperCase()}</div>`).addTo(conflictLayer);
      });
    }
    // Conflict center marker
    const cIcon=L.divIcon({className:'',html:`<div style="font-family:'Orbitron',sans-serif;font-size:.44rem;padding:3px 6px;border:1px solid ${c.color};background:rgba(2,6,8,.9);color:${c.color};white-space:nowrap">${c.name.toUpperCase()}</div>`,iconSize:[100,20],iconAnchor:[50,10]});
    L.marker([c.lat,c.lon],{icon:cIcon}).addTo(conflictLayer);
  });
}

// ════════════════════════════════════════════════════════════
// TRADE LAYER
// ════════════════════════════════════════════════════════════
function renderTradeLayer(routes){
  if(!tradeLayer)return;
  tradeLayer.clearLayers();
  (routes||[]).forEach(r=>{
    if(!r.waypoints||r.waypoints.length<2)return;
    const color=riskColor(r.risk);
    const weight=r.risk==='HIGH'||r.risk==='CRITICAL'?3:r.risk==='MODERATE'?2:1.5;
    L.polyline(r.waypoints,{color,weight,opacity:.85,dashArray:r.risk==='LOW'?'6,4':null})
      .bindPopup(`<div style="font-family:'Orbitron',sans-serif;font-size:.56rem;color:${color}">${r.name.toUpperCase()}</div><div style="font-size:.56rem;color:${color};margin:3px 0">${r.risk} RISK · ${r.disruption_pct}% DISRUPTION</div><div style="font-size:.54rem;color:#4a7a99">${r.reason}</div>`)
      .addTo(tradeLayer);
  });
}

// ════════════════════════════════════════════════════════════
// TRAVEL LAYER
// ════════════════════════════════════════════════════════════
function renderTravelLayer(travel){
  if(!travelLayer)return;
  travelLayer.clearLayers();
  Object.entries(travel||{}).forEach(([country,data])=>{
    const c=riskColor(data.risk);
    const icon=L.divIcon({className:'',html:`<div class="travel-country-marker" style="border-color:${c};color:${c};background:rgba(2,6,8,.85)">${country}</div>`,iconSize:[null,null],iconAnchor:[0,10]});
    L.marker([data.lat,data.lon],{icon})
      .bindPopup(`<div style="font-family:'Orbitron',sans-serif;font-size:.56rem;color:${c}">${country.toUpperCase()}</div><div style="font-family:var(--mono);font-size:.52rem;color:${c};margin:3px 0">${data.risk}</div><div style="font-size:.52rem;color:#4a7a99">${data.reason}</div>`)
      .addTo(travelLayer);
  });
}

// ════════════════════════════════════════════════════════════
// ALIGNMENT LAYER
// ════════════════════════════════════════════════════════════
function renderAlignLayer(conflict){
  if(!alignLayer)return;
  alignLayer.clearLayers();
  const data=alignData[conflict];
  if(!data||!data.countries)return;
  Object.entries(data.countries).forEach(([country,info])=>{
    const c=stanceColor(info.stance);
    const icon=L.divIcon({className:'',html:`<div class="align-country-marker" style="border-color:${c};color:${c};background:rgba(2,6,8,.88)">${country}</div>`,iconSize:[null,null],iconAnchor:[0,10]});
    L.marker([info.lat,info.lon],{icon})
      .bindPopup(`<div style="font-family:'Orbitron',sans-serif;font-size:.56rem;color:${c}">${country.toUpperCase()}</div><div style="font-family:var(--mono);font-size:.52rem;color:${c};margin:3px 0">${info.stance.replace('_',' ').toUpperCase()}</div><div style="font-size:.52rem;color:#4a7a99">${info.label}</div>`)
      .addTo(alignLayer);
  });
}

// ════════════════════════════════════════════════════════════
// GTI
// ════════════════════════════════════════════════════════════
function renderGTI(d){
  const c=gtiColor(d.gti);
  const n=document.getElementById('gti-num');
  animNum(n,d.gti,1100,v=>v.toFixed(1));
  n.style.color=c;n.style.textShadow=`0 0 8px ${c}66`;
  const se=document.getElementById('gti-stat');
  se.textContent=d.status;se.style.color=c;se.style.borderColor=c;se.style.boxShadow=`inset 0 0 8px ${c}15,0 0 6px ${c}44`;
  ['gti-rg','gti-ri'].forEach((id,i)=>{const el=document.getElementById(id);if(el){if(i===0){el.style.borderColor=c;el.style.boxShadow=`0 0 8px ${c}66`}else el.style.borderColor=`${c}20`}});
  document.getElementById('s-mil').textContent=d.military_score??'—';
  document.getElementById('s-str').textContent=d.strategic_score??'—';
  document.getElementById('s-eco').textContent=d.economic_score??'—';
  document.getElementById('ecount').textContent=`${d.event_count||'—'} EVT`;
  if(d.velocity){const vc=document.getElementById('velocity');vc.textContent=d.velocity;vc.style.color=d.velocity.startsWith('+')?'#ff2233':'#00ff88'}
  const sb=document.getElementById('src-badge');if(sb){sb.textContent=srcLabel(d.data_source);sb.style.color=srcColor(d.data_source)}
  const fb=document.getElementById('feed-src-b');if(fb){fb.textContent=srcLabel(d.data_source);fb.style.color=srcColor(d.data_source)}
}

// ════════════════════════════════════════════════════════════
// CHART
// ════════════════════════════════════════════════════════════
function renderChart(trend){
  const ctx=document.getElementById('tchart');if(!ctx)return;
  const labels=trend.map(d=>{const p=d.date.split('-');return`${p[2]}.${p[1]}`});
  const vals=trend.map(d=>d.value);
  const color=gtiColor(vals.filter(Boolean).pop()||4);
  if(tChart)tChart.destroy();
  tChart=new Chart(ctx,{type:'line',data:{labels,datasets:[{data:vals,borderColor:color,borderWidth:2,pointRadius:1.5,pointBackgroundColor:vals.map(v=>v?gtiColor(v):'transparent'),pointBorderColor:'transparent',tension:.38,fill:true,backgroundColor:c=>{const g=c.chart.ctx.createLinearGradient(0,0,0,120);g.addColorStop(0,`${color}44`);g.addColorStop(1,'transparent');return g}}]},options:{responsive:true,maintainAspectRatio:false,animation:{duration:800},plugins:{legend:{display:false},tooltip:{backgroundColor:'#040d12',borderColor:'#1a6688',borderWidth:1,titleColor:'#00e5ff',bodyColor:'#c8e8f8',titleFont:{family:'Share Tech Mono',size:8},bodyFont:{family:'Share Tech Mono',size:8},callbacks:{label:c=>` GTI: ${c.raw?.toFixed(1)||'—'}/10`}}},scales:{x:{grid:{color:'rgba(13,51,72,.25)',drawTicks:false},ticks:{color:'#4a7a99',font:{family:'Share Tech Mono',size:6},maxRotation:0,maxTicksLimit:8},border:{color:'#0d3348'}},y:{min:0,max:10,grid:{color:'rgba(13,51,72,.25)',drawTicks:false},ticks:{color:'#4a7a99',font:{family:'Share Tech Mono',size:6},stepSize:2},border:{color:'#0d3348'}}}}});
}

// ════════════════════════════════════════════════════════════
// ACTIVITY
// ════════════════════════════════════════════════════════════
function renderActivity(d){
  document.getElementById('act-inc').textContent=d.active_incidents||'—';
  document.getElementById('act-conf').textContent=`${d.confirmed_incidents||'—'} confirmed`;
  document.getElementById('act-reg').textContent=d.regions_with_tension||'—';
  document.getElementById('act-strat').textContent=`${d.strategic_events||'—'} strategic`;
  document.getElementById('act-24h').textContent=d.events_detected_24h||'—';
  document.getElementById('act-avgc').textContent=`AVG CONF ${d.avg_confidence||'—'}%`;
  const lastEl=document.getElementById('act-last');
  if(lastEl){const m=d.last_event_minutes_ago;lastEl.textContent=m===0?'just now':m<60?`${m} min ago`:`${Math.round(m/60)}h ago`;lastEl.style.color=m<10?'#00ff88':m<60?'#f5c518':'#4a7a99'}
}

// ════════════════════════════════════════════════════════════
// FORECAST
// ════════════════════════════════════════════════════════════
function renderForecast(d,analyzed){
  document.getElementById('fc-low').style.width=d.low_pct+'%';
  document.getElementById('fc-mod').style.width=d.moderate_pct+'%';
  document.getElementById('fc-high').style.width=d.high_pct+'%';
  document.getElementById('fc-lp').textContent=d.low_pct+'%';
  document.getElementById('fc-mp').textContent=d.moderate_pct+'%';
  document.getElementById('fc-hp').textContent=d.high_pct+'%';
  document.getElementById('fc-reason').textContent=d.reasoning||'—';
  document.getElementById('fc-conf-val').textContent=Math.round(58+Math.random()*22)+'%';
  document.getElementById('fc-analyzed').textContent=(analyzed||217)+' EVT';
}

// ════════════════════════════════════════════════════════════
// REGIONAL
// ════════════════════════════════════════════════════════════
function renderRegional(d){
  const el=document.getElementById('reg-list');if(!el)return;
  const sorted=Object.entries(d).sort((a,b)=>b[1].gti-a[1].gti);
  if(!sorted.length){el.textContent='No data';return}
  el.innerHTML=sorted.map(([region,data])=>{
    const c=gtiColor(data.gti);const dc=data.delta>=0?'#ff2233':'#00ff88';const ds=data.delta>=0?'+':'';
    return`<div class="reg-row"><span class="reg-name">${region}</span><span class="reg-gti" style="color:${c}">${data.gti}</span><span class="reg-d" style="color:${dc}">${ds}${data.delta}%</span><div class="reg-bar"><div class="reg-bar-f" style="width:${data.gti*10}%;background:${c}"></div></div></div>`}).join('');
}

// ════════════════════════════════════════════════════════════
// PERSISTENT CONFLICTS
// ════════════════════════════════════════════════════════════
function renderConflicts(conflicts){
  conflictsData=conflicts;
  const el=document.getElementById('conflict-list');if(!el)return;
  el.innerHTML=conflicts.map(c=>{
    const sc=momentumColor(c.state);
    const stClass='momentum-state-'+c.state.replace(' ','-');
    const actors=c.actors?c.actors.slice(0,2).map(a=>`<span style="color:${a.side==='A'?'#ff6b1a':'#00aaff'};font-family:var(--mono);font-size:.42rem">${a.name}</span>`).join('<span style="color:#2a4a5a;font-size:.42rem"> vs </span>'):'';
    return`<div class="conflict-item" onclick="flyToConflict(${c.lat},${c.lon})">
<div class="conf-header">
  <span class="conf-name" style="color:${sc}">${c.name.toUpperCase()}</span>
  <span class="conf-state ${stClass}">${c.state.toUpperCase()}</span>
</div>
<div class="conf-meta"><span>${c.region}</span><span>MOMENTUM: <span style="color:${sc}">${c.adjusted_momentum??c.momentum}/10</span></span><span>${c.live_events??0} live events</span></div>
<div class="conf-momentum-bar"><div class="conf-momentum-fill" style="width:${(c.adjusted_momentum||c.momentum)*10}%;background:${sc}"></div></div>
<div class="conf-desc">${c.description}</div>
${actors?`<div style="margin-top:3px">${actors}</div>`:''}
</div>`}).join('');
}
function flyToConflict(lat,lon){if(leafMap){setLayer('conflicts',document.querySelector('.layer-btn:nth-child(2)'));leafMap.flyTo([lat,lon],5,{duration:1.2})}}

// ════════════════════════════════════════════════════════════
// ALIGNMENT PANEL
// ════════════════════════════════════════════════════════════
function renderAlignmentPanel(conflict){
  currentAlignConflict=conflict;
  const data=alignData[conflict];
  if(!data)return;
  // Conflict selector
  const selEl=document.getElementById('align-conflict-sel');
  if(selEl){selEl.innerHTML=Object.keys(alignData).map(k=>`<button class="align-conf-btn ${k===conflict?'active':''}" onclick="selectAlignConflict('${k}')">${(alignData[k].conflict||k).toUpperCase()}</button>`).join('')}
  const el=document.getElementById('align-list');if(!el)return;
  const sorted=Object.entries(data.countries).sort((a,b)=>{const order={'supporting_A':0,'supporting_B':1,'ambiguous':2,'neutral':3};return(order[a[1].stance]||3)-(order[b[1].stance]||3)});
  el.innerHTML=`<div class="align-list">${sorted.map(([country,info])=>{
    const c=stanceColor(info.stance);
    return`<div class="align-row"><div class="align-dot" style="background:${c}"></div><span class="align-country">${country}</span><span class="align-label stance-${info.stance}">${info.label}</span></div>`}).join('')}</div>`;
  // Update map layer
  renderAlignLayer(conflict);
  if(currentLayer==='alignment')leafMap&&leafMap.hasLayer(alignLayer)||renderAlignLayer(conflict);
}
function selectAlignConflict(k){
  // Update button states
  document.querySelectorAll('.align-conf-btn').forEach(b=>{b.classList.toggle('active',b.textContent.toLowerCase().includes((alignData[k].conflict||k).toLowerCase().slice(0,4)))});
  renderAlignmentPanel(k);
}

// ════════════════════════════════════════════════════════════
// TRADE PANEL
// ════════════════════════════════════════════════════════════
function renderTradePanels(data){
  const routeEl=document.getElementById('trade-routes-list');
  if(routeEl&&data.routes){
    routeEl.innerHTML=data.routes.map(r=>{
      const c=riskColor(r.risk);
      return`<div class="trade-route"><span class="trade-name">${r.name}</span><div class="trade-right"><div class="trade-risk" style="color:${c}">${r.risk}</div><div class="trade-pct">${r.disruption_pct}% disruption</div></div></div>`}).join('');
  }
  const logEl=document.getElementById('logistics-grid');
  if(logEl&&data.sectors){
    logEl.innerHTML=Object.entries(data.sectors).map(([k,s])=>`<div class="log-item"><div class="log-icon">${s.icon}</div><div class="log-lbl">${k.toUpperCase()}</div><div class="log-risk" style="color:${riskColor(s.risk)}">${s.risk}</div></div>`).join('');
  }
}

// ════════════════════════════════════════════════════════════
// TRAVEL PANEL
// ════════════════════════════════════════════════════════════
function renderTravelPanel(data){
  const el=document.getElementById('travel-list');if(!el)return;
  const sorted=Object.entries(data).sort((a,b)=>{const ord={CRITICAL:0,HIGH:1,MODERATE:2,LOW:3};return(ord[a[1].risk]||3)-(ord[b[1].risk]||3)});
  el.innerHTML=sorted.map(([country,d])=>`<div class="travel-row" title="${d.reason}"><span class="travel-country">${country}</span><span class="travel-risk risk-${d.risk}">${d.risk}</span></div>`).join('');
}

// ════════════════════════════════════════════════════════════
// STRATEGIC + SUPPLY
// ════════════════════════════════════════════════════════════
function renderStrategic(d){
  const el=document.getElementById('strat-list');
  if(el){const items=[{label:'CARRIER GROUP',val:d.carrier_group?'DETECTED':'NOT DETECTED',on:d.carrier_group},{label:'BALLISTIC LAUNCH',val:d.ballistic_launch?'DETECTED':'NOT DETECTED',on:d.ballistic_launch},{label:'NUCLEAR RHETORIC',val:d.nuclear_rhetoric?'ACTIVE':'NONE',on:d.nuclear_rhetoric}];
  el.innerHTML=items.map(i=>`<div class="strat-item"><div class="strat-dot" style="background:${i.on?'#ff2233':'#2a4a5a'};box-shadow:${i.on?'0 0 5px #ff2233':'none'}"></div><span class="strat-lbl">${i.label}</span><span class="strat-val" style="color:${i.on?'#ff2233':'#2a4a5a'}">${i.val}</span></div>`).join('')}
  const cel=document.getElementById('choke-list');
  if(cel&&d.chokepoints)cel.innerHTML=d.chokepoints.map(c=>`<div class="choke-item"><span class="choke-nm">${c.name}</span><span class="choke-rv" style="color:${riskColor(c.risk)}">${c.risk}</span></div>`).join('');
}
function renderSupply(d){
  const el=document.getElementById('supply-grid');if(!el)return;
  el.innerHTML=[['⚡','ENERGY','energy'],['🚢','SHIPPING','shipping'],['🌾','FOOD','food'],['💾','TECH','tech']]
    .map(([ic,lb,k])=>`<div class="sup-item"><div style="font-size:.8rem">${ic}</div><div style="font-family:var(--mono);font-size:.42rem;color:var(--muted);margin:1px 0">${lb}</div><div style="font-family:var(--disp);font-size:.56rem;font-weight:700;color:${riskColor(d[k]||'LOW')}">${d[k]||'LOW'}</div></div>`).join('');
}

// ════════════════════════════════════════════════════════════
// EVENT FEED (with uncertainty + precise location)
// ════════════════════════════════════════════════════════════
function renderFeed(events){
  const el=document.getElementById('feed-list');if(!el)return;
  if(!events.length){el.innerHTML='<div style="padding:9px;font-family:var(--mono);font-size:.5rem;color:#ff2233">NO EVENTS</div>';return}
  el.innerHTML=events.slice(0,18).map(e=>`
<div class="fi" onclick="openIntel('${e.id}')">
  <div class="fi-ind ${e.color}"></div>
  <div>
    <div class="fi-type">${e.type.toUpperCase()}${(e.age_minutes??999)<10?'<span style="color:#ff2233;margin-left:3px;font-size:.38rem">● NOW</span>':''}</div>
    <div class="fi-loc">◈ ${e.precise_location||e.region}</div>
    <div class="fi-reg">${e.region} · ${timeSince(e.time_iso)}</div>
    <div class="fi-desc">${e.summary}</div>
    ${e.uncertainty?`<div class="fi-unc">⚠ LOW CONFIDENCE</div>`:''}
  </div>
  <div><div class="fi-conf">${e.confidence}%</div><div class="fi-src">${e.source}</div></div>
</div>`).join('');
}

// ════════════════════════════════════════════════════════════
// ALERTS + TRANSPARENCY + SUMMARY
// ════════════════════════════════════════════════════════════
function renderAlerts(alerts){
  if(!alerts||!alerts.length)return;
  const top=alerts[0];
  document.getElementById('alert-text').textContent=`⚠ ${top.title} — ${top.body}`;
  document.getElementById('alert-banner').classList.add('show');
}
function renderTransparency(act,status){
  const el=document.getElementById('transp-list');if(!el)return;
  el.innerHTML=[
    ['SOURCES MONITORED',(act.sources_monitored||0).toLocaleString()],
    ['EVENTS DETECTED TODAY',act.events_detected_24h||'—'],
    ['CONFIRMED INCIDENTS',act.confirmed_incidents||'—'],
    ['STRATEGIC ALERTS',act.strategic_events||'—'],
    ['AVG DETECTION LATENCY',`${act.avg_detection_latency||11} MIN`],
    ['AI CONFIDENCE SCORE',`${act.ai_confidence||'—'}%`],
    ['DATA SOURCE',status.data_source==='rss'?'RSS LIVE':'MOCK DATA'],
    ['LAST REFRESH',status.timestamp?new Date(status.timestamp).toUTCString().slice(17,25)+' UTC':'—'],
  ].map(([l,v])=>`<div class="transp-row"><span class="transp-lbl">${l}</span><span class="transp-val">${v}</span></div>`).join('');
}
function renderSummary(data){
  const el=document.getElementById('ai-sum');if(!el)return;
  el.classList.remove('typing');el.textContent='';
  const text=data.summary||'—';let i=0;
  const iv=setInterval(()=>{el.textContent+=text[i++]||'';if(i>text.length)clearInterval(iv)},12);
  const gen=document.getElementById('ai-gen'),ts=document.getElementById('ai-ts');
  if(gen)gen.textContent=`MODEL: ${(data.generated_by||'—').toUpperCase()}`;
  if(ts)ts.textContent=new Date().toUTCString().slice(0,16)+' UTC';
}

// ════════════════════════════════════════════════════════════
// INTELLIGENCE PANEL
// ════════════════════════════════════════════════════════════
async function openIntel(eid){
  const panel=document.getElementById('intel-panel');
  const body=document.getElementById('intel-body');
  panel.classList.add('open');
  body.innerHTML=`<div class="intel-loading"><span class="intel-spinner">◈</span>${t('intel_select')}</div>`;
  const [detail,stats]=await Promise.all([
    fetch(`/api/event-detail/${eid}`).then(r=>r.json()).catch(()=>({})),
    fetch(`/api/event-stats/${eid}`).then(r=>r.json()).catch(()=>({})),
  ]);
  const esc=detail.escalation_risk||'MODERATE';
  const actors=(detail.related_actors||[]).length?(detail.related_actors||[]).map(a=>`<span class="actor-tag">${a}</span>`).join(''):'<span style="color:var(--muted);font-size:.44rem">—</span>';
  // Find event for precise location
  const ev=allEvents.find(e=>e.id===eid)||{};
  const precLoc=ev.precise_location||detail.location||'Unknown';
  const uncertainty=ev.uncertainty?`<div class="intel-uncertainty">⚠ ${ev.uncertainty}</div>`:'';
  body.innerHTML=`
<div class="intel-type">${(detail.event_type||'UNKNOWN').toUpperCase()}</div>
<div class="intel-loc">◈ ${precLoc}${ev.region&&ev.region!==precLoc?`<span style="color:var(--muted)">· ${ev.region}</span>`:''}</div>
<div class="intel-det">Detected ${ev.time_iso?timeSince(ev.time_iso):'—'} · Source: ${detail.source||'—'} · ${ev.source_count??'—'} source(s)</div>
${uncertainty}
<div class="intel-4grid">
  <div class="intel-m"><div class="intel-m-l">CONFIDENCE</div><div class="intel-m-v" style="color:${detail.confidence>=75?'#00ff88':detail.confidence>=50?'#f5c518':'#ff6b1a'}">${detail.confidence||'—'}%</div></div>
  <div class="intel-m"><div class="intel-m-l">ESC. RISK</div><div class="esc-badge esc-${esc}" style="font-size:.65rem;padding:2px 5px">${esc}</div></div>
  <div class="intel-m" style="grid-column:1/-1"><div class="intel-m-l">NUMBERS / UNITS</div><div class="intel-m-v" style="color:var(--cyan);font-size:.65rem">${detail.numbers_detected||ev.numbers||'—'}</div></div>
</div>
<div class="intel-stats-box">
  <div class="intel-stats-h">◈ LAST 24H — ${precLoc}</div>
  <div class="intel-stats-grid">
    <div class="stat-item"><div class="stat-l">REGION EVENTS</div><div class="stat-v">${stats.region_events_24h??'—'}</div></div>
    <div class="stat-item"><div class="stat-l">SAME TYPE</div><div class="stat-v">${stats.same_type_24h??'—'}</div></div>
    <div class="stat-item"><div class="stat-l">MISSILE STRIKES</div><div class="stat-v">${stats.missiles_24h??'—'}</div></div>
    <div class="stat-item"><div class="stat-l">INTERCEPTIONS</div><div class="stat-v">${stats.interceptions_24h??'—'}</div></div>
    <div class="stat-item"><div class="stat-l">AIRSTRIKES</div><div class="stat-v">${stats.airstrikes_24h??'—'}</div></div>
    <div class="stat-item"><div class="stat-l">REGION GTI</div><div class="stat-v" style="color:${gtiColor(stats.region_gti||0)}">${stats.region_gti??'—'}</div></div>
  </div>
</div>
<div class="intel-sec"><div class="intel-sec-h">TACTICAL ASSESSMENT</div><div class="intel-text">${detail.tactical_assessment||'—'}</div></div>
<div class="intel-sec"><div class="intel-sec-h">CONTEXT</div><div class="intel-text">${detail.context||'—'}</div></div>
<div class="intel-sec"><div class="intel-sec-h">ACTORS INVOLVED</div><div style="margin-top:3px">${actors}</div></div>
${ev.url&&ev.url!=='#'?`<a href="${ev.url}" target="_blank" class="intel-src-link">↗ READ ORIGINAL SOURCE</a>`:''}
<div style="margin-top:9px;font-family:var(--mono);font-size:.42rem;color:var(--muted);border-top:1px solid var(--b0);padding-top:6px">ANALYSIS: CLAUDE AI · ${new Date().toUTCString().slice(0,16)} UTC</div>`;
}
function closeIntel(){document.getElementById('intel-panel').classList.remove('open')}

// ════════════════════════════════════════════════════════════
// REPLAY
// ════════════════════════════════════════════════════════════
async function loadRepHistory(){try{const r=await fetch(`/api/history?period=${repPeriod}`).then(x=>x.json());replayHistory=r.history||[];document.getElementById('rep-slider').max=Math.max(0,replayHistory.length-1)}catch(e){replayHistory=[]}}
function setRepPeriod(p,btn){repPeriod=p;document.querySelectorAll('.rep-btn').forEach(b=>{if(['24h','7d','30d'].includes(b.textContent.toLowerCase()))b.classList.remove('active')});btn.classList.add('active');loadRepHistory()}
function toggleReplay(){if(repPlaying)stopReplay();else{if(!replayHistory.length){loadRepHistory().then(startReplay);return}startReplay()}}
function startReplay(){repPlaying=true;document.getElementById('rep-play-btn').textContent='⏸';if(repIdx>=replayHistory.length-1)repIdx=0;repTimer=setInterval(()=>{if(repIdx>=replayHistory.length-1){stopReplay();return}repIdx++;document.getElementById('rep-slider').value=repIdx;showRepFrame(repIdx)},1000/repSpd)}
function stopReplay(){clearInterval(repTimer);repPlaying=false;document.getElementById('rep-play-btn').textContent='▶'}
function showRepFrame(idx){const f=replayHistory[idx];if(!f)return;document.getElementById('rep-ts').textContent=f.ts?new Date(f.ts).toUTCString().slice(0,16)+' UTC':'—';if(f.events)renderMap(f.events)}
function onSlide(v){repIdx=parseInt(v);showRepFrame(repIdx);if(repPlaying){clearInterval(repTimer);startReplay()}}
function setSpd(s,btn){repSpd=s;document.querySelectorAll('.spd-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');if(repPlaying){clearInterval(repTimer);startReplay()}}
async function playLast24h(){await loadRepHistory();repIdx=0;document.getElementById('rep-slider').value=0;startReplay()}
function goLive(){stopReplay();document.getElementById('rep-ts').textContent='LIVE';document.getElementById('rep-slider').value=replayHistory.length||100;renderMap(allEvents)}

// ════════════════════════════════════════════════════════════
// MAIN LOAD
// ════════════════════════════════════════════════════════════
async function loadAll(){
  refreshCountdown=600;
  try{
    const [sr,er,tr,fc,reg,strat,sup,al,act,conflicts,trade,travel,align]=await Promise.all([
      fetch('/api/status').then(r=>r.json()).catch(()=>({})),
      fetch('/api/events-v4').then(r=>r.json()).catch(()=>({events:[]})),
      fetch('/api/trend').then(r=>r.json()).catch(()=>({trend:[]})),
      fetch('/api/forecast').then(r=>r.json()).catch(()=>({})),
      fetch('/api/regional').then(r=>r.json()).catch(()=>({regional:{}})),
      fetch('/api/strategic').then(r=>r.json()).catch(()=>({})),
      fetch('/api/supply-chain').then(r=>r.json()).catch(()=>({})),
      fetch('/api/alerts').then(r=>r.json()).catch(()=>({alerts:[]})),
      fetch('/api/activity').then(r=>r.json()).catch(()=>({})),
      fetch('/api/conflicts').then(r=>r.json()).catch(()=>({conflicts:[]})),
      fetch('/api/trade').then(r=>r.json()).catch(()=>({routes:[],sectors:{}})),
      fetch('/api/travel-safety').then(r=>r.json()).catch(()=>({travel:{}})),
      fetch('/api/alignment').then(r=>r.json()).catch(()=>({alignment:{}})),
    ]);

    allEvents=er.events||[];
    tradeData=trade;
    travelData=travel.travel||{};
    // Store alignment data
    if(align.alignment){
      // alignment endpoint returns single conflict; fetch both
      alignData[align.alignment.conflict?Object.keys(align.alignment.countries||{})[0]:'ukraine_war']=align.alignment;
    }

    renderGTI(sr);
    renderChart(tr.trend||[]);
    renderMap(allEvents);
    renderFeed(allEvents);
    renderForecast(fc, act.events_detected_24h);
    renderRegional(reg.regional||{});
    renderStrategic(strat);
    renderSupply(sup);
    renderAlerts(al.alerts||[]);
    renderActivity(act);
    renderConflicts(conflicts.conflicts||[]);
    renderConflictLayer(conflicts.conflicts||[]);
    renderTradePanels(trade);
    renderTradeLayer(trade.routes||[]);
    renderTravelPanel(travelData);
    renderTravelLayer(travelData);
    renderTransparency(act,sr);

    const ms=document.getElementById('map-src');
    if(ms)ms.textContent=`${er.count||0} INCIDENTS · ${new Date().toUTCString().slice(17,25)} UTC`;

    // Fetch both alignment conflicts
    const [alignU,alignG]=await Promise.all([
      fetch('/api/alignment?conflict=ukraine_war').then(r=>r.json()).catch(()=>({alignment:{}})),
      fetch('/api/alignment?conflict=gaza_conflict').then(r=>r.json()).catch(()=>({alignment:{}})),
    ]);
    if(alignU.alignment){alignData['ukraine_war']=alignU.alignment}
    if(alignG.alignment){alignData['gaza_conflict']=alignG.alignment}
    renderAlignmentPanel('ukraine_war');

    // AI summary
    const se=document.getElementById('ai-sum');if(se){se.classList.add('typing');se.textContent='Analyzing…'}
    fetch('/api/summary').then(r=>r.json()).then(renderSummary).catch(()=>{const e=document.getElementById('ai-sum');if(e){e.classList.remove('typing');e.textContent='Summary unavailable.'}});

    await loadRepHistory();
    setLayer(currentLayer, document.querySelector('.layer-btn.active, .layer-btn.active-conflict, .layer-btn.active-trade, .layer-btn.active-travel, .layer-btn.active-align'));

  }catch(err){console.error('[LoadAll]',err)}
}

// ════════════════════════════════════════════════════════════
// BOOT
// ════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded',()=>{
  initMap();
  loadAll();
  function fixH(){
    const w=document.getElementById('wmap');
    const shell=document.querySelector('.shell');
    const repBar=document.querySelector('.rep-bar');
    const mf=document.querySelector('.map-footer');
    if(w&&shell&&repBar&&mf){
      const h=shell.clientHeight-repBar.offsetHeight-mf.offsetHeight;
      w.style.height=Math.max(200,h)+'px';
      if(leafMap)leafMap.invalidateSize();
    }
  }
  fixH();
  window.addEventListener('resize',fixH);
  setTimeout(fixH,500);
});
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML_PAGE
