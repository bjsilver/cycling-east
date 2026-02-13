import os
import json
import math
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

def load_data_v49():
    print("\n--- LOADING V49 PERFECT STATE ---")
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
        stage_files = sorted([f for f in os.listdir(STAGES_DIR) if f.endswith('.json')])
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

CACHED_ROUTES, CACHED_STAGES, CACHED_STORIES, CACHED_DIST = load_data_v49()

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
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;1,700&family=Inter:wght@300;400;600&family=Space+Mono&display=swap" rel="stylesheet">
    <style>
        :root { --accent: #e63946; --speed: #457b9d; --text: #1d3557; --story: #475569; --card-bg: rgba(255, 255, 255, 0.95); }
        body { background: #f1f5f9; color: var(--text); font-family: 'Inter', sans-serif; overflow: hidden; margin: 0; touch-action: none; }
        h1, h2 { font-family: 'Playfair Display', serif; }
        .mono { font-family: 'Space Mono', monospace; }

        .hero, .ui-layer, #gallery-window, #stage-card { will-change: transform, opacity; transform: translate3d(0,0,0); }

        #map-container { position: fixed; inset: 0; z-index: 0; }
        #map { width: 100%; height: 100%; outline: none; background: #aad3df; }
        
        .ui-layer { position: absolute; inset: 0; pointer-events: none; z-index: 100; transition: opacity 0.5s; }
        .interactive { pointer-events: auto; }
        
        body.story-mode .ui-layer, body.journey-mode .ui-layer { pointer-events: none; }
        body.story-mode .hero-gradient, body.journey-mode .hero-gradient { opacity: 0; transform: translateX(-100%); }
        body.story-mode .start-btn-container, body.journey-mode .start-btn-container { display: none; }

        /* HERO */
        .hero { position: fixed; inset: 0; pointer-events: none; z-index: 200; user-select: none; transition: 1s cubic-bezier(0.16, 1, 0.3, 1); }
        .hero-content { position: absolute; top: 50%; left: 5vw; transform: translateY(-50%); transition: inherit; transform-origin: top left; }
        .hero h1 { font-size: 6rem; line-height: 1; }
        @media (max-width: 768px) { .hero h1 { font-size: 3.5rem; } .hero-content { left: 20px; } }
        
        /* Shrunk State - LOCKED */
        .shrunk .hero-content { top: 20px; left: 20px; transform: scale(0.5) !important; opacity: 0.8; }
        .hero-gradient { position: fixed; inset: 0; width: 45%; background: linear-gradient(to right, rgba(241, 245, 249, 0.98), transparent); pointer-events: none; z-index: 50; transition: 0.8s ease; }
        .shrunk .hero-gradient { opacity: 0; transform: translateX(-100%); }

        /* MARKERS */
        .start-marker, .end-marker { background: #000; border: 2px solid white; width: 16px; height: 16px; border-radius: 50%; box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.5); z-index: 1000 !important; }
        .story-marker-wrap { position: relative; width: 0; height: 0; }
        .story-dot {
            position: absolute; top: -8px; left: -8px; width: 16px; height: 16px; background: var(--story);
            border: 2px solid white; border-radius: 50%; box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            cursor: pointer; display: flex; align-items: center; justify-content: center;
        }
        .story-dot svg { width: 10px; height: 10px; fill: white; }
        .story-bubble {
            position: absolute; bottom: 15px; left: -75px; width: 150px; background: white; padding: 5px; border-radius: 8px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2); display: flex; gap: 8px; align-items: center;
            opacity: 0; pointer-events: none; transform: translateY(10px) scale(0.8); transition: 0.3s;
        }
        .story-bubble img { width: 40px; height: 40px; border-radius: 4px; object-fit: cover; }
        .map-zoomed-in .story-dot { opacity: 0; pointer-events: none; } 
        .map-zoomed-in .story-bubble { opacity: 1; pointer-events: auto; transform: translateY(0) scale(1); }

        /* GALLERY WINDOW */
        #gallery-window {
            position: fixed; top: 20px; right: 5%; width: 600px; max-width: 90vw; 
            max-height: 85vh; background: white; border-radius: 12px; box-shadow: 0 20px 50px rgba(0,0,0,0.4);
            display: none; flex-direction: column; overflow: hidden; z-index: 5000;
        }
        @media (max-width: 768px) {
            #gallery-window { top: 0 !important; left: 0 !important; width: 100% !important; height: 100% !important; max-width: none; max-height: none; border-radius: 0; }
            .gal-header { padding-top: 10px; } 
            .gal-close { position: absolute; bottom: 20px; right: 20px; background: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 10px rgba(0,0,0,0.3); z-index: 1000; }
        }
        #gallery-window.dragging { transition: none !important; }
        #gallery-window.visible { display: flex; animation: popup 0.3s ease; }
        #gallery-window.maximized { inset: 0 !important; width: 100% !important; height: 100% !important; max-width: none; max-height: none; border-radius: 0; top: 0 !important; left: 0 !important; }

        .gal-header { height: 30px; background: #f1f5f9; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: flex-end; align-items: center; cursor: grab; padding-right: 10px; }
        .gal-close { cursor: pointer; font-size: 24px; color: #94a3b8; }
        .gal-content { position: relative; flex: 1; background: black; display: flex; align-items: center; justify-content: center; overflow: hidden; }
        .gal-content img, .gal-content video { max-width: 100%; max-height: 100%; object-fit: contain; }
        .gal-touch-area { position: absolute; top: 0; height: 100%; width: 25%; z-index: 100; cursor: pointer; display: flex; align-items: center; justify-content: center; opacity: 0; transition: 0.3s; }
        .gal-touch-area:hover { opacity: 1; }
        .gal-touch-left { left: 0; background: linear-gradient(to right, rgba(255,255,255,0.1), transparent); }
        .gal-touch-right { right: 0; background: linear-gradient(to left, rgba(255,255,255,0.1), transparent); }
        .gal-touch-area::after { color: white; font-size: 30px; }
        .gal-touch-left::after { content: '❮'; } .gal-touch-right::after { content: '❯'; }
        .gal-expand-btn { position: absolute; bottom: 15px; right: 15px; width: 30px; height: 30px; background: rgba(0,0,0,0.5); border-radius: 4px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: white; z-index: 200; }

        /* UI ELEMENTS */
        .dev-label { background: #000; color: #fff; padding: 4px 10px; border-radius: 4px; font-family: 'Space Mono', monospace; font-size: 14px; font-weight: bold; border: 1px solid #fff; box-shadow: 0 4px 10px rgba(0,0,0,0.5); white-space: nowrap; }
        .ctrl-group { position: fixed; top: 20px; right: 20px; z-index: 6000; display: flex; gap: 10px; pointer-events: auto; }
        .ctrl-btn { width: 40px; height: 40px; background: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.2); font-size: 18px; color: var(--text); }
        
        .start-btn-container { position: absolute; bottom: 30px; left: 30px; transform: none; z-index: 300; pointer-events: auto; }
        .start-btn { background: white; color: var(--text); border: 1px solid var(--text); padding: 15px 40px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 3px; cursor: pointer; }
        
        #stage-card { 
            position: absolute; top: 160px; left: 30px; width: 350px; max-height: 50vh; overflow-y: auto; scrollbar-width: none; 
            background: var(--card-bg); backdrop-filter: blur(20px); border-radius: 12px; padding: 25px; 
            transform: translateX(-150%); transition: transform 0.6s ease; pointer-events: auto; z-index: 400; 
        }
        @media (max-width: 768px) {
            #stage-card { top: auto; bottom: 80px; left: 10px; right: 10px; width: auto; transform: translateY(150%); }
            body.journey-mode #stage-card { transform: translateY(0); }
        }
        body.journey-mode #stage-card { transform: translateX(0); }
        
        /* NAV BAR - FIXED: Fully hidden when inactive */
        .nav-bar { 
            position: absolute; bottom: 0; left: 0; width: 100%; height: 70px; background: white; 
            display: flex; align-items: center; justify-content: center; 
            transform: translateY(100%); transition: transform 0.6s ease, opacity 0.6s ease; 
            pointer-events: none; opacity: 0; z-index: 400; /* Default Hidden */
        }
        @media (max-width: 768px) { .nav-bar { justify-content: flex-start; overflow-x: auto; padding-left: 20px; padding-right: 60px; } .timeline { min-width: 200%; } }
        
        /* ACTIVE NAV BAR */
        body.journey-mode .nav-bar { transform: translateY(0); opacity: 1; pointer-events: auto; }
        
        .nav-close { position: absolute; right: 20px; top: 50%; transform: translateY(-50%); font-size: 24px; color: #000; cursor: pointer; font-weight: bold; background: rgba(255,255,255,0.8); width: 40px; height: 70px; display: flex; align-items: center; justify-content: center; z-index: 500; }
        
        .timeline { position: relative; width: 80%; height: 4px; background: #e2e8f0; }
        .timeline-fill { position: absolute; top: 0; left: 0; height: 100%; background: var(--accent); }
        .nav-dot { position: absolute; top: -6px; width: 16px; height: 16px; background: #94a3b8; border: 3px solid white; border-radius: 50%; cursor: pointer; z-index: 50; }
        .nav-dot.active { background: var(--accent); transform: scale(1.3); }
        .dot-tooltip { 
            position: absolute; bottom: 25px; left: 50%; transform: translateX(-50%); 
            background: #1e293b; color: white; padding: 4px 10px; font-size: 11px; 
            border-radius: 4px; opacity: 1; white-space: nowrap; pointer-events: none;
        }
        
        .thumb-grid { display: flex; gap: 8px; margin-top: 15px; overflow-x: auto; scrollbar-width: none; }
        .thumb-wrap { flex: 0 0 100px; height: 70px; border-radius: 6px; overflow: hidden; cursor: pointer; flex-shrink: 0; }
        .thumb-wrap img { width: 100%; height: 100%; object-fit: cover; }
        
        #detail-panel { position: absolute; bottom: 90px; right: 30px; width: 400px; background: var(--card-bg); backdrop-filter: blur(20px); border-radius: 12px; padding: 20px; transform: translateY(150%); transition: transform 0.5s cubic-bezier(0.2, 1, 0.3, 1); box-shadow: 0 5px 30px rgba(0,0,0,0.15); z-index: 400; }
        #detail-panel.open { transform: translateY(0); }
        @media (max-width: 768px) { #detail-panel { left: 10px; right: 10px; width: auto; bottom: 20px; } }
        .chart-toggle { cursor: pointer; padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; background: #eee; color: #666; }
        .chart-toggle.active { background: var(--accent); color: white; }

        /* STORY MODE */
        #story-overlay { position: fixed; inset: 0; z-index: 2000; display: none; }
        body.story-mode #story-overlay { display: block; }
        .story-scroller { 
            position: absolute; top: 0; right: 0; width: 60%; height: 100%; 
            overflow-y: auto; padding: 0; /* JS Spacer Handles Alignment */
            background: linear-gradient(to right, transparent, rgba(241, 245, 249, 0.98)); 
            scrollbar-width: none; pointer-events: auto; 
        }
        .story-card { background: white; margin: 0 10% 50vh 10%; padding: 25px; border-radius: 12px; opacity: 0.3; transition: 0.5s; box-shadow: 0 4px 20px rgba(0,0,0,0.05); }
        .story-card.active { opacity: 1; border-left: 5px solid var(--story); }
        
        @media (max-width: 768px) {
            .story-scroller { 
                width: 100%; height: 45%; top: auto; bottom: 0; 
                display: flex; flex-direction: row; overflow-x: auto; overflow-y: hidden;
                padding: 0; 
                background: linear-gradient(to top, rgba(241, 245, 249, 1), rgba(241, 245, 249, 0.9));
                align-items: center; scroll-snap-type: x mandatory;
            }
            .story-card { 
                flex: 0 0 85vw; margin: 0 10px; height: auto; max-height: 90%; 
                opacity: 0.5; scroll-snap-align: center; margin-bottom: 0;
            }
            .story-card.active { opacity: 1; transform: scale(1.05); }
        }

        /* SCROLL HINT */
        .scroll-hint {
            position: fixed; bottom: 30px; left: 75%; transform: translateX(-50%);
            color: #000; font-family: 'Space Mono', monospace; font-size: 14px; letter-spacing: 2px;
            font-weight: bold; text-shadow: 0 0 10px rgba(255,255,255,0.8);
            animation: bounce 2s infinite; opacity: 0; transition: opacity 0.5s; z-index: 3000; pointer-events: none;
        }
        .scroll-hint::after { content: 'SCROLL ↓'; }
        @media (max-width: 768px) {
            .scroll-hint { bottom: 22%; right: 20px; left: auto; transform: none; }
            .scroll-hint::after { content: 'SWIPE →'; }
        }
        body.story-mode .scroll-hint { opacity: 1; }
        @keyframes bounce { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(10px); } }

        .bike-icon { font-size: 36px; transition: transform 0.1s linear, opacity 0.5s; opacity: 0; z-index: 2500 !important; }
        .bike-icon.visible { opacity: 1; }
        .map-chapter-thumb { width: 30px; height: 30px; border-radius: 4px; border: 2px solid white; box-shadow: 0 2px 8px rgba(0,0,0,0.3); overflow: hidden; background: white; opacity: 0; transform: translateY(10px); transition: 0.3s; }
        .map-chapter-thumb img { width: 100%; height: 100%; object-fit: cover; }
        .map-chapter-thumb.visible { opacity: 1; transform: translateY(0); }
        .map-chapter-thumb.active { transform: scale(1.6); border-color: var(--story); z-index: 1500 !important; }
    </style>
</head>
<body id="main-body">
    <div id="map-container"><div id="map"></div></div>
    <div class="hero-gradient"></div>

    <div class="ctrl-group interactive">
        <div class="ctrl-btn" onclick="toggleSat()" title="Satellite View">🛰</div>
        <div class="ctrl-btn" onclick="resetView()" title="Reset View">&#8635;</div>
    </div>

    <div class="ui-layer">
        <div id="hero" class="hero"><div class="hero-content"><h1 class="italic text-slate-800 mb-4">Cycling East</h1><p class="text-sm uppercase tracking-[0.3em] text-slate-500">Leeds → Hong Kong &bull; {{ distance }} KM</p></div></div>
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
                <div class="flex gap-1"><span id="btn-ele" class="chart-toggle active" onclick="switchChart('ele')">ELEV</span><span id="btn-speed" class="chart-toggle" onclick="switchChart('speed')">SPEED</span></div>
            </div>
            <div class="h-24 md:h-40 w-full"><canvas id="elChart"></canvas></div>
        </div>
        
        <div id="nav-bar" class="nav-bar interactive">
            <div class="timeline" id="timeline-track"><div class="timeline-fill" id="timeline-fill"></div></div>
            <div class="nav-close" onclick="exitJourneyMode()">&times;</div>
        </div>
    </div>

    <div id="gallery-window" class="interactive">
        <div class="gal-header" id="gal-header"><div class="gal-close" onclick="closeGallery()">&times;</div></div>
        <div class="gal-content">
            <div class="gal-touch-area gal-touch-left" onclick="changeSlide(-1)"></div>
            <div class="gal-touch-area gal-touch-right" onclick="changeSlide(1)"></div>
            <img id="gal-img" src="">
            <video id="gal-vid" controls playsinline style="display:none"></video>
            <div class="gal-expand-btn" onclick="toggleMaximize()">⤢</div>
        </div>
    </div>

    <div id="story-overlay">
        <div class="story-scroller" id="story-scroller" onscroll="checkStoryScroll()"></div>
        <div class="scroll-hint" id="scroll-hint"></div>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const routes = {{ routes|tojson }};
        const STAGES = {{ stages|tojson }};
        const STORIES = {{ stories|tojson }};
        const isMobile = window.innerWidth < 768;
        
        var map = L.map('map', { zoomControl: false, attributionControl: false, renderer: L.canvas() }).setView([50, 0], 4);
        const voyager = L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', { maxZoom: 19 });
        const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19 });
        voyager.addTo(map);

        let isSat = false;
        function toggleSat() {
            isSat = !isSat;
            if(isSat) { map.removeLayer(voyager); map.addLayer(satellite); }
            else { map.removeLayer(satellite); map.addLayer(voyager); }
            document.querySelector('.ctrl-btn').classList.toggle('active', isSat);
        }

        let activeChart = null, currentRouteData = null, chartType = 'ele', routeLayers = [];
        let bikeMarker = null, storyChapterMarkers = [], currentStoryPoints = [], routeDistances = [], totalRouteLength = 0;
        let allPoints = [], devLabels = [], storyMarkers = [], isDevMode = false;
        let savedMapState = null; 
        let currentMaxProgress = 1.0;

        // --- ROUTES ---
        routes.forEach((route, idx) => {
            allPoints.push(...route.coords);
            const visual = L.polyline(route.coords, { color: '#e63946', weight: 3, opacity: 0 }).addTo(map);
            routeLayers.push(visual);
            const hit = L.polyline(route.coords, { color: 'transparent', weight: 30, opacity: 0, zIndexOffset: 1000 }).addTo(map);
            hit.on('mouseover', () => { visual.setStyle({ color: '#1d3557', weight: 5, opacity: 1 }); });
            hit.on('mouseout', () => { visual.setStyle({ color: '#e63946', weight: 3, opacity: 0.9 }); });
            hit.on('click', (e) => { L.DomEvent.stopPropagation(e); showDetail(route); });
        });

        // --- STORIES ---
        STORIES.forEach(story => {
            const html = `<div class="story-marker-wrap"><div class="story-dot"><svg viewBox="0 0 24 24"><path d="M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z"/></svg></div><div class="story-bubble"><img src="${story.thumb}"><span>${story.title}</span></div></div>`;
            const m = L.marker(story.location, { icon: L.divIcon({ className: 'story-div-icon', html: html }) }).addTo(map).on('click', (e) => { L.DomEvent.stopPropagation(e); startStory(story); });
            storyMarkers.push({ marker: m, dayIdx: story.closest_segment });
        });

        // --- INTERACTION ---
        function shrinkHero() { document.body.classList.add('shrunk'); }
        map.on('mousedown touchstart wheel dragstart', shrinkHero);
        document.getElementById('map-container').addEventListener('touchmove', shrinkHero); 

        window.addEventListener('keydown', (e) => {
            if(e.key === '`' || e.key === '~') { isDevMode = !isDevMode; devLabels.forEach(l => isDevMode ? l.addTo(map) : map.removeLayer(l)); }
            if(galWin.classList.contains('visible')) {
                if(e.key === 'ArrowLeft') changeSlide(-1);
                if(e.key === 'ArrowRight') changeSlide(1);
                if(e.key === 'Escape') closeGallery();
            }
        });

        // --- INIT ---
        window.addEventListener('load', () => {
            if(allPoints.length) {
                let boundsPoints = allPoints;
                if(isMobile) boundsPoints = allPoints.slice(0, Math.floor(allPoints.length * 0.2));
                const pad = isMobile ? [20, 20] : [window.innerWidth * 0.25, 50];
                map.fitBounds(L.polyline(boundsPoints).getBounds(), { paddingTopLeft: pad, paddingBottomRight: [50, 50] });
                
                L.marker(allPoints[0], { icon: L.divIcon({ className: 'start-marker' }) }).addTo(map);
                L.marker(allPoints[allPoints.length-1], { icon: L.divIcon({ className: 'end-marker' }) }).addTo(map);

                setTimeout(() => {
                    requestAnimationFrame(() => {
                        routeLayers.forEach((l, i) => setTimeout(() => { 
                            l.setStyle({opacity:1, color:'#fff', weight:4}); 
                            setTimeout(()=>l.setStyle({color:'#e63946', weight:3, opacity: 0.9}), 100); 
                        }, i*20)); 
                    });
                }, 800);
                
                routes.forEach((r, i) => {
                    const mid = r.coords[Math.floor(r.coords.length/2)];
                    devLabels.push(L.marker(mid, { icon: L.divIcon({ className: 'dev-label', html: i, iconAnchor: [15, 12] }) }));
                });
            }
        });

        map.on('zoomend', () => {
            if(map.getZoom() >= 6) document.getElementById('map-container').classList.add('map-zoomed-in');
            else document.getElementById('map-container').classList.remove('map-zoomed-in');
        });

        // --- GALLERY ---
        let currStg = 0, currImg = 0;
        const galWin = document.getElementById('gallery-window');
        function openLB(sIdx, iIdx) { currStg = sIdx; currImg = iIdx; updateGallery(); galWin.classList.add('visible'); shrinkHero(); }
        function closeGallery() { galWin.classList.remove('visible', 'maximized'); document.getElementById('gal-vid').pause(); }
        function updateGallery() {
            const url = STAGES[currStg].images[currImg];
            const isVid = url.match(/\.(mp4|mov)$/i);
            const v = document.getElementById('gal-vid'), i = document.getElementById('gal-img');
            if(isVid) { i.style.display='none'; v.style.display='block'; v.src=url; v.play(); } 
            else { v.pause(); v.style.display='none'; i.style.display='block'; i.src=url; }
        }
        function changeSlide(dir) { const imgs = STAGES[currStg].images; currImg = (currImg + dir + imgs.length) % imgs.length; updateGallery(); }
        function toggleMaximize() { galWin.classList.toggle('maximized'); }

        const head = document.getElementById('gal-header');
        let isDrag = false, sx, sy, il, it;
        head.addEventListener('mousedown', (e) => { if(galWin.classList.contains('maximized')) return; isDrag = true; sx = e.clientX; sy = e.clientY; const r = galWin.getBoundingClientRect(); il = r.left; it = r.top; galWin.classList.add('dragging'); });
        window.addEventListener('mousemove', (e) => { if(!isDrag) return; galWin.style.left = `${il + (e.clientX - sx)}px`; galWin.style.top = `${it + (e.clientY - sy)}px`; galWin.style.right = 'auto'; });
        window.addEventListener('mouseup', () => { isDrag = false; galWin.classList.remove('dragging'); });

        // --- STORY ENGINE ---
        function setupMath(p) { routeDistances = [0]; totalRouteLength = 0; for(let i=1; i<p.length; i++) { totalRouteLength += map.distance(p[i-1], p[i]); routeDistances.push(totalRouteLength); } }
        function getPtAtD(d) { for(let i=1; i<routeDistances.length; i++) { if(routeDistances[i] >= d) { const frac = (d - routeDistances[i-1]) / (routeDistances[i] - routeDistances[i-1]); return [currentStoryPoints[i-1][0] + (currentStoryPoints[i][0] - currentStoryPoints[i-1][0]) * frac, currentStoryPoints[i-1][1] + (currentStoryPoints[i][1] - currentStoryPoints[i-1][1]) * frac]; } } return currentStoryPoints[currentStoryPoints.length-1]; }
        function forwardScroll(e) { document.getElementById('story-scroller').scrollTop += e.deltaY; }

        function startStory(s) {
            shrinkHero(); document.body.classList.add('story-mode'); closePanel();
            savedMapState = { center: map.getCenter(), zoom: map.getZoom() };
            currentMaxProgress = s.max_progress || 1.0;
            if(bikeMarker) map.removeLayer(bikeMarker); bikeMarker = null;
            storyChapterMarkers.forEach(m => map.removeLayer(m)); storyChapterMarkers = [];
            
            const sc = document.getElementById('story-scroller'); 
            sc.innerHTML = ''; sc.scrollTop = 0; sc.scrollLeft = 0;
            
            // DYNAMIC SPACER - Fixes First Image Alignment
            const spacer = document.createElement('div');
            spacer.style.height = isMobile ? '1px' : '50vh'; 
            spacer.style.width = isMobile ? '50vw' : '100%';
            spacer.style.flexShrink = '0'; 
            sc.appendChild(spacer);

            currentStoryPoints = []; s.route_segment_ids.forEach(id => { if(routes[id]) currentStoryPoints.push(...routes[id].coords); });
            if(currentStoryPoints.length) {
                setupMath(currentStoryPoints);
                const pad = isMobile ? [20, 100] : [50, 50];
                map.flyToBounds(L.polyline(currentStoryPoints).getBounds(), { paddingTopLeft: [20,20], paddingBottomRight: pad, duration: 1.5 });
                map.once('moveend', () => {
                    if(!document.body.classList.contains('story-mode')) return;
                    bikeMarker = L.marker(currentStoryPoints[0], { icon: L.divIcon({ className: 'bike-icon', html: '🚴', iconSize:[30,30] }), zIndexOffset: 2000 }).addTo(map);
                    setTimeout(() => bikeMarker._icon.classList.add('visible'), 100);
                    s.chapters.forEach((c, i) => {
                        const pt = getPtAtD(c.progress * totalRouteLength);
                        const tm = L.marker(pt, { icon: L.divIcon({ className: 'map-chapter-thumb', html: `<img src="${c.image}">`, iconSize: [30, 30] }) }).addTo(map);
                        setTimeout(() => tm._icon.classList.add('visible'), 500 + (i*200)); storyChapterMarkers.push(tm);
                    });
                });
            }
            s.chapters.forEach(c => { const d = document.createElement('div'); d.className = 'story-card'; d.innerHTML = `<img src="${c.image}"><p>${c.text}</p>`; sc.appendChild(d); });
            
            const trail = document.createElement('div'); 
            trail.style.height = isMobile ? '1px' : '50vh'; 
            trail.style.width = isMobile ? '50vw' : '100%';
            trail.style.flexShrink = '0';
            sc.appendChild(trail);
            
            document.getElementById('scroll-hint').style.opacity = '1';
        }

        let lastScroll = 0;
        function checkStoryScroll() {
            const now = Date.now(); if (now - lastScroll < 16) return; lastScroll = now;
            const sc = document.getElementById('story-scroller');
            
            if(sc.scrollLeft > 10 || sc.scrollTop > 10) document.getElementById('scroll-hint').style.opacity = '0';

            let scrollPct = 0;
            if(isMobile) {
                scrollPct = sc.scrollLeft / (sc.scrollWidth - sc.clientWidth);
            } else {
                if((sc.scrollTop + sc.clientHeight) > (sc.scrollHeight - 50)) { exitStory(); return; }
                scrollPct = sc.scrollTop / (sc.scrollHeight - sc.clientHeight - 200);
            }
            
            const constrainedPct = Math.max(0, Math.min(1, scrollPct));
            const targetDist = constrainedPct * currentMaxProgress * totalRouteLength;
            
            if(bikeMarker && totalRouteLength > 0) bikeMarker.setLatLng(getPtAtD(targetDist));
            
            document.querySelectorAll('.story-card').forEach((card, i) => {
                const box = card.getBoundingClientRect();
                const center = isMobile ? (box.left + box.width/2) : (box.top + box.height/2);
                const screenCenter = isMobile ? (window.innerWidth/2) : (window.innerHeight/2);
                
                if(Math.abs(center - screenCenter) < (isMobile ? 150 : 300)) {
                    if(!card.classList.contains('active')) { card.classList.add('active'); storyChapterMarkers.forEach((m, idx) => m._icon && (idx === i ? m._icon.classList.add('active') : m._icon.classList.remove('active'))); }
                } else card.classList.remove('active');
            });
        }

        function exitStory() {
            if(!document.body.classList.contains('story-mode')) return; 
            document.body.classList.remove('story-mode');
            if(bikeMarker) map.removeLayer(bikeMarker); bikeMarker = null;
            storyChapterMarkers.forEach(m => map.removeLayer(m));
            if(savedMapState) map.flyTo(savedMapState.center, savedMapState.zoom, { duration: 1.5 });
        }

        function exitJourneyMode() {
            document.body.classList.remove('journey-mode');
            document.getElementById('chapter-btn-wrap').style.display = 'block'; 
        }

        function resetView() { 
            exitStory(); closeGallery(); closePanel(); exitJourneyMode();
            // document.body.classList.remove('shrunk'); // REMOVED - KEEP SHRUNK
            document.body.classList.remove('map-mode');
            
            let boundsPoints = allPoints;
            if(isMobile) boundsPoints = allPoints.slice(0, Math.floor(allPoints.length * 0.2));
            const pad = isMobile ? [20, 20] : [window.innerWidth * 0.25, 50];
            map.fitBounds(L.polyline(boundsPoints).getBounds(), { paddingTopLeft: pad, paddingBottomRight: [50, 50], duration: 1.5 }); 
        }
        
        function startJourney() { 
            shrinkHero();
            document.body.classList.add('journey-mode'); 
            closePanel();
            document.getElementById('chapter-btn-wrap').style.display = 'none';
            const track = document.getElementById('timeline-track'); 
            if(track.querySelectorAll('.nav-dot').length === 0) { 
                STAGES.forEach((s, i) => { 
                    const d = document.createElement('div'); d.className = 'nav-dot'; 
                    d.style.left = `${(i / (STAGES.length - 1)) * 100}%`; 
                    d.onclick = () => setStage(i); 
                    d.innerHTML = `<div class="dot-tooltip">${s.title}</div>`; 
                    track.appendChild(d); 
                }); 
            } 
        }

        function setStage(index) {
            const s = STAGES[index]; document.getElementById('st-title').innerText = s.title; document.getElementById('st-date').innerText = s.date_range; document.getElementById('st-desc').innerText = s.description; const tc = document.getElementById('st-thumbs'); tc.innerHTML = ''; s.images.forEach((u, i) => tc.innerHTML += `<div class="thumb-wrap" onclick="openLB(${index}, ${i})"><img src="${u}"></div>`); document.getElementById('timeline-fill').style.width = `${(index / (STAGES.length - 1)) * 100}%`; document.querySelectorAll('.nav-dot').forEach((d, i) => d.classList.toggle('active', i === index)); let pts = []; for(let i=s.start_index; i<=s.end_index; i++) { if(routes[i]) pts.push(...routes[i].coords); } if(pts.length) map.flyToBounds(L.polyline(pts).getBounds(), { padding: [100,100], duration: 2 });
        }

        function showDetail(data) { 
            currentRouteData = data; 
            document.getElementById('p-day').innerText = `Day ${data.day}`; 
            document.getElementById('p-date').innerText = data.date; 
            document.getElementById('p-dist').innerText = data.distance; 
            document.getElementById('p-time').innerText = data.duration; 
            document.getElementById('detail-panel').classList.add('open'); 
            renderChart(); 
        }
        function closePanel() { document.getElementById('detail-panel').classList.remove('open'); }
        function switchChart(type) { chartType = type; document.getElementById('btn-ele').className = `chart-toggle ${type==='ele'?'active':''}`; document.getElementById('btn-speed').className = `chart-toggle ${type==='speed'?'active blue':''}`; renderChart(); }
        function renderChart() { 
            if(!currentRouteData) return; 
            const ctx = document.getElementById('elChart').getContext('2d'); 
            if(activeChart) activeChart.destroy(); 
            const isEle = chartType === 'ele'; 
            activeChart = new Chart(ctx, { type: 'line', data: { datasets: [{ data: isEle ? currentRouteData.elevation : currentRouteData.speed, borderColor: isEle ? '#e63946' : '#457b9d', backgroundColor: isEle ? 'rgba(230, 57, 70, 0.1)' : 'rgba(69, 123, 157, 0.1)', fill: true, pointRadius: 0, borderWidth: 2, tension: 0.2 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { type: 'linear', display: true, title: { display: true, text: 'Distance (km)', color: '#94a3b8' }, ticks: { color: '#94a3b8' } }, y: { title: { display: true, text: isEle ? 'Elev (m)' : 'Speed (km/h)', color: '#94a3b8' }, ticks: { color: '#94a3b8' }, grid: { borderDash:[4,4] } } } } }); 
        }
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