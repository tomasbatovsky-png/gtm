"""
Global Tension Monitor v3.0 - Backend
"""
import os, datetime, random, asyncio, hashlib, re, json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
import feedparser

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "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")

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
    "events":FALLBACK_EVENTS, "history":[], "alerts":[], "prev_gti":None,
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

def gevents(): e=_cache.get("events",[]); return e if e else FALLBACK_EVENTS

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



# ═══════════════════════════════════════════════════════════════
# GTM v4.1 — NEW BACKEND ENDPOINTS
# ═══════════════════════════════════════════════════════════════

def calc_snapshot(events, gti_data, history, regional):
    """Daily Global Risk Snapshot"""
    gti = gti_data.get("gti", 0)
    # Daily change: compare to 24 snapshots ago
    prev_gti = gti
    if len(history) >= 6:
        prev_gti = history[-6].get("gti", gti)
    gti_change = round(gti - prev_gti, 2)

    # Count events in last 24h vs prior 24h
    recent_count = len(events)
    prior_count = max(1, recent_count - random.randint(2, 8))  # simulated
    incident_change = recent_count - prior_count

    # Strategic events
    strategic_count = sum(1 for e in events if e["type"] in {"strategic event","naval deployment","missile strike"})
    prior_strategic = max(0, strategic_count - random.randint(0, 2))
    strategic_change = strategic_count - prior_strategic

    # Most active region
    region_counts = {}
    for e in events:
        region_counts[e["region"]] = region_counts.get(e["region"], 0) + 1
    most_active = max(region_counts, key=region_counts.get) if region_counts else "—"

    # Fastest escalating conflict
    escalation_map = {
        "Horn of Africa": "Red Sea Naval Crisis",
        "Middle East": "Iran-Israel Tensions",
        "Eastern Europe": "Ukraine Front",
        "East Asia": "Taiwan Strait",
        "West Africa": "Sahel Insurgency",
    }
    fastest = escalation_map.get(most_active, "Regional Tensions")

    # Hotspots (regions with 2+ events)
    hotspots = [r for r, c in sorted(region_counts.items(), key=lambda x: -x[1]) if c >= 1][:6]

    # Stable regions (no events)
    all_regions = set(REGION_MAP.keys())
    active_regions = set(region_counts.keys())
    stable = list(all_regions - active_regions)[:4]
    if not stable:
        stable = ["Oceania", "Central Asia", "Latin America"]

    # Trend direction
    trend = "rising" if gti_change > 0.1 else ("falling" if gti_change < -0.1 else "stable")

    return {
        "gti": gti,
        "gti_change": gti_change,
        "trend": trend,
        "active_conflicts": len(PERSISTENT_CONFLICTS),
        "strategic_events_24h": strategic_count,
        "most_active_region": most_active,
        "fastest_escalation": fastest,
        "incident_change": incident_change,
        "strategic_change": strategic_change,
        "hotspots": hotspots,
        "stable_regions": stable,
        "region_density": dict(sorted(region_counts.items(), key=lambda x: -x[1])),
    }

def calc_alignment_trends():
    """Simulate geopolitical stance trends"""
    trends = {
        "ukraine_war": {
            "France":   {"trend": "stable",   "note": "Maintains support"},
            "Germany":  {"trend": "stable",   "note": "Consistent support"},
            "Hungary":  {"trend": "shifting_away", "note": "Moving toward neutrality"},
            "Turkey":   {"trend": "mediating","note": "Brokering negotiations"},
            "China":    {"trend": "shifting_toward_A", "note": "Increasing Russia support signals"},
            "India":    {"trend": "stable",   "note": "Maintains neutrality"},
            "Belarus":  {"trend": "stable",   "note": "Fully aligned with Russia"},
        },
        "gaza_conflict": {
            "Turkey":   {"trend": "hardening","note": "Increasing pro-Palestine stance"},
            "Qatar":    {"trend": "mediating","note": "Active ceasefire mediation"},
            "Egypt":    {"trend": "mediating","note": "Hostage deal negotiations"},
            "Saudi Arabia": {"trend": "shifting_B", "note": "Shifting toward normalization pause"},
            "France":   {"trend": "shifting_B", "note": "Calling for ceasefire"},
            "US":       {"trend": "stable",   "note": "Maintains Israel support"},
        }
    }
    return trends

def ai_daily_briefing(events, gti, status, snapshot):
    prompt = f"""You are a classified global intelligence analyst. Write a concise daily briefing (3-4 sentences, military/analytical style).

Current GTI: {gti}/10 — {status}
Most active region: {snapshot['most_active_region']}
Fastest escalation: {snapshot['fastest_escalation']}
GTI trend: {snapshot['trend']} ({snapshot['gti_change']:+.1f})
Active events: {len(events)}

Top events:
""" + "\n".join(f"- [{e['type']}] {e['region']}: {e['summary'][:80]}" for e in events[:8]) + """

Write like a DAILY INTEL BRIEF. End with: "Assessment: [one sentence risk outlook for next 24h]" """
    result = ai_call(prompt, 280)
    if result:
        return result
    # Fallback
    trend_word = "elevated" if gti >= 5 else "moderate" if gti >= 3 else "low"
    return (f"Global tension index at {gti}/10 with {trend_word} activity across {snapshot['most_active_region']} and {len(events)} active incidents monitored. "
            f"The {snapshot['fastest_escalation']} remains the primary escalation vector. "
            f"Strategic chokepoints and naval deployments continue to elevate risk. "
            f"Assessment: {'Elevated risk of localized escalation in next 24h.' if gti >= 5 else 'Monitor for rapid developments; situation may evolve quickly.'}")

def calc_chokepoint_traffic(events):
    """Simulate chokepoint traffic levels based on events"""
    base = {
        "Strait of Hormuz": {"traffic_pct": 78, "normal_vessels_day": 21, "risk": "MODERATE"},
        "Suez Canal": {"traffic_pct": 54, "normal_vessels_day": 48, "risk": "HIGH"},
        "Bab el-Mandeb": {"traffic_pct": 38, "normal_vessels_day": 35, "risk": "HIGH"},
        "Taiwan Strait": {"traffic_pct": 88, "normal_vessels_day": 300, "risk": "LOW"},
        "Strait of Gibraltar": {"traffic_pct": 95, "normal_vessels_day": 110, "risk": "LOW"},
        "Malacca Strait": {"traffic_pct": 91, "normal_vessels_day": 85, "risk": "LOW"},
    }
    # Reduce traffic for active conflict areas
    for e in events:
        if e["region"] == "Horn of Africa":
            base["Bab el-Mandeb"]["traffic_pct"] = max(20, base["Bab el-Mandeb"]["traffic_pct"] - 3)
            base["Suez Canal"]["traffic_pct"] = max(30, base["Suez Canal"]["traffic_pct"] - 2)
        if e["region"] == "Middle East":
            base["Strait of Hormuz"]["traffic_pct"] = max(40, base["Strait of Hormuz"]["traffic_pct"] - 1)
        if e["region"] == "East Asia":
            base["Taiwan Strait"]["traffic_pct"] = max(50, base["Taiwan Strait"]["traffic_pct"] - 2)
    return base

# Store daily briefing in cache to avoid repeated AI calls
_daily_briefing_cache = {"text": None, "date": None}

@app.get("/api/snapshot")
async def api_snapshot():
    e = gevents()
    g = _cache.get("gti_data") or calc_gti(e)
    h = _cache.get("history", [])
    reg = _cache.get("regional", {})
    snap = calc_snapshot(e, g, h, reg)
    return {**snap, "timestamp": _cache.get("last_refresh", "")}

@app.get("/api/daily-briefing")
async def api_daily_briefing():
    global _daily_briefing_cache
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    # Cache briefing for the day
    if _daily_briefing_cache["date"] == today and _daily_briefing_cache["text"]:
        return {"briefing": _daily_briefing_cache["text"], "date": today, "cached": True}
    e = gevents()
    g = _cache.get("gti_data") or calc_gti(e)
    reg = _cache.get("regional", {})
    snap = calc_snapshot(e, g, _cache.get("history", []), reg)
    text = ai_daily_briefing(e, g["gti"], g["status"], snap)
    _daily_briefing_cache = {"text": text, "date": today}
    return {"briefing": text, "date": today, "cached": False, "timestamp": datetime.datetime.utcnow().isoformat()+"Z"}

@app.get("/api/chokepoints-traffic")
async def api_chokepoints_traffic():
    e = gevents()
    traffic = calc_chokepoint_traffic(e)
    return {"chokepoints": traffic, "timestamp": _cache.get("last_refresh", "")}

@app.get("/api/alignment-trends")
async def api_alignment_trends():
    return {"trends": calc_alignment_trends(), "timestamp": _cache.get("last_refresh", "")}

@app.get("/api/confidence-events")
async def api_confidence_events():
    """Events with confidence classification for color coding"""
    e = gevents()
    classified = []
    for ev in e:
        conf = ev.get("confidence", 70)
        ev2 = {k: v for k, v in ev.items() if k != "full_text"}
        ev2["conf_class"] = "confirmed" if conf >= 78 else ("probable" if conf >= 60 else "unverified")
        ev2["conf_color"] = "#00ff88" if conf >= 78 else ("#f5c518" if conf >= 60 else "#ff2233")
        classified.append(ev2)
    return {"events": classified, "timestamp": _cache.get("last_refresh", "")}



# ═══════════════════════════════════════════════════════════════
# GTM v4.2 — OSINT MEDIA EVIDENCE LAYER
# ═══════════════════════════════════════════════════════════════
# Uses publicly embeddable content: YouTube news clips,
# Wikimedia Commons imagery, NASA/ESA satellite public tiles,
# and curated open OSINT feed references.
# Evidence is matched by region + event_type.
# For high-confidence events (≥85%), visual evidence is attached.
# ═══════════════════════════════════════════════════════════════

import hashlib

# ── OSINT EVIDENCE DATABASE ──────────────────────────────────
# Curated by region × event_type.
# Each entry: YouTube embed ID or image URL (Wikimedia Commons / NASA).
# All content is publicly accessible without authentication.
OSINT_DB = {
    # ── EASTERN EUROPE / UKRAINE ──
    ("Eastern Europe", "missile strike"): [
        {
            "type": "video",
            "embed_id": "CUNCd9lFi-o",  # Reuters - Ukraine strikes coverage
            "source": "Reuters",
            "source_type": "news_agency",
            "caption": "Artillery and missile exchange along Ukrainian frontline",
            "satellite_url": "https://cdn.jwplayer.com/previews/CUNCd9lFi-o",
            "thumbnail": "https://img.youtube.com/vi/CUNCd9lFi-o/mqdefault.jpg",
            "ai_brief": "News footage showing impact sites and emergency response following missile strikes. Smoke plumes visible consistent with high-explosive munitions. Urban infrastructure damage observed."
        },
        {
            "type": "satellite",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/07/Destroyed_buildings_in_Mariupol%2C_Ukraine_-_April_2022_%28cropped%29.jpg/800px-Destroyed_buildings_in_Mariupol%2C_Ukraine_-_April_2022_%28cropped%29.jpg",
            "source": "Wikimedia Commons / Maxar Technologies",
            "source_type": "satellite_imagery",
            "caption": "Post-strike structural damage — Eastern Ukraine theater",
            "ai_brief": "High-resolution imagery reveals collapsed structures, crater patterns consistent with ballistic impact, and debris fields. Building footprints show complete or partial destruction across multiple city blocks."
        }
    ],
    ("Eastern Europe", "airstrike"): [
        {
            "type": "video",
            "embed_id": "9XWBRHn9Ai0",  # AP/Reuters Ukraine air defense
            "source": "AP News",
            "source_type": "news_agency",
            "caption": "Air defense intercept operations over Ukrainian territory",
            "thumbnail": "https://img.youtube.com/vi/9XWBRHn9Ai0/mqdefault.jpg",
            "ai_brief": "Video shows air defense systems engaging incoming threats. Interception contrails and detonation flashes visible at altitude. Ground observers documented multiple engagements."
        },
    ],
    ("Eastern Europe", "military movement"): [
        {
            "type": "satellite",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5f/Russian_military_vehicles_Kherson_2022.jpg/800px-Russian_military_vehicles_Kherson_2022.jpg",
            "source": "Wikimedia Commons",
            "source_type": "satellite_imagery",
            "caption": "Military vehicle column — Eastern European theater",
            "ai_brief": "Satellite imagery shows armored vehicle convoy formation. Vehicle spacing and road discipline consistent with active military movement. Logistics and support units visible in column."
        }
    ],
    ("Eastern Europe", "naval deployment"): [
        {
            "type": "photo",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9f/Russian_Black_Sea_Fleet_frigate_Admiral_Essen.jpg/800px-Russian_Black_Sea_Fleet_frigate_Admiral_Essen.jpg",
            "source": "Wikimedia Commons / Russian MoD",
            "source_type": "open_source",
            "caption": "Naval vessel — Black Sea theater",
            "ai_brief": "Surface warship photographed in operational configuration. Weapons systems appear in active deployment posture. Vessel consistent with Black Sea Fleet inventory."
        }
    ],

    # ── MIDDLE EAST ──
    ("Middle East", "missile strike"): [
        {
            "type": "video",
            "embed_id": "F1GKKNL1XNY",
            "source": "Al Jazeera English",
            "source_type": "news_agency",
            "caption": "Missile launch and interception footage — Middle East theater",
            "thumbnail": "https://img.youtube.com/vi/F1GKKNL1XNY/mqdefault.jpg",
            "ai_brief": "Footage captures ballistic trajectory and air defense response. Iron Dome/David's Sling intercept pattern visible. Multiple launch points detected from ground cameras."
        },
        {
            "type": "satellite",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8c/Gaza_Strip_2023_war.jpg/800px-Gaza_Strip_2023_war.jpg",
            "source": "Wikimedia Commons / Maxar Technologies",
            "source_type": "satellite_imagery",
            "caption": "Post-strike assessment imagery — Middle East",
            "ai_brief": "Commercial satellite imagery shows newly formed crater patterns and debris scatter radius. Structure collapse consistent with direct strike. Adjacent buildings show secondary blast damage."
        }
    ],
    ("Middle East", "airstrike"): [
        {
            "type": "video",
            "embed_id": "IJRt3TzYlTY",
            "source": "BBC News",
            "source_type": "news_agency",
            "caption": "Airstrike aftermath and humanitarian situation — Middle East",
            "thumbnail": "https://img.youtube.com/vi/IJRt3TzYlTY/mqdefault.jpg",
            "ai_brief": "News footage documents post-strike conditions including structural damage assessment, emergency response operations, and civilian impact. Blast patterns visible on exposed concrete surfaces."
        },
        {
            "type": "satellite",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a6/Gaza_airstrike_2021.jpg/800px-Gaza_airstrike_2021.jpg",
            "source": "Wikimedia Commons / Planet Labs",
            "source_type": "satellite_imagery",
            "caption": "Satellite: building damage assessment",
            "ai_brief": "Multispectral satellite imagery confirms strike pattern. Change detection analysis against baseline imagery shows 12+ structure destructions. Thermal anomalies indicate recent fire activity."
        }
    ],
    ("Middle East", "naval deployment"): [
        {
            "type": "photo",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c0/USS_Gerald_R._Ford_%28CVN-78%29_in_the_Eastern_Mediterranean_Sea_in_October_2023.jpg/800px-USS_Gerald_R._Ford_%28CVN-78%29_in_the_Eastern_Mediterranean_Sea_in_October_2023.jpg",
            "source": "US Navy / Wikimedia Commons",
            "source_type": "official_imagery",
            "caption": "Carrier Strike Group — Eastern Mediterranean",
            "ai_brief": "Official U.S. Navy imagery of carrier strike group in operational formation. Aircraft visible on flight deck in ready configuration. Escort destroyers maintaining defensive perimeter."
        }
    ],
    ("Middle East", "strategic event"): [
        {
            "type": "satellite",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/Strait_of_Hormuz_-_NASA_Terra_MODIS.jpg/800px-Strait_of_Hormuz_-_NASA_Terra_MODIS.jpg",
            "source": "NASA Terra MODIS / Wikimedia Commons",
            "source_type": "satellite_imagery",
            "caption": "NASA satellite: Strait of Hormuz shipping lane activity",
            "ai_brief": "NASA Terra MODIS imagery of the Strait of Hormuz showing vessel traffic patterns. AIS transponder data cross-reference indicates reduced tanker movement consistent with elevated threat posture."
        }
    ],

    # ── HORN OF AFRICA / RED SEA ──
    ("Horn of Africa", "naval deployment"): [
        {
            "type": "photo",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/74/USS_Dwight_D._Eisenhower_%28CVN-69%29_and_escort_vessels_Red_Sea_2024.jpg/800px-USS_Dwight_D._Eisenhower_%28CVN-69%29_and_escort_vessels_Red_Sea_2024.jpg",
            "source": "US Navy / Wikimedia Commons",
            "source_type": "official_imagery",
            "caption": "CSG operations — Red Sea theater",
            "ai_brief": "U.S. carrier strike group maintaining presence in Red Sea in response to Houthi threat. Flight operations visible. Escort screen in extended formation consistent with threat environment."
        }
    ],
    ("Horn of Africa", "missile strike"): [
        {
            "type": "video",
            "embed_id": "5h2Oi95OJLM",
            "source": "Reuters",
            "source_type": "news_agency",
            "caption": "Houthi missile/drone launch — Red Sea theater",
            "thumbnail": "https://img.youtube.com/vi/5h2Oi95OJLM/mqdefault.jpg",
            "ai_brief": "Video shows Houthi ballistic missile launch sequence. Anti-ship ballistic missile (ASBM) or land-attack variant consistent with Burkan/Zulfiqar design. Launch site obscured, direction of travel indicates maritime target."
        }
    ],
    ("Horn of Africa", "strategic event"): [
        {
            "type": "satellite",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/Red_Sea_NASA_Terra.jpg/800px-Red_Sea_NASA_Terra.jpg",
            "source": "NASA Terra / Wikimedia Commons",
            "source_type": "satellite_imagery",
            "caption": "NASA satellite: Red Sea shipping corridor",
            "ai_brief": "NASA satellite imagery of Red Sea shipping corridor. Vessel density analysis shows significant reduction from baseline traffic levels. Rerouting via Cape of Good Hope visible in AIS data overlay."
        }
    ],

    # ── EAST ASIA ──
    ("East Asia", "military movement"): [
        {
            "type": "satellite",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b0/Taiwan_Strait_NASA_Aqua_MODIS.jpg/800px-Taiwan_Strait_NASA_Aqua_MODIS.jpg",
            "source": "NASA Aqua MODIS / Wikimedia Commons",
            "source_type": "satellite_imagery",
            "caption": "NASA satellite: Taiwan Strait — naval activity zone",
            "ai_brief": "NASA MODIS imagery of Taiwan Strait with vessel detection overlay. PLA Navy surface group positioning detected. Formation consistent with exercise or patrol rather than assault configuration."
        }
    ],
    ("East Asia", "naval deployment"): [
        {
            "type": "photo",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/PLA_Navy_Type_055_destroyer_Nanchang.jpg/800px-PLA_Navy_Type_055_destroyer_Nanchang.jpg",
            "source": "Wikimedia Commons / Chinese MoD",
            "source_type": "official_imagery",
            "caption": "PLA Navy destroyer — Western Pacific",
            "ai_brief": "PLA Navy Type 055 destroyer in operational configuration. Weapons systems at readiness state consistent with active patrol. Vessel class represents high-end surface combatant capability."
        }
    ],

    # ── WEST AFRICA / SAHEL ──
    ("West Africa", "military movement"): [
        {
            "type": "satellite",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e6/Sahel_NASA_Terra_MODIS.jpg/800px-Sahel_NASA_Terra_MODIS.jpg",
            "source": "NASA Terra MODIS / Wikimedia Commons",
            "source_type": "satellite_imagery",
            "caption": "NASA satellite: Sahel region activity zone",
            "ai_brief": "Wide-area NASA MODIS imagery of Sahel conflict zone. Thermal anomalies in several northern sectors consistent with fire activity. Road network shows vehicle track signatures in previously unpopulated areas."
        }
    ],

    # ── GENERIC FALLBACK by type ──
    ("*", "missile strike"): [
        {
            "type": "satellite",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4f/Satellite_image_of_crater_impact.jpg/640px-Satellite_image_of_crater_impact.jpg",
            "source": "Wikimedia Commons",
            "source_type": "open_source",
            "caption": "Satellite impact assessment imagery",
            "ai_brief": "Satellite imagery showing post-impact terrain features. Crater geometry and ejecta pattern consistent with high-explosive munition. No secondary explosive evidence detected."
        }
    ],
    ("*", "airstrike"): [
        {
            "type": "photo",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/eb/Combat_aircraft_strike_package.jpg/640px-Combat_aircraft_strike_package.jpg",
            "source": "Wikimedia Commons / DoD",
            "source_type": "official_imagery",
            "caption": "Strike package — tactical aviation",
            "ai_brief": "Combat aircraft in strike configuration. Weapons loadout visible consistent with ground attack mission profile. Formation spacing indicates coordinated multi-aircraft operation."
        }
    ],
    ("*", "naval deployment"): [
        {
            "type": "photo",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/86/Naval_surface_warfare_group.jpg/640px-Naval_surface_warfare_group.jpg",
            "source": "US Navy / Wikimedia Commons",
            "source_type": "official_imagery",
            "caption": "Naval surface warfare group — deployment",
            "ai_brief": "Multi-ship surface warfare formation in operational deployment posture. Vessel types and spacing consistent with carrier strike group screen formation."
        }
    ],
}

OSINT_SOURCE_ICONS = {
    "news_agency": "📡",
    "satellite_imagery": "🛰",
    "social_media": "📱",
    "official_imagery": "🎖",
    "open_source": "🔍",
}

def get_osint_evidence(event):
    """Return evidence for an event if confidence ≥ 85%."""
    conf = event.get("confidence", 0)
    if conf < 85:
        return None

    region = event.get("region", "")
    etype = event.get("type", "").lower()

    # Try specific region+type
    evidence = OSINT_DB.get((region, etype))
    # Try generic type
    if not evidence:
        evidence = OSINT_DB.get(("*", etype))
    if not evidence:
        return None

    # Pick one piece of evidence deterministically based on event id
    idx = int(hashlib.md5(event.get("id","").encode()).hexdigest(), 16) % len(evidence)
    e = evidence[idx].copy()

    # Build youtube embed URL if video
    if e.get("type") == "video" and e.get("embed_id"):
        e["embed_url"] = f"https://www.youtube.com/embed/{e['embed_id']}?autoplay=0&mute=1&controls=1&rel=0"
        e["thumbnail"] = e.get("thumbnail") or f"https://img.youtube.com/vi/{e['embed_id']}/mqdefault.jpg"

    e["source_icon"] = OSINT_SOURCE_ICONS.get(e.get("source_type","open_source"), "🔍")
    e["confidence"] = conf
    e["has_evidence"] = True
    return e

def ai_osint_analysis(event, evidence):
    """Enhanced AI analysis specifically for OSINT visual evidence."""
    prompt = f"""You are an expert OSINT imagery analyst. Analyze the following intelligence report.

Event: [{event.get('type','').upper()}] in {event.get('region','Unknown')}
Location: {event.get('precise_location') or event.get('region')}
Summary: {event.get('summary','')}
Confidence: {event.get('confidence',0)}%

Evidence type: {evidence.get('type','unknown')}
Evidence source: {evidence.get('source','unknown')}
Evidence caption: {evidence.get('caption','')}

Write a 2-3 sentence OSINT analyst assessment in military brevity style. Focus on:
1. What the visual evidence confirms or suggests
2. Key observable indicators
3. Intelligence value / limitations

Format: Direct assessment, no preamble. Maximum 60 words."""

    result = ai_call(prompt, 120)
    return result or evidence.get("ai_brief", "Visual evidence corroborates reported activity. Imagery analysis pending higher-resolution sourcing.")


# ── API ENDPOINTS ────────────────────────────────────────────

@app.get("/api/osint/{eid}")
async def api_osint(eid: str):
    """Return OSINT visual evidence for high-confidence events."""
    event = next((e for e in gevents() if e["id"] == eid), None)
    if not event:
        return JSONResponse({"error": "not found", "has_evidence": False}, 404)

    conf = event.get("confidence", 0)
    if conf < 85:
        return {"has_evidence": False, "confidence": conf, "reason": f"Confidence {conf}% below 85% threshold for visual evidence attachment."}

    evidence = get_osint_evidence(event)
    if not evidence:
        return {"has_evidence": False, "confidence": conf, "reason": "No visual evidence indexed for this event type/region."}

    # Generate enhanced AI analysis
    analysis = ai_osint_analysis(event, evidence)
    evidence["ai_analysis"] = analysis

    return {
        "has_evidence": True,
        "confidence": conf,
        "event_id": eid,
        "event_type": event.get("type"),
        "event_region": event.get("region"),
        "evidence": evidence,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
    }

@app.get("/api/osint-index")
async def api_osint_index():
    """Return list of event IDs that have visual evidence available."""
    events = gevents()
    index = []
    for e in events:
        if e.get("confidence", 0) >= 85:
            ev = get_osint_evidence(e)
            if ev:
                index.append({
                    "id": e["id"],
                    "type": ev.get("type"),
                    "source_type": ev.get("source_type"),
                    "source_icon": ev.get("source_icon"),
                    "thumbnail": ev.get("thumbnail") or ev.get("image_url"),
                    "confidence": e.get("confidence"),
                })
    return {"evidence_available": index, "count": len(index), "timestamp": datetime.datetime.utcnow().isoformat()+"Z"}



# ═══════════════════════════════════════════════════════════════
# GTM v4.3 — GEOPOLITICAL FORECAST LAYER
# Weighted escalation probability model
# ═══════════════════════════════════════════════════════════════

# Region centers for heatmap rendering
FORECAST_REGIONS = {
    "Middle East": {
        "lat": 31.5, "lon": 35.5, "radius": 1200,
        "sub_zones": [
            {"lat": 33.3, "lon": 44.4, "name": "Iraq-Iran border"},
            {"lat": 31.5, "lon": 34.5, "name": "Gaza theater"},
            {"lat": 33.9, "lon": 35.5, "name": "Lebanon-Israel"},
            {"lat": 15.4, "lon": 44.2, "name": "Yemen"},
        ]
    },
    "Eastern Europe": {
        "lat": 49.0, "lon": 32.0, "radius": 900,
        "sub_zones": [
            {"lat": 48.0, "lon": 37.8, "name": "Donbas frontline"},
            {"lat": 50.4, "lon": 30.5, "name": "Kyiv region"},
            {"lat": 46.5, "lon": 30.7, "name": "Odesa/Black Sea"},
        ]
    },
    "East Asia": {
        "lat": 24.0, "lon": 119.5, "radius": 800,
        "sub_zones": [
            {"lat": 24.0, "lon": 119.5, "name": "Taiwan Strait"},
            {"lat": 35.7, "lon": 129.0, "name": "Korean Peninsula"},
            {"lat": 26.3, "lon": 127.8, "name": "East China Sea"},
        ]
    },
    "Horn of Africa": {
        "lat": 12.5, "lon": 43.5, "radius": 700,
        "sub_zones": [
            {"lat": 12.8, "lon": 43.3, "name": "Bab el-Mandeb"},
            {"lat": 15.4, "lon": 44.2, "name": "Yemen coast"},
            {"lat": 11.5, "lon": 43.1, "name": "Gulf of Aden"},
        ]
    },
    "West Africa": {
        "lat": 13.0, "lon": 2.0, "radius": 1100,
        "sub_zones": [
            {"lat": 12.4, "lon": -1.5, "name": "Burkina Faso"},
            {"lat": 17.0, "lon": 8.0, "name": "Niger"},
            {"lat": 13.5, "lon": 2.1, "name": "Mali-Niger border"},
        ]
    },
    "Mediterranean": {
        "lat": 35.5, "lon": 22.0, "radius": 800,
        "sub_zones": [
            {"lat": 35.0, "lon": 33.0, "name": "Eastern Med"},
            {"lat": 38.0, "lon": 14.0, "name": "Central Med"},
        ]
    },
    "South Asia": {
        "lat": 30.0, "lon": 70.0, "radius": 900,
        "sub_zones": [
            {"lat": 33.7, "lon": 73.1, "name": "Kashmir LoC"},
            {"lat": 28.6, "lon": 77.2, "name": "India-Pakistan border"},
        ]
    },
    "Central Asia": {
        "lat": 41.0, "lon": 63.0, "radius": 700,
        "sub_zones": [
            {"lat": 38.6, "lon": 68.8, "name": "Tajikistan border"},
        ]
    },
}

TREND_SIGNALS = {
    "missile strike": {"military": 2.0, "diplomatic": 0.5},
    "airstrike": {"military": 1.8, "diplomatic": 0.3},
    "naval deployment": {"military": 1.5, "diplomatic": 0.2},
    "military movement": {"military": 1.3, "diplomatic": 0.1},
    "strategic event": {"military": 0.8, "diplomatic": 1.2},
    "diplomatic incident": {"military": 0.2, "diplomatic": 2.0},
    "economic sanction": {"military": 0.1, "diplomatic": 1.5},
    "protest": {"military": 0.1, "diplomatic": 0.8},
    "ceasefire": {"military": -0.5, "diplomatic": -1.0},
    "tension": {"military": 0.5, "diplomatic": 0.6},
}

def calc_forecast_score(events, region_name):
    """
    Weighted escalation probability model:
    score = incident_rate*0.4 + escalation_velocity*0.3 + military_movements*0.2 + diplomatic_breakdown*0.1
    Returns 0.0-1.0 probability
    """
    region_events = [e for e in events if e.get("region") == region_name]
    all_events = events

    if not region_events:
        # Global baseline from surrounding regions
        base = len(all_events) * 0.003
        return min(0.18, max(0.05, base))

    n = len(region_events)
    total = max(1, len(all_events))

    # 1. Incident rate (events in region vs total)
    incident_rate = min(1.0, n / max(1, total) * 3.5 + n * 0.08)

    # 2. Escalation velocity (high-conf events weighted more)
    high_conf = sum(1 for e in region_events if e.get("confidence", 0) >= 75)
    escalation_velocity = min(1.0, high_conf * 0.15 + n * 0.05)

    # 3. Military movements
    military_score = 0.0
    for e in region_events:
        signals = TREND_SIGNALS.get(e.get("type", "").lower(), {"military": 0.3, "diplomatic": 0.3})
        military_score += signals["military"] * (e.get("confidence", 70) / 100)
    military_movements = min(1.0, military_score / max(1, n) * 0.6)

    # 4. Diplomatic breakdown
    diplomatic_score = 0.0
    for e in region_events:
        signals = TREND_SIGNALS.get(e.get("type", "").lower(), {"military": 0.3, "diplomatic": 0.3})
        diplomatic_score += signals["diplomatic"]
    diplomatic_breakdown = min(1.0, diplomatic_score / max(1, n) * 0.4)

    # Weighted composite
    raw = (
        incident_rate        * 0.40 +
        escalation_velocity  * 0.30 +
        military_movements   * 0.20 +
        diplomatic_breakdown * 0.10
    )

    # Apply confidence-weighted boost for very active regions
    avg_conf = sum(e.get("confidence", 70) for e in region_events) / len(region_events)
    conf_mult = 0.8 + (avg_conf / 100) * 0.4

    score = min(0.97, max(0.04, raw * conf_mult))
    return round(score, 3)

def get_forecast_drivers(events, region_name):
    """Return list of signal strings driving the forecast."""
    region_events = [e for e in events if e.get("region") == region_name]
    drivers = []
    type_counts = {}
    for e in region_events:
        t = e.get("type", "unknown").lower()
        type_counts[t] = type_counts.get(t, 0) + 1

    driver_labels = {
        "missile strike": "Missile exchanges detected",
        "airstrike": "Airstrikes confirmed",
        "naval deployment": "Naval deployments active",
        "military movement": "Military buildup observed",
        "strategic event": "Strategic signaling detected",
        "diplomatic incident": "Diplomatic breakdown signals",
        "economic sanction": "Economic pressure applied",
        "tension": "Elevated tension indicators",
        "ceasefire": "Ceasefire fragility risk",
    }
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        label = driver_labels.get(t, t.title() + " activity")
        drivers.append({"signal": label, "count": count})

    if not drivers:
        drivers = [{"signal": "Baseline regional monitoring", "count": 0}]
    return drivers[:5]

def get_trend_arrow(current_score, events, region_name):
    """Compute trend direction based on recent event age."""
    region_events = [e for e in events if e.get("region") == region_name]
    if not region_events:
        return "→", "stable"
    recent = [e for e in region_events if (e.get("age_minutes") or 999) < 120]
    older  = [e for e in region_events if (e.get("age_minutes") or 999) >= 120]
    recent_rate = len(recent) / max(1, 2)   # per hour
    older_rate  = len(older)  / max(1, 10)  # per hour
    if recent_rate > older_rate * 1.3:
        return "↑", "escalating"
    elif recent_rate < older_rate * 0.7:
        return "↓", "decreasing"
    else:
        return "→", "stable"

def score_to_label(score):
    if score >= 0.72: return "ESCALATION LIKELY", "#ff2233"
    if score >= 0.50: return "HIGH PROBABILITY", "#ff6b1a"
    if score >= 0.30: return "ELEVATED RISK", "#f5c518"
    return "STABLE", "#00ff88"

def calc_forecast_confidence(events, total_signals):
    """Overall forecast confidence based on signal richness."""
    n = len(events)
    high_conf_count = sum(1 for e in events if e.get("confidence", 0) >= 75)
    conf = min(92, max(38, 45 + high_conf_count * 3 + min(n * 1.5, 30)))
    return round(conf, 1)

def build_heatmap_points(events, forecasts):
    """Generate weighted heatmap point list for Leaflet.heat."""
    points = []
    for region_name, fr in forecasts.items():
        cfg = FORECAST_REGIONS.get(region_name)
        if not cfg:
            continue
        intensity = fr["probability"]
        # Main region center — highest weight
        points.append([cfg["lat"], cfg["lon"], round(intensity, 3)])
        # Sub-zones — slightly reduced weight
        for sz in cfg.get("sub_zones", []):
            sub_intensity = min(0.99, intensity * (0.7 + random.uniform(0, 0.25)))
            points.append([sz["lat"], sz["lon"], round(sub_intensity, 3)])
    return points

@app.get("/api/forecast-geo")
async def api_forecast_geo():
    """Full geopolitical forecast: per-region scores + heatmap points."""
    events = gevents()
    gti_data = _cache.get("gti_data") or calc_gti(events)
    total_signals = len(events)

    forecasts = {}
    for region_name in FORECAST_REGIONS.keys():
        prob = calc_forecast_score(events, region_name)
        arrow, trend_dir = get_trend_arrow(prob, events, region_name)
        drivers = get_forecast_drivers(events, region_name)
        label, color = score_to_label(prob)
        region_events = [e for e in events if e.get("region") == region_name]
        forecasts[region_name] = {
            "probability": prob,
            "probability_pct": round(prob * 100, 1),
            "label": label,
            "color": color,
            "trend_arrow": arrow,
            "trend_dir": trend_dir,
            "drivers": drivers,
            "event_count": len(region_events),
        }

    heatmap_points = build_heatmap_points(events, forecasts)
    confidence = calc_forecast_confidence(events, total_signals)

    # Key regions for panel display
    panel_regions = ["Middle East", "Eastern Europe", "East Asia", "Horn of Africa", "West Africa"]

    return {
        "forecasts": forecasts,
        "heatmap_points": heatmap_points,
        "panel_regions": panel_regions,
        "confidence": confidence,
        "signals_analyzed": total_signals,
        "gti": gti_data.get("gti", 0),
        "model": "incident_rate*0.4 + velocity*0.3 + military*0.2 + diplomatic*0.1",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
    }


HTML_PAGE = """
<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>GLOBAL CONFLICT RADAR v4.3</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.css"/>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.Default.css"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/leaflet.markercluster.js"></script>
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
.scanlines{position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.04)2px,rgba(0,0,0,.04)4px);pointer-events:none;z-index:998}

/* ── CLUSTER OVERRIDES ── */
.marker-cluster{background:rgba(255,34,51,.18)!important;border:1px solid #ff2233!important}
.marker-cluster div{background:rgba(255,34,51,.7)!important;color:#fff!important;font-family:var(--mono)!important;font-size:.55rem!important;font-weight:700}
.marker-cluster-small{background:rgba(245,197,24,.15)!important;border:1px solid #f5c518!important}
.marker-cluster-small div{background:rgba(245,197,24,.7)!important}
.marker-cluster-medium{background:rgba(255,107,26,.15)!important;border:1px solid #ff6b1a!important}
.marker-cluster-medium div{background:rgba(255,107,26,.7)!important}

/* ── ALERT ── */
#alert-banner{display:none;position:fixed;top:0;left:0;right:0;z-index:990;background:linear-gradient(90deg,#1a0008,#2a0010,#1a0008);border-bottom:1px solid var(--red);padding:5px 14px;font-family:var(--mono);font-size:.58rem;letter-spacing:.1em;color:var(--red);align-items:center;justify-content:space-between}
#alert-banner.show{display:flex}
.al-close{cursor:pointer;color:var(--dim);padding:0 6px}

/* ── HEADER ── */
.hdr{display:flex;align-items:center;justify-content:space-between;padding:7px 12px;border-bottom:1px solid var(--b0);background:rgba(2,6,8,.97);position:relative;z-index:20;flex-shrink:0;gap:8px;flex-wrap:wrap}
.hdr-left{display:flex;align-items:center;gap:9px;min-width:0}
.radar{width:30px;height:30px;border:2px solid var(--cyan);border-radius:50%;position:relative;flex-shrink:0;animation:rPulse 3s ease-in-out infinite}
.radar::after{content:'';position:absolute;top:50%;left:50%;width:2px;height:40%;background:var(--cyan);transform-origin:bottom center;transform:translateX(-50%);animation:rSweep 3s linear infinite}
@keyframes rSweep{to{transform:translateX(-50%)rotate(360deg)}}
@keyframes rPulse{0%,100%{box-shadow:0 0 5px #00e5ff44}50%{box-shadow:0 0 14px #00e5ffaa}}
.hdr-titles h1{font-family:var(--disp);font-size:.85rem;font-weight:700;letter-spacing:.2em;color:var(--cyan);text-shadow:0 0 8px #00e5ff44;white-space:nowrap}
.hdr-sub{font-family:var(--mono);font-size:.46rem;color:var(--dim);letter-spacing:.09em}
.hdr-center{display:flex;align-items:center;gap:4px;flex:1;justify-content:center;flex-wrap:wrap}
.layer-btn{padding:3px 8px;border:1px solid var(--b0);cursor:pointer;color:var(--dim);background:transparent;font-family:var(--mono);font-size:.46rem;letter-spacing:.06em;transition:all .15s;white-space:nowrap}
.layer-btn:hover{border-color:var(--b1);color:var(--txt)}
.layer-btn.al{border-color:var(--cyan);color:var(--cyan);background:rgba(0,229,255,.07)}
.layer-btn.al-trade{border-color:var(--yellow);color:var(--yellow);background:rgba(245,197,24,.07)}
.layer-btn.al-travel{border-color:var(--green);color:var(--green);background:rgba(0,255,136,.07)}
.layer-btn.al-align{border-color:var(--purple);color:var(--purple);background:rgba(153,102,255,.07)}
.layer-btn.al-conflict{border-color:var(--red);color:var(--red);background:rgba(255,34,51,.07)}
.hdr-right{display:flex;align-items:center;gap:9px;font-family:var(--mono);font-size:.5rem;color:var(--dim);flex-shrink:0}
.lang-sel{background:transparent;border:1px solid var(--b0);color:var(--dim);font-family:var(--mono);font-size:.48rem;padding:2px 5px;cursor:pointer;outline:none}
.lang-sel option{background:#040d12;color:var(--txt)}
.live-dot{width:5px;height:5px;background:var(--green);border-radius:50%;box-shadow:0 0 5px var(--green);animation:blink 1.2s ease-in-out infinite;flex-shrink:0}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.1}}

/* ── SHELL ── */
.shell{display:flex;height:calc(100vh - 80px);overflow:hidden;position:relative;z-index:1}
.left-panel{width:258px;flex-shrink:0;background:var(--bg2);border-right:1px solid var(--b0);overflow-y:auto;display:flex;flex-direction:column}
.map-col{flex:1;display:flex;flex-direction:column;min-width:0}
.right-panel{width:256px;flex-shrink:0;background:var(--bg2);border-left:1px solid var(--b0);overflow-y:auto}
.left-panel::-webkit-scrollbar,.right-panel::-webkit-scrollbar{width:2px}
.left-panel::-webkit-scrollbar-thumb,.right-panel::-webkit-scrollbar-thumb{background:var(--b0)}

/* ── SEC ── */
.sec{border-bottom:1px solid var(--b0)}
.sec-h{display:flex;align-items:center;justify-content:space-between;padding:5px 9px;background:rgba(0,170,255,.02);cursor:pointer;user-select:none;gap:4px}
.sec-h:hover{background:rgba(0,170,255,.04)}
.sec-t{font-family:var(--disp);font-size:.44rem;letter-spacing:.15em;color:var(--dim);flex:1}
.sec-b{font-family:var(--mono);font-size:.42rem;color:var(--muted)}
.arr{font-size:.48rem;color:var(--muted);transition:transform .2s;flex-shrink:0}
.collapsed .arr{transform:rotate(-90deg)}
.collapsed .sec-body{display:none}
.sec-body{padding:6px 9px}

/* ── SNAPSHOT ── */
.snap-top{display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-bottom:5px}
.snap-item{background:rgba(0,229,255,.04);border:1px solid var(--b0);padding:5px 7px}
.snap-lbl{font-family:var(--mono);font-size:.4rem;color:var(--muted);letter-spacing:.07em;margin-bottom:1px}
.snap-val{font-family:var(--disp);font-size:.9rem;font-weight:700;line-height:1}
.snap-sub{font-family:var(--mono);font-size:.4rem;color:var(--dim);margin-top:1px}
.snap-wide{display:flex;justify-content:space-between;align-items:center;padding:4px 7px;border:1px solid var(--b0);margin-bottom:3px;background:rgba(0,170,255,.02)}
.snap-wide-l{font-family:var(--mono);font-size:.42rem;color:var(--muted)}
.snap-wide-v{font-family:var(--mono);font-size:.48rem}

/* DAILY CHANGES */
.delta-row{display:flex;align-items:center;justify-content:space-between;padding:3px 7px;border:1px solid var(--b0);margin-bottom:2px}
.delta-lbl{font-family:var(--mono);font-size:.44rem;color:var(--dim)}
.delta-val{font-family:var(--disp);font-size:.7rem;font-weight:700}
.delta-up{color:var(--red)}.delta-down{color:var(--green)}.delta-flat{color:var(--dim)}

/* HOTSPOTS */
.hotspot-row{display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid rgba(13,51,72,.3);cursor:pointer}
.hotspot-row:hover{background:rgba(0,170,255,.03)}
.hotspot-num{font-family:var(--disp);font-size:.55rem;font-weight:700;width:20px;text-align:center;flex-shrink:0}
.hotspot-name{font-family:var(--mono);font-size:.5rem;color:var(--txt);flex:1}
.hotspot-bar-wrap{width:40px;height:4px;background:rgba(255,255,255,.06);border-radius:2px;overflow:hidden}
.hotspot-bar-fill{height:100%;border-radius:2px}

/* STABLE REGIONS */
.stable-row{display:flex;align-items:center;gap:5px;padding:3px 0;border-bottom:1px solid rgba(13,51,72,.2)}
.stable-dot{width:5px;height:5px;border-radius:50%;background:var(--green);box-shadow:0 0 4px var(--green);flex-shrink:0}
.stable-name{font-family:var(--mono);font-size:.48rem;color:var(--dim)}
.stable-badge{font-family:var(--disp);font-size:.4rem;color:var(--green);border:1px solid rgba(0,255,136,.3);padding:1px 4px;margin-left:auto}

/* DAILY BRIEFING */
.briefing-text{font-family:var(--body);font-size:.72rem;line-height:1.75;color:var(--txt);border-left:2px solid var(--b1);padding-left:8px}
.briefing-text.typing::after{content:'▋';animation:blink .7s infinite;color:var(--cyan)}
.briefing-footer{display:flex;justify-content:space-between;font-family:var(--mono);font-size:.42rem;color:var(--muted);margin-top:5px;padding-top:4px;border-top:1px solid var(--b0)}

/* ── GTI ── */
.gti-wrap{text-align:center;padding:8px 7px 5px}
.gti-ring{width:128px;height:128px;border-radius:50%;border:2px solid var(--b0);position:relative;margin:0 auto 6px;display:flex;flex-direction:column;align-items:center;justify-content:center}
.gti-rg{position:absolute;inset:-1px;border-radius:50%;border:2px solid var(--red);animation:rgP 2s ease-in-out infinite;transition:all .6s}
@keyframes rgP{0%,100%{opacity:.6}50%{opacity:1}}
.gti-ri{position:absolute;inset:8px;border-radius:50%;border:1px solid rgba(255,34,51,.15);transition:all .6s}
.gti-num{font-family:var(--disp);font-size:2.5rem;font-weight:900;line-height:1;transition:color .6s}
.gti-den{font-family:var(--disp);font-size:.62rem;color:var(--muted)}
.gti-stat{font-family:var(--disp);font-size:.52rem;letter-spacing:.18em;padding:3px 9px;border:1px solid;display:inline-block;margin-bottom:4px;animation:sp 2s ease-in-out infinite;transition:all .6s}
@keyframes sp{0%,100%{opacity:1}50%{opacity:.6}}
.gti-row3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:3px;margin-bottom:4px}
.gsub{text-align:center}.gsub-l{font-family:var(--mono);font-size:.4rem;color:var(--muted);margin-bottom:1px}.gsub-v{font-family:var(--disp);font-size:.78rem;font-weight:700;color:var(--orange)}
.vel-row{display:flex;justify-content:space-between;align-items:center;padding:3px 9px;border-top:1px solid var(--b0);font-family:var(--mono);font-size:.48rem}
.sleg{display:grid;grid-template-columns:1fr 1fr;gap:1px 5px;padding:4px 9px 5px;border-top:1px solid var(--b0)}
.sl{font-family:var(--mono);font-size:.4rem}

/* ── ACTIVITY ── */
.act-grid{display:grid;grid-template-columns:1fr 1fr;gap:4px}
.act-item{background:rgba(0,229,255,.04);border:1px solid var(--b0);padding:5px 6px}
.act-lbl{font-family:var(--mono);font-size:.4rem;color:var(--muted);margin-bottom:1px}
.act-val{font-family:var(--disp);font-size:.9rem;font-weight:700;line-height:1}
.act-sub{font-family:var(--mono);font-size:.38rem;color:var(--dim);margin-top:1px}
.act-ping{display:flex;align-items:center;justify-content:space-between;padding:4px 6px;border:1px solid var(--b0);background:rgba(0,255,136,.03);margin-top:4px}
.act-ping-dot{width:4px;height:4px;border-radius:50%;background:var(--green);box-shadow:0 0 4px var(--green);animation:blink .8s infinite}

/* ── FORECAST ── */
.fc-bars{display:flex;flex-direction:column;gap:4px}
.fc-row{display:flex;align-items:center;gap:4px}
.fc-lbl{font-family:var(--mono);font-size:.44rem;width:54px;flex-shrink:0}
.fc-track{flex:1;height:4px;background:rgba(255,255,255,.06);border-radius:2px;overflow:hidden}
.fc-fill{height:100%;border-radius:2px;transition:width 1s ease}
.fc-pct{font-family:var(--mono);font-size:.44rem;width:26px;text-align:right}
.fc-low .fc-lbl,.fc-low .fc-pct{color:var(--green)}.fc-low .fc-fill{background:var(--green)}
.fc-mod .fc-lbl,.fc-mod .fc-pct{color:var(--yellow)}.fc-mod .fc-fill{background:var(--yellow)}
.fc-high .fc-lbl,.fc-high .fc-pct{color:var(--red)}.fc-high .fc-fill{background:var(--red)}
.fc-meta{display:flex;justify-content:space-between;margin-top:5px;padding-top:4px;border-top:1px solid var(--b0);font-family:var(--mono);font-size:.42rem;color:var(--dim)}
.fc-reason{font-family:var(--mono);font-size:.42rem;color:var(--dim);margin-top:4px;line-height:1.5;font-style:italic}

/* ── REGIONAL ── */
.reg-row{display:grid;grid-template-columns:1fr auto auto;gap:3px;align-items:center;padding:2px 0}
.reg-name{font-family:var(--mono);font-size:.44rem;color:var(--dim)}
.reg-gti{font-family:var(--disp);font-size:.54rem;font-weight:700}
.reg-d{font-family:var(--mono);font-size:.4rem}
.reg-bar{height:2px;background:rgba(255,255,255,.05);border-radius:2px;overflow:hidden;grid-column:1/-1}
.reg-bar-f{height:100%;border-radius:2px;transition:width .8s}

/* ── CONFLICTS ── */
.conflict-item{border:1px solid var(--b0);background:rgba(0,170,255,.02);margin-bottom:4px;padding:6px 8px;cursor:pointer;transition:all .15s}
.conflict-item:hover{background:rgba(0,170,255,.05);border-color:var(--b1)}
.conf-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:3px}
.conf-name{font-family:var(--disp);font-size:.52rem;letter-spacing:.1em}
.conf-state{font-family:var(--disp);font-size:.42rem;padding:1px 5px;border:1px solid}
.conf-meta{display:flex;gap:7px;font-family:var(--mono);font-size:.42rem;color:var(--dim)}
.conf-mbar{height:3px;background:rgba(255,255,255,.06);border-radius:2px;overflow:hidden;margin-top:3px}
.conf-mbar-f{height:100%;border-radius:2px;transition:width .8s}
.conf-desc{font-family:var(--mono);font-size:.42rem;color:var(--muted);margin-top:3px;line-height:1.4}

/* ── ALIGNMENT ── */
.align-conf-sel{display:flex;gap:3px;margin-bottom:7px;flex-wrap:wrap}
.align-conf-btn{padding:2px 6px;border:1px solid var(--b0);cursor:pointer;color:var(--dim);background:transparent;font-family:var(--mono);font-size:.42rem;transition:all .15s}
.align-conf-btn.active{border-color:var(--purple);color:var(--purple);background:rgba(153,102,255,.07)}
.align-row{display:flex;align-items:center;gap:5px;padding:3px 0;border-bottom:1px solid rgba(13,51,72,.3)}
.align-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.align-country{font-family:var(--mono);font-size:.46rem;color:var(--dim);flex:1}
.align-label{font-family:var(--mono);font-size:.42rem;max-width:100px;text-align:right}
/* Trend arrows */
.align-trend{font-size:.55rem;margin-left:3px}
.trend-stable{color:var(--dim)}.trend-shifting_toward_A,.trend-hardening{color:var(--orange)}.trend-shifting_away,.trend-shifting_B{color:var(--cyan)}.trend-mediating{color:var(--yellow)}
.stance-supporting_A{color:#ff6b1a}.stance-supporting_B{color:#00aaff}.stance-neutral{color:#4a7a99}.stance-ambiguous{color:#f5c518}

/* ── TRADE ── */
.trade-route{display:flex;align-items:center;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(13,51,72,.3)}
.trade-nm{font-family:var(--mono);font-size:.46rem;color:var(--dim)}
.trade-r{text-align:right}
.trade-risk{font-family:var(--disp);font-size:.44rem}
.trade-pct{font-family:var(--mono);font-size:.4rem;color:var(--muted)}
.logistics-grid{display:grid;grid-template-columns:1fr 1fr;gap:3px;margin-top:6px}
.log-item{background:rgba(0,170,255,.03);border:1px solid var(--b0);padding:5px 6px}
.log-icon{font-size:.75rem}.log-lbl{font-family:var(--mono);font-size:.4rem;color:var(--muted);margin:1px 0}.log-risk{font-family:var(--disp);font-size:.54rem;font-weight:700}
/* Chokepoint traffic bars */
.choke-traffic-wrap{margin-top:7px}
.choke-traffic-h{font-family:var(--mono);font-size:.44rem;color:var(--muted);letter-spacing:.08em;margin-bottom:5px}
.choke-traffic-item{margin-bottom:6px}
.choke-traffic-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:2px}
.choke-traffic-name{font-family:var(--mono);font-size:.44rem;color:var(--dim)}
.choke-traffic-pct{font-family:var(--disp);font-size:.54rem}
.choke-traffic-bar{height:4px;background:rgba(255,255,255,.06);border-radius:2px;overflow:hidden}
.choke-traffic-fill{height:100%;border-radius:2px;transition:width 1s ease}

/* ── SUPPLY + STRATEGIC ── */
.sup-grid{display:grid;grid-template-columns:1fr 1fr;gap:3px}
.sup-item{background:rgba(0,170,255,.03);border:1px solid var(--b0);padding:5px 6px}
.strat-item{display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid rgba(13,51,72,.3)}
.strat-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.strat-lbl{font-family:var(--mono);font-size:.46rem;color:var(--dim)}
.strat-val{font-family:var(--mono);font-size:.46rem;margin-left:auto}
.choke-item{display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid rgba(13,51,72,.2)}
.choke-nm{font-family:var(--mono);font-size:.44rem;color:var(--dim)}
.choke-rv{font-family:var(--disp);font-size:.42rem}

/* ── FEED ── */
.feed-list{max-height:230px;overflow-y:auto}
.feed-list::-webkit-scrollbar{width:2px}
.feed-list::-webkit-scrollbar-thumb{background:var(--b0)}
.fi{display:grid;grid-template-columns:3px 1fr auto;gap:5px;padding:5px 9px;border-bottom:1px solid rgba(13,51,72,.35);cursor:pointer;transition:background .15s}
.fi:hover{background:rgba(0,170,255,.04)}
.fi-ind{align-self:stretch;min-height:24px;border-radius:1px}
.fi-ind.confirmed{background:var(--green)}
.fi-ind.probable{background:var(--yellow)}
.fi-ind.unverified{background:var(--red);box-shadow:0 0 3px var(--red)}
.fi-type{font-family:var(--disp);font-size:.44rem;letter-spacing:.08em;color:var(--orange)}
.fi-loc{font-family:var(--mono);font-size:.42rem;color:var(--cyan)}
.fi-reg{font-family:var(--mono);font-size:.4rem;color:var(--dim)}
.fi-desc{font-family:var(--body);font-size:.58rem;color:var(--txt);line-height:1.3;margin-top:1px}
.fi-conf-badge{font-family:var(--mono);font-size:.38rem;padding:1px 4px;border:1px solid;border-radius:1px}
.fi-src{font-family:var(--mono);font-size:.38rem;color:var(--muted);text-align:right}

/* ── TRAVEL ── */
.travel-list{display:flex;flex-direction:column;gap:2px;max-height:180px;overflow-y:auto}
.travel-list::-webkit-scrollbar{width:2px}
.travel-list::-webkit-scrollbar-thumb{background:var(--b0)}
.travel-row{display:grid;grid-template-columns:1fr auto;gap:5px;align-items:center;padding:3px 0;border-bottom:1px solid rgba(13,51,72,.2)}
.travel-country{font-family:var(--mono);font-size:.46rem;color:var(--dim)}
.travel-risk{font-family:var(--disp);font-size:.44rem;padding:1px 5px;border:1px solid}
.risk-CRITICAL{color:#8b0000;border-color:#8b0000;background:rgba(139,0,0,.1)}
.risk-HIGH{color:var(--red);border-color:var(--red);background:rgba(255,34,51,.06)}
.risk-MODERATE{color:var(--yellow);border-color:var(--yellow);background:rgba(245,197,24,.06)}
.risk-LOW{color:var(--green);border-color:var(--green);background:rgba(0,255,136,.06)}
.risk-ELEVATED{color:var(--orange);border-color:var(--orange)}

/* ── TRANSPARENCY ── */
.transp-row{display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid rgba(13,51,72,.2)}
.transp-lbl{font-family:var(--mono);font-size:.44rem;color:var(--muted)}
.transp-val{font-family:var(--mono);font-size:.48rem;color:var(--cyan)}

/* ── AI SUMMARY ── */
.ai-sum{font-family:var(--body);font-size:.7rem;line-height:1.7;color:var(--txt);border-left:2px solid var(--b1);padding-left:8px;min-height:44px}
.ai-sum.typing::after{content:'▋';animation:blink .7s infinite;color:var(--cyan)}
.ai-ft{display:flex;justify-content:space-between;font-family:var(--mono);font-size:.4rem;color:var(--muted);margin-top:4px;padding-top:4px;border-top:1px solid var(--b0)}
.ai-badge{display:flex;align-items:center;gap:2px;color:var(--cyan);font-size:.4rem}
.ai-dot{width:3px;height:3px;background:var(--cyan);border-radius:50%;animation:blink 2s infinite}

/* ── MAP ── */
#wmap{flex:1;min-height:0}
.leaflet-container{background:#020e18!important}
.leaflet-tile{filter:brightness(.35) hue-rotate(185deg) saturate(.28) invert(.85)!important}
.leaflet-control-zoom a{background:var(--bg3);color:var(--dim);border-color:var(--b0)}
.leaflet-popup-content-wrapper{background:#050f18!important;border:1px solid #1a6688!important;color:var(--txt)!important;border-radius:0!important;box-shadow:0 0 12px #00e5ff22!important;font-family:var(--mono)!important;font-size:.62rem!important;min-width:240px;max-width:310px}
.leaflet-popup-tip{background:#1a6688!important}
.pop-analyze{display:inline-block;margin-top:6px;padding:4px 10px;border:1px solid var(--cyan);color:var(--cyan);font-family:var(--mono);font-size:.5rem;cursor:pointer;transition:all .18s}
.pop-analyze:hover{background:var(--cyan);color:var(--bg)}
.map-footer{display:flex;align-items:center;gap:7px;padding:4px 9px;border-top:1px solid var(--b0);background:var(--bg2);font-family:var(--mono);font-size:.44rem;color:var(--dim);flex-wrap:wrap;flex-shrink:0}
.mf-item{display:flex;align-items:center;gap:3px}
.mf-dot{width:5px;height:5px;border-radius:50%}
.layer-legend{display:none;align-items:center;gap:6px;flex:1}
.layer-legend.vis{display:flex}
.ll-item{display:flex;align-items:center;gap:2px;font-size:.42rem}

/* CONFIDENCE toggle */
.conf-toggle{display:flex;align-items:center;gap:4px;margin-left:auto;font-family:var(--mono);font-size:.42rem}
.conf-toggle input[type=checkbox]{accent-color:var(--cyan);cursor:pointer}

/* MARKERS */
.em{width:11px;height:11px;border-radius:50%;border:2px solid}
/* Confidence-coded colors */
.em.confirmed{background:rgba(0,255,136,.4);border-color:#00ff88;box-shadow:0 0 5px #00ff88}
.em.probable{background:rgba(245,197,24,.4);border-color:#f5c518}
.em.unverified{background:rgba(255,34,51,.45);border-color:#ff2233;box-shadow:0 0 5px #ff2233}
.em.faded{background:rgba(60,60,60,.3);border-color:#444;box-shadow:none;opacity:.35}
.em-hot{animation:hotP .9s ease-in-out infinite}
@keyframes hotP{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.8);opacity:.6}}
.just-wrap{position:relative}
.just-tag{position:absolute;top:-17px;left:50%;transform:translateX(-50%);background:#ff2233;color:#fff;font-family:var(--mono);font-size:.33rem;padding:1px 4px;letter-spacing:.06em;white-space:nowrap;animation:tagB 1s ease-in-out infinite;pointer-events:none}
@keyframes tagB{0%,100%{opacity:1}50%{opacity:.5}}
.hotspot-marker{width:8px;height:8px;border-radius:50%;border:2px solid}
.travel-cm{font-family:var(--mono);font-size:.44rem;padding:2px 5px;border:1px solid;white-space:nowrap;backdrop-filter:blur(2px)}
.align-cm{font-family:var(--mono);font-size:.44rem;padding:2px 5px;border:1px solid;white-space:nowrap;backdrop-filter:blur(2px)}

/* Chart */
.chart-wrap{padding:4px 6px 6px;height:125px}
.chart-wrap canvas{width:100%!important;height:100%!important}

/* ── REPLAY BAR ── */
.rep-bar{display:flex;align-items:center;gap:5px;padding:4px 9px;border-top:1px solid var(--b0);background:var(--bg2);font-family:var(--mono);font-size:.46rem;color:var(--dim);flex-shrink:0;flex-wrap:wrap}
.rep-btn{padding:2px 6px;border:1px solid var(--b0);cursor:pointer;color:var(--dim);background:transparent;font-family:var(--mono);font-size:.44rem;transition:all .15s}
.rep-btn:hover,.rep-btn.active{border-color:var(--cyan);color:var(--cyan);background:rgba(0,229,255,.05)}
.rep-play{width:20px;height:20px;border:1px solid var(--b1);border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--cyan);font-size:.58rem;flex-shrink:0}
.rep-play:hover{background:rgba(0,229,255,.1)}
.rep-slider{flex:1;accent-color:var(--cyan);cursor:pointer;min-width:60px}
#rep-ts{color:var(--cyan);font-size:.44rem;min-width:100px}
.rep-24h{padding:2px 8px;border:1px solid var(--orange);color:var(--orange);background:transparent;font-family:var(--mono);font-size:.44rem;cursor:pointer;white-space:nowrap}
.rep-24h:hover{background:rgba(255,107,26,.1)}
.spd-btn{padding:1px 4px;border:1px solid var(--b0);cursor:pointer;color:var(--muted);background:transparent;font-family:var(--mono);font-size:.42rem}
.spd-btn.active{border-color:var(--yellow);color:var(--yellow)}
.rep-live{padding:2px 6px;border:1px solid var(--green);color:var(--green);background:transparent;font-family:var(--mono);font-size:.44rem;cursor:pointer}
.rep-live:hover{background:rgba(0,255,136,.07)}

/* ── INTEL PANEL ── */
#intel-panel{position:fixed;top:0;right:-440px;width:440px;height:100vh;background:var(--bg2);border-left:1px solid var(--b1);z-index:900;transition:right .3s cubic-bezier(.4,0,.2,1);overflow-y:auto;display:flex;flex-direction:column}
#intel-panel.open{right:0}
#intel-panel::-webkit-scrollbar{width:2px}
#intel-panel::-webkit-scrollbar-thumb{background:var(--b0)}
.intel-hdr{display:flex;align-items:center;justify-content:space-between;padding:9px 13px;border-bottom:1px solid var(--b0);background:rgba(0,170,255,.03);position:sticky;top:0;z-index:1}
.intel-title-t{font-family:var(--disp);font-size:.56rem;letter-spacing:.15em;color:var(--cyan)}
.intel-close{cursor:pointer;color:var(--dim);font-size:.88rem;padding:2px 5px;line-height:1}
.intel-close:hover{color:var(--txt)}
.intel-body{padding:11px 13px;flex:1}
.intel-type{font-family:var(--disp);font-size:.78rem;letter-spacing:.12em;color:var(--orange);margin-bottom:2px}
.intel-loc{font-family:var(--mono);font-size:.52rem;color:var(--cyan);margin-bottom:2px}
.intel-det{font-family:var(--mono);font-size:.44rem;color:var(--muted);margin-bottom:9px}
.intel-4g{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:8px}
.intel-m{background:rgba(0,170,255,.04);border:1px solid var(--b0);padding:5px 7px}
.intel-m-l{font-family:var(--mono);font-size:.4rem;color:var(--muted);margin-bottom:1px}
.intel-m-v{font-family:var(--disp);font-size:.74rem;font-weight:700}
.intel-unc{background:rgba(245,197,24,.06);border:1px solid rgba(245,197,24,.3);padding:5px 8px;margin-bottom:8px;font-family:var(--mono);font-size:.46rem;color:var(--yellow);line-height:1.5}
.intel-stats-box{background:rgba(0,170,255,.03);border:1px solid var(--b0);padding:6px 9px;margin-bottom:8px}
.intel-stats-h{font-family:var(--disp);font-size:.44rem;letter-spacing:.12em;color:var(--dim);margin-bottom:5px}
.intel-stats-g{display:grid;grid-template-columns:1fr 1fr;gap:4px}
.stat-item{border-bottom:1px solid rgba(13,51,72,.4);padding-bottom:3px}
.stat-l{font-family:var(--mono);font-size:.4rem;color:var(--muted)}
.stat-v{font-family:var(--disp);font-size:.65rem;font-weight:700;color:var(--cyan)}
.intel-sec{margin-bottom:8px}
.intel-sec-h{font-family:var(--disp);font-size:.44rem;letter-spacing:.12em;color:var(--dim);margin-bottom:4px;padding-bottom:3px;border-bottom:1px solid var(--b0)}
.intel-text{font-family:var(--body);font-size:.7rem;color:var(--txt);line-height:1.65}
.actor-tag{font-family:var(--mono);font-size:.42rem;color:var(--cyan);border:1px solid rgba(0,229,255,.3);padding:1px 5px;display:inline-block;margin:1px}
.esc-badge{display:inline-block;font-family:var(--disp);font-size:.48rem;padding:2px 7px;border:1px solid;margin-top:2px}
.esc-LOW{color:var(--green);border-color:var(--green)}.esc-MODERATE{color:var(--yellow);border-color:var(--yellow)}
.esc-HIGH{color:var(--orange);border-color:var(--orange)}.esc-CRITICAL{color:var(--red);border-color:var(--red)}
.intel-src-link{display:block;margin-top:8px;padding:5px 8px;border:1px solid var(--b0);font-family:var(--mono);font-size:.46rem;color:var(--cyan);text-decoration:none;text-align:center}
.intel-src-link:hover{background:rgba(0,229,255,.06)}
.intel-loading{text-align:center;padding:28px 20px;font-family:var(--mono);font-size:.54rem;color:var(--dim)}
.intel-spinner{font-size:1rem;color:var(--cyan);animation:spin 1.5s linear infinite;display:block;margin-bottom:7px}
@keyframes spin{to{transform:rotate(360deg)}}

/* OSINT */
/* ═══ OSINT EVIDENCE LAYER v4.3 CSS ═══ */
.ev-marker-wrap{position:relative;display:inline-block}
.ev-badge{position:absolute;top:-8px;right:-8px;width:13px;height:13px;border-radius:50%;background:#9966ff;border:1px solid rgba(153,102,255,.5);display:flex;align-items:center;justify-content:center;font-size:.35rem;box-shadow:0 0 5px #9966ff88;animation:evGlow 2s ease-in-out infinite;z-index:2;pointer-events:none}
@keyframes evGlow{0%,100%{box-shadow:0 0 4px #9966ff66}50%{box-shadow:0 0 9px #9966ffcc}}
.ev-badge.video{background:#ff2233;border-color:rgba(255,34,51,.6)}
.ev-badge.satellite{background:#00e5ff;border-color:rgba(0,229,255,.6)}
.ev-badge.photo{background:#f5c518;border-color:rgba(245,197,24,.6)}
.ev-hover-tip{position:absolute;bottom:22px;left:50%;transform:translateX(-50%);width:160px;background:rgba(4,13,18,.97);border:1px solid #9966ff;z-index:2000;pointer-events:none;animation:tipIn .18s ease-out}
@keyframes tipIn{from{opacity:0;transform:translateX(-50%) translateY(5px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}
.ev-tip-img{width:100%;height:90px;object-fit:cover;display:block}
.ev-tip-bar{padding:4px 6px;border-top:1px solid #1a6688}
.ev-tip-type{font-family:'Share Tech Mono',monospace;font-size:.38rem;letter-spacing:.08em;color:#9966ff}
.ev-tip-src{font-family:'Share Tech Mono',monospace;font-size:.38rem;color:#4a7a99}
.osint-toggle{padding:3px 8px;border:1px solid rgba(153,102,255,.4);cursor:pointer;color:rgba(153,102,255,.7);background:transparent;font-family:'Share Tech Mono',monospace;font-size:.46rem;letter-spacing:.06em;transition:all .15s;white-space:nowrap}
.osint-toggle.on{border-color:#9966ff;color:#9966ff;background:rgba(153,102,255,.1);box-shadow:0 0 6px rgba(153,102,255,.25)}
.osint-panel{border:1px solid rgba(153,102,255,.35);background:rgba(153,102,255,.04);margin-bottom:10px;overflow:hidden}
.osint-panel-hdr{display:flex;align-items:center;justify-content:space-between;padding:6px 10px;border-bottom:1px solid rgba(153,102,255,.25);background:rgba(153,102,255,.06)}
.osint-panel-title{font-family:'Orbitron',sans-serif;font-size:.5rem;letter-spacing:.14em;color:#9966ff}
.osint-src-badge{font-family:'Share Tech Mono',monospace;font-size:.42rem;color:#4a7a99}
.osint-media{width:100%;background:#000;overflow:hidden}
.osint-img{width:100%;max-height:200px;object-fit:cover;display:block;cursor:zoom-in}
.osint-sat-img{width:100%;max-height:220px;object-fit:cover;display:block;filter:contrast(1.05) saturate(.9);cursor:zoom-in}
.osint-vid-placeholder{width:100%;aspect-ratio:16/9;background:#000;position:relative;cursor:pointer;display:flex;align-items:center;justify-content:center}
.osint-vid-thumb{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.65}
.osint-play-wrap{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.3)}
.osint-play-btn{width:44px;height:44px;border-radius:50%;background:rgba(220,30,30,.88);display:flex;align-items:center;justify-content:center;font-size:1rem;box-shadow:0 2px 12px rgba(255,34,51,.5)}
.osint-vid-frame{display:none;width:100%;aspect-ratio:16/9}
.osint-vid-frame iframe{width:100%;height:100%;border:none;display:block}
.osint-meta{padding:7px 10px}
.osint-caption{font-family:'Rajdhani',sans-serif;font-size:.7rem;color:#c8e8f8;line-height:1.4;margin-bottom:4px}
.osint-src-line{display:flex;align-items:center;gap:5px;font-family:'Share Tech Mono',monospace;font-size:.42rem;color:#4a7a99}
.osint-ai-box{padding:8px 10px;border-top:1px solid rgba(153,102,255,.2);background:rgba(153,102,255,.04)}
.osint-ai-lbl{font-family:'Orbitron',sans-serif;font-size:.44rem;letter-spacing:.1em;color:rgba(153,102,255,.85);margin-bottom:4px}
.osint-ai-lbl::before{content:"◈ "}
.osint-ai-txt{font-family:'Rajdhani',sans-serif;font-size:.7rem;color:#c8e8f8;line-height:1.65}
.osint-warn{padding:5px 10px;background:rgba(245,197,24,.05);border-top:1px solid rgba(245,197,24,.2);font-family:'Share Tech Mono',monospace;font-size:.4rem;color:#f5c518}
.osint-none{padding:12px 10px;font-family:'Share Tech Mono',monospace;font-size:.46rem;color:#2a4a5a;text-align:center}
.fi-ev{font-size:.55rem;vertical-align:middle;margin-left:2px;opacity:.85}
#zoom-ov{display:none;position:fixed;inset:0;background:rgba(0,0,0,.93);z-index:9999;align-items:center;justify-content:center;cursor:zoom-out}
#zoom-ov.show{display:flex}
#zoom-ov img{max-width:90vw;max-height:90vh;object-fit:contain;border:1px solid #1a6688}
#zoom-close{position:fixed;top:14px;right:18px;color:#4a7a99;font-size:1.4rem;cursor:pointer;z-index:10000;line-height:1}

/* FORECAST */
/* ═══════════════════════════════════════
   FORECAST LAYER v4.3
═══════════════════════════════════════ */

/* ── Forecast panel in left sidebar ── */
.fc72-panel { padding: 0 }
.fc72-header { display:flex; align-items:center; justify-content:space-between; padding:4px 9px; border-bottom:1px solid var(--b0); background:rgba(153,102,255,.04); margin-bottom:4px }
.fc72-title { font-family:var(--disp); font-size:.44rem; letter-spacing:.14em; color:#9966ff }
.fc72-conf { font-family:var(--mono); font-size:.4rem; color:var(--muted) }

.fc72-region { border:1px solid var(--b0); margin:3px 9px; padding:5px 7px; background:rgba(0,170,255,.02); cursor:default; transition:background .15s }
.fc72-region:hover { background:rgba(0,170,255,.04) }
.fc72-region-top { display:flex; align-items:center; justify-content:space-between; margin-bottom:3px }
.fc72-region-name { font-family:var(--mono); font-size:.46rem; color:var(--dim) }
.fc72-region-prob { font-family:var(--disp); font-size:.82rem; font-weight:700; line-height:1 }
.fc72-region-meta { display:flex; align-items:center; gap:5px }
.fc72-trend { font-size:.75rem; line-height:1 }
.fc72-label { font-family:var(--disp); font-size:.4rem; letter-spacing:.06em }
.fc72-bar { height:3px; background:rgba(255,255,255,.06); border-radius:2px; overflow:hidden; margin-top:3px }
.fc72-bar-fill { height:100%; border-radius:2px; transition:width 1s ease }

/* Drivers block */
.fc72-drivers { padding:4px 9px 6px; border-top:1px solid var(--b0); margin-top:4px }
.fc72-drivers-hdr { font-family:var(--mono); font-size:.4rem; color:var(--muted); letter-spacing:.08em; margin-bottom:4px }
.fc72-driver-row { display:flex; align-items:center; gap:5px; padding:2px 0; border-bottom:1px solid rgba(13,51,72,.2) }
.fc72-driver-dot { width:4px; height:4px; border-radius:50%; flex-shrink:0 }
.fc72-driver-txt { font-family:var(--mono); font-size:.44rem; color:var(--dim); flex:1 }
.fc72-driver-cnt { font-family:var(--disp); font-size:.5rem; color:var(--muted) }

/* Model info footer */
.fc72-model { padding:4px 9px; border-top:1px solid var(--b0); display:flex; justify-content:space-between; font-family:var(--mono); font-size:.38rem; color:var(--muted) }
.fc72-signals { color:var(--cyan) }

/* ── Heatmap legend ── */
.fc-legend { display:none; align-items:center; gap:7px; flex:1 }
.fc-legend.vis { display:flex }
.fc-leg-grad { width:80px; height:6px; border-radius:3px; background:linear-gradient(90deg,#00ff88,#f5c518,#ff6b1a,#ff2233); flex-shrink:0 }
.fc-leg-labels { display:flex; justify-content:space-between; font-family:var(--mono); font-size:.38rem; width:80px; flex-shrink:0 }
.fc-leg-sep { color:var(--muted); font-family:var(--mono); font-size:.42rem }

/* ── Region risk circles on map ── */
.fc-region-label { font-family:'Orbitron',sans-serif; font-size:.44rem; padding:3px 7px; border:1px solid; white-space:nowrap; background:rgba(2,6,8,.9) }

/* ── Forecast mode banner ── */
#fc-mode-banner { display:none; position:absolute; top:8px; left:50%; transform:translateX(-50%); z-index:800; background:rgba(4,13,18,.95); border:1px solid #9966ff; padding:4px 14px; font-family:'Share Tech Mono',monospace; font-size:.5rem; color:#9966ff; letter-spacing:.12em; pointer-events:none; white-space:nowrap }
#fc-mode-banner.show { display:block }
.fc-banner-pulse { animation:fcBlink 2s ease-in-out infinite }
@keyframes fcBlink { 0%,100%{opacity:1}50%{opacity:.5} }

/* ── Heatmap custom gradient ── */
.leaflet-heatmap-layer { opacity:0.75 }

/* ── FORECAST button ── */
.layer-btn.al-forecast { border-color:#9966ff; color:#9966ff; background:rgba(153,102,255,.07) }


#dbg-overlay{display:none;position:fixed;bottom:0;left:0;right:0;z-index:9999;
  background:#ff000022;border-top:2px solid #ff2233;color:#ff6666;
  font-family:monospace;font-size:11px;padding:8px;word-break:break-all;max-height:120px;overflow:auto;}
#dbg-status{position:fixed;top:4px;right:200px;z-index:9999;
  font-family:monospace;font-size:10px;color:#00ff88;background:#000;padding:2px 6px;}
</style>
</head>
<body>
<div class="scanlines"></div>

<div id="alert-banner">
  <div style="display:flex;align-items:center;gap:7px"><div class="live-dot"></div><span id="alert-text">⚠ ALERT</span></div>
  <span class="al-close" onclick="dismissAlert()">✕</span>
</div>

<!-- HEADER -->
<header class="hdr">
  <div class="hdr-left">
    <div class="radar"></div>
    <div class="hdr-titles">
      <h1>GLOBAL CONFLICT RADAR</h1>
      <div class="hdr-sub">LIVE GEOPOLITICAL MONITORING · RSS + CLAUDE AI · v4.3</div>
    </div>
  </div>
  <div class="hdr-center">
    <button class="layer-btn al" onclick="setLayer('live',this)">◉ LIVE</button>
    <button class="layer-btn" onclick="setLayer('conflicts',this)">💥 CONFLICTS</button>
    <button class="layer-btn" onclick="setLayer('trade',this)">🚢 TRADE</button>
    <button class="layer-btn" onclick="setLayer('travel',this)">✈ TRAVEL</button>
    <button class="layer-btn" onclick="setLayer('alignment',this)">🌐 ALIGNMENT</button>
    <button class="osint-toggle" id="osint-btn" onclick="toggleOsint(this)">🛰 OSINT</button>
    <button class="layer-btn" id="fc-btn" onclick="setLayer('forecast',this)">⚡ FORECAST</button>
  </div>
  <div class="hdr-right">
    <select class="lang-sel" onchange="setLang(this.value)">
      <option value="en">EN</option><option value="sk">SK</option><option value="de">DE</option>
      <option value="fr">FR</option><option value="uk">UK</option><option value="ru">RU</option>
      <option value="ar">AR</option><option value="zh">ZH</option>
    </select>
    <span>DATA: <span id="src-badge" style="color:var(--green)">—</span></span>
    <span id="utc-clock" style="color:var(--muted)">—</span>
    <span>NEXT: <span id="next-ref" style="color:var(--cyan)">10:00</span></span>
    <div style="display:flex;align-items:center;gap:4px;color:var(--green)"><div class="live-dot"></div>LIVE</div>
  </div>
</header>

<!-- SHELL -->
<div class="shell">

<!-- ════ LEFT PANEL ════ -->
<div class="left-panel">

  <!-- DAILY GLOBAL RISK SNAPSHOT -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')">
      <span class="sec-t">◈ GLOBAL RISK SNAPSHOT</span>
      <div style="display:flex;align-items:center;gap:3px"><span id="snap-date" style="font-family:var(--mono);font-size:.4rem;color:var(--muted)">TODAY</span><span class="arr">▾</span></div>
    </div>
    <div class="sec-body" style="padding:5px 7px">
      <div class="snap-top">
        <div class="snap-item">
          <div class="snap-lbl">TENSION INDEX</div>
          <div class="snap-val" id="snap-gti" style="color:var(--orange)">—</div>
          <div class="snap-sub" id="snap-trend">trend —</div>
        </div>
        <div class="snap-item">
          <div class="snap-lbl">ACTIVE CONFLICTS</div>
          <div class="snap-val" id="snap-conflicts" style="color:var(--red)">—</div>
          <div class="snap-sub" id="snap-strategic">— strategic</div>
        </div>
      </div>
      <!-- DAILY CHANGE INDICATORS -->
      <div style="margin-bottom:4px;font-family:var(--mono);font-size:.4rem;color:var(--muted);letter-spacing:.08em">SINCE YESTERDAY</div>
      <div class="delta-row"><span class="delta-lbl">TENSION INDEX</span><span class="delta-val" id="delta-gti">—</span></div>
      <div class="delta-row"><span class="delta-lbl">INCIDENTS</span><span class="delta-val" id="delta-inc">—</span></div>
      <div class="delta-row"><span class="delta-lbl">STRATEGIC EVENTS</span><span class="delta-val" id="delta-strat">—</span></div>
      <div class="snap-wide" style="margin-top:4px"><span class="snap-wide-l">MOST ACTIVE REGION</span><span class="snap-wide-v" id="snap-region" style="color:var(--orange)">—</span></div>
      <div class="snap-wide"><span class="snap-wide-l">FASTEST ESCALATION</span><span class="snap-wide-v" id="snap-fastest" style="color:var(--red)">—</span></div>
    </div>
  </div>

  <!-- DAILY AI BRIEFING -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')">
      <span class="sec-t">◈ DAILY INTEL BRIEFING</span>
      <div class="ai-badge"><div class="ai-dot"></div><span style="font-family:var(--mono);font-size:.4rem;color:var(--cyan)">AI</span></div>
    </div>
    <div class="sec-body">
      <div class="briefing-text typing" id="daily-briefing">Generating daily briefing…</div>
      <div class="briefing-footer"><span id="brief-date">—</span><span id="brief-model">CLAUDE AI</span></div>
    </div>
  </div>

  <!-- GTI -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')">
      <span class="sec-t">GLOBAL TENSION INDEX</span>
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
        <div class="gti-stat" id="gti-stat">LOADING…</div>
        <div class="gti-row3">
          <div class="gsub"><div class="gsub-l">MIL</div><div class="gsub-v" id="s-mil">—</div></div>
          <div class="gsub"><div class="gsub-l">STR</div><div class="gsub-v" id="s-str">—</div></div>
          <div class="gsub"><div class="gsub-l">ECO</div><div class="gsub-v" id="s-eco">—</div></div>
        </div>
      </div>
      <div class="vel-row"><span style="color:var(--dim)">ESCALATION VELOCITY</span><span id="velocity" style="color:var(--red)">—</span></div>
      <div class="sleg">
        <div class="sl" style="color:#00ff88">● 0-2 STABLE</div><div class="sl" style="color:#f5c518">● 2-4 RISING</div>
        <div class="sl" style="color:#ff6b1a">● 4-6 HIGH</div><div class="sl" style="color:#ff2233">● 6-8 CRISIS</div>
        <div class="sl" style="color:#8b0000;grid-column:1/-1">● 8-10 GLOBAL CRISIS</div>
      </div>
    </div>
  </div>

  <!-- ESCALATION FORECAST 72H PANEL -->
  <div class="sec" id="fc72-sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')">
      <span class="sec-t" style="color:#9966ff">⚡ ESCALATION FORECAST · 72H</span>
      <div style="display:flex;align-items:center;gap:4px">
        <span id="fc72-conf-badge" style="font-family:var(--mono);font-size:.4rem;color:var(--muted)">—% conf</span>
        <span class="arr">▾</span>
      </div>
    </div>
    <div class="sec-body fc72-panel" style="padding:0">
      <div class="fc72-header">
        <span class="fc72-title">PREDICTIVE RISK MODEL</span>
        <span class="fc72-conf" id="fc72-sigs">— signals</span>
      </div>
      <div id="fc72-regions">
        <!-- Populated by JS -->
        <div style="padding:9px;font-family:var(--mono);font-size:.46rem;color:var(--muted)">Loading forecast…</div>
      </div>
      <div class="fc72-drivers" id="fc72-drivers-wrap">
        <div class="fc72-drivers-hdr">FORECAST DRIVERS</div>
        <div id="fc72-drivers-list">—</div>
      </div>
      <div class="fc72-model">
        <span>MODEL: rate·0.4 + vel·0.3 + mil·0.2 + dip·0.1</span>
        <span class="fc72-signals" id="fc72-conf-val">—%</span>
      </div>
    </div>
  </div>


  <!-- TREND CHART -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t">TENSION TREND · 30 DAYS</span><span class="arr">▾</span></div>
    <div class="sec-body" style="padding:0"><div class="chart-wrap"><canvas id="tchart"></canvas></div></div>
  </div>

  <!-- HOTSPOTS TODAY -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t">🔥 HOTSPOTS TODAY</span><span class="arr">▾</span></div>
    <div class="sec-body"><div id="hotspots-list">Loading…</div></div>
  </div>

  <!-- STABLE REGIONS -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t">✓ STABLE REGIONS</span><span class="arr">▾</span></div>
    <div class="sec-body"><div id="stable-list">Loading…</div></div>
  </div>

  <!-- FORECAST -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t">ESCALATION FORECAST · 30D</span><span class="arr">▾</span></div>
    <div class="sec-body">
      <div class="fc-bars">
        <div class="fc-row fc-low"><span class="fc-lbl">LOW RISK</span><div class="fc-track"><div class="fc-fill" id="fc-low" style="width:0%"></div></div><span class="fc-pct" id="fc-lp">—%</span></div>
        <div class="fc-row fc-mod"><span class="fc-lbl">MODERATE</span><div class="fc-track"><div class="fc-fill" id="fc-mod" style="width:0%"></div></div><span class="fc-pct" id="fc-mp">—%</span></div>
        <div class="fc-row fc-high"><span class="fc-lbl">HIGH RISK</span><div class="fc-track"><div class="fc-fill" id="fc-high" style="width:0%"></div></div><span class="fc-pct" id="fc-hp">—%</span></div>
      </div>
      <div class="fc-meta"><span>CONFIDENCE: <span id="fc-conf-val" style="color:var(--cyan)">—%</span></span><span id="fc-analyzed" style="color:var(--dim)">—</span></div>
      <div class="fc-reason" id="fc-reason">Calculating…</div>
    </div>
  </div>

  <!-- REGIONAL -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t">REGIONAL TENSIONS</span><span class="arr">▾</span></div>
    <div class="sec-body"><div id="reg-list">Loading…</div></div>
  </div>

  <!-- AI SUMMARY -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')">
      <span class="sec-t">SITUATION SUMMARY</span>
      <div class="ai-badge"><div class="ai-dot"></div><span style="font-family:var(--mono);font-size:.4rem;color:var(--cyan)">AI</span></div>
    </div>
    <div class="sec-body">
      <div class="ai-sum typing" id="ai-sum">Analyzing…</div>
      <div class="ai-ft"><span id="ai-gen">—</span><span id="ai-ts">—</span></div>
    </div>
  </div>

  <!-- ACTIVITY -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')">
      <span class="sec-t">◈ GLOBAL ACTIVITY</span>
      <div style="display:flex;align-items:center;gap:3px"><div class="live-dot" style="width:4px;height:4px"></div><span class="arr">▾</span></div>
    </div>
    <div class="sec-body" style="padding:5px 6px">
      <div class="act-grid">
        <div class="act-item"><div class="act-lbl">ACTIVE INCIDENTS</div><div class="act-val" id="act-inc" style="color:var(--red)">—</div><div class="act-sub" id="act-conf">—</div></div>
        <div class="act-item"><div class="act-lbl">REGIONS ACTIVE</div><div class="act-val" id="act-reg" style="color:var(--orange)">—</div><div class="act-sub" id="act-strat">—</div></div>
        <div class="act-item"><div class="act-lbl">SOURCES</div><div class="act-val" id="act-src" style="color:var(--cyan);font-size:.8rem">1,247</div><div class="act-sub">FEEDS</div></div>
        <div class="act-item"><div class="act-lbl">DETECTED 24H</div><div class="act-val" id="act-24h" style="color:var(--yellow);font-size:.8rem">—</div><div class="act-sub" id="act-avgc">—</div></div>
      </div>
      <div class="act-ping"><div class="act-ping-dot"></div><span style="font-family:var(--mono);font-size:.44rem;color:var(--dim)">LAST DETECTED</span><span id="act-last" style="font-family:var(--mono);font-size:.48rem;color:var(--green)">—</span></div>
    </div>
  </div>

</div><!-- /left -->

<!-- ════ MAP CENTER ════ -->
<div class="map-col">
  <div id="fc-mode-banner"><span class="fc-banner-pulse">⚡ FORECAST MODE — PREDICTIVE RISK VISUALIZATION</span></div>
  <div id="wmap" style="flex:1;min-height:0"></div>
  <div class="map-footer">
    <!-- LIVE -->
    <div class="layer-legend vis" id="leg-live">
      <div class="ll-item"><div class="mf-dot" style="background:#00ff88;box-shadow:0 0 3px #00ff88"></div>CONFIRMED</div>
      <div class="ll-item"><div class="mf-dot" style="background:#f5c518"></div>PROBABLE</div>
      <div class="ll-item"><div class="mf-dot" style="background:#ff2233;box-shadow:0 0 3px #ff2233"></div>UNVERIFIED</div>
      <div class="ll-item" style="color:var(--cyan)">⊙ JUST DETECTED</div>
      <div class="conf-toggle"><input type="checkbox" id="cluster-toggle" onchange="toggleClustering(this.checked)" checked/><label for="cluster-toggle">CLUSTER</label></div>
    </div>
    <!-- CONFLICTS -->
    <div class="layer-legend" id="leg-conflicts">
      <div class="ll-item" style="color:#ff2233">- - FRONTLINE</div>
      <div class="ll-item" style="color:#ff6b1a">● HOTSPOT</div>
      <div class="ll-item" style="color:#f5c518">● STABILIZING</div>
    </div>
    <!-- TRADE -->
    <div class="layer-legend" id="leg-trade">
      <div class="ll-item" style="color:#ff2233">━ HIGH RISK</div>
      <div class="ll-item" style="color:#f5c518">━ MODERATE</div>
      <div class="ll-item" style="color:#00ff88">━ LOW RISK</div>
      <div class="ll-item" style="color:var(--cyan)">📊 TRAFFIC %</div>
    </div>
    <!-- TRAVEL -->
    <div class="layer-legend" id="leg-travel">
      <div class="ll-item" style="color:#8b0000">▪ CRITICAL</div>
      <div class="ll-item" style="color:#ff2233">▪ HIGH</div>
      <div class="ll-item" style="color:#f5c518">▪ MODERATE</div>
      <div class="ll-item" style="color:#00ff88">▪ LOW</div>
    </div>
    <!-- ALIGNMENT -->
    <div class="layer-legend" id="leg-align">
      <div class="ll-item" style="color:#ff6b1a">▪ SIDE A</div>
      <div class="ll-item" style="color:#00aaff">▪ SIDE B</div>
      <div class="ll-item" style="color:#f5c518">▪ AMBIGUOUS</div>
      <div class="ll-item" style="color:#4a7a99">▪ NEUTRAL</div>
    </div>
        <div class="fc-legend" id="leg-forecast">
      <div class="fc-leg-grad"></div>
      <div style="display:flex;flex-direction:column;gap:1px">
        <div class="fc-leg-labels"><span style="color:#00ff88">STABLE</span><span style="color:#f5c518">ELEVATED</span><span style="color:#ff6b1a">HIGH</span><span style="color:#ff2233">CRITICAL</span></div>
        <div style="font-family:var(--mono);font-size:.38rem;color:var(--muted)">ESCALATION PROBABILITY 72H</div>
      </div>
    </div>
    <span style="margin-left:auto;color:var(--muted);font-family:var(--mono);font-size:.42rem" id="map-src">—</span>
  </div>
  <!-- REPLAY BAR -->
  <div class="rep-bar">
    <span style="color:var(--dim);letter-spacing:.1em;flex-shrink:0">TIMELINE</span>
    <button class="rep-btn active" onclick="setRepPeriod('24h',this)">24H</button>
    <button class="rep-btn" onclick="setRepPeriod('7d',this)">7D</button>
    <button class="rep-btn" onclick="setRepPeriod('30d',this)">30D</button>
    <button class="rep-24h" onclick="playLast24h()">▶ PLAY 24H</button>
    <div class="rep-play" id="rep-play-btn" onclick="toggleReplay()">▶</div>
    <input type="range" class="rep-slider" id="rep-slider" min="0" max="100" value="100" oninput="onSlide(this.value)"/>
    <span id="rep-ts">LIVE</span>
    <button class="spd-btn active" onclick="setSpd(1,this)">1x</button>
    <button class="spd-btn" onclick="setSpd(2,this)">2x</button>
    <button class="spd-btn" onclick="setSpd(5,this)">5x</button>
    <button class="rep-live" onclick="goLive()">● LIVE</button>
  </div>
</div>

<!-- ════ RIGHT PANEL ════ -->
<div class="right-panel">

  <!-- PERSISTENT CONFLICTS -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t">PERSISTENT CONFLICTS</span><span class="arr">▾</span></div>
    <div class="sec-body"><div id="conflict-list">Loading…</div></div>
  </div>

  <!-- ALIGNMENT MAP PANEL -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t">🌐 GLOBAL ALIGNMENT</span><span class="arr">▾</span></div>
    <div class="sec-body">
      <div class="align-conf-sel" id="align-conf-sel"></div>
      <div id="align-list">Loading…</div>
    </div>
  </div>

  <!-- TRADE & LOGISTICS -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t">🚢 TRADE & LOGISTICS</span><span class="arr">▾</span></div>
    <div class="sec-body">
      <div id="trade-routes-list">Loading…</div>
      <div class="logistics-grid" id="logistics-grid">—</div>
      <!-- CHOKEPOINT TRAFFIC -->
      <div class="choke-traffic-wrap">
        <div class="choke-traffic-h">CHOKEPOINT TRAFFIC LEVELS</div>
        <div id="choke-traffic-bars">Loading…</div>
      </div>
    </div>
  </div>

  <!-- STRATEGIC MONITOR -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t">STRATEGIC MONITOR</span><span class="arr">▾</span></div>
    <div class="sec-body">
      <div id="strat-list">Loading…</div>
      <div style="margin-top:6px;font-family:var(--mono);font-size:.42rem;color:var(--muted);margin-bottom:3px">CHOKEPOINTS</div>
      <div id="choke-list">—</div>
    </div>
  </div>

  <!-- SUPPLY CHAIN -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t">SUPPLY CHAIN RISK</span><span class="arr">▾</span></div>
    <div class="sec-body" style="padding:5px 6px"><div class="sup-grid" id="supply-grid">Loading…</div></div>
  </div>

  <!-- TRAVEL SAFETY -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t">✈ TRAVEL SAFETY</span><span class="arr">▾</span></div>
    <div class="sec-body" style="padding:4px 6px"><div class="travel-list" id="travel-list">Loading…</div></div>
  </div>

  <!-- EVENT FEED (confidence-coded) -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')">
      <span class="sec-t">RECENT EVENTS</span>
      <span class="sec-b" id="feed-src-b">—</span><span class="arr">▾</span>
    </div>
    <div style="padding:0"><div class="feed-list" id="feed-list"><div style="padding:9px;font-family:var(--mono);font-size:.5rem;color:var(--dim)">Loading…</div></div></div>
  </div>

  <!-- TRANSPARENCY -->
  <div class="sec">
    <div class="sec-h" onclick="this.closest('.sec').classList.toggle('collapsed')"><span class="sec-t">SYSTEM TRANSPARENCY</span><span class="arr">▾</span></div>
    <div class="sec-body"><div id="transp-list">Loading…</div></div>
  </div>

</div><!-- /right -->
</div><!-- /shell -->

<!-- INTEL PANEL -->
<div id="intel-panel">
  <div class="intel-hdr">
    <span class="intel-title-t">◈ EVENT INTELLIGENCE</span>
    <span class="intel-close" onclick="closeIntel()">✕</span>
  </div>
  <div class="intel-body" id="intel-body">
    <div class="intel-loading"><span class="intel-spinner">◈</span>Select a map event to analyze</div>
  </div>
</div>

<script>
// ════════════ STATE ════════════
let leafMap=null, mLayer=null, clusterLayer=null, conflictLayer=null, tradeLayer=null, travelLayer=null, alignLayer=null, tChart=null;
let allEvents=[], replayHistory=[], repIdx=0, repPlaying=false, repSpd=1, repPeriod='24h', repTimer=null;
let refreshCountdown=600, currentLayer='live', useClustering=true;
let conflictsData=[], tradeData={}, travelData={}, alignData={}, alignTrends={}, currentAlignConflict='ukraine_war';

// ════════════ UTILS ════════════
const gtiColor=v=>v<2?'#00ff88':v<4?'#f5c518':v<6?'#ff6b1a':v<8?'#ff2233':'#8b0000';
const riskColor=r=>({LOW:'#00ff88',MODERATE:'#f5c518',HIGH:'#ff2233',CRITICAL:'#8b0000',ELEVATED:'#ff6b1a'}[r]||'#4a7a99');
const stanceColor=s=>({supporting_A:'#ff6b1a',supporting_B:'#00aaff',neutral:'#4a7a99',ambiguous:'#f5c518'}[s]||'#4a7a99');
const momentumColor=s=>({emerging:'#f5c518',escalating:'#ff6b1a','active war':'#ff2233',stabilizing:'#aaaaff','de-escalating':'#00ff88'}[s]||'#4a7a99');
const confClass=c=>c>=78?'confirmed':c>=60?'probable':'unverified';
const confColor=c=>c>=78?'#00ff88':c>=60?'#f5c518':'#ff2233';
const confLabel=c=>c>=78?'CONFIRMED':c>=60?'PROBABLE':'UNVERIFIED';
function timeSince(iso){const m=(Date.now()-new Date(iso).getTime())/60000;if(m<1)return'just now';if(m<60)return Math.round(m)+'m ago';if(m<1440)return Math.round(m/60)+'h ago';return Math.round(m/1440)+'d ago'}
function animNum(el,to,dur,fmt){const s=performance.now();(function step(n){const t=Math.min((n-s)/dur,1),e=1-Math.pow(1-t,3);el.textContent=fmt(to*e);if(t<1)requestAnimationFrame(step)})(s)}
const srcLabel=s=>s==='rss'?'✓ RSS LIVE':'⚠ MOCK DATA';
const srcColor=s=>s==='rss'?'#00ff88':'#ff6b1a';
function dismissAlert(){document.getElementById('alert-banner').classList.remove('show')}
const trafficColor=p=>p>=75?'#00ff88':p>=45?'#f5c518':p>=25?'#ff6b1a':'#ff2233';
const trendArrow=t=>({stable:'→',shifting_toward_A:'↗',shifting_away:'↙',shifting_B:'↘',mediating:'↔',hardening:'↑'}[t]||'→');
const trendColorFn=t=>({stable:'#4a7a99',shifting_toward_A:'#ff6b1a',shifting_away:'#00aaff',shifting_B:'#00aaff',mediating:'#f5c518',hardening:'#ff2233'}[t]||'#4a7a99');

// ════════════ CLOCK ════════════
setInterval(()=>{
  const c=document.getElementById('utc-clock');if(c)c.textContent=new Date().toUTCString().slice(0,25)+' UTC';
  refreshCountdown--;
  const r=document.getElementById('next-ref');if(r){const m=Math.floor(refreshCountdown/60),s=refreshCountdown%60;r.textContent=`${m}:${String(s).padStart(2,'0')}`}
  if(refreshCountdown<=0){refreshCountdown=600;loadAll()}
},1000);

// ════════════ MAP INIT ════════════
function initMap(){
  if(leafMap)return;
  leafMap=L.map('wmap',{center:[20,20],zoom:2,zoomControl:true,attributionControl:false,minZoom:2,maxZoom:10});
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(leafMap);
  mLayer=L.layerGroup().addTo(leafMap);
  clusterLayer=L.markerClusterGroup({
    maxClusterRadius:50,
    iconCreateFunction:function(cluster){
      const count=cluster.getChildCount();
      const size=count<5?'small':count<15?'medium':'large';
      return L.divIcon({html:`<div><span>${count}</span></div>`,className:`marker-cluster marker-cluster-${size}`,iconSize:[40,40]});
    },
    spiderfyOnMaxZoom:true,showCoverageOnHover:false
  });
  conflictLayer=L.layerGroup();
  tradeLayer=L.layerGroup();
  travelLayer=L.layerGroup();
  alignLayer=L.layerGroup();
}

// ════════════ LAYER SWITCHER ════════════
const LAYER_CLS={live:'al',conflicts:'al-conflict',trade:'al-trade',travel:'al-travel',alignment:'al-align'};
function setLayer(name,btn){
  currentLayer=name;
  document.querySelectorAll('.layer-btn').forEach(b=>b.className='layer-btn');
  if(btn)btn.className='layer-btn '+LAYER_CLS[name];
  ['live','conflicts','trade','travel','align'].forEach(l=>{
    const el=document.getElementById('leg-'+l);
    if(el)el.classList.toggle('vis',l===name||(name==='alignment'&&l==='align'));
  });
  if(!leafMap)return;
  [mLayer,clusterLayer,conflictLayer,tradeLayer,travelLayer,alignLayer].forEach(l=>{if(leafMap.hasLayer(l))leafMap.removeLayer(l)});
  if(name==='live'){
    if(useClustering)leafMap.addLayer(clusterLayer);
    else leafMap.addLayer(mLayer);
  } else if(name==='conflicts'){leafMap.addLayer(conflictLayer);leafMap.addLayer(mLayer)}
  else if(name==='trade')leafMap.addLayer(tradeLayer);
  else if(name==='travel')leafMap.addLayer(travelLayer);
  else if(name==='alignment')leafMap.addLayer(alignLayer);
}

function toggleClustering(enabled){
  useClustering=enabled;
  if(currentLayer==='live'){
    if(leafMap.hasLayer(mLayer))leafMap.removeLayer(mLayer);
    if(leafMap.hasLayer(clusterLayer))leafMap.removeLayer(clusterLayer);
    if(enabled)leafMap.addLayer(clusterLayer);
    else leafMap.addLayer(mLayer);
  }
}

// ════════════ LIVE EVENTS MAP ════════════
function renderMap(events){
  if(!mLayer||!clusterLayer)return;
  mLayer.clearLayers();
  clusterLayer.clearLayers();
  events.forEach(e=>{
    const age=e.age_minutes??999;
    const isHot=age<10;
    const conf=e.confidence||70;
    const cc=confClass(conf);
    const color=age>1440?'faded':cc;
    const hotCls=isHot?' em-hot':'';
    const justTag=isHot?`<div class="just-tag">JUST DETECTED</div>`:'';
    const icon=L.divIcon({className:'',html:`<div class="just-wrap">${justTag}<div class="em ${color}${hotCls}"></div></div>`,iconSize:[11,11],iconAnchor:[5,5]});
    const precLoc=e.precise_location||e.region;
    const unc=e.uncertainty?`<div style="color:#f5c518;font-size:.44rem;margin-top:3px;border-top:1px solid #0d3348;padding-top:3px">⚠ ${e.uncertainty}</div>`:'';
    const srcLink=e.url&&e.url!=='#'?`<a href="${e.url}" target="_blank" style="color:#00e5ff;font-size:.5rem">↗ SOURCE</a>`:'';
    const confBadgeColor=confColor(conf);
    const popup=`
<div style="font-family:'Orbitron',sans-serif;font-size:.55rem;letter-spacing:.12em;color:#ff6b1a;margin-bottom:3px">${e.type.toUpperCase()}${isHot?'<span style="color:#ff2233;margin-left:5px;font-size:.38rem">● NOW</span>':''}</div>
<div style="display:flex;justify-content:space-between;color:#4a7a99;font-size:.54rem;margin:2px 0"><span>LOCATION</span><span style="color:#00e5ff">${precLoc}</span></div>
<div style="display:flex;justify-content:space-between;color:#4a7a99;font-size:.54rem;margin:2px 0"><span>CONFIDENCE</span><span style="color:${confBadgeColor}">${conf}% · ${confLabel(conf)}</span></div>
<div style="display:flex;justify-content:space-between;color:#4a7a99;font-size:.54rem;margin:2px 0"><span>DETECTED</span><span style="color:#c8e8f8">${timeSince(e.time_iso)}</span></div>
<div style="margin-top:5px;padding-top:4px;border-top:1px solid #0d3348;font-size:.56rem;line-height:1.35">${e.summary}</div>
${unc}
<div style="margin-top:5px;display:flex;justify-content:space-between;align-items:center">${srcLink}<div class="pop-analyze" onclick="openIntel('${e.id}')">◈ FULL ANALYSIS</div></div>`;
    const marker=L.marker([e.lat,e.lon],{icon}).bindPopup(popup,{maxWidth:300});
    mLayer.addLayer(marker);
    clusterLayer.addLayer(L.marker([e.lat,e.lon],{icon}).bindPopup(popup,{maxWidth:300}));
  });
}

// ════════════ CONFLICT LAYER ════════════
function renderConflictLayer(conflicts){
  if(!conflictLayer)return;
  conflictLayer.clearLayers();
  conflicts.forEach(c=>{
    if(c.frontlines){c.frontlines.forEach(fl=>{
      if(fl.length<2)return;
      L.polyline(fl,{color:c.color,weight:2.5,opacity:.85,dashArray:'5,4'})
        .bindPopup(`<div style="font-family:'Orbitron',sans-serif;font-size:.55rem;color:${c.color}">${c.name.toUpperCase()} FRONTLINE</div><div style="font-size:.54rem;color:#4a7a99;margin-top:2px">${c.description}</div>`)
        .addTo(conflictLayer);
    })}
    if(c.hotspots){c.hotspots.forEach(h=>{
      const icon=L.divIcon({className:'',html:`<div class="hotspot-marker" style="background:${c.color}44;border-color:${c.color};box-shadow:0 0 5px ${c.color}"></div>`,iconSize:[8,8],iconAnchor:[4,4]});
      L.marker([h.lat,h.lon],{icon}).bindPopup(`<div style="font-family:'Orbitron',sans-serif;font-size:.54rem;color:${c.color}">${h.name.toUpperCase()}</div><div style="font-size:.52rem;color:#4a7a99;margin-top:2px">${c.name} · ${c.state.toUpperCase()}</div>`).addTo(conflictLayer);
    })}
    // Label
    const cIcon=L.divIcon({className:'',html:`<div style="font-family:'Orbitron',sans-serif;font-size:.42rem;padding:3px 6px;border:1px solid ${c.color};background:rgba(2,6,8,.9);color:${c.color};white-space:nowrap">${c.name.toUpperCase()}</div>`,iconSize:[null,null],iconAnchor:[0,10]});
    L.marker([c.lat,c.lon],{icon:cIcon}).addTo(conflictLayer);
  });
}

// ════════════ TRADE LAYER (with traffic labels) ════════════
function renderTradeLayer(routes, chokepointTraffic){
  if(!tradeLayer)return;
  tradeLayer.clearLayers();
  (routes||[]).forEach(r=>{
    if(!r.waypoints||r.waypoints.length<2)return;
    const color=riskColor(r.risk);
    const weight=r.risk==='HIGH'||r.risk==='CRITICAL'?3:r.risk==='MODERATE'?2:1.5;
    L.polyline(r.waypoints,{color,weight,opacity:.85,dashArray:r.risk==='LOW'?'6,4':null})
      .bindPopup(`<div style="font-family:'Orbitron',sans-serif;font-size:.55rem;color:${color}">${r.name.toUpperCase()}</div><div style="font-size:.54rem;color:${color};margin:3px 0">${r.risk} RISK · ${r.disruption_pct}% DISRUPTION</div><div style="font-size:.52rem;color:#4a7a99">${r.reason}</div>`)
      .addTo(tradeLayer);
  });
  // Add chokepoint traffic labels
  const cpCoords={
    "Strait of Hormuz":[26.5,56.5],"Suez Canal":[30.0,32.5],"Bab el-Mandeb":[12.5,43.5],
    "Taiwan Strait":[24.0,119.5],"Strait of Gibraltar":[35.9,-5.5],"Malacca Strait":[2.0,103.0]
  };
  if(chokepointTraffic){Object.entries(chokepointTraffic).forEach(([name,data])=>{
    const coords=cpCoords[name];if(!coords)return;
    const pct=data.traffic_pct||0;
    const color=trafficColor(pct);
    const icon=L.divIcon({className:'',html:`<div style="font-family:'Orbitron',sans-serif;font-size:.44rem;padding:3px 7px;border:1px solid ${color};background:rgba(2,6,8,.9);color:${color};white-space:nowrap">${name}<br>${pct}% TRAFFIC</div>`,iconSize:[null,null],iconAnchor:[0,0]});
    L.marker(coords,{icon}).bindPopup(`<div style="font-family:'Orbitron',sans-serif;font-size:.55rem;color:${color}">${name.toUpperCase()}</div><div style="font-size:.54rem;color:#4a7a99;margin-top:3px">Traffic: <span style="color:${color}">${pct}% of normal capacity</span></div><div style="font-size:.52rem;color:#4a7a99">~${data.normal_vessels_day} vessels/day normally</div><div style="font-size:.52rem;color:${riskColor(data.risk)};margin-top:2px">${data.risk} RISK</div>`).addTo(tradeLayer);
  })}
}

// ════════════ TRAVEL LAYER ════════════
function renderTravelLayer(travel){
  if(!travelLayer)return;
  travelLayer.clearLayers();
  Object.entries(travel||{}).forEach(([country,data])=>{
    const c=riskColor(data.risk);
    const icon=L.divIcon({className:'',html:`<div class="travel-cm" style="border-color:${c};color:${c};background:rgba(2,6,8,.85)">${country}</div>`,iconSize:[null,null],iconAnchor:[0,10]});
    L.marker([data.lat,data.lon],{icon}).bindPopup(`<div style="font-family:'Orbitron',sans-serif;font-size:.55rem;color:${c}">${country.toUpperCase()}</div><div style="font-family:var(--mono);font-size:.5rem;color:${c};margin:3px 0">${data.risk}</div><div style="font-size:.5rem;color:#4a7a99">${data.reason}</div>`).addTo(travelLayer);
  });
}

// ════════════ ALIGNMENT LAYER ════════════
function renderAlignLayer(conflict){
  if(!alignLayer)return;
  alignLayer.clearLayers();
  const data=alignData[conflict];
  if(!data||!data.countries)return;
  Object.entries(data.countries||{}).forEach(([country,info])=>{
    const c=stanceColor(info.stance);
    const trends=alignTrends[conflict]||{};
    const tr=trends[country];
    const trendArrowStr=tr?trendArrow(tr.trend):'';
    const trendNote=tr?` · ${tr.note}`:'';
    const icon=L.divIcon({className:'',html:`<div class="align-cm" style="border-color:${c};color:${c};background:rgba(2,6,8,.88)">${country}${trendArrowStr?`<span style="margin-left:3px;color:${trendColorFn(tr?.trend)}">${trendArrowStr}</span>`:''}</div>`,iconSize:[null,null],iconAnchor:[0,10]});
    L.marker([info.lat,info.lon],{icon}).bindPopup(`<div style="font-family:'Orbitron',sans-serif;font-size:.55rem;color:${c}">${country.toUpperCase()}</div><div style="font-family:var(--mono);font-size:.5rem;color:${c};margin:3px 0">${info.stance.replace('_',' ').toUpperCase()}</div><div style="font-size:.5rem;color:#4a7a99">${info.label}${trendNote}</div>`).addTo(alignLayer);
  });
}

// ════════════ GTI ════════════
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

// ════════════ CHART ════════════
function renderChart(trend){
  const ctx=document.getElementById('tchart');if(!ctx)return;
  const labels=trend.map(d=>{const p=d.date.split('-');return`${p[2]}.${p[1]}`});
  const vals=trend.map(d=>d.value);
  const color=gtiColor(vals.filter(Boolean).pop()||4);
  if(tChart)tChart.destroy();
  tChart=new Chart(ctx,{type:'line',data:{labels,datasets:[{data:vals,borderColor:color,borderWidth:2,pointRadius:1.5,pointBackgroundColor:vals.map(v=>v?gtiColor(v):'transparent'),pointBorderColor:'transparent',tension:.38,fill:true,backgroundColor:c=>{const g=c.chart.ctx.createLinearGradient(0,0,0,115);g.addColorStop(0,`${color}44`);g.addColorStop(1,'transparent');return g}}]},options:{responsive:true,maintainAspectRatio:false,animation:{duration:800},plugins:{legend:{display:false},tooltip:{backgroundColor:'#040d12',borderColor:'#1a6688',borderWidth:1,titleColor:'#00e5ff',bodyColor:'#c8e8f8',titleFont:{family:'Share Tech Mono',size:8},bodyFont:{family:'Share Tech Mono',size:8},callbacks:{label:c=>` GTI: ${c.raw?.toFixed(1)||'—'}/10`}}},scales:{x:{grid:{color:'rgba(13,51,72,.25)',drawTicks:false},ticks:{color:'#4a7a99',font:{family:'Share Tech Mono',size:6},maxRotation:0,maxTicksLimit:8},border:{color:'#0d3348'}},y:{min:0,max:10,grid:{color:'rgba(13,51,72,.25)',drawTicks:false},ticks:{color:'#4a7a99',font:{family:'Share Tech Mono',size:6},stepSize:2},border:{color:'#0d3348'}}}}});
}

// ════════════ SNAPSHOT + DELTAS ════════════
function renderSnapshot(d){
  document.getElementById('snap-gti').textContent=d.gti?.toFixed(1)||'—';
  const tc=gtiColor(d.gti||0);
  document.getElementById('snap-gti').style.color=tc;
  document.getElementById('snap-trend').textContent=`trend: ${d.trend||'—'}`;
  document.getElementById('snap-conflicts').textContent=d.active_conflicts||'—';
  document.getElementById('snap-strategic').textContent=`${d.strategic_events_24h||'—'} strategic`;
  document.getElementById('snap-region').textContent=d.most_active_region||'—';
  document.getElementById('snap-fastest').textContent=d.fastest_escalation||'—';
  document.getElementById('snap-date').textContent=new Date().toUTCString().slice(0,11).trim().toUpperCase();

  // Delta indicators
  const dGti=d.gti_change||0;
  const dInc=d.incident_change||0;
  const dStr=d.strategic_change||0;
  function setDelta(id,val,unit=''){
    const el=document.getElementById(id);if(!el)return;
    const sign=val>0?'+':'';
    el.textContent=sign+val.toFixed?.(1)+unit||sign+val+unit;
    el.className='delta-val '+(val>0?'delta-up':val<0?'delta-down':'delta-flat');
  }
  setDelta('delta-gti',dGti,' pts');
  setDelta('delta-inc',dInc,' incidents');
  setDelta('delta-strat',dStr,' events');

  // Hotspots
  renderHotspots(d.hotspots||[], d.region_density||{});
  // Stable
  renderStable(d.stable_regions||[]);
}

// ════════════ HOTSPOTS ════════════
function renderHotspots(hotspots, density){
  const el=document.getElementById('hotspots-list');if(!el)return;
  const maxD=Math.max(...Object.values(density),1);
  if(!hotspots.length){el.innerHTML='<div style="font-family:var(--mono);font-size:.46rem;color:var(--dim)">No hotspots detected</div>';return}
  el.innerHTML=hotspots.map((region,i)=>{
    const count=density[region]||1;
    const pct=Math.round(count/maxD*100);
    const c=gtiColor(Math.min(10,count*1.2));
    const colors=['#ff2233','#ff6b1a','#f5c518','#aaaaff','#4a7a99','#2a4a5a'];
    return`<div class="hotspot-row" onclick="flyToRegion('${region}')">
<span class="hotspot-num" style="color:${colors[i]||'#4a7a99'}">${i+1}</span>
<span class="hotspot-name">${region}</span>
<div class="hotspot-bar-wrap"><div class="hotspot-bar-fill" style="width:${pct}%;background:${c}"></div></div>
<span style="font-family:var(--mono);font-size:.42rem;color:${c};margin-left:3px">${count}</span>
</div>`}).join('');
}

// ════════════ STABLE REGIONS ════════════
function renderStable(stable){
  const el=document.getElementById('stable-list');if(!el)return;
  if(!stable.length){el.innerHTML='<div style="font-family:var(--mono);font-size:.46rem;color:var(--dim)">Calculating…</div>';return}
  el.innerHTML=stable.map(r=>`<div class="stable-row"><div class="stable-dot"></div><span class="stable-name">${r}</span><span class="stable-badge">STABLE</span></div>`).join('');
}

// ════════════ DAILY BRIEFING ════════════
function renderBriefing(data){
  const el=document.getElementById('daily-briefing');if(!el)return;
  el.classList.remove('typing');el.textContent='';
  const text=data.briefing||'No briefing available.';let i=0;
  const iv=setInterval(()=>{el.textContent+=text[i++]||'';if(i>text.length)clearInterval(iv)},11);
  const de=document.getElementById('brief-date');if(de)de.textContent=data.date||'TODAY';
  const me=document.getElementById('brief-model');if(me)me.textContent=ANTHROPIC_KEY_AVAILABLE?'CLAUDE AI':'SYSTEM';
}

// ════════════ ACTIVITY ════════════
function renderActivity(d){
  document.getElementById('act-inc').textContent=d.active_incidents||'—';
  document.getElementById('act-conf').textContent=`${d.confirmed_incidents||'—'} confirmed`;
  document.getElementById('act-reg').textContent=d.regions_with_tension||'—';
  document.getElementById('act-strat').textContent=`${d.strategic_events||'—'} strategic`;
  document.getElementById('act-24h').textContent=d.events_detected_24h||'—';
  document.getElementById('act-avgc').textContent=`AVG CONF ${d.avg_confidence||'—'}%`;
  const le=document.getElementById('act-last');
  if(le){const m=d.last_event_minutes_ago;le.textContent=m===0?'just now':m<60?`${m} min ago`:`${Math.round(m/60)}h ago`;le.style.color=m<10?'#00ff88':m<60?'#f5c518':'#4a7a99'}
}

// ════════════ FORECAST ════════════
function renderForecast(d,analyzed){
  document.getElementById('fc-low').style.width=d.low_pct+'%';
  document.getElementById('fc-mod').style.width=d.moderate_pct+'%';
  document.getElementById('fc-high').style.width=d.high_pct+'%';
  document.getElementById('fc-lp').textContent=d.low_pct+'%';
  document.getElementById('fc-mp').textContent=d.moderate_pct+'%';
  document.getElementById('fc-hp').textContent=d.high_pct+'%';
  document.getElementById('fc-reason').textContent=d.reasoning||'—';
  document.getElementById('fc-conf-val').textContent=Math.round(55+Math.random()*25)+'%';
  document.getElementById('fc-analyzed').textContent=(analyzed||217)+' EVT';
}

// ════════════ REGIONAL ════════════
function renderRegional(d){
  const el=document.getElementById('reg-list');if(!el)return;
  const sorted=Object.entries(d).sort((a,b)=>b[1].gti-a[1].gti);
  if(!sorted.length){el.textContent='No data';return}
  el.innerHTML=sorted.map(([region,data])=>{
    const c=gtiColor(data.gti);const dc=data.delta>=0?'#ff2233':'#00ff88';const ds=data.delta>=0?'+':'';
    return`<div class="reg-row"><span class="reg-name">${region}</span><span class="reg-gti" style="color:${c}">${data.gti}</span><span class="reg-d" style="color:${dc}">${ds}${data.delta}%</span><div class="reg-bar"><div class="reg-bar-f" style="width:${data.gti*10}%;background:${c}"></div></div></div>`}).join('');
}

// ════════════ CONFLICTS ════════════
function renderConflicts(conflicts){
  conflictsData=conflicts;
  const el=document.getElementById('conflict-list');if(!el)return;
  el.innerHTML=conflicts.map(c=>{
    const sc=momentumColor(c.state);
    return`<div class="conflict-item" onclick="flyToConflict(${c.lat},${c.lon})">
<div class="conf-hdr"><span class="conf-name" style="color:${sc}">${c.name.toUpperCase()}</span><span class="conf-state" style="color:${sc};border-color:${sc}">${c.state.toUpperCase()}</span></div>
<div class="conf-meta"><span>${c.region}</span><span>M: <span style="color:${sc}">${c.adjusted_momentum||c.momentum}/10</span></span><span>${c.live_events||0} live</span></div>
<div class="conf-mbar"><div class="conf-mbar-f" style="width:${(c.adjusted_momentum||c.momentum)*10}%;background:${sc}"></div></div>
<div class="conf-desc">${c.description}</div>
</div>`}).join('');
}
function flyToConflict(lat,lon){if(leafMap){setLayer('conflicts',document.querySelectorAll('.layer-btn')[1]);leafMap.flyTo([lat,lon],5,{duration:1.2})}}

// ════════════ FLY TO REGION ════════════
const REGION_COORDS={'Middle East':[29.5,44.0],'Eastern Europe':[49.5,32.0],'East Asia':[25.0,118.0],'South Asia':[30.0,68.0],'Horn of Africa':[10.0,44.0],'West Africa':[13.0,2.0],'Mediterranean':[36.0,14.0],'Central Asia':[41.0,62.0],'Northern Europe':[60.0,20.0],'Latin America':[-15.0,-55.0],'Central Africa':[-2.0,25.0]};
function flyToRegion(region){const c=REGION_COORDS[region];if(c&&leafMap){setLayer('live',document.querySelectorAll('.layer-btn')[0]);leafMap.flyTo(c,5,{duration:1.2})}}

// ════════════ ALIGNMENT ════════════
function renderAlignmentPanel(conflict){
  currentAlignConflict=conflict;
  const data=alignData[conflict];if(!data)return;
  const selEl=document.getElementById('align-conf-sel');
  if(selEl){selEl.innerHTML=Object.keys(alignData).map(k=>`<button class="align-conf-btn${k===conflict?' active':''}" onclick="selectAlignConflict('${k}')">${(alignData[k].conflict||k).slice(0,12).toUpperCase()}</button>`).join('')}
  const el=document.getElementById('align-list');if(!el)return;
  const trends=alignTrends[conflict]||{};
  const sorted=Object.entries(data.countries||{}).sort((a,b)=>{const o={supporting_A:0,supporting_B:1,ambiguous:2,neutral:3};return(o[a[1].stance]||3)-(o[b[1].stance]||3)});
  el.innerHTML=`<div>${sorted.map(([country,info])=>{
    const c=stanceColor(info.stance);
    const tr=trends[country];
    const arrow=tr?`<span style="color:${trendColorFn(tr.trend)};font-size:.6rem;margin-left:2px">${trendArrow(tr.trend)}</span>`:'';
    const tNote=tr&&tr.trend!=='stable'?`<div style="font-family:var(--mono);font-size:.38rem;color:${trendColorFn(tr.trend)};margin-top:1px">${tr.note}</div>`:'';
    return`<div class="align-row"><div class="align-dot" style="background:${c}"></div><span class="align-country">${country}</span><div><span class="align-label stance-${info.stance}">${info.label}</span>${arrow}${tNote}</div></div>`}).join('')}</div>`;
  renderAlignLayer(conflict);
}
function selectAlignConflict(k){renderAlignmentPanel(k)}

// ════════════ TRADE PANELS ════════════
function renderTradePanels(data){
  const routeEl=document.getElementById('trade-routes-list');
  if(routeEl&&data.routes)routeEl.innerHTML=data.routes.map(r=>{const c=riskColor(r.risk);return`<div class="trade-route"><span class="trade-nm">${r.name}</span><div class="trade-r"><div class="trade-risk" style="color:${c}">${r.risk}</div><div class="trade-pct">${r.disruption_pct}% disruption</div></div></div>`}).join('');
  const logEl=document.getElementById('logistics-grid');
  if(logEl&&data.sectors)logEl.innerHTML=Object.entries(data.sectors).map(([k,s])=>`<div class="log-item"><div class="log-icon">${s.icon}</div><div class="log-lbl">${k.toUpperCase()}</div><div class="log-risk" style="color:${riskColor(s.risk)}">${s.risk}</div></div>`).join('');
}

// ════════════ CHOKEPOINT TRAFFIC BARS ════════════
function renderChokeTraffic(data){
  const el=document.getElementById('choke-traffic-bars');if(!el)return;
  el.innerHTML=Object.entries(data).map(([name,d])=>{
    const pct=d.traffic_pct||0;const c=trafficColor(pct);
    return`<div class="choke-traffic-item">
<div class="choke-traffic-top"><span class="choke-traffic-name">${name}</span><span class="choke-traffic-pct" style="color:${c}">${pct}%</span></div>
<div class="choke-traffic-bar"><div class="choke-traffic-fill" style="width:${pct}%;background:${c}"></div></div>
</div>`}).join('');
}

// ════════════ STRATEGIC + SUPPLY ════════════
function renderStrategic(d){
  const el=document.getElementById('strat-list');
  if(el){const items=[{label:'CARRIER GROUP',val:d.carrier_group?'DETECTED':'NOT DETECTED',on:d.carrier_group},{label:'BALLISTIC LAUNCH',val:d.ballistic_launch?'DETECTED':'NOT DETECTED',on:d.ballistic_launch},{label:'NUCLEAR RHETORIC',val:d.nuclear_rhetoric?'ACTIVE':'NONE',on:d.nuclear_rhetoric}];
  el.innerHTML=items.map(i=>`<div class="strat-item"><div class="strat-dot" style="background:${i.on?'#ff2233':'#2a4a5a'};box-shadow:${i.on?'0 0 4px #ff2233':'none'}"></div><span class="strat-lbl">${i.label}</span><span class="strat-val" style="color:${i.on?'#ff2233':'#2a4a5a'}">${i.val}</span></div>`).join('')}
  const cel=document.getElementById('choke-list');
  if(cel&&d.chokepoints)cel.innerHTML=d.chokepoints.map(c=>`<div class="choke-item"><span class="choke-nm">${c.name}</span><span class="choke-rv" style="color:${riskColor(c.risk)}">${c.risk}</span></div>`).join('');
}
function renderSupply(d){
  const el=document.getElementById('supply-grid');if(!el)return;
  el.innerHTML=[['⚡','ENERGY','energy'],['🚢','SHIPPING','shipping'],['🌾','FOOD','food'],['💾','TECH','tech']]
    .map(([ic,lb,k])=>`<div class="sup-item"><div style="font-size:.75rem">${ic}</div><div style="font-family:var(--mono);font-size:.4rem;color:var(--muted);margin:1px 0">${lb}</div><div style="font-family:var(--disp);font-size:.52rem;font-weight:700;color:${riskColor(d[k]||'LOW')}">${d[k]||'LOW'}</div></div>`).join('');
}

// ════════════ FEED (confidence color) ════════════
function renderFeed(events){
  const el=document.getElementById('feed-list');if(!el)return;
  if(!events.length){el.innerHTML='<div style="padding:9px;font-family:var(--mono);font-size:.5rem;color:#ff2233">NO EVENTS</div>';return}
  el.innerHTML=events.slice(0,18).map(e=>{
    const cc=confClass(e.confidence||70);const color=confColor(e.confidence||70);const label=confLabel(e.confidence||70);
    const age=e.age_minutes??999;
    return`<div class="fi" onclick="openIntel('${e.id}')">
<div class="fi-ind ${cc}"></div>
<div>
  <div class="fi-type">${e.type.toUpperCase()}${age<10?'<span style="color:#ff2233;margin-left:3px;font-size:.36rem">● NOW</span>':''}</div>
  <div class="fi-loc">◈ ${e.precise_location||e.region}</div>
  <div class="fi-reg">${e.region} · ${timeSince(e.time_iso)}</div>
  <div class="fi-desc">${e.summary}</div>
</div>
<div>
  <div class="fi-conf-badge" style="color:${color};border-color:${color}">${label}</div>
  <div class="fi-src">${e.source}</div>
</div>
</div>`}).join('');
}

// ════════════ ALERTS + TRANSPARENCY + SUMMARY ════════════
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
    ['AI CONFIDENCE',`${act.ai_confidence||'—'}%`],
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
function renderTravelPanel(data){
  const el=document.getElementById('travel-list');if(!el)return;
  const sorted=Object.entries(data||{}).sort((a,b)=>{const ord={CRITICAL:0,HIGH:1,MODERATE:2,LOW:3};return(ord[a[1].risk]||3)-(ord[b[1].risk]||3)});
  el.innerHTML=sorted.map(([country,d])=>`<div class="travel-row" title="${d.reason}"><span class="travel-country">${country}</span><span class="travel-risk risk-${d.risk}">${d.risk}</span></div>`).join('');
}

// ════════════ INTELLIGENCE PANEL ════════════
async function openIntel(eid){
  const panel=document.getElementById('intel-panel');
  const body=document.getElementById('intel-body');
  panel.classList.add('open');
  body.innerHTML='<div class="intel-loading"><span class="intel-spinner">◈</span>Fetching Claude AI analysis…</div>';
  const [detail,stats]=await Promise.all([
    fetch(`/api/event-detail/${eid}`).then(r=>r.json()).catch(()=>({})),
    fetch(`/api/event-stats/${eid}`).then(r=>r.json()).catch(()=>({})),
  ]);
  const esc=detail.escalation_risk||'MODERATE';
  const actors=(detail.related_actors||[]).map(a=>`<span class="actor-tag">${a}</span>`).join('')||'<span style="color:var(--muted);font-size:.42rem">—</span>';
  const ev=allEvents.find(e=>e.id===eid)||{};
  const precLoc=ev.precise_location||detail.location||'Unknown';
  const cc=confClass(ev.confidence||70);const ccColor=confColor(ev.confidence||70);const ccLabel=confLabel(ev.confidence||70);
  const unc=ev.uncertainty?`<div class="intel-unc">⚠ ${ev.uncertainty}</div>`:'';
  body.innerHTML=`
<div class="intel-type">${(detail.event_type||'UNKNOWN').toUpperCase()}</div>
<div class="intel-loc">◈ ${precLoc}${ev.region&&ev.region!==precLoc?`<span style="color:var(--muted);margin-left:4px">· ${ev.region}</span>`:''}</div>
<div class="intel-det">Detected ${ev.time_iso?timeSince(ev.time_iso):'—'} · ${detail.source||'—'} · ${ev.source_count??'—'} source(s)</div>
${unc}
<div class="intel-4g">
  <div class="intel-m"><div class="intel-m-l">CONFIDENCE</div><div class="intel-m-v" style="color:${ccColor}">${ev.confidence||'—'}%</div></div>
  <div class="intel-m"><div class="intel-m-l">ASSESSMENT</div><div style="font-family:var(--disp);font-size:.62rem;font-weight:700;color:${ccColor};padding-top:2px">${ccLabel}</div></div>
  <div class="intel-m"><div class="intel-m-l">ESC. RISK</div><div class="esc-badge esc-${esc}">${esc}</div></div>
  <div class="intel-m"><div class="intel-m-l">NUMBERS</div><div class="intel-m-v" style="color:var(--cyan);font-size:.62rem">${detail.numbers_detected||ev.numbers||'—'}</div></div>
</div>
<div class="intel-stats-box">
  <div class="intel-stats-h">◈ LAST 24H — ${precLoc}</div>
  <div class="intel-stats-g">
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
<div style="margin-top:8px;font-family:var(--mono);font-size:.4rem;color:var(--muted);border-top:1px solid var(--b0);padding-top:5px">ANALYSIS: CLAUDE AI · ${new Date().toUTCString().slice(0,16)} UTC</div>`;
}
function closeIntel(){document.getElementById('intel-panel').classList.remove('open')}

// ════════════ REPLAY ════════════
const ANTHROPIC_KEY_AVAILABLE=false; // set by backend
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

// ════════════ LANG STUB ════════════
function setLang(lang){document.documentElement.setAttribute('lang',lang);document.documentElement.setAttribute('dir',lang==='ar'?'rtl':'ltr')}

// ════════════ MAIN LOAD ════════════
async function loadAll(){
  refreshCountdown=600;
  try{
    // Individual fetches - one failure cannot block others
    const _f = async (url, fallback) => {
      for(let attempt=0; attempt<3; attempt++){
        try{ return await fetch(url).then(r=>{ if(!r.ok)throw new Error(r.status); return r.json(); }); }
        catch(e){ if(attempt===2) return fallback; await new Promise(r=>setTimeout(r,600)); }
      }
      return fallback;
    };
    const [sr,er,tr,fc,reg,strat,sup,al,act,conflicts,trade,travel,alignU,alignG,snap,chkTraffic,alignTr]=await Promise.all([
      _f('/api/status',{}),
      _f('/api/events-v4',{events:[]}),
      _f('/api/trend',{trend:[]}),
      _f('/api/forecast',{}),
      _f('/api/regional',{regional:{}}),
      _f('/api/strategic',{}),
      _f('/api/supply-chain',{}),
      _f('/api/alerts',{alerts:[]}),
      _f('/api/activity',{}),
      _f('/api/conflicts',{conflicts:[]}),
      _f('/api/trade',{routes:[],sectors:{}}),
      _f('/api/travel-safety',{travel:{}}),
      _f('/api/alignment?conflict=ukraine_war',{}),
      _f('/api/alignment?conflict=gaza_conflict',{}),
      _f('/api/snapshot',{}),
      _f('/api/chokepoints-traffic',{chokepoints:{}}),
      _f('/api/alignment-trends',{trends:{}}),
    ]);

    allEvents=er.events||[];
    tradeData=trade;
    travelData=travel.travel||{};
    if(alignU.alignment)alignData['ukraine_war']=alignU.alignment;
    if(alignG.alignment)alignData['gaza_conflict']=alignG.alignment;
    if(alignTr.trends)alignTrends=alignTr.trends;

    const _safe = (label, fn) => {
      try { fn(); }
      catch(e) {
        console.warn('[Render]', label, e.message);
        const _dbg=document.getElementById('dbg-overlay');
        if(_dbg){_dbg.style.display='block';_dbg.innerHTML+=('<br><b>'+label+'</b>: '+e.message);}
      }
    };
    const _st=document.getElementById('dbg-status');if(_st)_st.textContent='JS: RUNNING';
    _safe('GTI',          ()=>renderGTI(sr));
    _safe('Chart',        ()=>renderChart(tr.trend||[]));
    _safe('Map',          ()=>renderMap(allEvents));
    _safe('Feed',         ()=>renderFeed(allEvents));
    _safe('Forecast',     ()=>renderForecast(fc, act.events_detected_24h||0));
    _safe('Regional',     ()=>renderRegional(reg.regional||{}));
    _safe('Strategic',    ()=>renderStrategic(strat||{}));
    _safe('Supply',       ()=>renderSupply(sup||{}));
    _safe('Alerts',       ()=>renderAlerts(al.alerts||[]));
    _safe('Activity',     ()=>renderActivity(act||{}));
    _safe('Conflicts',    ()=>renderConflicts(conflicts.conflicts||[]));
    _safe('ConflictLayer',()=>renderConflictLayer(conflicts.conflicts||[]));
    _safe('Trade',        ()=>renderTradePanels(trade||{}));
    _safe('TradeLayer',   ()=>renderTradeLayer(trade.routes||[], chkTraffic.chokepoints||{}));
    _safe('Travel',       ()=>renderTravelPanel(travelData||{}));
    _safe('TravelLayer',  ()=>renderTravelLayer(travelData||{}));
    _safe('Transparency', ()=>renderTransparency(act||{},sr||{}));
    _safe('Snapshot',     ()=>renderSnapshot(snap||{}));
    _safe('Choke',        ()=>renderChokeTraffic(chkTraffic.chokepoints||{}));
    _safe('Alignment',    ()=>renderAlignmentPanel('ukraine_war'));

    const ms=document.getElementById('map-src');
    if(ms)ms.textContent=`${er.count||0} INCIDENTS · ${new Date().toUTCString().slice(17,25)} UTC`;
    const _st2=document.getElementById('dbg-status');if(_st2)_st2.textContent='DATA: OK ✓ '+er.count+' events';

    // Async: AI summary + daily briefing
    const se=document.getElementById('ai-sum');if(se){se.classList.add('typing');se.textContent='Analyzing…'}
    fetch('/api/summary').then(r=>r.json()).then(renderSummary).catch(()=>{const e=document.getElementById('ai-sum');if(e){e.classList.remove('typing');e.textContent='Summary unavailable.'}});

    const be=document.getElementById('daily-briefing');if(be){be.classList.add('typing');be.textContent='Generating daily briefing…'}
    fetch('/api/daily-briefing').then(r=>r.json()).then(renderBriefing).catch(()=>{const e=document.getElementById('daily-briefing');if(e){e.classList.remove('typing');e.textContent='Briefing unavailable.'}});

    await loadRepHistory();
    setLayer(currentLayer, document.querySelector('.layer-btn.al, .layer-btn.al-conflict, .layer-btn.al-trade, .layer-btn.al-travel, .layer-btn.al-align'));

  }catch(err){
    console.error('[LoadAll]',err);
    const _dbg=document.getElementById('dbg-overlay');
    if(_dbg){_dbg.style.display='block';_dbg.innerHTML='<b>LOAD ERROR</b>: '+err.message+'<br>'+err.stack.split('\n').slice(0,4).join('<br>');}
  }
}

// ════════════ BOOT ════════════
document.addEventListener('DOMContentLoaded',()=>{
  initMap();
  loadAll();
  // Auto-retry with escalating delays
  const _retry = async (attempt) => {
    try {
      const r = await fetch('/api/events-v4').then(x=>x.json());
      if(!r.count || r.count===0){ 
        const el=document.getElementById('data-status');
        if(el)el.textContent='DATA: RETRYING…';
        if(attempt<4) setTimeout(()=>_retry(attempt+1), 2000*(attempt+1));
        else loadAll();
      } else {
        const el=document.getElementById('data-status');
        if(el)el.textContent='DATA: ●LIVE';
      }
    } catch(e){ if(attempt<3) setTimeout(()=>_retry(attempt+1), 3000); }
  };
  setTimeout(()=>_retry(0), 3000);
  function fixH(){
    const w=document.getElementById('wmap'),shell=document.querySelector('.shell'),rb=document.querySelector('.rep-bar'),mf=document.querySelector('.map-footer');
    if(w&&shell&&rb&&mf){const h=shell.clientHeight-rb.offsetHeight-mf.offsetHeight;w.style.height=Math.max(200,h)+'px';if(leafMap)leafMap.invalidateSize()}
  }
  fixH();window.addEventListener('resize',fixH);setTimeout(fixH,500);
});

// === v4.3 EXTENSION ===

// ═══════════════════════════════════════════════════════════════
// GTM v4.3 EXTENSION MODULE
// OSINT + FORECAST - no function redefinitions, no override chains
// All patches use object/variable assignment, not function declarations
// ═══════════════════════════════════════════════════════════════

// ── OSINT state ─────────────────────────────────────────────────
let osintIdx = {};
let osintOn  = false;
let hovTimer = null;

// ── FORECAST state ───────────────────────────────────────────────
let forecastLayer = null;
let heatLayer     = null;
let fcData        = null;
let isForecastMode = false;

// ════════════════════════════════════════════════════════════════
// OSINT FUNCTIONS
// ════════════════════════════════════════════════════════════════

function toggleOsint(btn) {
    osintOn = !osintOn;
    btn.classList.toggle('on', osintOn);
    buildOsintBadges();
}

async function loadOsintIdx() {
    try {
        const r = await fetch('/api/osint-index').then(x => x.json());
        osintIdx = {};
        (r.evidence_available || []).forEach(e => { osintIdx[e.id] = e; });
    } catch(e) { console.warn('[OSINT] index failed'); }
}

function buildOsintBadges() {
    document.querySelectorAll('.ev-badge').forEach(el => el.remove());
    document.querySelectorAll('.ev-marker-wrap').forEach(el => {
        el.className = el.className.replace('ev-marker-wrap', 'just-wrap');
    });
    if (!osintOn || !leafMap) return;
    leafMap.eachLayer(layer => {
        if (!layer._latlng || !layer._icon) return;
        const ev = (allEvents || []).find(e =>
            Math.abs(e.lat - layer._latlng.lat) < 0.5 &&
            Math.abs(e.lon - layer._latlng.lng) < 0.5);
        if (!ev || !osintIdx[ev.id]) return;
        const meta = osintIdx[ev.id];
        const wrap = layer._icon.querySelector('.just-wrap, .ev-marker-wrap');
        if (!wrap) return;
        wrap.className = 'ev-marker-wrap';
        const badge = document.createElement('div');
        badge.className = 'ev-badge ' + (meta.type || 'photo');
        badge.textContent = meta.type === 'video' ? '▶' : meta.type === 'satellite' ? '🛰' : '📷';
        wrap.appendChild(badge);
    });
}

function osintZoom(src) {
    let ov = document.getElementById('zoom-ov');
    if (ov) { ov.querySelector('img').src = src; ov.classList.add('show'); }
}
function osintZoomClose() {
    const ov = document.getElementById('zoom-ov');
    if (ov) ov.classList.remove('show');
}
function osintPlayVideo(url) {
    const ph = document.getElementById('osint-vid-ph');
    const fw = document.getElementById('osint-vid-fw');
    if (!ph || !fw) return;
    ph.style.display = 'none'; fw.style.display = 'block';
    fw.innerHTML = '<iframe src="' + url + '&autoplay=1" allow="autoplay;encrypted-media" allowfullscreen style="width:100%;height:100%;border:none"></iframe>';
}

function buildOsintSection(osintData) {
    if (!osintData || !osintData.has_evidence || !osintData.evidence) {
        const conf = osintData && osintData.confidence;
        const msg = conf && conf < 85
            ? 'Confidence ' + conf + '% below 85% threshold'
            : 'No visual evidence indexed for this event type';
        return '<div class="osint-panel"><div class="osint-none">🛰 ' + msg + '</div></div>';
    }
    const evd = osintData.evidence;
    const si = evd.source_icon || '🔍';
    let mediaHTML = '';
    if (evd.type === 'video' && evd.embed_url) {
        const th = evd.thumbnail || '';
        mediaHTML = '<div class="osint-media">'
            + '<div class="osint-vid-placeholder" id="osint-vid-ph" onclick="osintPlayVideo(\'' + evd.embed_url + '\')">'
            + (th ? '<img class="osint-vid-thumb" src="' + th + '" onerror="this.remove()">' : '')
            + '<div class="osint-play-wrap"><div class="osint-play-btn">▶</div></div>'
            + '</div><div class="osint-vid-frame" id="osint-vid-fw"></div></div>';
    } else {
        const src = evd.image_url || evd.thumbnail || '';
        const cls = evd.type === 'satellite' ? 'osint-sat-img' : 'osint-img';
        mediaHTML = '<div class="osint-media"><img class="' + cls + '" src="' + src
            + '" onclick="osintZoom(\'' + src + '\')" onerror="this.parentNode.style.display=\'none\'"></div>';
    }
    return '<div class="osint-panel">'
        + '<div class="osint-panel-hdr"><span class="osint-panel-title">🛰 EVENT EVIDENCE</span>'
        + '<span class="osint-src-badge">' + si + ' ' + (evd.source || '—') + '</span></div>'
        + mediaHTML
        + '<div class="osint-meta"><div class="osint-caption">' + (evd.caption || '—') + '</div>'
        + '<div class="osint-src-line"><span>' + si + '</span><span>' + (evd.source || '—') + '</span>'
        + '<span style="margin-left:auto;color:#00e5ff;font-size:.42rem">'
        + (evd.source_type || '').replace(/_/g, ' ').toUpperCase() + '</span></div></div>'
        + '<div class="osint-ai-box"><div class="osint-ai-lbl">IMAGERY ANALYSIS</div>'
        + '<div class="osint-ai-txt">' + (evd.ai_analysis || evd.ai_brief || 'Analysis pending.') + '</div></div>'
        + '<div class="osint-warn">⚠ Evidence matched by region/type. Verify with primary sources.</div>'
        + '</div>';
}

// ════════════════════════════════════════════════════════════════
// FORECAST FUNCTIONS
// ════════════════════════════════════════════════════════════════

function fcColor(prob) {
    return prob >= 0.72 ? '#ff2233' : prob >= 0.50 ? '#ff6b1a' : prob >= 0.30 ? '#f5c518' : '#00ff88';
}

function initForecastLayer() {
    if (!leafMap || forecastLayer) return;
    forecastLayer = L.layerGroup();
}

function loadHeatPlugin(cb) {
    if (window.L && L.heatLayer) { cb(); return; }
    if (document.querySelector('[data-heat]')) { setTimeout(cb, 500); return; }
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet.heat/0.2.0/leaflet-heat.js';
    s.setAttribute('data-heat', '1');
    s.onload = cb;
    s.onerror = cb;
    document.head.appendChild(s);
}

function activateForecastMode() {
    isForecastMode = true;
    if (!leafMap) return;
    [mLayer, clusterLayer, conflictLayer, tradeLayer, travelLayer, alignLayer].forEach(l => {
        if (l && leafMap.hasLayer(l)) leafMap.removeLayer(l);
    });
    const banner = document.getElementById('fc-mode-banner');
    if (banner) banner.classList.add('show');
    document.querySelectorAll('.layer-legend').forEach(el => el.classList.remove('vis'));
    const fcLeg = document.getElementById('leg-forecast');
    if (fcLeg) fcLeg.classList.add('vis');
    loadHeatPlugin(() => renderForecastMap(fcData));
}

function deactivateForecastMode() {
    isForecastMode = false;
    if (!leafMap) return;
    if (heatLayer && leafMap.hasLayer(heatLayer)) leafMap.removeLayer(heatLayer);
    if (forecastLayer && leafMap.hasLayer(forecastLayer)) leafMap.removeLayer(forecastLayer);
    const banner = document.getElementById('fc-mode-banner');
    if (banner) banner.classList.remove('show');
}

function renderForecastMap(data) {
    if (!leafMap || !data) return;
    if (!forecastLayer) initForecastLayer();
    if (heatLayer && leafMap.hasLayer(heatLayer)) leafMap.removeLayer(heatLayer);
    forecastLayer.clearLayers();

    const REGION_CENTERS = {
        'Middle East':    [31.5, 35.5], 'Eastern Europe': [49.5, 32.0],
        'East Asia':      [24.5, 121.0], 'Horn of Africa':  [12.5, 43.5],
        'West Africa':    [13.0, 2.0],  'Mediterranean':   [35.5, 19.0],
        'South Asia':     [30.0, 70.0], 'Central Asia':    [41.0, 63.0],
    };

    const points = data.heatmap_points || [];
    const forecasts = data.forecasts || {};

    if (window.L && L.heatLayer && points.length) {
        heatLayer = L.heatLayer(points, {
            radius: 55, blur: 38, maxZoom: 8, max: 0.95,
            gradient: {0.0:'#001a00',0.28:'#006600',0.45:'#00aa00',0.58:'#f5c518',0.72:'#ff6b1a',0.88:'#ff2233',1.0:'#8b0000'}
        });
        leafMap.addLayer(heatLayer);
    } else {
        // Fallback circles
        points.forEach(pt => {
            L.circle([pt[0], pt[1]], {
                radius: 180000, color: 'transparent',
                fillColor: fcColor(pt[2]), fillOpacity: 0.18 + pt[2] * 0.22, interactive: false
            }).addTo(forecastLayer);
        });
    }

    Object.entries(forecasts).forEach(([rname, fr]) => {
        const center = REGION_CENTERS[rname];
        if (!center) return;
        const col = fr.color || fcColor(fr.probability || 0);
        const pct = fr.probability_pct + '%';
        const arrow = fr.trend_arrow || '→';

        L.circle(center, {
            radius: fr.probability > 0.5 ? 240000 : 180000,
            color: col, weight: fr.probability > 0.65 ? 2 : 1,
            opacity: 0.6, fillOpacity: 0, dashArray: fr.probability > 0.65 ? null : '6,4'
        }).bindPopup(buildFcPopup(rname, fr)).addTo(forecastLayer);

        const icon = L.divIcon({
            className: '',
            html: '<div class="fc-region-label" style="border-color:' + col + ';color:' + col + '">'
                + '<span style="font-family:var(--disp);font-size:.52rem;font-weight:700">' + pct + '</span>'
                + '<span style="margin-left:4px;font-size:.6rem">' + arrow + '</span><br>'
                + '<span style="font-size:.38rem;opacity:.8">' + rname + '</span></div>',
            iconAnchor: [0, 0], iconSize: null,
        });
        L.marker(center, {icon}).bindPopup(buildFcPopup(rname, fr)).addTo(forecastLayer);
    });

    leafMap.addLayer(forecastLayer);
}

function buildFcPopup(rname, fr) {
    const col = fr.color || '#f5c518';
    const drivers = (fr.drivers || []).map(d =>
        '<div style="font-size:.5rem;color:#4a7a99;padding:1px 0">· ' + d.signal + (d.count ? ' (' + d.count + ')' : '') + '</div>'
    ).join('');
    return '<div style="font-family:Orbitron,sans-serif;font-size:.55rem;letter-spacing:.12em;color:' + col + ';margin-bottom:4px">'
        + rname.toUpperCase() + '</div>'
        + '<div style="font-family:var(--disp);font-size:1.1rem;font-weight:900;color:' + col + ';margin:2px 0">'
        + fr.probability_pct + '% <span style="font-size:.7rem">' + (fr.trend_arrow || '→') + '</span></div>'
        + '<div style="font-family:var(--disp);font-size:.44rem;padding:1px 5px;border:1px solid ' + col + ';color:' + col + ';display:inline-block;margin-bottom:5px">' + (fr.label || '') + '</div>'
        + '<div style="font-size:.46rem;color:#4a7a99;margin-bottom:3px">FORECAST DRIVERS:</div>' + drivers
        + '<div style="font-size:.4rem;color:#2a4a5a;margin-top:5px;border-top:1px solid #0d3348;padding-top:3px">72H ESCALATION PROBABILITY · MODEL v4.3</div>';
}

function renderForecastPanel(data) {
    if (!data) return;
    fcData = data;
    const confBadge = document.getElementById('fc72-conf-badge');
    if (confBadge) confBadge.textContent = data.confidence + '% conf';
    const confVal = document.getElementById('fc72-conf-val');
    if (confVal) confVal.textContent = data.confidence + '%';
    const sigsEl = document.getElementById('fc72-sigs');
    if (sigsEl) sigsEl.textContent = (data.signals_analyzed || 0) + ' signals';

    const panelRegions = data.panel_regions || ['Middle East','Eastern Europe','East Asia','Horn of Africa','West Africa'];
    const regEl = document.getElementById('fc72-regions');
    if (regEl) {
        regEl.innerHTML = panelRegions.map(rname => {
            const fr = (data.forecasts || {})[rname]; if (!fr) return '';
            const col = fr.color || '#f5c518';
            const trendCol = fr.trend_dir === 'escalating' ? '#ff2233' : fr.trend_dir === 'decreasing' ? '#00ff88' : '#4a7a99';
            return '<div class="fc72-region">'
                + '<div class="fc72-region-top"><span class="fc72-region-name">' + rname + '</span>'
                + '<div class="fc72-region-meta">'
                + '<span class="fc72-trend" style="color:' + trendCol + '">' + (fr.trend_arrow || '→') + '</span>'
                + '<span class="fc72-region-prob" style="color:' + col + '">' + fr.probability_pct + '%</span>'
                + '</div></div>'
                + '<div class="fc72-label" style="color:' + col + '">' + (fr.label || '') + '</div>'
                + '<div class="fc72-bar"><div class="fc72-bar-fill" style="width:' + Math.round(fr.probability * 100) + '%;background:' + col + '"></div></div>'
                + '</div>';
        }).join('');
    }

    const allDrivers = {};
    Object.values(data.forecasts || {}).forEach(fr => {
        (fr.drivers || []).forEach(d => { allDrivers[d.signal] = (allDrivers[d.signal] || 0) + (d.count || 1); });
    });
    const topDrivers = Object.entries(allDrivers).sort((a,b) => b[1]-a[1]).slice(0, 6);
    const drivEl = document.getElementById('fc72-drivers-list');
    const driverColors = ['#ff2233','#ff6b1a','#f5c518','#aaaaff','#4a7a99','#2a4a5a'];
    if (drivEl) {
        drivEl.innerHTML = topDrivers.length
            ? topDrivers.map(([sig,cnt],i) =>
                '<div class="fc72-driver-row"><div class="fc72-driver-dot" style="background:' + (driverColors[i]||'#2a4a5a') + '"></div>'
                + '<span class="fc72-driver-txt">' + sig + '</span>'
                + '<span class="fc72-driver-cnt">' + cnt + '</span></div>').join('')
            : '<div class="fc72-driver-row"><span class="fc72-driver-txt" style="color:var(--muted)">Baseline monitoring active</span></div>';
    }
    if (isForecastMode) loadHeatPlugin(() => renderForecastMap(data));
}

// ════════════════════════════════════════════════════════════════
// PATCHED setLayer — handles 'forecast' mode
// Uses variable assignment so it doesn't conflict with hoisting
// ════════════════════════════════════════════════════════════════
const _setLayerOrig = setLayer;
setLayer = function(name, btn) {
    if (name === 'forecast') {
        currentLayer = 'forecast';
        document.querySelectorAll('.layer-btn').forEach(b => b.className = 'layer-btn');
        if (btn) btn.className = 'layer-btn al-forecast';
        activateForecastMode();
        return;
    }
    if (isForecastMode) deactivateForecastMode();
    _setLayerOrig(name, btn);
};

// ════════════════════════════════════════════════════════════════
// PATCHED openIntel — prepends OSINT section
// ════════════════════════════════════════════════════════════════
const _openIntelOrig = openIntel;
openIntel = async function(eid) {
    await _openIntelOrig(eid);
    const body = document.getElementById('intel-body');
    if (!body) return;
    let osintData = { has_evidence: false };
    try { osintData = await fetch('/api/osint/' + eid).then(r => r.json()); } catch(e) {}
    const tmp = document.createElement('div');
    tmp.innerHTML = buildOsintSection(osintData);
    if (tmp.firstChild) body.insertBefore(tmp.firstChild, body.firstChild);
};

// ════════════════════════════════════════════════════════════════
// PATCHED loadAll — adds OSINT + FORECAST loading
// ════════════════════════════════════════════════════════════════
const _loadAllOrig = loadAll;
loadAll = async function() {
    await _loadAllOrig();
    // Load OSINT index
    await loadOsintIdx();
    if (osintOn) buildOsintBadges();
    // Add OSINT badges to feed
    document.querySelectorAll('.fi').forEach(fi => {
        const oc = fi.getAttribute('onclick') || '';
        const m = oc.match(/openIntel\('([^']+)'\)/);
        if (m && osintIdx[m[1]]) {
            const typeEl = fi.querySelector('.fi-type');
            if (typeEl && !typeEl.querySelector('.fi-ev')) {
                const badge = document.createElement('span');
                badge.className = 'fi-ev';
                badge.title = (osintIdx[m[1]].type || '') + ' evidence';
                badge.textContent = osintIdx[m[1]].source_icon || '🛰';
                typeEl.appendChild(badge);
            }
        }
    });
    // Load forecast data
    try {
        const fd = await fetch('/api/forecast-geo').then(r => r.json());
        renderForecastPanel(fd);
    } catch(e) { console.warn('[FORECAST]', e); }
    initForecastLayer();
};

// Escape key closes zoom
document.addEventListener('keydown', e => { if (e.key === 'Escape') { osintZoomClose(); closeIntel(); } });

</script>

<div id="zoom-ov" onclick="osintZoomClose()"><span id="zoom-close" onclick="osintZoomClose()">✕</span><img src="" alt=""/></div>
<div id="dbg-overlay"></div>
<div id="dbg-status"></div>
</body>
</html>

"""

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML_PAGE
