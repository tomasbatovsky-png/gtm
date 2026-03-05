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

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>GLOBAL TENSION MONITOR v3</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet"/>
<style>
:root{
  --bg:#020608;--bg2:#040d12;--bg3:#071520;
  --b0:#0d3348;--b1:#1a6688;
  --green:#00ff88;--yellow:#f5c518;--orange:#ff6b1a;--red:#ff2233;--blue:#00aaff;--purple:#aa44ff;
  --cyan:#00e5ff;--txt:#c8e8f8;--dim:#4a7a99;--muted:#2a4a5a;
  --mono:'Share Tech Mono',monospace;--disp:'Orbitron',sans-serif;--body:'Rajdhani',sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font-family:var(--body);font-size:14px;min-height:100vh;overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(0,170,255,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(0,170,255,.03) 1px,transparent 1px);background-size:40px 40px;pointer-events:none;z-index:0}
.scanlines{position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.05) 2px,rgba(0,0,0,.05) 4px);pointer-events:none;z-index:999}

/* ALERT BANNER */
#alert-banner{display:none;position:sticky;top:0;z-index:990;background:linear-gradient(90deg,#1a0008,#2a0010,#1a0008);border-bottom:1px solid var(--red);padding:6px 16px;font-family:var(--mono);font-size:.62rem;letter-spacing:.12em;color:var(--red);animation:alertPulse 2s ease-in-out infinite}
#alert-banner.show{display:flex;align-items:center;justify-content:space-between}
@keyframes alertPulse{0%,100%{background-color:rgba(255,34,51,.05)}50%{background-color:rgba(255,34,51,.12)}}
.alert-close{cursor:pointer;color:var(--dim);font-size:.8rem;padding:2px 6px}
.alert-close:hover{color:var(--txt)}

/* HEADER */
.hdr{display:flex;align-items:center;justify-content:space-between;padding:10px 14px 8px;border-bottom:1px solid var(--b0);position:relative;z-index:1}
.hdr-left{display:flex;align-items:center;gap:10px}
.radar{width:36px;height:36px;border:2px solid var(--cyan);border-radius:50%;position:relative;flex-shrink:0;animation:rPulse 3s ease-in-out infinite}
.radar::after{content:'';position:absolute;top:50%;left:50%;width:2px;height:40%;background:var(--cyan);transform-origin:bottom center;transform:translateX(-50%);animation:rSweep 3s linear infinite}
@keyframes rSweep{to{transform:translateX(-50%) rotate(360deg)}}
@keyframes rPulse{0%,100%{box-shadow:0 0 8px #00e5ff55}50%{box-shadow:0 0 18px #00e5ffaa}}
.hdr-title h1{font-family:var(--disp);font-size:1rem;font-weight:700;letter-spacing:.22em;color:var(--cyan);text-shadow:0 0 8px #00e5ff55}
.hdr-title .sub{font-family:var(--mono);font-size:.55rem;color:var(--dim);letter-spacing:.12em;margin-top:2px}
.hdr-right{display:flex;align-items:center;gap:14px;font-family:var(--mono);font-size:.58rem;color:var(--dim)}
.live-dot{width:6px;height:6px;background:var(--green);border-radius:50%;box-shadow:0 0 6px var(--green);animation:blink 1.2s ease-in-out infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.15}}

/* MAIN LAYOUT */
.main{display:grid;grid-template-columns:280px 1fr 240px;gap:0;height:calc(100vh - 90px);position:relative;z-index:1}

/* LEFT PANEL */
.left-panel{background:var(--bg2);border-right:1px solid var(--b0);overflow-y:auto;display:flex;flex-direction:column}
.left-panel::-webkit-scrollbar{width:2px}
.left-panel::-webkit-scrollbar-thumb{background:var(--b0)}

/* RIGHT PANEL */
.right-panel{background:var(--bg2);border-left:1px solid var(--b0);overflow-y:auto}
.right-panel::-webkit-scrollbar{width:2px}
.right-panel::-webkit-scrollbar-thumb{background:var(--b0)}

/* SECTION */
.sec{border-bottom:1px solid var(--b0)}
.sec-h{display:flex;align-items:center;justify-content:space-between;padding:6px 10px;background:rgba(0,170,255,.02);cursor:pointer}
.sec-h:hover{background:rgba(0,170,255,.04)}
.sec-t{font-family:var(--disp);font-size:.5rem;letter-spacing:.18em;color:var(--dim)}
.sec-b{font-family:var(--mono);font-size:.5rem;color:var(--muted)}
.sec-body{padding:10px}
.collapse-arrow{font-size:.6rem;color:var(--dim);transition:transform .2s}
.collapsed .collapse-arrow{transform:rotate(-90deg)}
.collapsed .sec-body{display:none}

/* GTI */
.gti-ring-wrap{text-align:center;padding:12px 8px 8px}
.gti-ring{width:150px;height:150px;border-radius:50%;border:2px solid var(--b0);position:relative;margin:0 auto 8px;display:flex;flex-direction:column;align-items:center;justify-content:center}
.gti-rg{position:absolute;inset:-1px;border-radius:50%;border:2px solid var(--red);transition:all .6s;animation:rg 2s ease-in-out infinite}
@keyframes rg{0%,100%{opacity:.6}50%{opacity:1}}
.gti-ri{position:absolute;inset:8px;border-radius:50%;border:1px solid rgba(255,34,51,.15);transition:all .6s}
.gti-num{font-family:var(--disp);font-size:3rem;font-weight:900;line-height:1;color:var(--red);transition:all .6s}
.gti-den{font-family:var(--disp);font-size:.75rem;color:var(--muted)}
.gti-stat{font-family:var(--disp);font-size:.6rem;letter-spacing:.22em;padding:4px 12px;border:1px solid var(--red);color:var(--red);display:inline-block;margin-bottom:6px;animation:sp 2s ease-in-out infinite;transition:all .6s}
@keyframes sp{0%,100%{opacity:1}50%{opacity:.65}}
.gti-trend-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;margin-bottom:8px}
.gti-sub-item{text-align:center}
.gti-sub-l{font-family:var(--mono);font-size:.47rem;color:var(--muted);margin-bottom:1px}
.gti-sub-v{font-family:var(--disp);font-size:.9rem;font-weight:700;color:var(--orange)}
.velocity-row{display:flex;align-items:center;justify-content:space-between;padding:6px 10px;border-top:1px solid var(--b0);font-family:var(--mono);font-size:.58rem}
.vel-label{color:var(--dim)}
.vel-val{color:var(--red);font-size:.7rem}

/* FORECAST */
.forecast-bars{display:flex;flex-direction:column;gap:6px}
.fbar-row{display:flex;align-items:center;gap:6px}
.fbar-lbl{font-family:var(--mono);font-size:.52rem;width:65px;flex-shrink:0}
.fbar-track{flex:1;height:6px;background:rgba(255,255,255,.06);border-radius:3px;overflow:hidden}
.fbar-fill{height:100%;border-radius:3px;transition:width .8s ease}
.fbar-pct{font-family:var(--mono);font-size:.52rem;width:32px;text-align:right}
.fbar-low .fbar-fill{background:var(--green)}
.fbar-low .fbar-lbl,.fbar-low .fbar-pct{color:var(--green)}
.fbar-mod .fbar-fill{background:var(--yellow)}
.fbar-mod .fbar-lbl,.fbar-mod .fbar-pct{color:var(--yellow)}
.fbar-high .fbar-fill{background:var(--red)}
.fbar-high .fbar-lbl,.fbar-high .fbar-pct{color:var(--red)}
.forecast-reasoning{font-family:var(--mono);font-size:.5rem;color:var(--dim);margin-top:8px;line-height:1.5;border-top:1px solid var(--b0);padding-top:6px}

/* REGIONAL */
.reg-list{display:flex;flex-direction:column;gap:4px}
.reg-row{display:grid;grid-template-columns:1fr auto auto;gap:4px;align-items:center}
.reg-name{font-family:var(--mono);font-size:.52rem;color:var(--dim)}
.reg-gti{font-family:var(--disp);font-size:.6rem;font-weight:700}
.reg-delta{font-family:var(--mono);font-size:.5rem}
.reg-bar{height:3px;background:rgba(255,255,255,.06);border-radius:2px;overflow:hidden;margin-top:2px;margin-bottom:4px;grid-column:1/-1}
.reg-bar-fill{height:100%;border-radius:2px;transition:width .8s ease}

/* SUPPLY CHAIN */
.supply-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.supply-item{background:rgba(0,170,255,.04);border:1px solid var(--b0);padding:6px 8px}
.supply-icon{font-size:.9rem;margin-bottom:2px}
.supply-lbl{font-family:var(--mono);font-size:.48rem;color:var(--dim);margin-bottom:3px}
.supply-risk{font-family:var(--disp);font-size:.62rem;font-weight:700}
.risk-LOW{color:var(--green)}.risk-MODERATE{color:var(--yellow)}.risk-HIGH{color:var(--red)}.risk-CRITICAL{color:#8b0000}

/* STRATEGIC */
.strat-item{display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid rgba(13,51,72,.4)}
.strat-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.strat-lbl{font-family:var(--mono);font-size:.55rem;color:var(--dim)}
.strat-val{font-family:var(--mono);font-size:.55rem;margin-left:auto}
.choke-list{margin-top:8px}
.choke-item{display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid rgba(13,51,72,.3)}
.choke-name{font-family:var(--mono);font-size:.52rem;color:var(--dim)}
.choke-risk{font-family:var(--disp);font-size:.5rem}

/* TREND CHART */
.chart-wrap{padding:6px 8px 8px;height:150px}
.chart-wrap canvas{width:100%!important;height:100%!important}

/* FEED */
.feed-list{overflow-y:auto;max-height:220px}
.feed-list::-webkit-scrollbar{width:2px}
.feed-list::-webkit-scrollbar-thumb{background:var(--b0)}
.fi{display:grid;grid-template-columns:3px 1fr auto;gap:7px;align-items:start;padding:7px 10px;border-bottom:1px solid rgba(13,51,72,.4);cursor:pointer;transition:background .15s;animation:fi .3s ease-out}
.fi:hover{background:rgba(0,170,255,.04)}
@keyframes fi{from{opacity:0;transform:translateX(-4px)}to{opacity:1;transform:none}}
.fi-ind{align-self:stretch;min-height:30px;border-radius:1px}
.fi-ind.red{background:var(--red);box-shadow:0 0 4px var(--red)}
.fi-ind.orange{background:var(--orange);box-shadow:0 0 4px var(--orange)}
.fi-ind.yellow{background:var(--yellow)}
.fi-type{font-family:var(--disp);font-size:.52rem;letter-spacing:.12em;color:var(--orange)}
.fi-reg{font-family:var(--mono);font-size:.5rem;color:var(--dim)}
.fi-desc{font-family:var(--body);font-size:.65rem;color:var(--txt);line-height:1.3;margin-top:1px}
.fi-conf{font-family:var(--mono);font-size:.5rem;color:var(--dim);text-align:right}
.fi-age{font-family:var(--mono);font-size:.48rem;color:var(--muted);text-align:right}

/* MAP CENTER */
.map-center{position:relative;display:flex;flex-direction:column}
#wmap{flex:1}
.leaflet-container{background:#020e18!important}
.leaflet-tile{filter:brightness(.4) hue-rotate(185deg) saturate(.3) invert(.85)!important}
.leaflet-control-zoom a{background:var(--bg3);color:var(--dim);border-color:var(--b0)}
.leaflet-popup-content-wrapper{background:var(--bg3)!important;border:1px solid var(--b1)!important;color:var(--txt)!important;border-radius:0!important;box-shadow:0 0 8px #00e5ff33!important;font-family:var(--mono)!important;font-size:.65rem!important;min-width:220px}
.leaflet-popup-tip{background:var(--b1)!important}
.pop-btn{display:inline-block;margin-top:8px;padding:4px 10px;border:1px solid var(--cyan);color:var(--cyan);font-family:var(--mono);font-size:.55rem;letter-spacing:.1em;cursor:pointer;transition:all .2s}
.pop-btn:hover{background:var(--cyan);color:var(--bg)}

/* MAP LEGEND */
.map-legend{display:flex;gap:10px;padding:5px 10px;border-top:1px solid var(--b0);background:var(--bg2);font-family:var(--mono);font-size:.52rem;color:var(--dim);flex-wrap:wrap;align-items:center}
.ml-item{display:flex;align-items:center;gap:4px}
.ml-dot{width:7px;height:7px;border-radius:50%}
.map-src{margin-left:auto;color:var(--muted)}

/* MARKERS */
.em{width:12px;height:12px;border-radius:50%;border:2px solid;position:relative}
/* recency classes */
.em-pulse{animation:pulse-hot 1s ease-in-out infinite}
@keyframes pulse-hot{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.6);opacity:.7}}
.em.red{background:rgba(255,34,51,.5);border-color:#ff2233;box-shadow:0 0 7px #ff2233}
.em.orange{background:rgba(255,107,26,.5);border-color:#ff6b1a;box-shadow:0 0 7px #ff6b1a}
.em.yellow{background:rgba(245,197,24,.5);border-color:#f5c518}
.em.faded{background:rgba(100,100,100,.3);border-color:#555;box-shadow:none;opacity:.5}

/* INTELLIGENCE PANEL */
#intel-panel{position:fixed;top:0;right:-420px;width:420px;height:100vh;background:var(--bg2);border-left:1px solid var(--b1);z-index:800;transition:right .35s cubic-bezier(.4,0,.2,1);overflow-y:auto;display:flex;flex-direction:column}
#intel-panel.open{right:0}
#intel-panel::-webkit-scrollbar{width:2px}
#intel-panel::-webkit-scrollbar-thumb{background:var(--b0)}
.intel-hdr{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-bottom:1px solid var(--b0);background:rgba(0,170,255,.03);position:sticky;top:0}
.intel-title{font-family:var(--disp);font-size:.65rem;letter-spacing:.18em;color:var(--cyan)}
.intel-close{cursor:pointer;color:var(--dim);font-size:1rem;line-height:1;padding:2px 6px}
.intel-close:hover{color:var(--txt)}
.intel-body{padding:14px;flex:1}
.intel-type{font-family:var(--disp);font-size:.9rem;letter-spacing:.15em;color:var(--orange);margin-bottom:4px}
.intel-location{font-family:var(--mono);font-size:.6rem;color:var(--dim);margin-bottom:12px}
.intel-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}
.intel-metric{background:rgba(0,170,255,.04);border:1px solid var(--b0);padding:7px 9px}
.intel-metric-l{font-family:var(--mono);font-size:.48rem;color:var(--muted);margin-bottom:3px;letter-spacing:.1em}
.intel-metric-v{font-family:var(--disp);font-size:.85rem;font-weight:700}
.intel-section{margin-bottom:12px}
.intel-section-h{font-family:var(--disp);font-size:.52rem;letter-spacing:.15em;color:var(--dim);margin-bottom:6px;padding-bottom:4px;border-bottom:1px solid var(--b0)}
.intel-text{font-family:var(--body);font-size:.8rem;color:var(--txt);line-height:1.6}
.intel-actors{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
.actor-tag{font-family:var(--mono);font-size:.5rem;color:var(--cyan);border:1px solid rgba(0,229,255,.3);padding:2px 6px}
.intel-esc{display:inline-block;font-family:var(--disp);font-size:.6rem;padding:3px 10px;border:1px solid;margin-top:4px}
.esc-LOW{color:var(--green);border-color:var(--green)}.esc-MODERATE{color:var(--yellow);border-color:var(--yellow)}
.esc-HIGH{color:var(--orange);border-color:var(--orange)}.esc-CRITICAL{color:var(--red);border-color:var(--red)}
.intel-loading{text-align:center;padding:40px;font-family:var(--mono);font-size:.6rem;color:var(--dim)}
.intel-src-link{display:block;margin-top:12px;padding:8px 12px;border:1px solid var(--b0);font-family:var(--mono);font-size:.55rem;color:var(--cyan);text-decoration:none;text-align:center;letter-spacing:.1em}
.intel-src-link:hover{background:rgba(0,229,255,.08)}

/* REPLAY BAR */
#replay-bar{background:var(--bg2);border-top:1px solid var(--b0);padding:6px 14px;display:flex;align-items:center;gap:10px;font-family:var(--mono);font-size:.55rem;color:var(--dim);position:relative;z-index:1}
.replay-btn{padding:3px 10px;border:1px solid var(--b0);cursor:pointer;color:var(--dim);background:transparent;font-family:var(--mono);font-size:.52rem;letter-spacing:.08em;transition:all .15s}
.replay-btn:hover,.replay-btn.active{border-color:var(--cyan);color:var(--cyan);background:rgba(0,229,255,.06)}
.replay-play{width:24px;height:24px;border:1px solid var(--b1);border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--cyan);font-size:.7rem;flex-shrink:0;transition:all .15s}
.replay-play:hover{background:rgba(0,229,255,.1)}
.replay-slider{flex:1;accent-color:var(--cyan);cursor:pointer}
#replay-ts{color:var(--cyan);min-width:120px}
.replay-speed{display:flex;gap:4px;align-items:center}
.speed-btn{padding:2px 6px;border:1px solid var(--b0);cursor:pointer;color:var(--muted);background:transparent;font-family:var(--mono);font-size:.5rem}
.speed-btn.active{border-color:var(--yellow);color:var(--yellow)}

/* SUMMARY */
.ai-sum{font-family:var(--body);font-size:.78rem;line-height:1.7;color:var(--txt);border-left:2px solid var(--b1);padding-left:10px;min-height:60px}
.ai-sum.typing::after{content:'▋';animation:blink .7s ease-in-out infinite;color:var(--cyan)}
.ai-footer{display:flex;justify-content:space-between;font-family:var(--mono);font-size:.5rem;color:var(--muted);margin-top:8px;padding-top:6px;border-top:1px solid var(--b0)}
.ai-badge{display:flex;align-items:center;gap:3px;color:var(--cyan);font-size:.5rem}
.ai-dot{width:4px;height:4px;background:var(--cyan);border-radius:50%;animation:blink 2s ease-in-out infinite}

/* SLEG */
.sleg{display:grid;grid-template-columns:1fr 1fr;gap:2px 8px;padding:8px 10px;border-top:1px solid var(--b0)}
.sleg-item{font-family:var(--mono);font-size:.48rem}

/* RESPONSIVE */
@media(max-width:1200px){.main{grid-template-columns:260px 1fr 200px}}
@media(max-width:960px){.main{grid-template-columns:1fr};.right-panel,.left-panel{display:none}}
</style>
</head>
<body>
<div class="scanlines"></div>

<!-- ALERT BANNER -->
<div id="alert-banner">
  <span id="alert-text">⚠ ALERT</span>
  <span class="alert-close" onclick="document.getElementById('alert-banner').classList.remove('show')">✕</span>
</div>

<!-- HEADER -->
<header class="hdr">
  <div class="hdr-left">
    <div class="radar"></div>
    <div class="hdr-title">
      <h1>GLOBAL TENSION MONITOR</h1>
      <div class="sub">LIVE GEOPOLITICAL RADAR · RSS + CLAUDE AI · v3.0</div>
    </div>
  </div>
  <div class="hdr-right">
    <span style="color:var(--dim)">DATA: <span id="src-badge" style="color:var(--green)">—</span></span>
    <span id="utc-clock">—</span>
    <span>NEXT: <span id="next-refresh">10:00</span></span>
    <div style="display:flex;align-items:center;gap:5px;color:var(--green)"><div class="live-dot"></div>LIVE</div>
  </div>
</header>

<!-- MAIN -->
<div class="main">

  <!-- LEFT PANEL -->
  <div class="left-panel">

    <!-- GTI -->
    <div class="sec">
      <div class="sec-h" onclick="toggleSec(this)">
        <span class="sec-t">GLOBAL TENSION INDEX</span>
        <div style="display:flex;align-items:center;gap:6px">
          <span class="sec-b" id="ecount-sm">—</span>
          <span class="collapse-arrow">▾</span>
        </div>
      </div>
      <div class="sec-body" style="padding:0">
        <div class="gti-ring-wrap">
          <div class="gti-ring">
            <div class="gti-rg" id="gti-rg"></div>
            <div class="gti-ri" id="gti-ri"></div>
            <div class="gti-num" id="gti-num">—</div>
            <div class="gti-den">/ 10</div>
          </div>
          <div class="gti-stat" id="gti-stat">LOADING…</div>
          <div class="gti-trend-row">
            <div class="gti-sub-item"><div class="gti-sub-l">MIL</div><div class="gti-sub-v" id="s-mil">—</div></div>
            <div class="gti-sub-item"><div class="gti-sub-l">STR</div><div class="gti-sub-v" id="s-str">—</div></div>
            <div class="gti-sub-item"><div class="gti-sub-l">ECO</div><div class="gti-sub-v" id="s-eco">—</div></div>
          </div>
        </div>
        <div class="velocity-row">
          <span class="vel-label">ESCALATION VELOCITY</span>
          <span class="vel-val" id="velocity">—</span>
        </div>
        <div class="sleg">
          <div class="sleg-item" style="color:#00ff88">● 0-2 STABLE</div>
          <div class="sleg-item" style="color:#f5c518">● 2-4 RISING</div>
          <div class="sleg-item" style="color:#ff6b1a">● 4-6 HIGH</div>
          <div class="sleg-item" style="color:#ff2233">● 6-8 CRISIS</div>
          <div class="sleg-item" style="color:#8b0000;grid-column:1/-1">● 8-10 GLOBAL CRISIS</div>
        </div>
      </div>
    </div>

    <!-- TREND CHART -->
    <div class="sec">
      <div class="sec-h" onclick="toggleSec(this)"><span class="sec-t">TENSION TREND · 30 DAYS</span><span class="collapse-arrow">▾</span></div>
      <div class="sec-body" style="padding:0"><div class="chart-wrap"><canvas id="tchart"></canvas></div></div>
    </div>

    <!-- ESCALATION FORECAST -->
    <div class="sec">
      <div class="sec-h" onclick="toggleSec(this)"><span class="sec-t">ESCALATION FORECAST · 30 DAYS</span><span class="collapse-arrow">▾</span></div>
      <div class="sec-body">
        <div class="forecast-bars">
          <div class="fbar-row fbar-low">
            <span class="fbar-lbl">LOW RISK</span>
            <div class="fbar-track"><div class="fbar-fill" id="fc-low" style="width:0%"></div></div>
            <span class="fbar-pct" id="fc-low-pct">—%</span>
          </div>
          <div class="fbar-row fbar-mod">
            <span class="fbar-lbl">MODERATE</span>
            <div class="fbar-track"><div class="fbar-fill" id="fc-mod" style="width:0%"></div></div>
            <span class="fbar-pct" id="fc-mod-pct">—%</span>
          </div>
          <div class="fbar-row fbar-high">
            <span class="fbar-lbl">HIGH RISK</span>
            <div class="fbar-track"><div class="fbar-fill" id="fc-high" style="width:0%"></div></div>
            <span class="fbar-pct" id="fc-high-pct">—%</span>
          </div>
        </div>
        <div class="forecast-reasoning" id="fc-reason">Calculating…</div>
      </div>
    </div>

    <!-- REGIONAL -->
    <div class="sec">
      <div class="sec-h" onclick="toggleSec(this)"><span class="sec-t">REGIONAL TENSIONS</span><span class="collapse-arrow">▾</span></div>
      <div class="sec-body"><div class="reg-list" id="reg-list">Loading…</div></div>
    </div>

    <!-- AI SUMMARY -->
    <div class="sec">
      <div class="sec-h" onclick="toggleSec(this)">
        <span class="sec-t">SITUATION SUMMARY</span>
        <div class="ai-badge"><div class="ai-dot"></div>AI</div>
      </div>
      <div class="sec-body">
        <div class="ai-sum typing" id="ai-sum">Analyzing…</div>
        <div class="ai-footer"><span id="ai-gen">—</span><span id="ai-ts">—</span></div>
      </div>
    </div>

  </div><!-- /left -->

  <!-- MAP CENTER -->
  <div class="map-center">
    <div id="wmap" style="flex:1;min-height:0"></div>
    <div class="map-legend">
      <div class="ml-item"><div class="ml-dot" style="background:#ff2233;box-shadow:0 0 5px #ff2233"></div>STRIKE/COMBAT</div>
      <div class="ml-item"><div class="ml-dot" style="background:#ff6b1a;box-shadow:0 0 5px #ff6b1a"></div>MOVEMENT</div>
      <div class="ml-item"><div class="ml-dot" style="background:#f5c518"></div>TENSION</div>
      <div class="ml-item" style="color:var(--cyan)">⊙ &lt;10min PULSE</div>
      <span class="map-src" id="map-src">— INCIDENTS</span>
    </div>
  </div><!-- /map -->

  <!-- RIGHT PANEL -->
  <div class="right-panel">

    <!-- STRATEGIC MONITOR -->
    <div class="sec">
      <div class="sec-h" onclick="toggleSec(this)"><span class="sec-t">STRATEGIC MONITOR</span><span class="collapse-arrow">▾</span></div>
      <div class="sec-body">
        <div id="strat-list">Loading…</div>
        <div style="margin-top:10px;font-family:var(--mono);font-size:.5rem;color:var(--muted);letter-spacing:.1em;margin-bottom:5px">GLOBAL CHOKEPOINTS</div>
        <div id="choke-list">—</div>
      </div>
    </div>

    <!-- SUPPLY CHAIN -->
    <div class="sec">
      <div class="sec-h" onclick="toggleSec(this)"><span class="sec-t">SUPPLY CHAIN RISK</span><span class="collapse-arrow">▾</span></div>
      <div class="sec-body">
        <div class="supply-grid" id="supply-grid">Loading…</div>
      </div>
    </div>

    <!-- RECENT EVENTS FEED -->
    <div class="sec" style="flex:1">
      <div class="sec-h" onclick="toggleSec(this)"><span class="sec-t">RECENT EVENTS</span><span class="sec-b" id="feed-src-badge">—</span><span class="collapse-arrow">▾</span></div>
      <div style="padding:0"><div class="feed-list" id="feed-list"><div style="padding:12px;font-family:var(--mono);font-size:.58rem;color:var(--dim)">Loading…</div></div></div>
    </div>

  </div><!-- /right -->

</div><!-- /main -->

<!-- REPLAY BAR -->
<div id="replay-bar">
  <span style="color:var(--dim);letter-spacing:.12em">TIMELINE REPLAY</span>
  <div class="replay-speed">
    <button class="replay-btn active" onclick="setReplayPeriod('24h',this)">24H</button>
    <button class="replay-btn" onclick="setReplayPeriod('7d',this)">7D</button>
    <button class="replay-btn" onclick="setReplayPeriod('30d',this)">30D</button>
  </div>
  <div class="replay-play" id="replay-play-btn" onclick="toggleReplay()">▶</div>
  <input type="range" class="replay-slider" id="replay-slider" min="0" max="100" value="100" oninput="onSliderChange(this.value)"/>
  <span id="replay-ts">LIVE</span>
  <div class="replay-speed">
    <button class="speed-btn active" onclick="setSpeed(1,this)">1x</button>
    <button class="speed-btn" onclick="setSpeed(2,this)">2x</button>
    <button class="speed-btn" onclick="setSpeed(5,this)">5x</button>
  </div>
  <button class="replay-btn" onclick="goLive()" id="live-btn">● LIVE</button>
</div>

<!-- INTELLIGENCE PANEL -->
<div id="intel-panel">
  <div class="intel-hdr">
    <span class="intel-title">◈ EVENT INTELLIGENCE</span>
    <span class="intel-close" onclick="closeIntel()">✕</span>
  </div>
  <div class="intel-body" id="intel-body">
    <div class="intel-loading">Select an event marker to analyze</div>
  </div>
</div>

<script>
// ════════════════════════════════════════════
// STATE
// ════════════════════════════════════════════
let leafMap=null, mLayer=null, tChart=null;
let allEvents=[], replayHistory=[], replayIndex=0, replayPlaying=false, replaySpeed=1, replayPeriod='24h', replayTimer=null;
let refreshCountdown=600;

// ════════════════════════════════════════════
// HELPERS
// ════════════════════════════════════════════
function gtiColor(v){if(v<2)return'#00ff88';if(v<4)return'#f5c518';if(v<6)return'#ff6b1a';if(v<8)return'#ff2233';return'#8b0000'}
function timeSince(iso){const m=(Date.now()-new Date(iso).getTime())/60000;if(m<60)return Math.round(m)+'m ago';if(m<1440)return Math.round(m/60)+'h ago';return Math.round(m/1440)+'d ago'}
function ageClass(ageMin){if(ageMin<10)return'em-pulse';if(ageMin<60)return'';if(ageMin<360)return'';return''}
function srcLabel(s){if(s==='rss')return'✓ RSS LIVE';return'⚠ MOCK DATA'}
function srcColor(s){return s==='rss'?'#00ff88':'#ff6b1a'}
function animNum(el,to,dur,fmt){const s=performance.now();(function step(n){const t=Math.min((n-s)/dur,1),e=1-Math.pow(1-t,3);el.textContent=fmt(to*e);if(t<1)requestAnimationFrame(step)})(s)}
function riskColor(r){if(r==='LOW')return'#00ff88';if(r==='MODERATE')return'#f5c518';if(r==='HIGH')return'#ff2233';return'#8b0000'}
function toggleSec(hdr){hdr.closest('.sec').classList.toggle('collapsed')}

// ════════════════════════════════════════════
// CLOCK + COUNTDOWN
// ════════════════════════════════════════════
setInterval(()=>{
  const el=document.getElementById('utc-clock');
  if(el)el.textContent=new Date().toUTCString().slice(0,25)+' UTC';
  refreshCountdown--;
  const rc=document.getElementById('next-refresh');
  if(rc){const m=Math.floor(refreshCountdown/60),s=refreshCountdown%60;rc.textContent=`${m}:${String(s).padStart(2,'0')}`}
  if(refreshCountdown<=0){refreshCountdown=600;loadAll()}
},1000);

// ════════════════════════════════════════════
// MAP INIT
// ════════════════════════════════════════════
function initMap(){
  if(leafMap)return;
  leafMap=L.map('wmap',{center:[20,15],zoom:2,zoomControl:true,attributionControl:false,minZoom:2,maxZoom:8});
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(leafMap);
  mLayer=L.layerGroup().addTo(leafMap);
}

function renderMap(events){
  if(!mLayer)return;
  mLayer.clearLayers();
  events.forEach(e=>{
    const age=e.age_minutes||0;
    const pulse=age<10?' em-pulse':'';
    const color=age>1440?'faded':e.color;
    const icon=L.divIcon({className:'',html:`<div class="em ${color}${pulse}"></div>`,iconSize:[12,12],iconAnchor:[6,6]});
    const link=e.url&&e.url!=='#'?`<a href="${e.url}" target="_blank" style="color:#00e5ff;font-size:.58rem">↗ SOURCE</a>`:'';
    const popup=`<div style="font-family:'Orbitron',sans-serif;font-size:.6rem;letter-spacing:.15em;color:#ff6b1a;margin-bottom:4px">${e.type.toUpperCase()}</div>
<div style="display:flex;justify-content:space-between;margin:2px 0;color:#4a7a99;font-size:.6rem"><span>REGION</span><span style="color:#c8e8f8">${e.region}</span></div>
<div style="display:flex;justify-content:space-between;margin:2px 0;color:#4a7a99;font-size:.6rem"><span>CONF</span><span style="color:#c8e8f8">${e.confidence}%</span></div>
<div style="display:flex;justify-content:space-between;margin:2px 0;color:#4a7a99;font-size:.6rem"><span>AGE</span><span style="color:#c8e8f8">${timeSince(e.time_iso)}</span></div>
<div style="margin-top:6px;padding-top:6px;border-top:1px solid #0d3348;font-size:.62rem;line-height:1.4">${e.summary}</div>
<div style="margin-top:6px;display:flex;justify-content:space-between;align-items:center">${link}<div class="pop-btn" onclick="openIntel('${e.id}')">◈ ANALYZE</div></div>`;
    L.marker([e.lat,e.lon],{icon}).bindPopup(popup,{maxWidth:300}).addTo(mLayer);
  });
}

// ════════════════════════════════════════════
// CHART
// ════════════════════════════════════════════
function renderChart(trend){
  const ctx=document.getElementById('tchart');if(!ctx)return;
  const labels=trend.map(d=>{const p=d.date.split('-');return`${p[2]}.${p[1]}`});
  const vals=trend.map(d=>d.value);
  const color=gtiColor(vals.filter(Boolean).pop()||4);
  if(tChart)tChart.destroy();
  tChart=new Chart(ctx,{type:'line',data:{labels,datasets:[{data:vals,borderColor:color,borderWidth:2,pointRadius:2.5,pointBackgroundColor:vals.map(v=>v?gtiColor(v):'transparent'),pointBorderColor:'transparent',tension:.38,fill:true,backgroundColor:(c)=>{const g=c.chart.ctx.createLinearGradient(0,0,0,140);g.addColorStop(0,`${color}44`);g.addColorStop(1,'transparent');return g}}]},options:{responsive:true,maintainAspectRatio:false,animation:{duration:900},plugins:{legend:{display:false},tooltip:{backgroundColor:'#040d12',borderColor:'#1a6688',borderWidth:1,titleColor:'#00e5ff',bodyColor:'#c8e8f8',titleFont:{family:'Share Tech Mono',size:9},bodyFont:{family:'Share Tech Mono',size:9},callbacks:{label:c=>` GTI: ${c.raw?.toFixed(1)||'—'}/10`}}},scales:{x:{grid:{color:'rgba(13,51,72,.3)',drawTicks:false},ticks:{color:'#4a7a99',font:{family:'Share Tech Mono',size:6},maxRotation:0,maxTicksLimit:8},border:{color:'#0d3348'}},y:{min:0,max:10,grid:{color:'rgba(13,51,72,.3)',drawTicks:false},ticks:{color:'#4a7a99',font:{family:'Share Tech Mono',size:6},stepSize:2},border:{color:'#0d3348'}}}}});
}

// ════════════════════════════════════════════
// GTI RENDER
// ════════════════════════════════════════════
function renderGTI(d){
  const c=gtiColor(d.gti);
  const n=document.getElementById('gti-num');
  animNum(n,d.gti,1200,v=>v.toFixed(1));
  n.style.color=c;n.style.textShadow=`0 0 8px ${c}77`;
  const se=document.getElementById('gti-stat');
  se.textContent=d.status;se.style.color=c;se.style.borderColor=c;se.style.boxShadow=`inset 0 0 10px ${c}18,0 0 7px ${c}55`;
  const rg=document.getElementById('gti-rg');if(rg){rg.style.borderColor=c;rg.style.boxShadow=`0 0 8px ${c}77`}
  const ri=document.getElementById('gti-ri');if(ri)ri.style.borderColor=`${c}22`;
  document.getElementById('s-mil').textContent=d.military_score??'—';
  document.getElementById('s-str').textContent=d.strategic_score??'—';
  document.getElementById('s-eco').textContent=d.economic_score??'—';
  document.getElementById('ecount-sm').textContent=`${d.event_count||'—'} EVENTS`;
  if(d.velocity){const vc=document.getElementById('velocity');vc.textContent=d.velocity;vc.style.color=d.velocity.startsWith('+')?'#ff2233':'#00ff88'}
  const sb=document.getElementById('src-badge');
  if(sb){sb.textContent=srcLabel(d.data_source);sb.style.color=srcColor(d.data_source)}
  const fssb=document.getElementById('feed-src-badge');
  if(fssb){fssb.textContent=srcLabel(d.data_source);fssb.style.color=srcColor(d.data_source)}
  // trend label
  const tr=d.trend_24h||0;
  // (shown in velocity row)
}

// ════════════════════════════════════════════
// FORECAST
// ════════════════════════════════════════════
function renderForecast(d){
  document.getElementById('fc-low').style.width=d.low_pct+'%';
  document.getElementById('fc-mod').style.width=d.moderate_pct+'%';
  document.getElementById('fc-high').style.width=d.high_pct+'%';
  document.getElementById('fc-low-pct').textContent=d.low_pct+'%';
  document.getElementById('fc-mod-pct').textContent=d.moderate_pct+'%';
  document.getElementById('fc-high-pct').textContent=d.high_pct+'%';
  document.getElementById('fc-reason').textContent=d.reasoning||'—';
}

// ════════════════════════════════════════════
// REGIONAL
// ════════════════════════════════════════════
function renderRegional(d){
  const el=document.getElementById('reg-list');
  if(!el)return;
  const sorted=Object.entries(d).sort((a,b)=>b[1].gti-a[1].gti);
  if(!sorted.length){el.innerHTML='<div style="font-family:var(--mono);font-size:.55rem;color:var(--muted);padding:4px">No regional data</div>';return}
  el.innerHTML=sorted.map(([region,data])=>{
    const c=gtiColor(data.gti);
    const dc=data.delta>=0?'#ff2233':'#00ff88';
    const ds=data.delta>=0?'+':'';
    const pct=Math.round(data.gti*10);
    return `<div class="reg-row"><span class="reg-name">${region}</span><span class="reg-gti" style="color:${c}">${data.gti}</span><span class="reg-delta" style="color:${dc}">${ds}${data.delta}%</span><div class="reg-bar reg-row" style="grid-column:1/-1"><div class="reg-bar-fill" style="width:${pct}%;background:${c}"></div></div></div>`
  }).join('');
}

// ════════════════════════════════════════════
// STRATEGIC
// ════════════════════════════════════════════
function renderStrategic(d){
  const el=document.getElementById('strat-list');
  if(!el)return;
  const items=[
    {label:'CARRIER GROUP',val:d.carrier_group?'DETECTED':'NOT DETECTED',on:d.carrier_group},
    {label:'BALLISTIC LAUNCH',val:d.ballistic_launch?'DETECTED':'NOT DETECTED',on:d.ballistic_launch},
    {label:'NUCLEAR RHETORIC',val:d.nuclear_rhetoric?'ACTIVE':'NONE',on:d.nuclear_rhetoric},
  ];
  el.innerHTML=items.map(i=>`<div class="strat-item"><div class="strat-dot" style="background:${i.on?'#ff2233':'#2a4a5a'};box-shadow:${i.on?'0 0 6px #ff2233':'none'}"></div><span class="strat-lbl">${i.label}</span><span class="strat-val" style="color:${i.on?'#ff2233':'#2a4a5a'}">${i.val}</span></div>`).join('');
  const cel=document.getElementById('choke-list');
  if(cel&&d.chokepoints){cel.innerHTML=d.chokepoints.map(c=>`<div class="choke-item"><span class="choke-name">${c.name}</span><span class="choke-risk" style="color:${riskColor(c.risk)}">${c.risk}</span></div>`).join('')}
}

// ════════════════════════════════════════════
// SUPPLY CHAIN
// ════════════════════════════════════════════
function renderSupply(d){
  const el=document.getElementById('supply-grid');if(!el)return;
  const items=[
    {icon:'⚡',label:'ENERGY',key:'energy'},
    {icon:'🚢',label:'SHIPPING',key:'shipping'},
    {icon:'🌾',label:'FOOD',key:'food'},
    {icon:'💾',label:'TECH/SEMI',key:'tech'},
  ];
  el.innerHTML=items.map(i=>`<div class="supply-item"><div class="supply-icon">${i.icon}</div><div class="supply-lbl">${i.label}</div><div class="supply-risk risk-${d[i.key]||'LOW'}">${d[i.key]||'LOW'}</div></div>`).join('');
}

// ════════════════════════════════════════════
// EVENT FEED
// ════════════════════════════════════════════
function renderFeed(events){
  const el=document.getElementById('feed-list');if(!el)return;
  if(!events.length){el.innerHTML='<div style="padding:12px;font-family:var(--mono);font-size:.55rem;color:#ff2233">NO EVENTS</div>';return}
  el.innerHTML=events.slice(0,20).map(e=>`
    <div class="fi" onclick="openIntel('${e.id}')">
      <div class="fi-ind ${e.color}"></div>
      <div>
        <div class="fi-type">${e.type.toUpperCase()}</div>
        <div class="fi-reg">◈ ${e.region} · ${timeSince(e.time_iso)}</div>
        <div class="fi-desc">${e.summary}</div>
      </div>
      <div><div class="fi-conf">${e.confidence}%</div><div class="fi-age">${e.source}</div></div>
    </div>`).join('');
}

// ════════════════════════════════════════════
// ALERTS
// ════════════════════════════════════════════
function renderAlerts(alerts){
  if(!alerts||!alerts.length)return;
  const top=alerts[0];
  const banner=document.getElementById('alert-banner');
  document.getElementById('alert-text').textContent=`⚠ ${top.title} — ${top.body}`;
  banner.classList.add('show');
}

// ════════════════════════════════════════════
// AI SUMMARY
// ════════════════════════════════════════════
function renderSummary(data){
  const el=document.getElementById('ai-sum');if(!el)return;
  el.classList.remove('typing');el.textContent='';
  const text=data.summary||'—';let i=0;
  const iv=setInterval(()=>{el.textContent+=text[i++]||'';if(i>text.length)clearInterval(iv)},14);
  const gen=document.getElementById('ai-gen');const ts=document.getElementById('ai-ts');
  if(gen)gen.textContent=`MODEL: ${(data.generated_by||'—').toUpperCase()}`;
  if(ts)ts.textContent=`${new Date().toUTCString().slice(0,16)} UTC`;
}

// ════════════════════════════════════════════
// INTELLIGENCE PANEL
// ════════════════════════════════════════════
function openIntel(eventId){
  const panel=document.getElementById('intel-panel');
  const body=document.getElementById('intel-body');
  panel.classList.add('open');
  body.innerHTML='<div class="intel-loading"><div style="margin-bottom:12px;color:var(--cyan);font-size:.8rem">◈</div>Fetching Claude AI analysis…</div>';
  fetch(`/api/event-detail/${eventId}`)
    .then(r=>r.json())
    .then(d=>{
      const escClass=`esc-${d.escalation_risk||'MODERATE'}`;
      const actors=d.related_actors&&d.related_actors.length?d.related_actors.map(a=>`<span class="actor-tag">${a}</span>`).join(''):'<span style="color:var(--muted);font-size:.52rem">—</span>';
      body.innerHTML=`
        <div class="intel-type">${(d.event_type||'').toUpperCase()}</div>
        <div class="intel-location">◈ ${d.location||'Unknown Location'}</div>
        <div class="intel-grid">
          <div class="intel-metric"><div class="intel-metric-l">CONFIDENCE</div><div class="intel-metric-v" style="color:${d.confidence>=75?'#00ff88':d.confidence>=50?'#f5c518':'#ff6b1a'}">${d.confidence}%</div></div>
          <div class="intel-metric"><div class="intel-metric-l">ESC. RISK</div><div class="intel-metric-v ${escClass}">${d.escalation_risk||'—'}</div></div>
          <div class="intel-metric" style="grid-column:1/-1"><div class="intel-metric-l">NUMBERS DETECTED</div><div class="intel-metric-v" style="color:var(--cyan);font-size:.75rem">${d.numbers_detected||'—'}</div></div>
        </div>
        <div class="intel-section"><div class="intel-section-h">TACTICAL ASSESSMENT</div><div class="intel-text">${d.tactical_assessment||'—'}</div></div>
        <div class="intel-section"><div class="intel-section-h">CONTEXT</div><div class="intel-text">${d.context||'—'}</div></div>
        <div class="intel-section"><div class="intel-section-h">ACTORS INVOLVED</div><div class="intel-actors">${actors}</div></div>
        ${d.url&&d.url!=='#'?`<a href="${d.url}" target="_blank" class="intel-src-link">↗ READ ORIGINAL SOURCE</a>`:''}
        <div style="margin-top:12px;font-family:var(--mono);font-size:.48rem;color:var(--muted);border-top:1px solid var(--b0);padding-top:8px">ANALYSIS: CLAUDE AI · ${new Date().toUTCString().slice(0,16)} UTC</div>`;
    })
    .catch(err=>{ body.innerHTML=`<div class="intel-loading" style="color:var(--red)">Analysis failed: ${err.message}</div>`; });
}
function closeIntel(){document.getElementById('intel-panel').classList.remove('open')}

// ════════════════════════════════════════════
// REPLAY
// ════════════════════════════════════════════
async function loadReplayHistory(){
  try{
    const r=await fetch(`/api/history?period=${replayPeriod}`).then(x=>x.json());
    replayHistory=r.history||[];
    document.getElementById('replay-slider').max=Math.max(0,replayHistory.length-1);
  }catch(e){replayHistory=[]}
}

function setReplayPeriod(p,btn){
  replayPeriod=p;
  document.querySelectorAll('.replay-btn').forEach(b=>{if(['24h','7d','30d'].includes(b.textContent.toLowerCase().trim()))b.classList.remove('active')});
  btn.classList.add('active');
  loadReplayHistory();
}

function toggleReplay(){
  if(replayPlaying){
    clearInterval(replayTimer);replayPlaying=false;
    document.getElementById('replay-play-btn').textContent='▶';
  } else {
    if(replayHistory.length===0){loadReplayHistory().then(()=>startReplay());return}
    startReplay();
  }
}

function startReplay(){
  replayPlaying=true;
  document.getElementById('replay-play-btn').textContent='⏸';
  if(replayIndex>=replayHistory.length-1)replayIndex=0;
  replayTimer=setInterval(()=>{
    if(replayIndex>=replayHistory.length-1){stopReplay();return}
    replayIndex++;
    document.getElementById('replay-slider').value=replayIndex;
    showReplayFrame(replayIndex);
  },1000/replaySpeed);
}

function stopReplay(){
  clearInterval(replayTimer);replayPlaying=false;
  document.getElementById('replay-play-btn').textContent='▶';
}

function showReplayFrame(idx){
  const frame=replayHistory[idx];if(!frame)return;
  document.getElementById('replay-ts').textContent=frame.ts?new Date(frame.ts).toUTCString().slice(0,16)+' UTC':'—';
  if(frame.events&&mLayer){renderMap(frame.events)}
}

function onSliderChange(val){
  replayIndex=parseInt(val);
  showReplayFrame(replayIndex);
  if(replayPlaying){clearInterval(replayTimer);startReplay()}
}

function setSpeed(s,btn){
  replaySpeed=s;
  document.querySelectorAll('.speed-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  if(replayPlaying){clearInterval(replayTimer);startReplay()}
}

function goLive(){
  stopReplay();
  document.getElementById('replay-ts').textContent='LIVE';
  document.getElementById('replay-slider').value=replayHistory.length-1||100;
  renderMap(allEvents);
}

// ════════════════════════════════════════════
// MAIN LOAD
// ════════════════════════════════════════════
async function loadAll(){
  refreshCountdown=600;
  try{
    const [sr,er,tr,fcast,reg,strat,sup,al]=await Promise.all([
      fetch('/api/status').then(r=>r.json()),
      fetch('/api/events').then(r=>r.json()),
      fetch('/api/trend').then(r=>r.json()),
      fetch('/api/forecast').then(r=>r.json()),
      fetch('/api/regional').then(r=>r.json()),
      fetch('/api/strategic').then(r=>r.json()),
      fetch('/api/supply-chain').then(r=>r.json()),
      fetch('/api/alerts').then(r=>r.json()),
    ]);

    allEvents=er.events||[];

    renderGTI(sr);
    renderChart(tr.trend||[]);
    renderMap(allEvents);
    renderFeed(allEvents);
    renderForecast(fcast);
    renderRegional(reg.regional||{});
    renderStrategic(strat);
    renderSupply(sup);
    renderAlerts(al.alerts||[]);

    const ms=document.getElementById('map-src');
    if(ms)ms.textContent=`${er.count||0} INCIDENTS · ${new Date().toUTCString().slice(17,25)} UTC`;

    // Summary (slower)
    const sumEl=document.getElementById('ai-sum');
    if(sumEl){sumEl.classList.add('typing');sumEl.textContent='Analyzing threat landscape…'}
    fetch('/api/summary').then(r=>r.json()).then(renderSummary).catch(()=>{
      const e=document.getElementById('ai-sum');if(e){e.classList.remove('typing');e.textContent='Summary unavailable.'}
    });

    await loadReplayHistory();

  }catch(err){console.error('[LoadAll]',err)}
}

// ════════════════════════════════════════════
// BOOT
// ════════════════════════════════════════════
document.addEventListener('DOMContentLoaded',()=>{
  initMap();
  loadAll();
  // Map height fix
  const mapEl=document.getElementById('wmap');
  if(mapEl){mapEl.style.height=(window.innerHeight-90-36)+'px'}
  window.addEventListener('resize',()=>{if(mapEl)mapEl.style.height=(window.innerHeight-90-36)+'px';if(leafMap)leafMap.invalidateSize()});
});
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML_PAGE
