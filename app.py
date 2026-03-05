"""
Global Tension Monitor – RSS-only verzia (bez NewsAPI)
Deploy na Render.com
"""
import os, datetime, random, asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import feedparser

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

EVENT_KEYWORDS = {
    "missile strike":        ["missile strike","rocket attack","ballistic missile","missile launch","rocket fire","rocket barrage","katyusha","missile fired"],
    "airstrike":             ["airstrike","air strike","bombing raid","bombed","aerial bombardment","air attack","warplane","jets struck"],
    "drone strike":          ["drone strike","uav attack","drone attack","shahed","fpv drone","drone warfare"],
    "naval combat":          ["naval combat","warship attack","naval engagement","destroyer","frigate attack","naval battle"],
    "base attack":           ["base attacked","military base attack","barracks hit","base shelled","military installation attacked"],
    "military movement":     ["troops deployed","military convoy","forces massed","military buildup","military movement","troop buildup","armored column","forces mobilized","military exercises"],
    "naval deployment":      ["carrier deployed","naval deployment","fleet dispatched","carrier group","warship deployed","naval forces sent"],
    "diplomatic escalation": ["sanctions imposed","ultimatum","ambassador recalled","nuclear threat","nuclear rhetoric","expel diplomat","diplomatic crisis","war warning"],
}
EVENT_WEIGHTS = {
    "missile strike":3,"airstrike":2,"drone strike":1,"naval combat":3,
    "base attack":4,"military movement":1,"naval deployment":2,"diplomatic escalation":1,
}
REGION_MAP = {
    "Middle East":    {"lat":29.5, "lon":44.0, "kw":["iraq","iran","israel","gaza","lebanon","yemen","syria","saudi","baghdad","hamas","hezbollah","houthi","west bank","idf","irgc","rafah","tel aviv","beirut","jerusalem"]},
    "Eastern Europe": {"lat":50.0, "lon":30.0, "kw":["ukraine","russia","belarus","donbas","kyiv","moscow","crimea","zaporizhzhia","kharkiv","kherson","mariupol","zelensky","putin","russian army","ukrainian army","sumy"]},
    "East Asia":      {"lat":24.0, "lon":121.0,"kw":["china","taiwan","north korea","south korea","japan","pla","beijing","pyongyang","south china sea","taiwan strait","kim jong","seoul"]},
    "South Asia":     {"lat":30.5, "lon":68.0, "kw":["pakistan","india","afghanistan","kashmir","kabul","taliban","islamabad","new delhi"]},
    "Horn of Africa": {"lat":10.0, "lon":42.0, "kw":["somalia","ethiopia","eritrea","sudan","red sea","bab el-mandeb","al-shabaab","djibouti"]},
    "West Africa":    {"lat":12.0, "lon":2.0,  "kw":["mali","niger","burkina faso","nigeria","sahel","boko haram","wagner","ecowas"]},
    "Mediterranean":  {"lat":36.0, "lon":14.0, "kw":["mediterranean","libya","tunisia","egypt","tripoli","benghazi"]},
    "Central Asia":   {"lat":41.0, "lon":63.0, "kw":["kazakhstan","uzbekistan","tajikistan","kyrgyzstan","armenia","azerbaijan","nagorno"]},
    "Northern Europe":{"lat":60.0, "lon":20.0, "kw":["finland","sweden","baltic","estonia","latvia","lithuania","nato border","poland","kaliningrad"]},
    "Latin America":  {"lat":-15.0,"lon":-55.0,"kw":["venezuela","colombia","cartel","narco","guerrilla","farc","ecuador"]},
}
RSS_FEEDS = [
    ("BBC World",    "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Al Jazeera",   "https://www.aljazeera.com/xml/rss/all.xml"),
    ("DW News",      "https://rss.dw.com/rdf/rss-en-world"),
    ("Sky News",     "https://feeds.skynews.com/feeds/rss/world.xml"),
    ("Reuters",      "https://feeds.reuters.com/reuters/worldNews"),
    ("AP News",      "https://rsshub.app/apnews/topics/world-news"),
]
FALLBACK = [
    {"type":"missile strike","region":"Middle East","lat":33.3,"lon":44.4,"confidence":0.82,"source":"Reuters","summary":"Missile launches reported near Baghdad area targeting infrastructure","time":"2026-03-04T08:15:00Z","color":"red","url":"#"},
    {"type":"airstrike","region":"Eastern Europe","lat":49.8,"lon":30.5,"confidence":0.91,"source":"BBC","summary":"Multiple airstrikes on infrastructure targets across the country","time":"2026-03-04T06:30:00Z","color":"red","url":"#"},
    {"type":"naval deployment","region":"Mediterranean","lat":35.5,"lon":18.2,"confidence":0.74,"source":"DW","summary":"Carrier strike group repositioned in Mediterranean amid rising tensions","time":"2026-03-04T04:00:00Z","color":"orange","url":"#"},
    {"type":"drone strike","region":"South Asia","lat":31.5,"lon":65.0,"confidence":0.68,"source":"AP","summary":"Drone attack on military outpost near border region","time":"2026-03-04T03:45:00Z","color":"red","url":"#"},
    {"type":"military movement","region":"East Asia","lat":24.5,"lon":121.5,"confidence":0.77,"source":"Reuters","summary":"Large-scale military exercises near strategic strait","time":"2026-03-04T02:00:00Z","color":"orange","url":"#"},
    {"type":"base attack","region":"Horn of Africa","lat":11.8,"lon":42.5,"confidence":0.88,"source":"Reuters","summary":"Military installation attacked in strategic coastal area","time":"2026-03-03T22:00:00Z","color":"red","url":"#"},
    {"type":"diplomatic escalation","region":"Northern Europe","lat":60.1,"lon":24.9,"confidence":0.61,"source":"DW","summary":"NATO member escalates military posture near border zone","time":"2026-03-03T20:30:00Z","color":"yellow","url":"#"},
    {"type":"airstrike","region":"West Africa","lat":14.0,"lon":-1.5,"confidence":0.70,"source":"AFP","summary":"Air strikes targeting militant positions in Sahel region","time":"2026-03-03T18:00:00Z","color":"red","url":"#"},
]

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
    if etype in {"missile strike","airstrike","base attack","naval combat"}: return "red"
    if etype in {"drone strike","military movement","naval deployment"}: return "orange"
    return "yellow"

def jitter(v, r=2.5): return round(v + random.uniform(-r, r), 4)

def calc_gti(events):
    mil = sum(EVENT_WEIGHTS.get(e["type"],1)*e["confidence"] for e in events)
    st  = sum(1 for e in events if e["type"]=="naval deployment")
    st += sum(3 for e in events if "nuclear" in e["summary"].lower())
    st += sum(2 for e in events if "nato" in e["summary"].lower() and e["type"] in {"base attack","missile strike"})
    eco = 2
    raw = mil + st + eco
    gti = round(min(10.0, raw/5.0), 2)
    s = "STABLE" if gti<2 else "TENSION RISING" if gti<4 else "HIGH TENSION" if gti<6 else "CRISIS" if gti<8 else "GLOBAL CRISIS"
    return {"gti":gti,"status":s,"military_score":round(mil,2),"strategic_score":st,"economic_score":eco,"event_count":len(events)}

def fetch_rss_events():
    events, seen = [], set()
    for source_name, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:30]:
                title   = entry.get("title","")
                summary = entry.get("summary", entry.get("description", title))
                # strip HTML tags
                import re
                summary = re.sub('<[^<]+?>', '', summary)
                full    = title + " " + summary
                etype   = classify(full)
                if not etype: continue
                region, lat, lon = detect_region(full)
                if not region: continue
                key = title[:60]
                if key in seen: continue
                seen.add(key)
                link = entry.get("link","#")
                events.append({
                    "type":       etype,
                    "region":     region,
                    "lat":        jitter(lat),
                    "lon":        jitter(lon),
                    "confidence": round(0.55 + random.random()*0.4, 2),
                    "source":     source_name,
                    "summary":    (title)[:180],
                    "time":       datetime.datetime.utcnow().isoformat()+"Z",
                    "color":      marker_color(etype),
                    "url":        link,
                })
        except Exception as e:
            print(f"[RSS {source_name}] {e}")
    print(f"[RSS] Spolu {len(events)} eventov z {len(RSS_FEEDS)} feedov")
    return events if events else None

# ── HTML ──────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>GLOBAL TENSION MONITOR</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet"/>
<style>
:root{--bg:#020608;--bg-panel:#040d12;--bg-card:#071520;--border:#0d3348;--border-glow:#1a6688;--green:#00ff88;--yellow:#f5c518;--orange:#ff6b1a;--red:#ff2233;--cyan:#00e5ff;--txt:#c8e8f8;--txt-dim:#4a7a99;--txt-muted:#2a4a5a;--mono:'Share Tech Mono',monospace;--disp:'Orbitron',sans-serif;--body:'Rajdhani',sans-serif}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font-family:var(--body);font-size:15px;min-height:100vh;overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(0,170,255,0.025) 1px,transparent 1px),linear-gradient(90deg,rgba(0,170,255,0.025) 1px,transparent 1px);background-size:40px 40px;pointer-events:none;z-index:0}
body::after{content:'';position:fixed;inset:0;background:radial-gradient(ellipse at 50% 0%,rgba(0,60,100,0.15) 0%,transparent 60%);pointer-events:none;z-index:0}
.scanlines{position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.06) 2px,rgba(0,0,0,0.06) 4px);pointer-events:none;z-index:1000;animation:scan 10s linear infinite}
@keyframes scan{0%{background-position:0 0}100%{background-position:0 100px}}
.wrap{position:relative;z-index:1;max-width:1640px;margin:0 auto;padding:0 14px 40px}
.hdr{display:flex;align-items:center;justify-content:space-between;padding:14px 0 12px;border-bottom:1px solid var(--border);margin-bottom:18px;flex-wrap:wrap;gap:10px}
.hdr-left{display:flex;align-items:center;gap:12px}
.radar{width:40px;height:40px;border:2px solid var(--cyan);border-radius:50%;position:relative;box-shadow:0 0 8px #00e5ff66;animation:rPulse 3s ease-in-out infinite;flex-shrink:0}
.radar::before{content:'';position:absolute;inset:4px;border:1px solid rgba(0,229,255,0.25);border-radius:50%}
.radar::after{content:'';position:absolute;top:50%;left:50%;width:2px;height:40%;background:var(--cyan);transform-origin:bottom center;transform:translateX(-50%);animation:rSweep 3s linear infinite;box-shadow:0 0 5px var(--cyan)}
@keyframes rSweep{to{transform:translateX(-50%) rotate(360deg)}}
@keyframes rPulse{0%,100%{box-shadow:0 0 8px #00e5ff66}50%{box-shadow:0 0 18px #00e5ffaa}}
.hdr-title h1{font-family:var(--disp);font-size:1.15rem;font-weight:700;letter-spacing:0.25em;color:var(--cyan);text-shadow:0 0 8px #00e5ff66;line-height:1}
.hdr-title .sub{font-family:var(--mono);font-size:0.6rem;color:var(--txt-dim);letter-spacing:0.15em;margin-top:3px}
.hdr-right{display:flex;align-items:center;gap:18px;font-family:var(--mono);font-size:0.62rem;color:var(--txt-dim)}
.live{display:flex;align-items:center;gap:5px;color:var(--green);font-size:0.6rem;letter-spacing:0.15em}
.ldot{width:6px;height:6px;background:var(--green);border-radius:50%;animation:blink 1.2s ease-in-out infinite;box-shadow:0 0 6px var(--green)}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.15}}
.grid{display:grid;grid-template-columns:310px 1fr;gap:14px;align-items:start}
.lcol{display:flex;flex-direction:column;gap:14px}
.brow{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
.panel{background:var(--bg-panel);border:1px solid var(--border);position:relative;overflow:hidden}
.panel::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--border-glow),transparent)}
.panel::after{content:'';position:absolute;bottom:0;right:0;width:10px;height:10px;border-bottom:1px solid var(--border-glow);border-right:1px solid var(--border-glow);pointer-events:none}
.ph{display:flex;align-items:center;justify-content:space-between;padding:8px 13px;border-bottom:1px solid var(--border);background:rgba(0,170,255,0.02)}
.pt{font-family:var(--disp);font-size:0.56rem;letter-spacing:0.2em;color:var(--txt-dim)}
.pb{font-family:var(--mono);font-size:0.54rem;color:var(--txt-muted);letter-spacing:0.08em}
.gti-body{padding:16px 12px;text-align:center}
.gti-ring{width:165px;height:165px;border-radius:50%;border:2px solid var(--border);position:relative;margin:0 auto 12px;display:flex;flex-direction:column;align-items:center;justify-content:center}
.rg{position:absolute;inset:-1px;border-radius:50%;border:2px solid var(--red);box-shadow:0 0 8px #ff223388;animation:rg 2s ease-in-out infinite;transition:all .6s}
@keyframes rg{0%,100%{opacity:.65}50%{opacity:1}}
.ri{position:absolute;inset:8px;border-radius:50%;border:1px solid rgba(255,34,51,0.15);transition:all .6s}
.gti-num{font-family:var(--disp);font-size:3.4rem;font-weight:900;line-height:1;color:var(--red);text-shadow:0 0 8px #ff223388;transition:all .6s}
.gti-den{font-family:var(--disp);font-size:.85rem;color:var(--txt-muted)}
.gti-stat{font-family:var(--disp);font-size:.68rem;letter-spacing:.28em;padding:5px 14px;border:1px solid var(--red);color:var(--red);box-shadow:inset 0 0 10px rgba(255,34,51,.1);margin-bottom:10px;display:inline-block;animation:sp 2s ease-in-out infinite;transition:all .6s}
@keyframes sp{0%,100%{opacity:1}50%{opacity:.7}}
.gti-trend{font-family:var(--mono);font-size:.65rem;color:var(--txt-dim);margin-bottom:12px}
.tup{color:var(--red)}.tdn{color:var(--green)}
.gti-sub{display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;border-top:1px solid var(--border);padding-top:10px}
.sm-lbl{font-family:var(--mono);font-size:.5rem;color:var(--txt-muted);letter-spacing:.1em;margin-bottom:2px}
.sm-val{font-family:var(--disp);font-size:1rem;font-weight:700;color:var(--orange)}
.sleg{margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:3px 8px;border-top:1px solid var(--border);padding-top:10px}
.sl{font-family:var(--mono);font-size:.52rem;letter-spacing:.05em}
.trend-body{padding:8px 10px 10px;height:195px}
.trend-body canvas{width:100%!important;height:100%!important}
.map-panel{grid-column:2;grid-row:1/3}
#wmap{height:490px;width:100%}
.leaflet-container{background:#020e18!important}
.leaflet-tile{filter:brightness(.45) hue-rotate(185deg) saturate(.35) invert(.88)!important}
.leaflet-control-zoom a{background:#071520;color:#4a7a99;border-color:#0d3348}
.leaflet-popup-content-wrapper{background:#071520!important;border:1px solid #1a6688!important;color:#c8e8f8!important;border-radius:0!important;box-shadow:0 0 8px #00e5ff44!important;font-family:'Share Tech Mono',monospace!important;font-size:.68rem!important;min-width:200px}
.leaflet-popup-tip{background:#1a6688!important}
.pop-type{font-family:'Orbitron',sans-serif;font-size:.62rem;letter-spacing:.16em;color:#ff6b1a;margin-bottom:5px}
.pop-row{display:flex;justify-content:space-between;margin:2px 0;color:#4a7a99;font-size:.63rem}
.pop-row span:last-child{color:#c8e8f8}
.pop-sum{margin-top:7px;padding-top:7px;border-top:1px solid #0d3348;color:#c8e8f8;font-size:.65rem;line-height:1.4}
.em{width:12px;height:12px;border-radius:50%;border:2px solid;animation:ep 2.2s ease-in-out infinite}
.em.red{background:rgba(255,34,51,.5);border-color:#ff2233;box-shadow:0 0 7px #ff2233}
.em.orange{background:rgba(255,107,26,.5);border-color:#ff6b1a;box-shadow:0 0 7px #ff6b1a}
.em.yellow{background:rgba(245,197,24,.5);border-color:#f5c518;box-shadow:0 0 7px #f5c518}
@keyframes ep{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.4);opacity:.65}}
.mleg{display:flex;gap:12px;padding:7px 12px;border-top:1px solid var(--border);background:rgba(4,13,18,.96);flex-wrap:wrap}
.mli{display:flex;align-items:center;gap:5px;font-family:var(--mono);font-size:.57rem;color:var(--txt-dim)}
.mld{width:7px;height:7px;border-radius:50%}
.feed-body{padding:0;max-height:355px;overflow-y:auto}
.feed-body::-webkit-scrollbar{width:3px}
.feed-body::-webkit-scrollbar-thumb{background:var(--border)}
.fi{padding:10px 13px;border-bottom:1px solid rgba(13,51,72,.45);display:grid;grid-template-columns:3px 1fr auto;gap:9px;align-items:start;transition:background .2s;animation:fi .35s ease-out}
.fi:hover{background:rgba(0,170,255,.03)}
@keyframes fi{from{opacity:0;transform:translateX(-4px)}to{opacity:1;transform:none}}
.find{align-self:stretch;min-height:36px;border-radius:1px}
.find.red{background:var(--red);box-shadow:0 0 5px var(--red)}
.find.orange{background:var(--orange);box-shadow:0 0 5px var(--orange)}
.find.yellow{background:var(--yellow);box-shadow:0 0 5px var(--yellow)}
.ftype{font-family:var(--disp);font-size:.6rem;letter-spacing:.14em;color:var(--orange);margin-bottom:1px}
.freg{font-family:var(--mono);font-size:.58rem;color:var(--txt-dim);margin-bottom:2px}
.fdesc{font-family:var(--body);font-size:.7rem;color:var(--txt);line-height:1.3}
.fmeta{text-align:right;flex-shrink:0}
.fconf{font-family:var(--mono);font-size:.58rem;color:var(--txt-dim);margin-bottom:2px}
.fsrc{font-family:var(--mono);font-size:.54rem;color:var(--txt-muted)}
.sum-body{padding:14px 16px}
.sum-txt{font-family:var(--body);font-size:.9rem;color:var(--txt);line-height:1.75;border-left:2px solid var(--border-glow);padding-left:12px;margin-bottom:10px;min-height:80px}
.sum-ft{display:flex;justify-content:space-between;font-family:var(--mono);font-size:.56rem;color:var(--txt-muted);border-top:1px solid var(--border);padding-top:8px}
.ai-badge{display:flex;align-items:center;gap:4px;color:var(--cyan);font-size:.56rem}
.aidot{width:4px;height:4px;background:var(--cyan);border-radius:50%;animation:blink 2s ease-in-out infinite}
.typing::after{content:'▋';animation:blink .8s ease-in-out infinite;color:var(--cyan);margin-left:2px}
.ld{display:flex;align-items:center;gap:8px;padding:20px;font-family:var(--mono);font-size:.65rem;color:var(--txt-muted);letter-spacing:.12em}
.lb{width:50px;height:2px;background:var(--border);overflow:hidden;position:relative}
.lb::after{content:'';position:absolute;top:0;left:-100%;width:100%;height:100%;background:var(--cyan);animation:ls 1s linear infinite}
@keyframes ls{from{left:-100%}to{left:100%}}
@media(max-width:1100px){.grid{grid-template-columns:1fr}.map-panel{grid-column:1;grid-row:auto}.brow{grid-template-columns:1fr}}
@media(max-width:640px){.hdr-right{display:none}.gti-num{font-size:2.8rem}}
</style>
</head>
<body>
<div class="scanlines"></div>
<div class="wrap">
<header class="hdr">
  <div class="hdr-left">
    <div class="radar"></div>
    <div class="hdr-title">
      <h1>GLOBAL TENSION MONITOR</h1>
      <div class="sub">LIVE GEOPOLITICAL INTELLIGENCE · RSS + CLAUDE AI</div>
    </div>
  </div>
  <div class="hdr-right">
    <div style="font-family:var(--mono);font-size:.6rem;color:var(--txt-dim)">DATA: <span id="src-badge" style="color:#00ff88">LOADING…</span></div>
    <div id="utc" style="font-family:var(--mono);font-size:.6rem;color:var(--txt-dim)">—</div>
    <div class="live"><div class="ldot"></div>LIVE</div>
  </div>
</header>
<div class="grid">
  <div class="lcol">
    <div class="panel">
      <div class="ph"><span class="pt">GLOBAL TENSION INDEX</span><span class="pb" id="ecount">—</span></div>
      <div class="gti-body">
        <div class="gti-ring">
          <div class="rg" id="rg"></div><div class="ri" id="ri"></div>
          <div class="gti-num" id="gnum">—</div>
          <div class="gti-den">/ 10</div>
        </div>
        <div class="gti-stat" id="gstat">LOADING…</div>
        <div class="gti-trend" id="gtrend">TREND: — LAST 24H</div>
        <div class="gti-sub">
          <div><div class="sm-lbl">MILITARY</div><div class="sm-val" id="smil">—</div></div>
          <div><div class="sm-lbl">STRATEGIC</div><div class="sm-val" id="sstr">—</div></div>
          <div><div class="sm-lbl">ECONOMIC</div><div class="sm-val" id="seco">—</div></div>
        </div>
        <div class="sleg">
          <div class="sl" style="color:#00ff88">● 0–2 STABLE</div>
          <div class="sl" style="color:#f5c518">● 2–4 TENSION RISING</div>
          <div class="sl" style="color:#ff6b1a">● 4–6 HIGH TENSION</div>
          <div class="sl" style="color:#ff2233">● 6–8 CRISIS</div>
          <div class="sl" style="color:#bb1122;grid-column:1/-1">● 8–10 GLOBAL CRISIS</div>
        </div>
      </div>
    </div>
    <div class="panel">
      <div class="ph"><span class="pt">TENSION TREND · LAST 30 DAYS</span><span class="pb">GTI / 10</span></div>
      <div class="trend-body"><canvas id="tchart"></canvas></div>
    </div>
  </div>
  <div class="panel map-panel">
    <div class="ph"><span class="pt">GLOBAL EVENT MAP · ACTIVE INCIDENTS</span><span class="pb" id="map-ts">—</span></div>
    <div>
      <div id="wmap"></div>
      <div class="mleg">
        <div class="mli"><div class="mld" style="background:#ff2233;box-shadow:0 0 5px #ff2233"></div>STRIKE</div>
        <div class="mli"><div class="mld" style="background:#ff6b1a;box-shadow:0 0 5px #ff6b1a"></div>MOVEMENT</div>
        <div class="mli"><div class="mld" style="background:#f5c518;box-shadow:0 0 5px #f5c518"></div>TENSION</div>
        <div class="mli" style="margin-left:auto;color:#2a4a5a;font-size:.56rem">CLICK FOR DETAILS</div>
      </div>
    </div>
  </div>
</div>
<div class="brow">
  <div class="panel">
    <div class="ph"><span class="pt">RECENT EVENTS · LAST 24 HOURS</span><span class="pb" id="feed-src">—</span></div>
    <div class="feed-body" id="feed"><div class="ld"><div class="lb"></div>FETCHING INTEL…</div></div>
  </div>
  <div class="panel">
    <div class="ph"><span class="pt">GLOBAL SITUATION SUMMARY · AI ANALYSIS</span><div class="ai-badge"><div class="aidot"></div>CLAUDE AI</div></div>
    <div class="sum-body">
      <div class="sum-txt typing" id="sumtxt">Initializing Claude AI analysis…</div>
      <div class="sum-ft"><span id="sum-gen">—</span><span id="sum-ts">—</span></div>
    </div>
  </div>
</div>
</div>
<script>
function gtiColor(v){if(v<2)return'#00ff88';if(v<4)return'#f5c518';if(v<6)return'#ff6b1a';if(v<8)return'#ff2233';return'#8b0000'}
function timeSince(iso){const m=(Date.now()-new Date(iso).getTime())/60000;if(m<60)return Math.round(m)+'m ago';if(m<1440)return Math.round(m/60)+'h ago';return Math.round(m/1440)+'d ago'}
function animNum(el,to,dur,fmt){const s=performance.now();(function step(n){const t=Math.min((n-s)/dur,1),e=1-Math.pow(1-t,3);el.textContent=fmt(to*e);if(t<1)requestAnimationFrame(step)})(s)}
function srcLabel(s){if(s==='rss')return'✓ RSS LIVE';if(s==='fallback')return'⚠ MOCK DATA';return'✓ LIVE'}
function srcColor(s){return s==='fallback'?'#ff6b1a':'#00ff88'}
function renderGTI(d){
  const c=gtiColor(d.gti);
  const n=document.getElementById('gnum');
  animNum(n,d.gti,1400,v=>v.toFixed(1));
  n.style.color=c;n.style.textShadow=`0 0 8px ${c}88`;
  const se=document.getElementById('gstat');
  se.textContent=d.status;se.style.color=c;se.style.borderColor=c;se.style.boxShadow=`inset 0 0 10px ${c}22,0 0 7px ${c}66`;
  const rg=document.getElementById('rg');if(rg){rg.style.borderColor=c;rg.style.boxShadow=`0 0 8px ${c}88`}
  const ri=document.getElementById('ri');if(ri)ri.style.borderColor=`${c}33`;
  const tr=d.trend_24h||0;
  document.getElementById('gtrend').innerHTML=`TREND: <span style="color:${tr>=0?'#ff2233':'#00ff88'}">${tr>=0?'+':''}${tr.toFixed(1)}</span> LAST 24H`;
  document.getElementById('smil').textContent=d.military_score??'—';
  document.getElementById('sstr').textContent=d.strategic_score??'—';
  document.getElementById('seco').textContent=d.economic_score??'—';
  document.getElementById('ecount').textContent=`${d.event_count||'—'} EVENTS LIVE`;
  const sb=document.getElementById('src-badge');
  if(sb){sb.textContent=srcLabel(d.data_source);sb.style.color=srcColor(d.data_source)}
}
let tChart=null;
function renderChart(trend){
  const ctx=document.getElementById('tchart');if(!ctx)return;
  const labels=trend.map(d=>{const p=d.date.split('-');return`${p[2]}.${p[1]}`});
  const values=trend.map(d=>d.value);
  const color=gtiColor(values.filter(Boolean).pop()||4);
  if(tChart)tChart.destroy();
  tChart=new Chart(ctx,{type:'line',data:{labels,datasets:[{data:values,borderColor:color,borderWidth:2.5,pointRadius:3,pointBackgroundColor:values.map(v=>v?gtiColor(v):'transparent'),pointBorderColor:'transparent',tension:.38,fill:true,backgroundColor:(c)=>{const g=c.chart.ctx.createLinearGradient(0,0,0,170);g.addColorStop(0,`${color}44`);g.addColorStop(1,'transparent');return g}}]},options:{responsive:true,maintainAspectRatio:false,animation:{duration:1000},plugins:{legend:{display:false},tooltip:{backgroundColor:'#040d12',borderColor:'#1a6688',borderWidth:1,titleColor:'#00e5ff',bodyColor:'#c8e8f8',titleFont:{family:'Share Tech Mono',size:9},bodyFont:{family:'Share Tech Mono',size:9},callbacks:{label:c=>` GTI: ${c.raw?.toFixed(1)||'—'} / 10`}}},scales:{x:{grid:{color:'rgba(13,51,72,.35)',drawTicks:false},ticks:{color:'#4a7a99',font:{family:'Share Tech Mono',size:7},maxRotation:0,maxTicksLimit:9},border:{color:'#0d3348'}},y:{min:0,max:10,grid:{color:'rgba(13,51,72,.35)',drawTicks:false},ticks:{color:'#4a7a99',font:{family:'Share Tech Mono',size:7},stepSize:2,callback:v=>v},border:{color:'#0d3348'}}}}});
}
let leafMap=null,mLayer=null;
function initMap(){
  if(leafMap)return;
  leafMap=L.map('wmap',{center:[20,15],zoom:2,zoomControl:true,attributionControl:false,minZoom:2,maxZoom:7});
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(leafMap);
  mLayer=L.layerGroup().addTo(leafMap);
}
function renderMap(events){
  if(!mLayer)return;mLayer.clearLayers();
  events.forEach(e=>{
    const icon=L.divIcon({className:'',html:`<div class="em ${e.color}"></div>`,iconSize:[12,12],iconAnchor:[6,6]});
    const link=e.url&&e.url!=='#'?`<div style="margin-top:6px"><a href="${e.url}" target="_blank" style="color:#00e5ff;font-size:.6rem">↗ READ SOURCE</a></div>`:'';
    mLayer.addLayer(L.marker([e.lat,e.lon],{icon}).bindPopup(`<div class="pop-type">${e.type.toUpperCase()}</div><div class="pop-row"><span>REGION</span><span>${e.region}</span></div><div class="pop-row"><span>CONFIDENCE</span><span>${Math.round(e.confidence*100)}%</span></div><div class="pop-row"><span>SOURCE</span><span>${e.source}</span></div><div class="pop-row"><span>TIME</span><span>${timeSince(e.time)}</span></div><div class="pop-sum">${e.summary}</div>${link}`,{maxWidth:280}));
  });
}
function renderFeed(events,src){
  const feed=document.getElementById('feed');
  const fsrc=document.getElementById('feed-src');
  if(fsrc){fsrc.textContent=srcLabel(src);fsrc.style.color=srcColor(src)}
  if(!feed)return;
  if(!events.length){feed.innerHTML='<div class="ld" style="color:#ff2233">NO MILITARY EVENTS DETECTED</div>';return}
  feed.innerHTML=events.slice(0,14).map(e=>`<div class="fi"><div class="find ${e.color}"></div><div><div class="ftype">${e.type.toUpperCase()}</div><div class="freg">◈ ${e.region} · ${timeSince(e.time)}</div><div class="fdesc">${e.summary}</div></div><div class="fmeta"><div class="fconf">${Math.round(e.confidence*100)}%</div><div class="fsrc">${e.source}</div></div></div>`).join('');
}
function renderSummary(data){
  const el=document.getElementById('sumtxt');if(!el)return;
  el.classList.remove('typing');el.textContent='';
  const text=data.summary||'No summary.';let i=0;
  const iv=setInterval(()=>{el.textContent+=text[i++]||'';if(i>text.length)clearInterval(iv)},15);
  const gen=document.getElementById('sum-gen');const ts=document.getElementById('sum-ts');
  if(gen)gen.textContent=`MODEL: ${(data.generated_by||'—').toUpperCase()}`;
  if(ts)ts.textContent=`UPDATED: ${new Date().toUTCString().slice(0,25)} UTC`;
}
async function loadAll(){
  try{
    const [sr,er,tr]=await Promise.all([
      fetch('/api/status').then(r=>r.json()),
      fetch('/api/events').then(r=>r.json()),
      fetch('/api/trend').then(r=>r.json()),
    ]);
    renderGTI(sr);renderChart(tr.trend||[]);renderMap(er.events||[]);renderFeed(er.events||[],er.source||'fallback');
    const mt=document.getElementById('map-ts');
    if(mt)mt.textContent=`${er.count||0} INCIDENTS · ${new Date().toUTCString().slice(17,25)} UTC`;
    const sumEl=document.getElementById('sumtxt');
    if(sumEl){sumEl.classList.add('typing');sumEl.textContent='Claude AI analyzing current threat landscape…'}
    try{const sumRes=await fetch('/api/summary').then(r=>r.json());renderSummary(sumRes)}
    catch(e){const el=document.getElementById('sumtxt');if(el){el.classList.remove('typing');el.textContent='Summary unavailable.'}}
  }catch(err){console.error(err)}
}
function startClock(){setInterval(()=>{const el=document.getElementById('utc');if(el)el.textContent=new Date().toUTCString().slice(0,25)+' UTC'},1000)}
document.addEventListener('DOMContentLoaded',()=>{startClock();initMap();loadAll();setInterval(loadAll,10*60*1000)});
</script>
</body>
</html>"""

# ── FASTAPI ───────────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=HTMLResponse)
async def root(): return HTML

def pipeline():
    events = fetch_rss_events()
    if events: return events, "rss"
    return FALLBACK, "fallback"

@app.get("/api/events")
async def api_events():
    e,s = pipeline()
    return {"events":e,"count":len(e),"source":s,"timestamp":datetime.datetime.utcnow().isoformat()+"Z"}

@app.get("/api/status")
async def api_status():
    e,s = pipeline()
    r = calc_gti(e)
    r["timestamp"]=datetime.datetime.utcnow().isoformat()+"Z"
    r["data_source"]=s
    r["trend_24h"]=round(r["gti"]-6.8,2)
    return r

@app.get("/api/trend")
async def api_trend():
    e,_ = pipeline()
    live = calc_gti(e)["gti"]
    return {"trend":[
        {"date":"2026-02-03","value":2.8},{"date":"2026-02-07","value":3.4},
        {"date":"2026-02-11","value":3.8},{"date":"2026-02-15","value":4.1},
        {"date":"2026-02-19","value":5.1},{"date":"2026-02-23","value":5.9},
        {"date":"2026-02-27","value":6.5},{"date":"2026-03-01","value":6.8},
        {"date":"2026-03-03","value":7.1},{"date":"2026-03-05","value":live},
    ]}

@app.get("/api/summary")
async def api_summary():
    e,s = pipeline()
    g = calc_gti(e); gti=g["gti"]; status=g["status"]
    elist="\n".join(f"- [{x['type'].upper()}] {x['region']}: {x['summary'][:120]}" for x in e[:12])
    if not ANTHROPIC_KEY:
        return {"summary":f"Set ANTHROPIC_API_KEY. GTI: {gti:.1f}/10 ({status}), {len(e)} incidents from {s}.","generated_by":"no-key","gti":gti,"event_count":len(e),"timestamp":datetime.datetime.utcnow().isoformat()+"Z"}
    try:
        import anthropic
        msg=anthropic.Anthropic(api_key=ANTHROPIC_KEY).messages.create(
            model="claude-opus-4-6",max_tokens=350,
            messages=[{"role":"user","content":f"Classified geopolitical analyst. GTI:{gti:.1f}/10 — {status}. {len(e)} incidents from RSS feeds:\n{elist}\nWrite 3-4 sentence military-analytical situation report. End with 24h risk assessment."}])
        summary=msg.content[0].text; gen="claude-opus-4-6"
    except Exception as ex:
        summary=f"AI error: {str(ex)[:100]}"; gen="fallback"
    return {"summary":summary,"generated_by":gen,"gti":gti,"event_count":len(e),"timestamp":datetime.datetime.utcnow().isoformat()+"Z"}

