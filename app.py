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

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def load_data_v62():
    routes = []
    total_dist = 0
    file_dates = {}
    
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
        except: pass

    stages = []
    if os.path.exists(STAGES_DIR):
        stage_files = sorted([f for f in os.listdir(STAGES_DIR) if f.endswith('.json')], key=natural_sort_key)
        for sf in stage_files:
            try:
                with open(os.path.join(STAGES_DIR, sf), 'r') as f:
                    d = json.load(f)
                    s = str(d.get('start_index',0)); e = str(d.get('end_index',0))
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
            except: pass

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
                        
                        prefix = s.get('img_prefix', '')
                        max_prog = 0
                        if 'chapters' in s:
                            for chap in s['chapters']:
                                if 'progress' in chap and chap['progress'] > max_prog: max_prog = chap['progress']
                                if prefix and not chap['image'].startswith('http'):
                                    chap['image'] = prefix + chap['image']
                        
                        s['max_progress'] = max_prog if max_prog > 0 else 1.0
                        s['thumb'] = s['chapters'][0].get('image', '') if 'chapters' in s and s['chapters'] else ""
                        stories.append(s)
                except: pass

    return routes, stages, stories, total_dist

CACHED_ROUTES, CACHED_STAGES, CACHED_STORIES, CACHED_DIST = load_data_v62()

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
        
        /* GRADIENT: Visible initially (Opacity 1), Hidden when shrunk (Opacity 0) */
        .hero-gradient { 
            position: fixed; inset: 0; width: 45%; 
            background: linear-gradient(to right, rgba(241, 245, 249, 0.98), transparent); 
            pointer-events: none; z-index: 50; 
            transition: opacity 0.8s ease; 
            opacity: 1; /* VISIBLE START */
        }
        body.shrunk .hero-gradient { opacity: 0; } /* HIDDEN AFTER INTERACTION */

        /* CONTROLS */
        .ctrl-group { position: fixed; top: 20px; right: 20px; z-index: 6000; display: flex; flex-direction: column; gap: 10px; pointer-events: auto; }
        .ctrl-btn { width: 40px; height: 40px; background: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.2); font-size: 18px; color: var(--text); transition: 0.2s; }
        .ctrl-btn:hover { transform: scale(1.1); }

        .start-btn-container { position: fixed; bottom: 40px; left: 40px; z-index: 300; transition: opacity 0.5s; pointer-events: auto; }
        .start-btn { background: white; color: var(--text); border: 1px solid var(--text); padding: 15px 40px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 3px; cursor: pointer; transition: 0.3s; }
        .start-btn:hover { background: var(--text); color: white; }

        /* NAVIGATION BAR */
        .nav-container {
            position: fixed; bottom: 0; left: 0; width: 100%; height: 90px;
            background: white; z-index: 500;
            display: grid; grid-template-columns: 50px 1fr 50px 60px;
            box-shadow: 0 -5px 20px rgba(0,0,0,0.05);
            transform: translateY(100%); transition: transform 0.5s ease;
            pointer-events: auto;
        }
        body.journey-mode .nav-container { transform: translateY(0); }
        .nav-btn { display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 24px; color: #94a3b8; transition: background 0.2s; background: #fff; }
        .nav-btn:hover { background: #f8fafc; color: var(--accent); }
        .nav-btn.close { border-left: 1px solid #e2e8f0; color: #000; font-size: 28px; font-weight: 300; }
        .nav-scroll-area { overflow-x: auto; scrollbar-width: none; scroll-behavior: smooth; display: flex; align-items: flex-end; padding-bottom: 25px; padding-left: 40px; padding-right: 40px; }
        .timeline-track { position: relative; height: 4px; background: #e2e8f0; margin: 0 auto; min-width: 100%; }
        .timeline-fill { position: absolute; top: 0; left: 0; height: 100%; background: var(--accent); transition: width 0.5s; }
        .nav-dot { position: absolute; top: -6px; width: 16px; height: 16px; background: #94a3b8; border: 3px solid white; border-radius: 50%; cursor: pointer; z-index: 50; transition: transform 0.2s; }
        .nav-dot.active { background: var(--accent); transform: scale(1.4); }
        .dot-label { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); font-family: 'Space Mono', monospace; font-size: 10px; color: #64748b; white-space: nowrap; pointer-events: none; }

        /* STORY MODE */
        #story-overlay { position: fixed; inset: 0; z-index: 2000; display: none; pointer-events: none; }
        body.story-mode #story-overlay { display: block; }
        #story-scroller { position: absolute; top: 0; right: 0; width: 60%; height: 100%; overflow-y: auto; background: linear-gradient(to right, transparent, rgba(241, 245, 249, 0.98)); scrollbar-width: none; pointer-events: auto; }
        .story-card { background: white; margin: 0 10% 50vh 10%; padding: 30px; border-radius: 8px; opacity: 0.3; transition: 0.5s; box-shadow: 0 15px 40px -5px rgba(0,0,0,0.15); display: flex; flex-direction: column; align-items: center; }
        .story-card.active { opacity: 1; transform: scale(1.02); }
        .story-card p { font-family: 'Playfair Display', serif; font-style: italic; font-size: 1.2rem; color: #1d3557; text-align: center; margin-bottom: 20px; order: 1; }
        .story-card img { width: 100%; height: auto; object-fit: cover; border-radius: 4px; order: 2; }
        .story-exit-btn { display: none; background: white; color: var(--text); border: 2px solid #e2e8f0; }
        body.story-mode .story-exit-btn { display: flex; }

        /* DEV MODE LABELS */
        .dev-label {
            color: #000; font-family: 'Space Mono', monospace; font-size: 14px; font-weight: 900;
            text-shadow: 2px 0 #fff, -2px 0 #fff, 0 2px #fff, 0 -2px #fff, 1px 1px #fff, -1px -1px #fff, 1px -1px #fff, -1px 1px #fff;
            white-space: nowrap; pointer-events: none;
        }

        /* ICONS & DOTS */
        .story-marker-wrap { position: relative; width: 0; height: 0; }
        .story-dot { position: absolute; top: -15px; left: -15px; width: 30px; height: 30px; background: var(--story); border: 2px solid white; border-radius: 50%; box-shadow: 0 4px 15px rgba(0,0,0,0.4); cursor: pointer; display: flex; align-items: center; justify-content: center; animation: pulse 2s infinite; }
        @keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.1); } 100% { transform: scale(1); } }
        .story-dot svg { width: 16px; height: 16px; fill: white; }
        .story-bubble { position: absolute; bottom: 20px; left: -100px; width: 200px; background: white; padding: 8px 15px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); display: flex; align-items: center; justify-content: center; text-align: center; font-family: 'Playfair Display', serif; font-weight: bold; font-style: italic; color: var(--story); pointer-events: auto; cursor: pointer; opacity: 0; transform: translateY(10px) scale(0.8); transition: 0.3s; visibility: hidden; }
        .map-zoomed-in .story-dot { opacity: 0; pointer-events: none; } 
        .map-zoomed-in .story-bubble { opacity: 1; transform: translateY(0) scale(1); visibility: visible; }
        
        body.story-mode .story-marker-wrap { opacity: 0; pointer-events: none; transition: opacity 0.5s; }

        .bike-icon { font-size: 36px; transition: transform 0.1s linear, opacity 0.5s; opacity: 0; z-index: 2500 !important; }
        .bike-inner { display: inline-block; transform: scaleX(-1); }
        .bike-icon.visible { opacity: 1; }

        /* GRAPH POPUP */
        #detail-panel { position: fixed; bottom: 40px; right: 30px; width: 400px; background: var(--card-bg); backdrop-filter: blur(20px); border-radius: 12px; padding: 20px; transform: translateY(200%); transition: transform 0.5s cubic-bezier(0.2, 1, 0.3, 1); box-shadow: 0 5px 30px rgba(0,0,0,0.15); z-index: 400; pointer-events: auto; }
        #detail-panel.open { transform: translateY(0); }
        
        #stage-card { position: fixed; top: 160px; left: 30px; width: 350px; max-height: 50vh; overflow-y: auto; scrollbar-width: none; background: var(--card-bg); backdrop-filter: blur(20px); border-radius: 12px; padding: 25px; transform: translateX(-150%); transition: transform 0.6s ease; pointer-events: auto; z-index: 400; }
        #stage-card.visible { transform: translateX(0); }
        
        @media (max-width: 768px) {
            #stage-card { top: auto; bottom: 100px; left: 10px; right: 10px; width: auto; transform: translateY(150%); }
            #stage-card.visible { transform: translateY(0); }
            #detail-panel { left: 10px; right: 10px; width: auto; bottom: 20px; }
            #story-scroller { width: 100%; height: 45%; top: auto; bottom: 0; display: flex; flex-direction: row; overflow-x: auto; overflow-y: hidden; padding: 0; background: linear-gradient(to top, rgba(241, 245, 249, 1), rgba(241, 245, 249, 0.9)); alignItems: center; scroll-snap-type: x mandatory; }
            .story-card { flex: 0 0 85vw; margin: 0 10px; height: auto; max-height: 90%; opacity: 0.5; scroll-snap-align: center; margin-bottom: 0; padding: 20px; justify-content: center; }
            .story-card.active { opacity: 1; transform: scale(1); }
            .scroll-hint { bottom: 22%; right: 20px; left: auto; transform: none; } .scroll-hint::after { content: 'SWIPE →'; }
        }

        #gallery-window { position: fixed; top: 20px; right: 5%; width: 600px; max-width: 90vw; max-height: 85vh; background: white; border-radius: 12px; box-shadow: 0 20px 50px rgba(0,0,0,0.4); display: none; flex-direction: column; overflow: hidden; z-index: 5000; }
        #gallery-window.visible { display: flex; animation: popup 0.3s ease; }
        @media (max-width: 768px) { #gallery-window { top: 0 !important; left: 0 !important; width: 100% !important; height: 100% !important; border-radius: 0; } .gal-header { padding-top: 10px; } .gal-close { position: absolute; bottom: 20px; right: 20px; background: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 10px rgba(0,0,0,0.3); z-index: 1000; } }
        .gal-header { height: 30px; background: #f1f5f9; display: flex; justify-content: flex-end; align-items: center; padding-right: 10px; }
        .gal-close { cursor: pointer; font-size: 24px; color: #94a3b8; }
        .gal-content { position: relative; flex: 1; background: black; display: flex; align-items: center; justify-content: center; overflow: hidden; }
        .gal-content img, .gal-content video { max-width: 100%; max-height: 100%; object-fit: contain; }
        .gal-touch-area { position: absolute; top: 0; height: 100%; width: 25%; z-index: 100; cursor: pointer; }
        .gal-touch-left { left: 0; } .gal-touch-right { right: 0; }
        .gal-expand-btn { position: absolute; bottom: 15px; right: 15px; width: 30px; height: 30px; background: rgba(0,0,0,0.5); border-radius: 4px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: white; z-index: 200; }
        .thumb-grid { display: flex; gap: 8px; margin-top: 15px; overflow-x: auto; scrollbar-width: none; }
        .thumb-wrap { flex: 0 0 100px; height: 70px; border-radius: 6px; overflow: hidden; cursor: pointer; flex-shrink: 0; }
        .thumb-wrap img { width: 100%; height: 100%; object-fit: cover; }
        .chart-toggle { cursor: pointer; padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; background: #eee; color: #666; }
        .chart-toggle.active { background: var(--accent); color: white; }
        .scroll-hint { position: fixed; bottom: 30px; left: 75%; transform: translateX(-50%); color: #000; font-family: 'Space Mono', monospace; font-size: 14px; letter-spacing: 2px; font-weight: bold; text-shadow: 0 0 10px rgba(255,255,255,0.8); animation: bounce 2s infinite; opacity: 0; transition: opacity 0.5s; z-index: 3000; pointer-events: none; }
        .scroll-hint::after { content: 'SCROLL ↓'; }
        @media (max-width: 768px) { .scroll-hint { bottom: 22%; right: 20px; left: auto; transform: none; } .scroll-hint::after { content: 'SWIPE →'; } }
        .map-chapter-thumb { width: 40px !important; height: 40px !important; border-radius: 4px; border: 2px solid white; box-shadow: 0 2px 8px rgba(0,0,0,0.3); overflow: hidden; background: white; opacity: 0; transform: translateY(10px); transition: 0.3s; }
        .map-chapter-thumb img { width: 100% !important; height: 100% !important; object-fit: cover !important; margin: 0 !important; }
        .map-chapter-thumb.visible { opacity: 1; transform: translateY(0); }
    </style>
</head>
<body id="main-body">
    <div id="map-container"><div id="map"></div></div>
    <div class="hero-gradient"></div>

    <div class="ctrl-group interactive">
        <div id="map-toggle-btn" class="ctrl-btn" onclick="cycleMap()" title="Change Map Type">🛰</div>
        <div class="ctrl-btn" onclick="resetView()" title="Reset View">&#8635;</div>
        <div class="ctrl-btn story-exit-btn" onclick="exitStory()" title="Exit Story">×</div>
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
        <div class="h-24 md:h-40 w-full"><canvas id="elChart"></canvas></div>
    </div>
    
    <div class="nav-container interactive">
        <div class="nav-btn" onclick="scrollNav(-1)">‹</div>
        <div class="nav-scroll-area" id="nav-scroll-area">
            <div class="timeline-track" id="timeline-track"><div class="timeline-fill" id="timeline-fill"></div></div>
        </div>
        <div class="nav-btn" onclick="scrollNav(1)">›</div>
        <div class="nav-btn close" onclick="exitJourneyMode()">×</div>
    </div>

    <div id="gallery-window" class="interactive">
        <div class="gal-header"><div class="gal-close" onclick="closeGallery()">×</div></div>
        <div class="gal-content">
            <div class="gal-touch-area" onclick="changeSlide(-1)"></div>
            <div class="gal-touch-area" onclick="changeSlide(1)" style="right:0"></div>
            <img id="gal-img" src="">
            <video id="gal-vid" controls playsinline style="display:none"></video>
        </div>
    </div>

    <div id="story-overlay">
        <div class="story-scroller" id="story-scroller" onscroll="checkStoryScroll()"></div>
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

        let activeChart = null, currentRouteData = null, routeLayers = [];
        let bikeMarker = null, storyChapterMarkers = [], currentStoryPoints = [], routeDistances = [], totalRouteLength = 0;
        let allPoints = [], devLabels = [], storyMarkers = [], isDevMode = false;
        let savedMapState = null, storyChapters = [], userInteracting = false;
        let chartType = 'ele';

        routes.forEach((route, idx) => {
            allPoints.push(...route.coords);
            const visual = L.polyline(route.coords, { color: '#e63946', weight: 3, opacity: 0 }).addTo(map);
            routeLayers.push(visual);
            const hit = L.polyline(route.coords, { color: 'transparent', weight: 30, opacity: 0, zIndexOffset: 1000 }).addTo(map);
            hit.on('mouseover', () => { visual.setStyle({ color: '#1d3557', weight: 5, opacity: 1 }); });
            hit.on('mouseout', () => { visual.setStyle({ color: '#e63946', weight: 3, opacity: 0.9 }); });
            hit.on('click', (e) => { L.DomEvent.stopPropagation(e); showDetail(route); });
        });

        STORIES.forEach(story => {
            const html = `<div class="story-marker-wrap"><div class="story-dot"><svg viewBox="0 0 512 512"><path d="M496 128v16a8 8 0 0 1-8 8h-24v12c0 6.627-5.373 12-12 12H60c-6.627 0-12-5.373-12-12v-12H24a8 8 0 0 1-8-8v-16a8 8 0 0 1 4.941-7.392l232-88a7.996 7.996 0 0 1 6.118 0l232 88A8 8 0 0 1 496 128zm-24 104v144c0 17.673-14.327 32-32 32H72c-17.673 0-32-14.327-32-32V232c0-17.673 14.327-32 32-32h368c17.673 0 32 14.327 32 32zM80 400h352v-24H80v24zm352-56v-24H80v24h352z"/></svg></div><div class="story-bubble">${story.title}</div></div>`;
            const m = L.marker(story.location, { icon: L.divIcon({ className: 'story-div-icon', html: html }) }).addTo(map).on('click', (e) => { L.DomEvent.stopPropagation(e); startStory(story); });
        });

        function shrinkHero() { if(userInteracting) document.body.classList.add('shrunk'); }
        ['mousedown', 'touchstart', 'wheel', 'keydown'].forEach(evt => window.addEventListener(evt, () => { userInteracting = true; shrinkHero(); }));
        map.on('dragstart', () => { userInteracting = true; shrinkHero(); });

        function closeAllModes() {
            document.body.classList.remove('journey-mode', 'story-mode');
            document.getElementById('stage-card').classList.remove('visible');
            document.getElementById('chapter-btn-wrap').style.display = 'block';
            closePanel();
            if(bikeMarker) map.removeLayer(bikeMarker);
            storyChapterMarkers.forEach(m => map.removeLayer(m));
        }

        window.addEventListener('keydown', (e) => {
            if(e.key === '`' || e.key === '~') { 
                isDevMode = !isDevMode; 
                devLabels.forEach(l => isDevMode ? l.addTo(map) : map.removeLayer(l)); 
            }
        });

        window.addEventListener('load', () => {
            if(allPoints.length) {
                let bp = allPoints; if(isMobile) bp = allPoints.slice(0, Math.floor(allPoints.length * 0.2));
                map.fitBounds(L.polyline(bp).getBounds(), { paddingTopLeft: isMobile ? [20,20] : [window.innerWidth*0.2, 50], paddingBottomRight: [50, 50] });
                setTimeout(() => { requestAnimationFrame(() => { routeLayers.forEach((l, i) => setTimeout(() => { l.setStyle({opacity:1, color:'#fff', weight:4}); setTimeout(()=>l.setStyle({color:'#e63946', weight:3, opacity: 0.9}), 100); }, i*20)); }); }, 800);
                
                routes.forEach((r, i) => {
                    const mid = r.coords[Math.floor(r.coords.length/2)];
                    devLabels.push(L.marker(mid, { icon: L.divIcon({ className: 'dev-label', html: i }) }));
                });
            }
        });

        map.on('zoomend', () => {
            const el = document.getElementById('map-container');
            if(map.getZoom() >= 7) el.classList.add('map-zoomed-in');
            else el.classList.remove('map-zoomed-in');
        });

        function startJourney() { 
            closeAllModes(); userInteracting = true; shrinkHero();
            document.body.classList.add('journey-mode'); 
            document.getElementById('chapter-btn-wrap').style.display = 'none';
            setupTimeline();
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
            const s = STAGES[index]; document.getElementById('st-title').innerText = s.title; document.getElementById('st-date').innerText = s.date_range; document.getElementById('st-desc').innerText = s.description; const tc = document.getElementById('st-thumbs'); tc.innerHTML = ''; s.images.forEach((u, i) => tc.innerHTML += `<div class="thumb-wrap" onclick="openLB(${index}, ${i})"><img src="${u}"></div>`); 
            document.getElementById('timeline-fill').style.width = `${(index / (STAGES.length - 1)) * 100}%`; 
            document.querySelectorAll('.nav-dot').forEach((d, i) => d.classList.toggle('active', i === index)); 
            document.getElementById('stage-card').classList.add('visible'); 
            let pts = []; for(let i=s.start_index; i<=s.end_index; i++) { if(routes[i]) pts.push(...routes[i].coords); } if(pts.length) map.flyToBounds(L.polyline(pts).getBounds(), { padding: [100,100], duration: 2 });
        }

        function startStory(s) {
            closeAllModes(); userInteracting = true; shrinkHero();
            document.body.classList.add('story-mode'); 
            savedMapState = { center: map.getCenter(), zoom: map.getZoom() };
            storyChapters = s.chapters || [];
            
            const sc = document.getElementById('story-scroller'); sc.innerHTML = ''; sc.scrollTop = 0; sc.scrollLeft = 0;
            const spacer = document.createElement('div'); spacer.style.height = isMobile ? '1px' : '50vh'; spacer.style.width = isMobile ? '50vw' : '100%'; spacer.style.flexShrink = '0'; sc.appendChild(spacer);

            currentStoryPoints = []; s.route_segment_ids.forEach(id => { if(routes[id]) currentStoryPoints.push(...routes[id].coords); });
            if(currentStoryPoints.length) {
                setupMath(currentStoryPoints);
                const pad = isMobile ? [20, 100] : [window.innerWidth * 0.6, 50];
                map.flyToBounds(L.polyline(currentStoryPoints).getBounds(), { paddingBottomRight: pad, maxZoom: 13, duration: 1.5 });
                map.once('moveend', () => {
                    if(!document.body.classList.contains('story-mode')) return;
                    bikeMarker = L.marker(currentStoryPoints[0], { icon: L.divIcon({ className: 'bike-icon', html: '<div class="bike-inner">🚴</div>', iconSize:[30,30] }), zIndexOffset: 2000 }).addTo(map);
                    setTimeout(() => bikeMarker._icon.classList.add('visible'), 100);
                    s.chapters.forEach((c, i) => {
                        const pt = getPtAtD(c.progress * totalRouteLength);
                        const tm = L.marker(pt, { icon: L.divIcon({ className: 'map-chapter-thumb', html: `<img src="${c.image}">`, iconSize: [30, 30] }) }).addTo(map);
                        setTimeout(() => tm._icon.classList.add('visible'), 500 + (i*200)); storyChapterMarkers.push(tm);
                    });
                });
            }
            s.chapters.forEach(c => { const d = document.createElement('div'); d.className = 'story-card'; d.innerHTML = `<p>${c.text}</p><img src="${c.image}">`; sc.appendChild(d); });
            const trail = document.createElement('div'); trail.style.height = isMobile ? '1px' : '50vh'; trail.style.width = isMobile ? '50vw' : '100%'; trail.style.flexShrink = '0'; sc.appendChild(trail);
            document.getElementById('scroll-hint').style.opacity = '1';
        }

        function checkStoryScroll() {
            const sc = document.getElementById('story-scroller');
            const cards = document.querySelectorAll('.story-card');
            let totalS = isMobile ? (sc.scrollWidth - window.innerWidth) : (sc.scrollHeight - window.innerHeight);
            let currS = isMobile ? sc.scrollLeft : sc.scrollTop;
            if(totalS <= 0 || cards.length < 2) return;
            
            let firstC = isMobile ? (cards[0].offsetLeft + cards[0].offsetWidth/2) : (cards[0].offsetTop + cards[0].offsetHeight/2);
            let lastC = isMobile ? (cards[cards.length-1].offsetLeft + cards[cards.length-1].offsetWidth/2) : (cards[cards.length-1].offsetTop + cards[cards.length-1].offsetHeight/2);
            let sCenter = isMobile ? (currS + window.innerWidth/2) : (currS + window.innerHeight/2);
            
            let cardPct = Math.max(0, Math.min(1, (sCenter - firstC) / (lastC - firstC)));
            let floatIdx = cardPct * (cards.length - 1);
            let lowIdx = Math.floor(floatIdx), highIdx = Math.ceil(floatIdx), localPct = floatIdx - lowIdx;
            
            if(storyChapters[lowIdx] && storyChapters[highIdx]) {
                let currentP = storyChapters[lowIdx].progress + (storyChapters[highIdx].progress - storyChapters[lowIdx].progress) * localPct;
                if(bikeMarker) {
                    bikeMarker.setLatLng(getPtAtD(currentP * totalRouteLength));
                    const bikePx = map.latLngToContainerPoint(bikeMarker.getLatLng());
                    const w = window.innerWidth, h = window.innerHeight;
                    let mX = isMobile ? 20 : 50, MX = isMobile ? w-20 : w*0.4-50, mY = 50, MY = isMobile ? h*0.45-50 : h-50;
                    if (bikePx.x < mX || bikePx.x > MX || bikePx.y < mY || bikePx.y > MY) {
                        map.panBy([bikePx.x - (isMobile ? w/2 : w*0.2), bikePx.y - (isMobile ? h*0.225 : h/2)], {animate: true, duration: 1.0});
                    }
                }
            }
            cards.forEach((c, i) => {
                const box = c.getBoundingClientRect();
                const center = isMobile ? (box.left + box.width/2) : (box.top + box.height/2);
                const screenC = isMobile ? (window.innerWidth/2) : (window.innerHeight/2);
                if(Math.abs(center - screenC) < 150) {
                    if(!c.classList.contains('active')) { c.classList.add('active'); storyChapterMarkers.forEach((m, idx) => m._icon && (idx === i ? m._icon.classList.add('active') : m._icon.classList.remove('active'))); }
                } else c.classList.remove('active');
            });
        }

        function exitStory() { closeAllModes(); if(savedMapState) map.flyTo(savedMapState.center, savedMapState.zoom, { duration: 1.5 }); }
        function exitJourneyMode() { closeAllModes(); }
        function resetView() { closeAllModes(); let bp = allPoints; if(isMobile) bp = allPoints.slice(0, Math.floor(allPoints.length * 0.2)); map.fitBounds(L.polyline(bp).getBounds(), { padding: [50, 50], duration: 1.5 }); }
        function scrollNav(dir) { document.getElementById('nav-scroll-area').scrollBy({ left: dir * 200, behavior: 'smooth' }); }
        function closePanel() { document.getElementById('detail-panel').classList.remove('open'); }
        function showDetail(d) { closeAllModes(); currentRouteData = d; document.getElementById('p-day').innerText = `Day ${d.day}`; document.getElementById('detail-panel').classList.add('open'); renderChart(); }
        function switchChart(t) { chartType = t; renderChart(); }

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
                    plugins: { legend: { display: false }, tooltip: { intersect: false, mode: 'index' } },
                    interaction: { mode: 'nearest', axis: 'x', intersect: false },
                    onClick: (e) => {
                        const points = activeChart.getElementsAtEventForMode(e, 'nearest', { intersect: true }, true);
                        if (points.length) {
                            const pct = points[0].index / len;
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

        function openLB(s, i) { currStg = s; currImg = i; updateGallery(); galWin.classList.add('visible'); userInteracting = true; shrinkHero(); }
        function closeGallery() { galWin.classList.remove('visible'); document.getElementById('gal-vid').pause(); }
        function updateGallery() { const url = STAGES[currStg].images[currImg]; const isV = url.match(/\.(mp4|mov)$/i); const v = document.getElementById('gal-vid'), i = document.getElementById('gal-img'); if(isV) { i.style.display='none'; v.style.display='block'; v.src=url; v.play(); } else { v.pause(); v.style.display='none'; i.style.display='block'; i.src=url; } }
        function changeSlide(d) { const imgs = STAGES[currStg].images; currImg = (currImg + d + imgs.length) % imgs.length; updateGallery(); }
        function toggleMaximize() { galWin.classList.toggle('maximized'); }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, 
                                  routes=CACHED_ROUTES, 
                                  stages=CACHED_STAGES, 
                                  stories=CACHED_STORIES,
                                  distance=CACHED_DIST)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)