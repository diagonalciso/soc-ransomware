#!/usr/bin/env python3
"""Ransomware tracker dashboard - mirrors ransomware.live data on port 8096.
Includes direct Qilin .onion scraper via Tor SOCKS5 (127.0.0.1:9050).
"""

import json
import time
import urllib.request
import os
import re
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Lock

PORT = int(os.environ.get("PORT", 8096))
CACHE_TTL = int(os.environ.get("CACHE_TTL", 300))
API_BASE = "https://api.ransomware.live"
WATCH_GROUPS = [g.strip().lower() for g in os.environ.get("WATCH_GROUPS", "shinyhunters,ShinySp1d3r").split(",") if g.strip()]

QILIN_ONION = "ijzn3sicrcy7guixkzjkib4ukbiilwc3xhnmby4mcbccnsd7j2rekvqd.onion"
QILIN_TTL = 3600  # 1 hour

_cache: dict = {}
_cache_lock = Lock()
_watch_companies: list = []
_watch_companies_lock = Lock()
_qilin: dict = {"ts": 0, "items": [], "error": None}
_qilin_lock = Lock()


def fetch_api(path: str) -> object:
    with _cache_lock:
        entry = _cache.get(path)
        if entry and time.time() - entry["ts"] < CACHE_TTL:
            return entry["data"]
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; RansomwareTracker/1.0)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        with _cache_lock:
            _cache[path] = {"ts": time.time(), "data": data}
        return data
    except Exception as e:
        return {"error": str(e)}


def _parse_qilin_html(html: str) -> list:
    victims = []
    parts = re.split(r'<div data-key="(\d+)">', html)
    # parts: [pre, key1, block1, key2, block2, ...]
    i = 1
    while i + 1 < len(parts):
        key = parts[i]
        block = parts[i + 1]
        try:
            name_m = re.search(r'class="item_box-title[^"]*"[^>]*>([^<]+)</a>', block)
            name = name_m.group(1).strip() if name_m else "?"

            uuid_m = re.search(r'/site/blog\?uuid=([a-f0-9-]+)', block)
            uuid = uuid_m.group(1) if uuid_m else ""

            sector_m = re.search(r'class="item_box-info">([^<]*)</p>', block)
            sector = sector_m.group(1).strip() if sector_m else ""

            url_m = re.search(r'class="item_box-info__link">Company url</a>', block)
            url_href = re.search(r'href="([^"]+)"[^>]*>Company url', block)
            company_url = url_href.group(1) if url_href else ""

            date_m = re.search(r'images/clock\.png[^>]+alt="">\s*</div>\s*([A-Za-z]+ \d+, \d{4})', block, re.DOTALL) or \
                     re.search(r'([A-Za-z]+ \d{1,2}, \d{4})', block)
            date = date_m.group(1).strip() if date_m else ""

            photos_m = re.search(r'(\d+) photos', block)
            photos = int(photos_m.group(1)) if photos_m else 0

            files_m = re.search(r'([\d,]+)\s+files?', block)
            files = files_m.group(1).replace(",", "") if files_m else ""

            size_m = re.search(r'([\d.]+)\s*GB', block)
            size_gb = float(size_m.group(1)) if size_m else 0.0

            published = bool(re.search(r'[Pp]ublicat', block))

            countdown_m = re.search(r'Time till publication.*?(\d+h\s*:\s*\d+m)', block, re.DOTALL)
            countdown = countdown_m.group(1).strip() if countdown_m else ""

            victims.append({
                "key": key,
                "uuid": uuid,
                "name": name,
                "sector": sector,
                "url": company_url,
                "date": date,
                "photos": photos,
                "files": int(files) if files else 0,
                "size_gb": size_gb,
                "published": published,
                "countdown": countdown,
                "onion_url": f"http://{QILIN_ONION}/site/blog?uuid={uuid}" if uuid else "",
            })
        except Exception:
            pass
        i += 2
    return victims


def fetch_qilin():
    with _qilin_lock:
        if time.time() - _qilin["ts"] < QILIN_TTL:
            return
    try:
        result = subprocess.run(
            ["curl", "-s", "--socks5-hostname", "127.0.0.1:9050", "--max-time", "60",
             "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0",
             f"http://{QILIN_ONION}/"],
            capture_output=True, text=True, timeout=75
        )
        if result.returncode != 0 or not result.stdout:
            raise RuntimeError(result.stderr[:200] or "empty response")
        items = _parse_qilin_html(result.stdout)
        if not items:
            raise RuntimeError("parsed 0 items — site structure may have changed")
        with _qilin_lock:
            _qilin.update({"ts": time.time(), "items": items, "error": None})
    except Exception as e:
        with _qilin_lock:
            _qilin["error"] = str(e)


def _qilin_refresh_loop():
    while True:
        with _qilin_lock:
            age = time.time() - _qilin["ts"]
        if age >= QILIN_TTL:
            fetch_qilin()
        time.sleep(60)


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SOC Ransomware — Ransomware Tracker</title><link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>☠️</text></svg>">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#e6edf3;font-family:'Segoe UI',monospace;font-size:13px}
a{color:#58a6ff;text-decoration:none}
a:hover{text-decoration:underline}
header{background:#161b22;border-bottom:1px solid #30363d;padding:12px 20px;display:flex;align-items:center;gap:16px}
header h1{font-size:16px;color:#f85149;font-weight:700;letter-spacing:1px}
header .sub{color:#8b949e;font-size:11px}
.stats-bar{background:#161b22;border-bottom:1px solid #21262d;display:flex}
.stat{flex:1;padding:14px 20px;border-right:1px solid #21262d;text-align:center}
.stat:last-child{border-right:none}
.stat .val{font-size:26px;font-weight:700;color:#f85149}
.stat .lbl{font-size:10px;color:#8b949e;text-transform:uppercase;letter-spacing:1px;margin-top:2px}
.tabs{background:#161b22;border-bottom:1px solid #21262d;display:flex;padding:0 20px}
.tab{padding:10px 16px;cursor:pointer;color:#8b949e;border-bottom:2px solid transparent;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.tab.active{color:#f85149;border-bottom-color:#f85149}
.tab:hover{color:#e6edf3}
.toolbar{padding:10px 20px;background:#0d1117;display:flex;gap:10px;align-items:center;border-bottom:1px solid #21262d;flex-wrap:wrap}
input[type=text]{background:#161b22;border:1px solid #30363d;color:#e6edf3;padding:6px 10px;border-radius:4px;font-size:12px;width:260px;outline:none}
input[type=text]:focus{border-color:#f85149}
select{background:#161b22;border:1px solid #30363d;color:#e6edf3;padding:6px 10px;border-radius:4px;font-size:12px;outline:none}
.count-badge{color:#8b949e;font-size:11px;margin-left:auto}
.panel{display:none}
.panel.active{display:block}
.loading{text-align:center;padding:40px;color:#8b949e}
.error{text-align:center;padding:40px;color:#f85149}
table{width:100%;border-collapse:collapse}
thead th{background:#161b22;color:#8b949e;padding:8px 12px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.8px;border-bottom:1px solid #21262d;position:sticky;top:0;z-index:10}
tbody tr{border-bottom:1px solid #21262d;transition:background .1s}
tbody tr:hover{background:#161b22}
tbody td{padding:8px 12px;vertical-align:middle}
.group-badge{display:inline-block;background:#1c2128;border:1px solid #f85149;color:#f85149;padding:2px 7px;border-radius:3px;font-size:10px;font-weight:600;text-transform:uppercase;cursor:pointer}
.group-badge:hover{background:#f85149;color:#0d1117}
.sector-badge{display:inline-block;background:#1c2128;border:1px solid #58a6ff;color:#58a6ff;padding:1px 6px;border-radius:3px;font-size:10px}
.online-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#3fb950;margin-right:5px}
.offline-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#f85149;margin-right:5px}
.watch-row{background:#1a1500!important}
.watch-row:hover{background:#241d00!important}
.watch-badge{display:inline-block;background:#1c2128;border:1px solid #d29922;color:#d29922;padding:2px 7px;border-radius:3px;font-size:10px;font-weight:600;text-transform:uppercase;cursor:pointer}
.watch-badge:hover{background:#d29922;color:#0d1117}
.flag{font-size:16px}
.date{color:#8b949e;font-size:11px;white-space:nowrap}
.company{font-weight:600;color:#e6edf3}
.description{color:#8b949e;font-size:11px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.victim-count{font-size:18px;font-weight:700;color:#f85149}
.group-name{font-weight:700;color:#e6edf3;font-size:13px}
.group-desc{color:#8b949e;font-size:11px;max-width:380px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.raas-badge{display:inline-block;background:#1c2128;border:1px solid #d29922;color:#d29922;padding:1px 5px;border-radius:3px;font-size:9px;text-transform:uppercase;margin-right:4px}
.btn{background:#1c2128;border:1px solid #30363d;color:#8b949e;padding:5px 12px;border-radius:4px;cursor:pointer;font-size:11px}
.btn:hover{border-color:#f85149;color:#f85149}
.shot-icon{cursor:pointer;font-size:14px;margin-right:4px}
.shot-icon:hover{filter:brightness(1.5)}
#modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.88);z-index:1000;align-items:center;justify-content:center}
#modal.open{display:flex}
#modal img{max-width:90vw;max-height:85vh;border:2px solid #30363d;border-radius:4px}
#modal .x{position:absolute;top:20px;right:28px;font-size:30px;cursor:pointer;color:#e6edf3;line-height:1}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;padding:20px}
.stat-card{background:#161b22;border:1px solid #21262d;border-radius:6px;padding:16px}
.stat-card h3{font-size:10px;text-transform:uppercase;color:#8b949e;letter-spacing:.8px;margin-bottom:12px}
.bar-row{display:flex;align-items:center;gap:8px;margin-bottom:5px}
.bar-label{width:130px;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#e6edf3}
.bar-track{flex:1;background:#21262d;border-radius:2px;height:7px}
.bar-fill{background:#f85149;height:7px;border-radius:2px;min-width:2px}
.bar-val{width:32px;text-align:right;font-size:11px;color:#8b949e}
.ticker{background:#0d1117;border-bottom:1px solid #21262d;padding:4px 20px;font-size:11px;color:#8b949e;overflow:hidden;white-space:nowrap}
.ticker span{display:inline-block;animation:scroll 60s linear infinite}
@keyframes scroll{0%{transform:translateX(100vw)}100%{transform:translateX(-100%)}}
.company-match-row{background:#001a1a!important}
.company-match-row:hover{background:#002626!important}
.company-match-badge{display:inline-block;background:#1c2128;border:1px solid #3fb950;color:#3fb950;padding:2px 7px;border-radius:3px;font-size:10px;font-weight:600;text-transform:uppercase;margin-left:6px}
.import-btn{background:#1c2128;border:1px solid #3fb950;color:#3fb950;padding:5px 10px;border-radius:4px;cursor:pointer;font-size:11px;font-weight:600}
.import-btn:hover{background:#3fb950;color:#0d1117}
.company-count{color:#3fb950;font-size:11px;font-weight:600}
.pub-badge{display:inline-block;background:#1c2128;border:1px solid #f85149;color:#f85149;padding:2px 7px;border-radius:3px;font-size:10px;font-weight:600;text-transform:uppercase}
.pending-badge{display:inline-block;background:#1c2128;border:1px solid #d29922;color:#d29922;padding:2px 7px;border-radius:3px;font-size:10px;font-weight:600;text-transform:uppercase}
.countdown{color:#d29922;font-size:11px;font-weight:600}
.qilin-row-pub{background:#1a0808!important}
.qilin-row-pub:hover{background:#240e0e!important}
</style>
</head>
<body><a href="/manual" target="_blank" title="Manual / Help" style="position:fixed;top:12px;right:14px;z-index:99999;width:30px;height:30px;border-radius:50%;background:#161b22;border:1px solid #30363d;color:#58a6ff;font:700 16px/30px system-ui,sans-serif;text-align:center;text-decoration:none;box-shadow:0 2px 8px rgba(0,0,0,.4)" onmouseover="this.style.borderColor='#58a6ff'" onmouseout="this.style.borderColor='#30363d'">?</a>

<header>
  <h1>&#9760; SOC Ransomware <span style="font-weight:400;opacity:.6;font-size:.6em">Ransomware Tracker</span></h1>
  <span class="sub">live data via <a href="https://www.ransomware.live" target="_blank">ransomware.live</a> API &middot; cache 5 min</span>
</header>

<div class="stats-bar">
  <div class="stat"><div class="val" id="st-groups">—</div><div class="lbl">Active Groups</div></div>
  <div class="stat"><div class="val" id="st-total">—</div><div class="lbl">Groups Tracked</div></div>
  <div class="stat"><div class="val" id="st-year">—</div><div class="lbl">Victims This Year</div></div>
  <div class="stat"><div class="val" id="st-month">—</div><div class="lbl">Victims This Month</div></div>
  <div class="stat"><div class="val" id="st-feed">—</div><div class="lbl">Recent Feed</div></div>
  <div class="stat"><div class="val" id="st-watched" style="color:#d29922">—</div><div class="lbl">Watched Hits</div></div>
  <div class="stat"><div class="val" id="st-qilin" style="color:#bc8cff">—</div><div class="lbl">Qilin Direct</div></div>
</div>

<div id="ticker-bar" class="ticker"><span id="ticker-text">Loading...</span></div>

<div class="tabs">
  <div class="tab active" onclick="showTab('victims')">Recent Victims</div>
  <div class="tab" onclick="showTab('groups')">Groups</div>
  <div class="tab" onclick="showTab('stats')">Statistics</div>
  <div class="tab" onclick="showTab('watched')" style="color:#d29922">&#9888; Watched</div>
  <div class="tab" onclick="showTab('qilin')" style="color:#bc8cff">&#9760; Qilin Direct</div>
</div>

<!-- VICTIMS -->
<div id="panel-victims" class="panel active">
  <div class="toolbar">
    <input type="text" id="v-q" placeholder="Search company, group, country, domain..." oninput="filterVictims()">
    <select id="v-sector" onchange="filterVictims()"><option value="">All Sectors</option></select>
    <select id="v-group" onchange="filterVictims()"><option value="">All Groups</option></select>
    <button class="btn" onclick="loadVictims(true)">&#8635; Refresh</button>
    <button class="import-btn" onclick="document.getElementById('csv-input').click()">&#8679; Import CSV</button>
    <input type="file" id="csv-input" accept=".csv,.txt" style="display:none" onchange="importCompanies(this)">
    <span class="company-count" id="company-count" style="display:none"></span>
    <span class="count-badge" id="v-count"></span>
  </div>
  <div id="victims-body"><div class="loading">Loading recent victims...</div></div>
</div>

<!-- GROUPS -->
<div id="panel-groups" class="panel">
  <div class="toolbar">
    <input type="text" id="g-q" placeholder="Search group name..." oninput="filterGroups()">
    <select id="g-status" onchange="filterGroups()">
      <option value="">All Status</option>
      <option value="online">Online</option>
      <option value="offline">Offline</option>
    </select>
    <button class="btn" onclick="loadGroups(true)">&#8635; Refresh</button>
    <span class="count-badge" id="g-count"></span>
  </div>
  <div id="groups-body"><div class="loading">Loading groups...</div></div>
</div>

<!-- STATS -->
<div id="panel-stats" class="panel">
  <div id="stats-body"><div class="loading">Loading statistics...</div></div>
</div>

<!-- WATCHED GROUPS -->
<div id="panel-watched" class="panel">
  <div class="toolbar">
    <span style="color:#d29922;font-size:12px;font-weight:700">&#9888; WATCHING &nbsp;&nbsp;<span id="w-groups-lbl" style="font-weight:400;color:#8b949e"></span></span>
    <span class="count-badge" id="w-count"></span>
  </div>
  <div id="watched-body"><div class="loading">Loading...</div></div>
</div>

<!-- QILIN DIRECT -->
<div id="panel-qilin" class="panel">
  <div class="toolbar">
    <input type="text" id="q-q" placeholder="Search company, sector..." oninput="filterQilin()">
    <select id="q-status" onchange="filterQilin()">
      <option value="">All</option>
      <option value="published">Published</option>
      <option value="pending">Pending</option>
    </select>
    <button class="btn" onclick="loadQilin(true)">&#8635; Refresh</button>
    <span style="color:#8b949e;font-size:10px;margin-left:8px">&#9679; Direct from <span style="color:#bc8cff">Qilin .onion</span> · 10 min cache · via Tor</span>
    <span class="count-badge" id="q-count"></span>
  </div>
  <div id="qilin-body"><div class="loading">Loading Qilin leak site...</div></div>
</div>

<!-- SCREENSHOT MODAL -->
<div id="modal" onclick="if(event.target===this)closeModal()">
  <span class="x" onclick="closeModal()">&times;</span>
  <img id="modal-img" src="" alt="Screenshot">
</div>

<script>
const WATCH_GROUPS=__WATCH_GROUPS_JSON__;
let WATCH_COMPANIES=__WATCH_COMPANIES_JSON__;
let allVictims=[], allGroups=[];

function matchesWatchlist(v){
  if(!WATCH_COMPANIES.length)return false;
  const name=(v.post_title||v.website||'').toLowerCase();
  return WATCH_COMPANIES.some(c=>name.includes(c.toLowerCase()));
}

async function importCompanies(input){
  const file=input.files[0];
  if(!file)return;
  const text=await file.text();
  try{
    const r=await fetch('/api/companies',{method:'POST',body:text,headers:{'Content-Type':'text/plain'}});
    const d=await r.json();
    WATCH_COMPANIES=text.split('\n').map(l=>l.split(',')[0].replace(/^["']|["']$/g,'').trim()).filter(Boolean);
    const el=document.getElementById('company-count');
    el.textContent='&#9670; '+d.count+' companies loaded';
    el.style.display='';
    filterVictims();
  }catch(e){alert('Import failed: '+e.message);}
  input.value='';
}

function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}

function flag(code){
  if(!code||code.length!==2)return'🌐';
  return String.fromCodePoint(...[...code.toUpperCase()].map(c=>0x1F1E6-65+c.charCodeAt(0)));
}

function ago(dateStr){
  if(!dateStr)return'—';
  const d=new Date(dateStr.replace(' ','T'));
  const s=Math.floor((Date.now()-d.getTime())/1000);
  if(s<60)return s+'s ago';
  if(s<3600)return Math.floor(s/60)+'m ago';
  if(s<86400)return Math.floor(s/3600)+'h ago';
  return Math.floor(s/86400)+'d ago';
}

function showTab(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  const idx={'victims':0,'groups':1,'stats':2,'watched':3,'qilin':4}[name];
  document.querySelectorAll('.tab')[idx].classList.add('active');
  document.getElementById('panel-'+name).classList.add('active');
  if(name==='groups'&&allGroups.length===0)loadGroups();
  if(name==='stats'){if(allVictims.length===0)loadVictims();else renderStats();}
  if(name==='watched'){if(allVictims.length===0)loadVictims();else renderWatched(allVictims);}
  if(name==='qilin')loadQilin();
}

async function loadVictims(force=false){
  document.getElementById('victims-body').innerHTML='<div class="loading">Fetching victims...</div>';
  try{
    const r=await fetch('/api/victims'+(force?'?force=1':''));
    const data=await r.json();
    if(data.error)throw new Error(data.error);
    allVictims=data;
    buildVictimFilters(data);
    filterVictims();
    computeStats(data);
    buildTicker(data);
  }catch(e){
    document.getElementById('victims-body').innerHTML='<div class="error">Error: '+esc(e.message)+'</div>';
  }
}

function buildVictimFilters(victims){
  const sectors=[...new Set(victims.map(v=>v.activity).filter(a=>a&&a!=='N/A'&&a!=='Not Found'))].sort();
  const groups=[...new Set(victims.map(v=>v.group_name).filter(Boolean))].sort();
  document.getElementById('v-sector').innerHTML='<option value="">All Sectors</option>'+sectors.map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join('');
  document.getElementById('v-group').innerHTML='<option value="">All Groups</option>'+groups.map(g=>`<option value="${esc(g)}">${esc(g)}</option>`).join('');
}

function filterVictims(){
  const q=document.getElementById('v-q').value.toLowerCase();
  const sector=document.getElementById('v-sector').value;
  const group=document.getElementById('v-group').value;
  const filtered=allVictims.filter(v=>{
    if(sector&&v.activity!==sector)return false;
    if(group&&v.group_name!==group)return false;
    if(q&&![(v.post_title||''),(v.group_name||''),(v.country||''),(v.website||''),(v.description||'')].some(f=>f.toLowerCase().includes(q)))return false;
    return true;
  });
  renderVictims(filtered);
}

function renderVictims(victims){
  document.getElementById('v-count').textContent=victims.length+' victims';
  if(!victims.length){document.getElementById('victims-body').innerHTML='<div class="loading">No results.</div>';return;}
  // Watchlist matches float to top
  const sorted=[...victims].sort((a,b)=>{
    const am=matchesWatchlist(a)?1:0, bm=matchesWatchlist(b)?1:0;
    return bm-am;
  });
  const rows=sorted.map(v=>{
    const f=flag(v.country);
    const isWatched=WATCH_GROUPS.includes((v.group_name||'').toLowerCase());
    const isCompanyMatch=matchesWatchlist(v);
    const shot=v.screenshot?`<span class="shot-icon" title="Screenshot" onclick="showModal('${esc(v.screenshot)}')">&#128247;</span>`:'';
    const web=v.website?`<a href="https://${esc(v.website)}" target="_blank" title="${esc(v.website)}">&#127760;</a>`:'';
    const sec=v.activity&&v.activity!=='N/A'&&v.activity!=='Not Found'?`<span class="sector-badge">${esc(v.activity)}</span>`:'';
    const wlistBadge=isCompanyMatch?'<span class="company-match-badge">&#9670; WATCHLIST</span>':'';
    let rowClass='';
    if(isCompanyMatch)rowClass='company-match-row';
    else if(isWatched)rowClass='watch-row';
    return`<tr${rowClass?' class="'+rowClass+'"':''}>
      <td class="company">${esc(v.post_title||v.website||'—')}${wlistBadge}</td>
      <td><span class="flag" title="${esc(v.country)}">${f}</span></td>
      <td><span class="${isWatched?'watch-badge':'group-badge'}" onclick="filterByGroup('${esc(v.group_name)}')">${esc(v.group_name)}</span></td>
      <td>${sec}</td>
      <td class="date">${ago(v.discovered||v.published)}</td>
      <td style="white-space:nowrap">${shot}${web}</td>
    </tr>`;
  }).join('');
  document.getElementById('victims-body').innerHTML=`<table><thead><tr><th>Company</th><th>Country</th><th>Group</th><th>Sector</th><th>Discovered</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
}

function filterByGroup(name){
  showTab('victims');
  document.getElementById('v-group').value=name;
  filterVictims();
}

function renderWatched(victims){
  const watched=victims.filter(v=>WATCH_GROUPS.includes((v.group_name||'').toLowerCase()));
  document.getElementById('w-count').textContent=watched.length+' victims';
  document.getElementById('w-groups-lbl').textContent=WATCH_GROUPS.join(' · ');
  if(!watched.length){document.getElementById('watched-body').innerHTML='<div class="loading">No victims from watched groups in recent feed.</div>';return;}
  const rows=watched.map(v=>{
    const f=flag(v.country);
    const shot=v.screenshot?`<span class="shot-icon" title="Screenshot" onclick="showModal('${esc(v.screenshot)}')">&#128247;</span>`:'';
    const web=v.website?`<a href="https://${esc(v.website)}" target="_blank" title="${esc(v.website)}">&#127760;</a>`:'';
    const sec=v.activity&&v.activity!=='N/A'&&v.activity!=='Not Found'?`<span class="sector-badge">${esc(v.activity)}</span>`:'';
    return`<tr class="watch-row">
      <td class="company">${esc(v.post_title||v.website||'—')}</td>
      <td><span class="flag" title="${esc(v.country)}">${f}</span></td>
      <td><span class="watch-badge" onclick="filterByGroup('${esc(v.group_name)}')">${esc(v.group_name)}</span></td>
      <td>${sec}</td>
      <td class="date">${ago(v.discovered||v.published)}</td>
      <td style="white-space:nowrap">${shot}${web}</td>
    </tr>`;
  }).join('');
  document.getElementById('watched-body').innerHTML=`<table><thead><tr><th>Company</th><th>Country</th><th>Group</th><th>Sector</th><th>Discovered</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
}

function computeStats(victims){
  document.getElementById('st-feed').textContent=victims.length;
  const now=new Date();
  const yr=now.getFullYear(), mo=now.getMonth();
  const yc=victims.filter(v=>{const d=new Date((v.discovered||v.published||'').replace(' ','T'));return d.getFullYear()===yr;}).length;
  const mc=victims.filter(v=>{const d=new Date((v.discovered||v.published||'').replace(' ','T'));return d.getFullYear()===yr&&d.getMonth()===mo;}).length;
  document.getElementById('st-year').textContent=yc+'';
  document.getElementById('st-month').textContent=mc+'';
  const wc=victims.filter(v=>WATCH_GROUPS.includes((v.group_name||'').toLowerCase())).length;
  document.getElementById('st-watched').textContent=wc+'';
}

function buildTicker(victims){
  const text=victims.slice(0,20).map(v=>`&#9760; ${esc(v.post_title||v.website)} [${esc(v.group_name)}] ${flag(v.country)}`).join('&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;');
  document.getElementById('ticker-text').innerHTML=text;
}

async function loadGroups(force=false){
  document.getElementById('groups-body').innerHTML='<div class="loading">Fetching groups...</div>';
  try{
    const r=await fetch('/api/groups'+(force?'?force=1':''));
    const data=await r.json();
    if(data.error)throw new Error(data.error);
    allGroups=data;
    document.getElementById('st-total').textContent=data.length;
    const active=data.filter(g=>g.locations&&g.locations.some(l=>l.available)).length;
    document.getElementById('st-groups').textContent=active;
    filterGroups();
  }catch(e){
    document.getElementById('groups-body').innerHTML='<div class="error">Error: '+esc(e.message)+'</div>';
  }
}

function filterGroups(){
  const q=document.getElementById('g-q').value.toLowerCase();
  const status=document.getElementById('g-status').value;
  const filtered=allGroups.filter(g=>{
    if(q&&!(g.name||'').toLowerCase().includes(q))return false;
    const online=g.locations&&g.locations.some(l=>l.available);
    if(status==='online'&&!online)return false;
    if(status==='offline'&&online)return false;
    return true;
  });
  renderGroups(filtered);
}

function renderGroups(groups){
  const sorted=[...groups].sort((a,b)=>(b._victim_count||0)-(a._victim_count||0));
  document.getElementById('g-count').textContent=sorted.length+' groups';
  if(!sorted.length){document.getElementById('groups-body').innerHTML='<div class="loading">No results.</div>';return;}
  const rows=sorted.map(g=>{
    const online=g.locations&&g.locations.some(l=>l.available);
    const dot=online?'<span class="online-dot"></span>Online':'<span class="offline-dot"></span>Offline';
    const raas=g.type&&g.type.raas?'<span class="raas-badge">RaaS</span>':'';
    const lastScrape=g.locations&&g.locations.length?[...g.locations].sort((a,b)=>((b.lastscrape||'')>(a.lastscrape||'')?1:-1))[0].lastscrape:null;
    return`<tr>
      <td><span class="group-name">${raas}${esc(g.name)}</span>${g.altname?`<br><span style="color:#8b949e;font-size:10px">${esc(g.altname)}</span>`:''}</td>
      <td class="victim-count">${g._victim_count||0}</td>
      <td style="white-space:nowrap">${dot}</td>
      <td class="date">${ago(lastScrape)}</td>
      <td class="group-desc" title="${esc(g.description||'')}">${esc(g.description||'—')}</td>
    </tr>`;
  }).join('');
  document.getElementById('groups-body').innerHTML=`<table><thead><tr><th>Group</th><th>Victims</th><th>Status</th><th>Last Seen</th><th>Description</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderStats(){
  const gc={},sc={},cc={};
  allVictims.forEach(v=>{
    if(v.group_name)gc[v.group_name]=(gc[v.group_name]||0)+1;
    if(v.activity&&v.activity!=='N/A'&&v.activity!=='Not Found')sc[v.activity]=(sc[v.activity]||0)+1;
    if(v.country)cc[v.country]=(cc[v.country]||0)+1;
  });
  const topG=Object.entries(gc).sort((a,b)=>b[1]-a[1]).slice(0,15);
  const topS=Object.entries(sc).sort((a,b)=>b[1]-a[1]).slice(0,12);
  const topC=Object.entries(cc).sort((a,b)=>b[1]-a[1]).slice(0,15);
  function bars(entries,max){
    return entries.map(([l,v])=>`<div class="bar-row"><span class="bar-label" title="${esc(l)}">${esc(l)}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.round(v/max*100)}%"></div></div><span class="bar-val">${v}</span></div>`).join('');
  }
  const mG=topG[0]?.[1]||1,mS=topS[0]?.[1]||1,mC=topC[0]?.[1]||1;
  document.getElementById('stats-body').innerHTML=`<div class="stats-grid">
    <div class="stat-card"><h3>Top Groups (recent 100)</h3>${bars(topG,mG)}</div>
    <div class="stat-card"><h3>Top Sectors (recent 100)</h3>${bars(topS,mS)}</div>
    <div class="stat-card"><h3>Top Countries (recent 100)</h3>${bars(topC.map(([c,v])=>[flag(c)+' '+c,v]),mC)}</div>
  </div>`;
}

let allQilin=[];
async function loadQilin(force=false){
  document.getElementById('qilin-body').innerHTML='<div class="loading">Fetching from Qilin .onion via Tor...</div>';
  try{
    const r=await fetch('/api/qilin'+(force?'?force=1':''));
    const d=await r.json();
    if(d.error&&!d.items?.length){
      document.getElementById('qilin-body').innerHTML='<div class="error">Tor error: '+esc(d.error)+'</div>';
      return;
    }
    allQilin=d.items||[];
    document.getElementById('st-qilin').textContent=allQilin.length;
    if(d.error)document.getElementById('qilin-body').innerHTML='<div class="error" style="margin:8px 20px">Warning: '+esc(d.error)+'</div>';
    filterQilin();
  }catch(e){
    document.getElementById('qilin-body').innerHTML='<div class="error">Error: '+esc(e.message)+'</div>';
  }
}
function filterQilin(){
  const q=(document.getElementById('q-q')||{}).value?.toLowerCase()||'';
  const st=(document.getElementById('q-status')||{}).value||'';
  const filtered=allQilin.filter(v=>{
    if(st==='published'&&!v.published)return false;
    if(st==='pending'&&v.published)return false;
    if(q&&![v.name,v.sector].some(f=>(f||'').toLowerCase().includes(q)))return false;
    return true;
  });
  renderQilin(filtered);
}
function renderQilin(items){
  document.getElementById('q-count').textContent=items.length+' entries';
  if(!items.length){document.getElementById('qilin-body').innerHTML='<div class="loading">No results.</div>';return;}
  const rows=items.map(v=>{
    const pubBadge=v.published?'<span class="pub-badge">&#9632; PUBLISHED</span>':'<span class="pending-badge">&#9650; PENDING</span>';
    const cd=v.countdown?`<span class="countdown">&#9201; ${esc(v.countdown)}</span>`:'';
    const sz=v.size_gb>0?`${v.size_gb} GB`:'';
    const fc=v.files>0?`${v.files.toLocaleString()} files`:'';
    const meta=[fc,sz,v.photos>0?v.photos+' photos':''].filter(Boolean).join(' · ');
    const rowCls=v.published?'qilin-row-pub':'';
    return`<tr${rowCls?' class="'+rowCls+'"':''}>
      <td class="company">${esc(v.name)}</td>
      <td><span class="sector-badge">${esc(v.sector||'—')}</span></td>
      <td>${pubBadge} ${cd}</td>
      <td class="date">${esc(v.date)}</td>
      <td style="color:#8b949e;font-size:11px">${esc(meta)}</td>
      <td>${v.url?`<a href="${esc(v.url)}" target="_blank">&#127760;</a>`:''}</td>
    </tr>`;
  }).join('');
  document.getElementById('qilin-body').innerHTML=`<table><thead><tr><th>Company</th><th>Sector</th><th>Status</th><th>Posted</th><th>Data</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
}

function showModal(url){document.getElementById('modal-img').src=url;document.getElementById('modal').classList.add('open');}
function closeModal(){document.getElementById('modal').classList.remove('open');document.getElementById('modal-img').src='';}

loadVictims();
loadGroups();
setInterval(()=>{loadVictims();loadGroups();},300000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {args[0]} {args[1]}")

    def send_json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str) -> None:
        html = html.replace("__WATCH_GROUPS_JSON__", json.dumps(WATCH_GROUPS))
        with _watch_companies_lock:
            html = html.replace("__WATCH_COMPANIES_JSON__", json.dumps(_watch_companies))
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.split("?")[0].rstrip("/") == "/manual":
            _serve_manual(self); return
        path = self.path.split("?")[0]
        force = "force=1" in self.path

        if path in ("/", "/index.html"):
            self.send_html(HTML)
        elif path == "/api/victims":
            if force:
                with _cache_lock:
                    _cache.pop("/recentvictims", None)
            self.send_json(fetch_api("/recentvictims"))
        elif path == "/api/groups":
            if force:
                with _cache_lock:
                    _cache.pop("/groups", None)
            self.send_json(fetch_api("/groups"))
        elif path == "/api/companies":
            with _watch_companies_lock:
                self.send_json(_watch_companies)
        elif path == "/api/qilin":
            if force:
                with _qilin_lock:
                    _qilin["ts"] = 0
                threading.Thread(target=fetch_qilin, daemon=True).start()
                time.sleep(1)
            with _qilin_lock:
                self.send_json(dict(_qilin))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        if path == "/api/companies":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            names = []
            for line in body.splitlines():
                # Take first CSV column, strip quotes and whitespace
                col = line.split(",")[0].strip().strip('"').strip("'").strip()
                if col:
                    names.append(col)
            with _watch_companies_lock:
                global _watch_companies
                _watch_companies = names
            self.send_json({"ok": True, "count": len(names)})
        else:
            self.send_response(404)
            self.end_headers()




# ---- injected: /manual help page (stdlib markdown renderer) ----------------
def _md_to_html(md):
    import html, re as _re
    lines = md.split("\n")
    out = []; i = 0; n = len(lines)
    def inline(t):
        t = html.escape(t)
        t = _re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        t = _re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
        t = _re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
                    r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
        return t
    while i < n:
        ln = lines[i]
        if ln.startswith("```"):
            i += 1; buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(html.escape(lines[i])); i += 1
            i += 1
            out.append("<pre><code>" + "\n".join(buf) + "</code></pre>"); continue
        m = _re.match(r"(#{1,6})\s+(.*)", ln)
        if m:
            lv = len(m.group(1)); out.append("<h%d>%s</h%d>" % (lv, inline(m.group(2)), lv)); i += 1; continue
        if _re.match(r"\s*[-*]\s+", ln):
            out.append("<ul>")
            while i < n and _re.match(r"\s*[-*]\s+", lines[i]):
                out.append("<li>" + inline(_re.sub(r"\s*[-*]\s+", "", lines[i], count=1)) + "</li>"); i += 1
            out.append("</ul>"); continue
        if _re.match(r"\s*\d+\.\s+", ln):
            out.append("<ol>")
            while i < n and _re.match(r"\s*\d+\.\s+", lines[i]):
                out.append("<li>" + inline(_re.sub(r"\s*\d+\.\s+", "", lines[i], count=1)) + "</li>"); i += 1
            out.append("</ol>"); continue
        if ln.strip().startswith("|") and i + 1 < n and _re.match(r"^\s*\|[-:\s|]+\|\s*$", lines[i+1]):
            hdr = [c.strip() for c in ln.strip().strip("|").split("|")]
            out.append("<table><thead><tr>" + "".join("<th>%s</th>" % inline(c) for c in hdr) + "</tr></thead><tbody>")
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                out.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in cells) + "</tr>"); i += 1
            out.append("</tbody></table>"); continue
        if _re.match(r"^\s*---+\s*$", ln):
            out.append("<hr>"); i += 1; continue
        if ln.strip() == "":
            i += 1; continue
        para = [ln]; i += 1
        while i < n and lines[i].strip() and not _re.match(r"(#{1,6}\s|```|\s*[-*]\s|\s*\d+\.\s|\|)", lines[i]):
            para.append(lines[i]); i += 1
        out.append("<p>" + inline(" ".join(para)) + "</p>")
    return "\n".join(out)


def _manual_page(inner):
    return ("""<!DOCTYPE html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Manual</title><link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>☠️</text></svg>"><style>
:root{--bg:#0d1117;--sf:#161b22;--bd:#30363d;--tx:#e6edf3;--mut:#8b949e;--ac:#58a6ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);
font:15px/1.65 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:32px 22px 80px}
.top{position:sticky;top:0;background:rgba(13,17,23,.92);backdrop-filter:blur(6px);
border-bottom:1px solid var(--bd);margin:-32px -22px 24px;padding:12px 22px;display:flex;
align-items:center;gap:12px}
.top a{color:var(--ac);text-decoration:none;font-size:13px}
h1,h2,h3,h4{color:#fff;line-height:1.25;margin:1.5em 0 .5em}
h1{font-size:26px;border-bottom:1px solid var(--bd);padding-bottom:.3em}
h2{font-size:20px;border-bottom:1px solid var(--bd);padding-bottom:.25em}
h3{font-size:16px}a{color:var(--ac)}
code{background:var(--sf);border:1px solid var(--bd);border-radius:4px;padding:1px 5px;
font:13px/1.4 ui-monospace,Menlo,monospace}
pre{background:var(--sf);border:1px solid var(--bd);border-radius:8px;padding:14px 16px;
overflow:auto}pre code{background:none;border:0;padding:0}
ul,ol{padding-left:1.4em}li{margin:.25em 0}
table{border-collapse:collapse;width:100%;margin:1em 0;font-size:14px}
th,td{border:1px solid var(--bd);padding:7px 10px;text-align:left}
th{background:var(--sf)}hr{border:0;border-top:1px solid var(--bd);margin:2em 0}
.mut{color:var(--mut)}
</style></head><body><div class=wrap>
<div class=top><a href="/">&larr; Back to app</a><span class=mut>&middot; Manual</span></div>
""" + inner + "\n</div></body></html>")


def _serve_manual(handler):
    import os as _os
    p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "MANUAL.md")
    try:
        with open(p, encoding="utf-8") as _fh:
            md = _fh.read()
    except OSError:
        md = "# Manual\n\nMANUAL.md not found next to the application."
    body = _manual_page(_md_to_html(md)).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
# ---- end injected block -----------------------------------------------------

if __name__ == "__main__":
    print(f"Ransomware Tracker → http://0.0.0.0:{PORT}")
    print("Starting Qilin onion fetch via Tor...")
    threading.Thread(target=fetch_qilin, daemon=True).start()
    threading.Thread(target=_qilin_refresh_loop, daemon=True).start()
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
