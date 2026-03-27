import os
import json
import math
import re
from flask import Flask, render_template_string

app = Flask(__name__)

# --- CONFIGURATION ---
DATA_FILE = "trip_data.json"
STAGES_DIR = os.path.join("data", "stages")
STORIES_DIR = os.path.join("data", "stories")
IMG_BASE_URL = "https://cdn.jsdelivr.net/gh/bjsilver/cycling-east@master/static/images"
# ---------------------

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def simplify_route(coords, threshold_meters=30):
    if not coords: return []
    new_coords = [coords[0]]
    last_pt = coords[0]
    for pt in coords[1:]:
        dist = haversine(last_pt[0], last_pt[1], pt[0], pt[1])
        if dist > threshold_meters:
            new_coords.append(pt)
            last_pt = pt
    if new_coords[-1] != coords[-1]: new_coords.append(coords[-1])
    return new_coords

# Helper for Natural Sort (so '11' comes after '2')
def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def load_data_final():
    routes = []
    total_dist = 0
    file_dates = {}
    
    # 1. Load Trip Data (Routes)
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                trip = json.load(f)
                raw_routes = trip.get('routes', [])
                for r in raw_routes:
                    r['coords'] = simplify_route(r['coords'])
                    routes.append(r)
                total_dist = trip.get('total_distance', 0)
                file_dates = trip.get('file_dates', {})
        except Exception as e:
            print(f"Error loading {DATA_FILE}: {e}")

    # 2. Load Stages
    stages = []
    if os.path.exists(STAGES_DIR):
        stage_files = sorted([f for f in os.listdir(STAGES_DIR) if f.endswith('.json')], key=natural_sort_key)
        for sf in stage_files:
            try:
                with open(os.path.join(STAGES_DIR, sf), 'r') as f:
                    d = json.load(f)
                    s = str(d.get('start_index',0)); e = str(d.get('end_index',0))
                    # Fallback to 'date_range' in json if not found in lookup
                    if 'date_range' not in d:
                        d['date_range'] = f"{file_dates.get(s,'?')} - {file_dates.get(e,'?')}"
                    
                    folder = f"{len(stages)+1:02d}"
                    lpath = os.path.join("static", "images", folder)
                    urls = []
                    if os.path.exists(lpath):
                        for fn in sorted(os.listdir(lpath)):
                            if fn.lower().endswith(('jpg','png','webp','mp4','mov')):
                                urls.append(f"{IMG_BASE_URL}/{folder}/{fn}")
                    d['images'] = urls
                    stages.append(d)
            except Exception as e:
                print(f"Error loading stage {sf}: {e}")

    # 3. Load Stories
    stories = []
    if os.path.exists(STORIES_DIR):
        for sf in sorted(os.listdir(STORIES_DIR)):
            if sf.endswith('.json'):
                try:
                    with open(os.path.join(STORIES_DIR, sf), 'r') as f:
                        s = json.load(f)
                        if 'location' not in s:
                            if 'marker' in s: s['location'] = [s['marker']['lat'], s['marker']['lon']]
                            elif 'lat' in s: s['location'] = [s['lat'], s['lon']]
                            else: continue
                        
                        min_dist = float('inf')
                        closest_idx = 0
                        for idx, r in enumerate(routes):
                            if r['coords']:
                                d = haversine(s['location'][0], s['location'][1], r['coords'][0][0], r['coords'][0][1])
                                if d < min_dist:
                                    min_dist = d
                                    closest_idx = idx
                        s['closest_segment'] = closest_idx

                        if 'route_segment_ids' not in s:
                            if 'route_segment_id' in s: s['route_segment_ids'] = [s['route_segment_id']]
                            else: s['route_segment_ids'] = []
                        
                        max_prog = 0
                        prefix = s.get('img_prefix', '')
                        if 'chapters' in s:
                            for chap in s['chapters']:
                                if 'progress' in chap and chap['progress'] > max_prog: max_prog = chap['progress']
                                if prefix and not chap['image'].startswith('http'):
                                    chap['image'] = prefix + chap['image']
                        
                        s['max_progress'] = max_prog if max_prog > 0 else 1.0
                        s['thumb'] = s['chapters'][0].get('image', '') if 'chapters' in s and s['chapters'] else ""
                        stories.append(s)
                except Exception as e:
                    print(f"Error loading story {sf}: {e}")

    return routes, stages, stories, total_dist

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Cycling East</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400;1,700&family=Inter:wght@300;400;600&family=Space+Mono&display=swap" rel="stylesheet">
    <style>
        :root { --accent: #e63946; --speed: #457b9d; --text: #1d3557; --story: #475569; --card-bg: rgba(255, 255, 255, 0.95); }
        * { box-sizing: border-box; }
        html, body { height: 100%; width: 100%; margin: 0; padding: 0; overflow: hidden; background: #aad3df; font-family: 'Inter', sans-serif; touch-action: none; }
        h1, h2, h3 { font-family: 'Playfair Display', serif; }
        .mono { font-family: 'Space Mono', monospace; }

        #map-container { position: fixed; inset: 0; z-index: 0; }
        #map { width: 100%; height: 100%; outline: none; }
        
        .hero, .nav-container, #stage-card, #gallery-window { will-change: transform, opacity; }

        /* HERO TITLE */
        .hero { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 200; user-select: none; }
        .hero-content { 
            position: absolute; top: 50%; left: 5vw; 
            transform: translateY(-50%); 
            transition: all 0.8s cubic-bezier(0.16, 1, 0.3, 1); 
            transform-origin: top left;
        }
        .hero h1 { font-size: 6rem; line-height: 1; color: #1d3557; font-style: italic; margin: 0; }
        .hero p { color: #475569; letter-spacing: 0.3em; margin-top: 10px; font-size: 0.9rem; }
        @media (max-width: 768px) { .hero h1 { font-size: 3.5rem; } .hero-content { left: 20px; } }
        
        body.shrunk .hero-content { top: 30px; left: 30px; transform: translateY(0) scale(0.5); opacity: 0.8; }
        .hero-gradient { 
            position: fixed; inset: 0; width: 45%; 
            background: linear-gradient(to right, rgba(241, 245, 249, 0.98), transparent); 
            pointer-events: none; z-index: 50; transition: 0.8s ease; opacity: 1; 
        }
        body.shrunk .hero-gradient { opacity: 0; }

        /* CONTROLS */
        .ctrl-group { position: fixed; top: 20px; right: 20px; z-index: 6000; display: flex; flex-direction: column; gap: 10px; pointer-events: auto; }
        .ctrl-btn { width: 40px; height: 40px; background: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.2); font-size: 18px; color: var(--text); transition: 0.2s; }
        .ctrl-btn:hover { transform: scale(1.1); }

        /* CHAPTERS BUTTON - Z-INDEX 5000 TO ENSURE CLICKABLE */
        .start-btn-container { position: fixed; bottom: 40px; left: 40px; z-index: 5000; transition: opacity 0.5s; pointer-events: auto; }
        .start-btn { background: white; color: var(--text); border: 1px solid var(--text); padding: 15px 40px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 3px; cursor: pointer; transition: 0.3s; }
        .start-btn:hover { background: var(--text); color: white; }

        /* NAVIGATION BAR - Z-INDEX 6000 */
        .nav-container {
            position: fixed; bottom: 0; left: 0; width: 100%; height: 90px;
            background: white; z-index: 6000;
            display: grid; grid-template-columns: 50px 1fr 50px 60px;
            box-shadow: 0 -5px 20px rgba(0,0,0,0.05);
            transform: translateY(100%); transition: transform 0.5s ease;
            pointer-events: auto;
        }
        body.journey-mode .nav-container { transform: translateY(0); }
        .nav-btn { display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 24px; color: #94a3b8; transition: background 0.2s; background: #fff; }
        .nav-btn:hover { background: #f8fafc; color: var(--accent); }
        .nav-btn.close { border-left: 1px solid #e2e8f0; color: #000; font-size: 28px; font-weight: 300; }
        
        /* SCROLL AREA WITH PADDING */
        .nav-scroll-area { 
            overflow-x: auto; scrollbar-width: none; scroll-behavior: smooth; 
            display: flex; align-items: flex-end; 
            padding-bottom: 25px; 
            padding-left: 60px; padding-right: 60px; 
        }
        .nav-scroll-area::-webkit-scrollbar { display: none; }
        .timeline-track { position: relative; height: 4px; background: #e2e8f0; margin: 0 auto; min-width: 100%; }
        .timeline-fill { position: absolute; top: 0; left: 0; height: 100%; background: var(--accent); transition: width 0.5s; }
        .nav-dot { position: absolute; top: -6px; width: 16px; height: 16px; background: #94a3b8; border: 3px solid white; border-radius: 50%; cursor: pointer; z-index: 50; transition: transform 0.2s; }
        .nav-dot.active { background: var(--accent); transform: scale(1.4); }
        .dot-label { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); font-family: 'Space Mono', monospace; font-size: 10px; color: #64748b; white-space: nowrap; pointer-events: none; }

        /* STORY MODE */
        #story-overlay { position: fixed; inset: 0; z-index: 2000; display: none; pointer-events: none; }
        body.story-mode #story-overlay { display: block; }
        #story-scroller { position: absolute; top: 0; right: 0; width: clamp(430px, 46vw, 760px); height: 100%; overflow-y: auto; background: linear-gradient(to right, rgba(241, 245, 249, 0), rgba(241, 245, 249, 0.95) 14%, rgba(248, 250, 252, 0.99)); scrollbar-width: none; pointer-events: auto; touch-action: pan-y; display: flex; flex-direction: column; gap: 18px; padding: 70px 34px 130px 34px; scroll-snap-type: y proximity; overscroll-behavior: contain; -webkit-overflow-scrolling: touch; }
        #story-scroller::-webkit-scrollbar { display: none; }
        .story-card { width: 100%; background: rgba(255, 255, 255, 0.94); border: 1px solid #e2e8f0; border-radius: 12px; padding: 22px; opacity: 0.55; transform: translateY(14px); transition: transform 0.35s ease, opacity 0.35s ease, box-shadow 0.35s ease; box-shadow: 0 14px 34px -20px rgba(15, 23, 42, 0.55); display: flex; flex-direction: column; gap: 14px; scroll-snap-align: center; }
        .story-card.active { opacity: 1; transform: translateY(0); box-shadow: 0 24px 42px -22px rgba(15, 23, 42, 0.65); }
        .story-card-title { margin: 0; font-family: 'Playfair Display', serif; font-size: clamp(1.4rem, 1.7vw, 2rem); line-height: 1.15; color: #0f172a; }
        .story-card-media { width: 100%; height: clamp(300px, 48vh, 620px); border-radius: 10px; background: #0f172a; overflow: hidden; display: flex; align-items: center; justify-content: center; }
        .story-card p { font-family: 'Inter', sans-serif; font-style: normal; font-size: clamp(1rem, 1.1vw, 1.1rem); line-height: 1.65; color: #1e293b; text-align: left; margin: 0; }
        .story-card img { width: 100%; height: 100%; object-fit: contain; object-position: center; border-radius: 10px; display: block; }
        
        .story-exit-btn { display: none; background: white; color: var(--text); border: 2px solid #e2e8f0; }
        body.story-mode .story-exit-btn { display: flex; }
        body.story-mode .story-marker-wrap { opacity: 0; pointer-events: none; transition: opacity 0.5s; }

        /* ICONS & DOTS */
        .story-marker-wrap { position: relative; width: 0; height: 0; }
        .story-dot { position: absolute; top: -15px; left: -15px; width: 30px; height: 30px; background: var(--story); border: 2px solid white; border-radius: 50%; box-shadow: 0 4px 15px rgba(0,0,0,0.4); cursor: pointer; display: flex; align-items: center; justify-content: center; animation: pulse 2s infinite; }
        @keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.1); } 100% { transform: scale(1); } }
        .story-dot svg { width: 16px; height: 16px; fill: white; }
        .story-bubble { position: absolute; bottom: 20px; left: -100px; width: 200px; background: white; padding: 8px 15px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); display: flex; align-items: center; justify-content: center; text-align: center; font-family: 'Playfair Display', serif; font-weight: bold; font-style: italic; color: var(--story); pointer-events: auto; cursor: pointer; opacity: 0; transform: translateY(10px) scale(0.8); transition: 0.3s; visibility: hidden; }
        .map-zoomed-in .story-dot { opacity: 0; pointer-events: none; } 
        .map-zoomed-in .story-bubble { opacity: 1; transform: translateY(0) scale(1); visibility: visible; }
        
        .bike-icon { font-size: 36px; transition: transform 0.1s linear, opacity 0.5s; opacity: 0; z-index: 2500 !important; }
        .bike-inner { display: inline-block; transform: scaleX(-1); }
        .bike-icon.visible { opacity: 1; }

        /* PANELS */
        #detail-panel { position: fixed; bottom: 40px; right: 30px; width: 400px; background: var(--card-bg); backdrop-filter: blur(20px); border-radius: 12px; padding: 20px; transform: translateY(200%); transition: transform 0.5s cubic-bezier(0.2, 1, 0.3, 1); box-shadow: 0 5px 30px rgba(0,0,0,0.15); z-index: 400; pointer-events: auto; }
        #detail-panel.open { transform: translateY(0); }
        #stage-card { position: fixed; top: 160px; left: 30px; width: 350px; max-height: 50vh; overflow-y: auto; scrollbar-width: none; background: var(--card-bg); backdrop-filter: blur(20px); border-radius: 12px; padding: 25px; transform: translateX(-150%); transition: transform 0.6s ease; pointer-events: auto; z-index: 400; }
        #stage-card.visible { transform: translateX(0); }
        @media (max-width: 768px) { 
            #stage-card { top: auto; bottom: 100px; left: 10px; right: 10px; width: auto; transform: translateY(150%); } 
            #stage-card.visible { transform: translateY(0); } 
            #detail-panel { left: 10px; right: 10px; width: auto; bottom: 20px; } 
            #story-scroller { width: 100%; height: 62%; top: auto; bottom: 0; padding: 16px 14px 120px 14px; gap: 14px; background: linear-gradient(to top, rgba(241, 245, 249, 1), rgba(241, 245, 249, 0.94)); scroll-snap-type: y proximity; } 
            .story-card { width: 100%; padding: 16px; opacity: 0.68; transform: translateY(0); } 
            .story-card.active { opacity: 1; transform: translateY(0); } 
            .story-card-title { font-size: 1.35rem; } 
            .story-card-media { height: min(52vw, 380px); } 
            .story-card p { font-size: 0.98rem; line-height: 1.55; } 
            .scroll-hint { bottom: 22%; right: 20px; left: auto; transform: none; } .scroll-hint::after { content: 'SWIPE →'; } 
        }

        /* GALLERY WINDOW */
        #gallery-window { 
            position: fixed; top: 20px; right: 5%; width: 600px; max-width: 90vw; max-height: 85vh; 
            background: white; border-radius: 12px; box-shadow: 0 20px 50px rgba(0,0,0,0.4); 
            display: none; flex-direction: column; overflow: hidden; z-index: 9999; 
        }
        #gallery-window.visible { display: flex; animation: popup 0.3s ease; opacity: 1; pointer-events: auto; }
        @keyframes popup { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
        #gallery-window.fullscreen { top: 0 !important; left: 0 !important; width: 100% !important; height: 100% !important; max-width: none; max-height: none; border-radius: 0; }
        @media (max-width: 768px) { #gallery-window { top: 0 !important; left: 0 !important; width: 100% !important; height: 100% !important; border-radius: 0; } .gal-header { padding-top: 10px; } .gal-close { position: absolute; bottom: 20px; right: 20px; background: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 10px rgba(0,0,0,0.3); z-index: 1000; } }
        
        .gal-header { height: 40px; background: #f1f5f9; display: flex; justify-content: space-between; align-items: center; padding: 0 10px; cursor: move; }
        .gal-controls { display: flex; gap: 10px; }
        .gal-btn { cursor: pointer; font-size: 20px; color: #64748b; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; border-radius: 4px; }
        .gal-btn:hover { background: #e2e8f0; }
        .gal-content { position: relative; flex: 1; background: black; display: flex; align-items: center; justify-content: center; overflow: hidden; }
        .gal-content img, .gal-content video { max-width: 100%; max-height: 100%; object-fit: contain; }
        .gal-touch-area { position: absolute; top: 0; height: 100%; width: 25%; z-index: 100; cursor: pointer; }
        .gal-touch-left { left: 0; } .gal-touch-right { right: 0; }
        .thumb-grid { display: flex; gap: 8px; margin-top: 15px; overflow-x: auto; scrollbar-width: none; }
        .thumb-wrap { flex: 0 0 100px; height: 70px; border-radius: 6px; overflow: hidden; cursor: pointer; flex-shrink: 0; }
        .thumb-wrap img { width: 100%; height: 100%; object-fit: cover; }
        .chart-toggle { cursor: pointer; padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; background: #eee; color: #666; }
        .chart-toggle.active { background: var(--accent); color: white; }
        .dev-label { color: #000; font-family: 'Space Mono', monospace; font-size: 14px; font-weight: 900; text-shadow: 2px 0 #fff, -2px 0 #fff, 0 2px #fff, 0 -2px #fff, 1px 1px #fff, -1px -1px #fff, 1px -1px #fff, -1px 1px #fff; white-space: nowrap; pointer-events: none; }
        .scroll-hint { position: fixed; bottom: 30px; left: 75%; transform: translateX(-50%); color: #000; font-family: 'Space Mono', monospace; font-size: 14px; letter-spacing: 2px; font-weight: bold; text-shadow: 0 0 10px rgba(255,255,255,0.8); animation: bounce 2s infinite; opacity: 0; transition: opacity 0.5s; z-index: 3000; pointer-events: none; }
        .scroll-hint::after { content: 'SCROLL ↓'; }
        @media (max-width: 768px) { .scroll-hint { bottom: 22%; right: 20px; left: auto; transform: none; } .scroll-hint::after { content: 'SWIPE ↑'; } }
        .map-chapter-thumb { width: 40px !important; height: 40px !important; border-radius: 4px; border: 2px solid white; box-shadow: 0 2px 8px rgba(0,0,0,0.3); overflow: hidden; background: white; opacity: 0; transform: translateY(10px); transition: transform 0.3s ease, opacity 0.3s ease, box-shadow 0.3s ease; }
        .map-chapter-thumb img { width: 100% !important; height: 100% !important; object-fit: cover !important; margin: 0 !important; }
        .map-chapter-thumb.visible { opacity: 1; transform: translateY(0); }
        .map-chapter-thumb.active { transform: translateY(-6px) scale(1.1); box-shadow: 0 8px 20px rgba(0,0,0,0.35); }
    </style>
</head>
<body id="main-body">
    <div id="map-container"><div id="map"></div></div>
    <div class="hero-gradient"></div>

    <div class="ctrl-group interactive">
        <div id="map-toggle-btn" class="ctrl-btn" onclick="cycleMap()" title="Change Map Type">🛰</div>
        <div class="ctrl-btn" onclick="resetView()" title="Reset View">&#8635;</div>
        <div class="ctrl-btn story-exit-btn" id="story-exit-btn" onclick="exitStory()" title="Exit Story">×</div>
    </div>

    <div class="hero">
        <div class="hero-content">
            <h1 class="italic text-slate-800 mb-4">Cycling East</h1>
            <p class="text-sm uppercase tracking-[0.3em] text-slate-500">Leeds → Hong Kong &bull; {{ distance }} KM</p>
        </div>
    </div>

    <div class="start-btn-container" id="chapter-btn-wrap"><button onclick="startJourney()" class="start-btn">Chapters</button></div>
    
    <div id="stage-card" class="interactive">
        <h2 id="st-title" class="text-3xl text-accent mb-1 italic">Title</h2>
        <p id="st-date" class="text-xs text-slate-400 mono mb-2 pl-3 border-l-2 border-slate-300 uppercase">Date</p>
        <p id="st-desc" class="text-slate-600 text-sm leading-relaxed mb-4 line-clamp-3">Desc</p>
        <div id="st-thumbs" class="thumb-grid"></div>
    </div>
    
    <div id="detail-panel" class="interactive">
        <div class="flex justify-between items-start mb-2">
            <div><h2 id="p-day" class="text-xl text-accent italic">Day X</h2><p id="p-date" class="text-[10px] mono uppercase">Date</p></div>
            <button onclick="closePanel()" class="text-slate-400 text-xl">&times;</button>
        </div>
        <div class="flex justify-between items-end mb-2 pb-2 border-b border-slate-100">
            <div class="flex gap-4 mono text-[10px] text-slate-500"><span><b id="p-dist"></b> KM</span><span><b id="p-time"></b> RIDING</span></div>
            <div class="flex gap-1">
                <span id="btn-ele" class="chart-toggle active" onclick="switchChart('ele')">ELEV</span>
                <span id="btn-speed" class="chart-toggle" onclick="switchChart('speed')">SPEED</span>
            </div>
        </div>
        <div class="h-24 md:h-40 w-full"><canvas id="elChart"></canvas></div>
    </div>
    
    <div class="nav-container interactive" id="nav-container">
        <div class="nav-btn" onclick="scrollNav(-1)">‹</div>
        <div class="nav-scroll-area" id="nav-scroll-area">
            <div class="timeline-track" id="timeline-track"><div class="timeline-fill" id="timeline-fill"></div></div>
        </div>
        <div class="nav-btn" onclick="scrollNav(1)">›</div>
        <div class="nav-btn close" onclick="exitJourneyMode()">×</div>
    </div>

    <div id="gallery-window" class="interactive">
        <div class="gal-header" id="gal-header">
            <span style="font-size:12px; color:#94a3b8; font-weight:bold; letter-spacing:1px;">GALLERY</span>
            <div class="gal-controls">
                <div class="gal-btn" onclick="toggleFullscreen()">⤢</div>
                <div class="gal-btn" onclick="closeGallery()">×</div>
            </div>
        </div>
        <div class="gal-content">
            <div class="gal-touch-area" onclick="changeSlide(-1)"></div>
            <div class="gal-touch-area" onclick="changeSlide(1)" style="right:0"></div>
            <img id="gal-img" src="">
            <video id="gal-vid" controls playsinline style="display:none"></video>
        </div>
    </div>

    <div id="story-overlay">
        <div class="story-scroller" id="story-scroller" onscroll="onStoryScroll()"></div>
        <div class="scroll-hint" id="scroll-hint"></div>
    </div>

    <script>
        const routes = {{ routes|tojson }};
        const STAGES = {{ stages|tojson }};
        const STORIES = {{ stories|tojson }};
    </script>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const isMobile = window.innerWidth < 768;
        
        var map = L.map('map', { zoomControl: false, attributionControl: false, renderer: L.canvas() }).setView([50, 0], 4);
        const layers = {
            voyager: L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', { maxZoom: 19 }),
            satellite: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19 }),
            topo: L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', { maxZoom: 17, attribution: 'Map data: © OpenStreetMap SRTM | Map style: © OpenTopoMap' })
        };
        layers.voyager.addTo(map);
        let currentMapMode = 'voyager';

        function cycleMap() {
            map.removeLayer(layers[currentMapMode]);
            const btn = document.getElementById('map-toggle-btn');
            if (currentMapMode === 'voyager') { currentMapMode = 'satellite'; btn.innerHTML = '⛰️'; }
            else if (currentMapMode === 'satellite') { currentMapMode = 'topo'; btn.innerHTML = '🗺️'; }
            else { currentMapMode = 'voyager'; btn.innerHTML = '🛰️'; }
            layers[currentMapMode].addTo(map);
        }

        let activeChart = null, currentRouteData = null, chartType = 'ele', routeLayers = [];
        let bikeMarker = null, storyChapterMarkers = [], currentStoryPoints = [], routeDistances = [], totalRouteLength = 0;
        let allPoints = [], devLabels = [], storyMarkers = [], isDevMode = false;
        let savedMapState = null, storyChapters = [], userInteracting = false;
        let storyScrollTicking = false;
        let currStg = 0, currImg = 0;

        // Render Routes
        routes.forEach((route, idx) => {
            allPoints.push(...route.coords);
            const visual = L.polyline(route.coords, { color: '#e63946', weight: 3, opacity: 0 }).addTo(map);
            routeLayers.push(visual);
            const hit = L.polyline(route.coords, { color: 'transparent', weight: 30, opacity: 0, zIndexOffset: 1000 }).addTo(map);
            hit.on('mouseover', () => { visual.setStyle({ color: '#1d3557', weight: 5, opacity: 1 }); });
            hit.on('mouseout', () => { visual.setStyle({ color: '#e63946', weight: 3, opacity: 0.9 }); });
            hit.on('click', (e) => { L.DomEvent.stopPropagation(e); showDetail(route); });
        });

        // Render Story Markers
        STORIES.forEach(story => {
            const html = `<div class="story-marker-wrap"><div class="story-dot"><svg viewBox="0 0 512 512"><path d="M496 128v16a8 8 0 0 1-8 8h-24v12c0 6.627-5.373 12-12 12H60c-6.627 0-12-5.373-12-12v-12H24a8 8 0 0 1-8-8v-16a8 8 0 0 1 4.941-7.392l232-88a7.996 7.996 0 0 1 6.118 0l232 88A8 8 0 0 1 496 128zm-24 104v144c0 17.673-14.327 32-32 32H72c-17.673 0-32-14.327-32-32V232c0-17.673 14.327-32 32-32h368c17.673 0 32 14.327 32 32zM80 400h352v-24H80v24zm352-56v-24H80v24h352z"/></svg></div><div class="story-bubble">${story.title}</div></div>`;
            const m = L.marker(story.location, { icon: L.divIcon({ className: 'story-div-icon', html: html }) }).addTo(map).on('click', (e) => { L.DomEvent.stopPropagation(e); startStory(story); });
            storyMarkers.push({ marker: m, dayIdx: story.closest_segment });
        });

        function shrinkHero() { if(userInteracting) document.body.classList.add('shrunk'); }
        ['mousedown', 'touchstart', 'wheel', 'keydown'].forEach(evt => window.addEventListener(evt, () => { userInteracting = true; shrinkHero(); }));
        map.on('dragstart', () => { userInteracting = true; shrinkHero(); });

        // UNIVERSAL CLOSE FUNCTION
        function closeAllModes() {
            document.body.classList.remove('journey-mode', 'story-mode');
            document.getElementById('stage-card').classList.remove('visible');
            document.getElementById('chapter-btn-wrap').style.display = 'block';
            document.getElementById('nav-container').style.transform = 'translateY(100%)';
            closePanel();
            if(bikeMarker) map.removeLayer(bikeMarker);
            storyChapterMarkers.forEach(m => map.removeLayer(m));
        }

        window.addEventListener('keydown', (e) => {
            if(e.key === '`' || e.key === '~') { 
                isDevMode = !isDevMode; 
                devLabels.forEach(l => isDevMode ? l.addTo(map) : map.removeLayer(l)); 
            }
            if(document.getElementById('gallery-window').classList.contains('visible')) {
                if(e.key === 'ArrowLeft') changeSlide(-1);
                if(e.key === 'ArrowRight') changeSlide(1);
                if(e.key === 'Escape') closeGallery();
            }
        });

        window.addEventListener('load', () => {
            if(allPoints.length) {
                let bp = allPoints; if(isMobile) bp = allPoints.slice(0, Math.floor(allPoints.length * 0.2));
                map.fitBounds(L.polyline(bp).getBounds(), { paddingTopLeft: isMobile ? [20,20] : [window.innerWidth*0.2, 50], paddingBottomRight: [50, 50] });
                setTimeout(() => { requestAnimationFrame(() => { routeLayers.forEach((l, i) => setTimeout(() => { l.setStyle({opacity:1, color:'#fff', weight:4}); setTimeout(()=>l.setStyle({color:'#e63946', weight:3, opacity: 0.9}), 100); }, i*20)); }); }, 800);
                routes.forEach((r, i) => { const mid = r.coords[Math.floor(r.coords.length/2)]; devLabels.push(L.marker(mid, { icon: L.divIcon({ className: 'dev-label', html: i }) })); });
            }
        });

        map.on('zoomend', () => {
            const el = document.getElementById('map-container');
            if(map.getZoom() >= 7) el.classList.add('map-zoomed-in');
            else el.classList.remove('map-zoomed-in');
        });

        // --- DRAGGABLE GALLERY ---
        const galWin = document.getElementById('gallery-window');
        const galHead = document.getElementById('gal-header');
        let isDrag = false, sx, sy, lx, ly;

        galHead.addEventListener('mousedown', (e) => {
            if(galWin.classList.contains('fullscreen')) return;
            isDrag = true; sx = e.clientX; sy = e.clientY;
            lx = galWin.offsetLeft; ly = galWin.offsetTop;
            galWin.classList.add('dragging');
        });
        window.addEventListener('mousemove', (e) => {
            if(!isDrag) return;
            galWin.style.left = `${lx + (e.clientX - sx)}px`;
            galWin.style.top = `${ly + (e.clientY - sy)}px`;
            galWin.style.right = 'auto'; 
        });
        window.addEventListener('mouseup', () => { isDrag = false; galWin.classList.remove('dragging'); });

        function openLB(sIdx, iIdx) { currStg = sIdx; currImg = iIdx; updateGallery(); galWin.classList.add('visible'); userInteracting = true; shrinkHero(); }
        function closeGallery() { galWin.classList.remove('visible'); document.getElementById('gal-vid').pause(); }
        function updateGallery() {
            const url = STAGES[currStg].images[currImg];
            const isVid = url.match(/\.(mp4|mov)$/i);
            const v = document.getElementById('gal-vid'), i = document.getElementById('gal-img');
            if(isVid) { i.style.display='none'; v.style.display='block'; v.src=url; v.play(); } 
            else { v.pause(); v.style.display='none'; i.style.display='block'; i.src=url; }
        }
        function changeSlide(dir) { const imgs = STAGES[currStg].images; currImg = (currImg + dir + imgs.length) % imgs.length; updateGallery(); }
        function toggleFullscreen() { galWin.classList.toggle('fullscreen'); }

        // --- MATH HELPERS ---
        function setupMath(p) { routeDistances = [0]; totalRouteLength = 0; for(let i=1; i<p.length; i++) { totalRouteLength += map.distance(p[i-1], p[i]); routeDistances.push(totalRouteLength); } }
        function getPtAtD(d) { for(let i=1; i<routeDistances.length; i++) { if(routeDistances[i] >= d) { const frac = (d - routeDistances[i-1]) / (routeDistances[i] - routeDistances[i-1]); return [currentStoryPoints[i-1][0] + (currentStoryPoints[i][0] - currentStoryPoints[i-1][0]) * frac, currentStoryPoints[i-1][1] + (currentStoryPoints[i][1] - currentStoryPoints[i-1][1]) * frac]; } } return currentStoryPoints[currentStoryPoints.length-1]; }

        // --- STORY MODE ---
        function startStory(s) {
            closeAllModes(); 
            userInteracting = true; shrinkHero();
            document.body.classList.add('story-mode'); 
            savedMapState = { center: map.getCenter(), zoom: map.getZoom() };
            storyChapters = s.chapters || [];
            storyChapterMarkers = [];
            
            const sc = document.getElementById('story-scroller'); sc.innerHTML = ''; sc.scrollTop = 0; sc.scrollLeft = 0;
            const spacer = document.createElement('div'); spacer.style.height = isMobile ? '20vh' : '26vh'; spacer.style.width = '100%'; spacer.style.flexShrink = '0'; sc.appendChild(spacer);
            const maxP = s.max_progress || 1.0;
            const chapterProgresses = storyChapters.map(c => Math.max(0, Math.min(1, (c.progress || 0) * maxP)));

            if(s.chapters) {
                s.chapters.forEach((c, i) => {
                    const d = document.createElement('div');
                    d.className = 'story-card';
                    d.dataset.progress = `${chapterProgresses[i] || 0}`;
                    d.innerHTML = `<h3 class="story-card-title">${s.title}</h3><div class="story-card-media"><img src="${c.image}" loading="lazy" decoding="async" alt="${(s.title || 'Story') + ' chapter ' + (i + 1)}"></div><p>${c.text}</p>`;
                    sc.appendChild(d);
                });
            }
            
            const trail = document.createElement('div'); trail.style.height = isMobile ? '24vh' : '30vh'; trail.style.width = '100%'; trail.style.flexShrink = '0'; sc.appendChild(trail);
            document.getElementById('scroll-hint').style.opacity = '1';

            currentStoryPoints = []; 
            if(s.route_segment_ids) s.route_segment_ids.forEach(id => { if(routes[id]) currentStoryPoints.push(...routes[id].coords); });
            
            if(currentStoryPoints.length > 0) {
                setupMath(currentStoryPoints);
                bikeMarker = L.marker(currentStoryPoints[0], { icon: L.divIcon({ className: 'bike-icon', html: '<div class="bike-inner">🚴</div>', iconSize:[30,30] }), zIndexOffset: 2000 }).addTo(map);
                setTimeout(() => bikeMarker._icon.classList.add('visible'), 100);
                
                if(s.chapters) {
                    s.chapters.forEach((c, i) => {
                        const progress = chapterProgresses[i] || 0;
                        const pt = getPtAtD(progress * totalRouteLength);
                        const tm = L.marker(pt, { icon: L.divIcon({ className: 'map-chapter-thumb', html: `<img src="${c.image}">`, iconSize: [30, 30] }) }).addTo(map);
                        setTimeout(() => tm._icon.classList.add('visible'), 500 + (i*200)); storyChapterMarkers.push(tm);
                    });
                }

                const pad = isMobile ? [20, 100] : [window.innerWidth * 0.6, 50];
                map.flyToBounds(L.polyline(currentStoryPoints).getBounds(), { paddingBottomRight: pad, maxZoom: 13, duration: 1.5 });
            } else {
                map.flyTo(s.location, 10);
            }
            setTimeout(checkStoryScroll, 120);
        }

        function onStoryScroll() {
            if(storyScrollTicking) return;
            storyScrollTicking = true;
            requestAnimationFrame(() => {
                checkStoryScroll();
                storyScrollTicking = false;
            });
        }

        function checkStoryScroll() {
            const sc = document.getElementById('story-scroller');
            const cards = Array.from(document.querySelectorAll('.story-card'));
            if(cards.length === 0) return;

            let currS = sc.scrollTop;
            if(currS > 10) document.getElementById('scroll-hint').style.opacity = '0';

            const scRect = sc.getBoundingClientRect();
            const viewportCenter = scRect.top + scRect.height / 2;
            const centers = cards.map(c => {
                const box = c.getBoundingClientRect();
                return box.top + box.height / 2;
            });

            let lowIdx = 0;
            let highIdx = 0;
            let localPct = 0;

            if(viewportCenter <= centers[0]) {
                lowIdx = 0;
                highIdx = 0;
            } else if(viewportCenter >= centers[centers.length - 1]) {
                lowIdx = centers.length - 1;
                highIdx = centers.length - 1;
            } else {
                for(let i = 0; i < centers.length - 1; i++) {
                    if(viewportCenter >= centers[i] && viewportCenter <= centers[i + 1]) {
                        lowIdx = i;
                        highIdx = i + 1;
                        const span = Math.max(1, centers[i + 1] - centers[i]);
                        localPct = (viewportCenter - centers[i]) / span;
                        break;
                    }
                }
            }

            const lowProgress = parseFloat(cards[lowIdx].dataset.progress || '0');
            const highProgress = parseFloat(cards[highIdx].dataset.progress || '0');
            const currentP = lowProgress + (highProgress - lowProgress) * localPct;

            if(totalRouteLength > 0) {
                if(bikeMarker) {
                    bikeMarker.setLatLng(getPtAtD(currentP * totalRouteLength));
                    const bikePx = map.latLngToContainerPoint(bikeMarker.getLatLng());
                    const w = window.innerWidth, h = window.innerHeight;
                    let mX = isMobile ? 20 : 45, MX = isMobile ? w-20 : w*0.44-45, mY = 45, MY = isMobile ? h*0.38 : h-45;
                    if (bikePx.x < mX || bikePx.x > MX || bikePx.y < mY || bikePx.y > MY) {
                        map.panBy([bikePx.x - (isMobile ? w/2 : w*0.22), bikePx.y - (isMobile ? h*0.2 : h/2)], {animate: true, duration: 0.9});
                    }
                }
            }

            const activeIdx = localPct < 0.5 ? lowIdx : highIdx;
            cards.forEach((c, i) => {
                c.classList.toggle('active', i === activeIdx);
                const marker = storyChapterMarkers[i];
                if(marker && marker._icon) marker._icon.classList.toggle('active', i === activeIdx);
            });
        }

        window.addEventListener('resize', () => {
            isMobile = window.innerWidth < 768;
            if(document.body.classList.contains('story-mode')) setTimeout(checkStoryScroll, 120);
        });

        // --- JOURNEY (CHAPTERS) MODE ---
        function startJourney() { 
            closeAllModes(); 
            userInteracting = true; shrinkHero();
            document.body.classList.add('journey-mode'); 
            document.getElementById('chapter-btn-wrap').style.display = 'none';
            setupTimeline();
            
            // Force Show Navbar
            document.getElementById('nav-container').style.transform = 'translateY(0)';
            document.getElementById('nav-scroll-area').scrollLeft = 0;
        }

        function setupTimeline() {
            const track = document.getElementById('timeline-track');
            if(track.querySelectorAll('.nav-dot').length === 0) {
                const minWidth = Math.max(100, STAGES.length * 15); 
                track.style.minWidth = isMobile ? "200%" : `${minWidth}%`;
                STAGES.forEach((s, i) => {
                    const d = document.createElement('div'); d.className = 'nav-dot';
                    d.style.left = `${(i / (STAGES.length - 1)) * 100}%`;
                    d.onclick = () => setStage(i);
                    d.innerHTML = `<div class="dot-label">${s.title}</div>`; 
                    track.appendChild(d);
                });
            }
        }

        function setStage(index) {
            const s = STAGES[index]; 
            document.getElementById('st-title').innerText = s.title; 
            document.getElementById('st-date').innerText = s.date_range; 
            document.getElementById('st-desc').innerText = s.description; 
            
            const tc = document.getElementById('st-thumbs'); tc.innerHTML = ''; 
            s.images.forEach((u, i) => tc.innerHTML += `<div class="thumb-wrap" onclick="openLB(${index}, ${i})"><img src="${u}"></div>`); 
            
            document.getElementById('timeline-fill').style.width = `${(index / (STAGES.length - 1)) * 100}%`; 
            document.querySelectorAll('.nav-dot').forEach((d, i) => d.classList.toggle('active', i === index)); 
            document.getElementById('stage-card').classList.add('visible'); 
            
            let pts = []; for(let i=s.start_index; i<=s.end_index; i++) { if(routes[i]) pts.push(...routes[i].coords); } 
            if(pts.length) map.flyToBounds(L.polyline(pts).getBounds(), { padding: [100,100], duration: 2 });
        }

        // --- GRAPH MODE ---
        function showDetail(d) { 
            closeAllModes(); 
            userInteracting = true; shrinkHero();
            currentRouteData = d; 
            document.getElementById('p-day').innerText = `Day ${d.day}`; 
            document.getElementById('p-date').innerText = d.date || 'Unknown Date'; 
            document.getElementById('p-dist').innerText = d.distance; 
            document.getElementById('p-time').innerText = d.duration; 
            document.getElementById('detail-panel').classList.add('open'); 
            
            // Default to Elevation when opening
            switchChart('ele'); 
        }
        
        function switchChart(t) { 
            chartType = t; 
            document.getElementById('btn-ele').className = `chart-toggle ${t === 'ele' ? 'active' : ''}`;
            document.getElementById('btn-speed').className = `chart-toggle ${t === 'speed' ? 'active' : ''}`;
            renderChart(); 
        }

        function renderChart() {
            if(!currentRouteData) return;
            const ctx = document.getElementById('elChart').getContext('2d');
            if(activeChart) activeChart.destroy();
            const isEle = chartType === 'ele';
            const dist = parseFloat(currentRouteData.distance);
            const len = currentRouteData.elevation.length;
            const labels = Array.from({length: len}, (_, i) => ((i / (len - 1)) * dist).toFixed(1));

            activeChart = new Chart(ctx, {
                type: 'line',
                data: { 
                    labels: labels, 
                    datasets: [{ 
                        data: isEle ? currentRouteData.elevation : currentRouteData.speed, 
                        borderColor: isEle ? '#e63946' : '#457b9d', 
                        backgroundColor: isEle ? 'rgba(230, 57, 70, 0.1)' : 'rgba(69, 123, 157, 0.1)', 
                        fill: true, pointRadius: 0, borderWidth: 2, tension: 0.2 
                    }] 
                },
                options: { 
                    responsive: true, maintainAspectRatio: false, 
                    plugins: { legend: { display: false } }, 
                    onClick: (e) => { 
                        const pts = activeChart.getElementsAtEventForMode(e, 'nearest', { intersect: true }, true); 
                        if(pts.length) { 
                            const pct = pts[0].index / len; 
                            map.flyTo(currentRouteData.coords[Math.floor(pct * currentRouteData.coords.length)], 14); 
                        } 
                    }, 
                    scales: { 
                        x: { display: true, title: { display: true, text: 'Distance (km)', color: '#94a3b8' }, ticks: { color: '#94a3b8', maxTicksLimit: 8, maxRotation: 0 }, grid: { display: false } }, 
                        y: { display: true, title: { display: true, text: isEle ? 'Elev (m)' : 'Speed (km/h)', color: '#94a3b8' }, ticks: { color: '#94a3b8' }, grid: { color: '#f1f5f9', borderDash: [4, 4] } } 
                    } 
                }
            });
        }

        // --- GLOBAL EXITS ---
        function exitStory() { closeAllModes(); if(savedMapState) map.flyTo(savedMapState.center, savedMapState.zoom, { duration: 1.5 }); }
        function exitJourneyMode() { closeAllModes(); }
        function closePanel() { document.getElementById('detail-panel').classList.remove('open'); }
        function scrollNav(dir) { document.getElementById('nav-scroll-area').scrollBy({ left: dir * 200, behavior: 'smooth' }); }
        function resetView() { closeAllModes(); let bp = allPoints; if(isMobile) bp = allPoints.slice(0, Math.floor(allPoints.length * 0.2)); map.fitBounds(L.polyline(bp).getBounds(), { padding: [50, 50], duration: 1.5 }); }
        
    </script>
</body>
</html>
"""

# IMPORTANT FLASK ROUTE: Do NOT delete this!
@app.route('/')
def index():
    routes, stages, stories, dist = load_data_final()
    return render_template_string(HTML_TEMPLATE, routes=routes, stages=stages, stories=stories, distance=dist)

if __name__ == '__main__':
    app.run(debug=True)
