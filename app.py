import os
import json
from flask import Flask, render_template_string

app = Flask(__name__)

# --- CONFIGURATION ---
DATA_FILE = "trip_data.json"
STAGES_DIR = os.path.join("data", "stages")
IMG_BASE_URL = "/static/images"
# ---------------------

def load_data_fast():
    print("--- LOADING V17 DATA ---")
    if not os.path.exists(DATA_FILE): return [], [], 0
    
    with open(DATA_FILE, 'r') as f:
        trip_data = json.load(f)
    
    routes = trip_data.get('routes', [])
    total_distance = trip_data.get('total_distance', 0)
    file_dates = trip_data.get('file_dates', {}) 

    stages = []
    if os.path.exists(STAGES_DIR):
        stage_files = sorted([f for f in os.listdir(STAGES_DIR) if f.endswith('.json')])
        for i, sf in enumerate(stage_files):
            try:
                with open(os.path.join(STAGES_DIR, sf), 'r') as f:
                    data = json.load(f)
                    s_idx = str(data.get('start_index', 0))
                    e_idx = str(data.get('end_index', 0))
                    data['date_range'] = f"{file_dates.get(s_idx, '?')} - {file_dates.get(e_idx, '?')}"

                    stage_folder = f"{i+1:02d}"
                    local_path = os.path.join("static", "images", stage_folder)
                    media_urls = []
                    if os.path.exists(local_path):
                        for f_name in sorted(os.listdir(local_path)):
                            if f_name.lower().endswith(('jpg','jpeg','png','webp', 'mp4', 'mov', 'webm')):
                                media_urls.append(f"{IMG_BASE_URL}/{stage_folder}/{f_name}")
                    data['images'] = media_urls
                    stages.append(data)
            except Exception: pass

    return routes, stages, total_distance

CACHED_ROUTES, CACHED_STAGES, CACHED_DIST = load_data_fast()

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
        :root { 
            --accent: #e63946; 
            --speed: #457b9d; 
            --text: #1d3557;
            --card-bg: rgba(255, 255, 255, 0.95);
        }
        body { background: #f1f5f9; color: var(--text); font-family: 'Inter', sans-serif; overflow: hidden; margin: 0; }
        h1, h2 { font-family: 'Playfair Display', serif; }
        .mono { font-family: 'Space Mono', monospace; }

        #map-container { position: fixed; inset: 0; z-index: 0; }
        #map { width: 100%; height: 100%; outline: none; background: #aad3df; }
        
        .ui-layer { position: absolute; inset: 0; pointer-events: none; z-index: 10; }
        .interactive { pointer-events: auto; }

        /* --- HERO SECTION --- */
        .hero { 
            position: fixed; inset: 0; pointer-events: none; z-index: 20;
            user-select: none; transition: 1s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .hero-content { 
            position: absolute; top: 50%; left: 5vw; transform: translateY(-50%); 
            transform-origin: top left; pointer-events: auto; transition: inherit;
        }
        .hero h1 { font-size: 6rem; line-height: 1; }
        .hero-gradient {
            position: fixed; inset: 0; width: 45%; 
            background: linear-gradient(to right, rgba(241, 245, 249, 0.98), transparent);
            pointer-events: none; z-index: 5; transition: 1s;
        }

        /* --- MOBILE RESPONSIVE HERO --- */
        @media (max-width: 768px) {
            .hero-content { left: 20px; right: 20px; top: 40%; text-align: center; transform: translateY(-50%); }
            .hero h1 { font-size: 3.5rem; margin-bottom: 1rem; }
            .hero-gradient { width: 100%; height: 60%; background: linear-gradient(to bottom, rgba(241,245,249,0.95), transparent); }
        }

        /* --- STATES --- */
        body.map-mode .hero-content { top: 30px; left: 30px; transform: scale(0.6); opacity: 0.8; }
        body.map-mode .hero-gradient { opacity: 0; }
        body.journey-mode .hero, body.journey-mode .hero-gradient { opacity: 0; pointer-events: none; }

        /* --- START BUTTON --- */
        .start-btn-container {
            position: absolute; bottom: 80px; left: 50%; transform: translateX(-50%);
            z-index: 30; pointer-events: auto; transition: 0.5s;
        }
        body.journey-mode .start-btn-container { opacity: 0; pointer-events: none; transform: translate(-50%, 100px); }
        .start-btn {
            background: white; color: var(--text); border: 1px solid var(--text); padding: 15px 40px;
            font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 3px; cursor: pointer;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1); transition: 0.3s;
        }
        .start-btn:hover { background: var(--text); color: white; transform: translateY(-3px); }

        /* --- STAGE CARD (Top Left on Desktop, Top Sheet on Mobile) --- */
        #stage-card {
            position: absolute; top: 30px; left: 30px; width: 400px;
            background: var(--card-bg); backdrop-filter: blur(20px);
            border-radius: 12px; padding: 25px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            transform: translateX(-150%); transition: transform 0.6s cubic-bezier(0.2, 1, 0.3, 1);
        }
        @media (max-width: 768px) {
            #stage-card { 
                top: 10px; left: 10px; right: 10px; width: auto; 
                transform: translateY(-150%); padding: 15px;
            }
            #stage-card h2 { font-size: 1.5rem; }
            #stage-card p { font-size: 0.8rem; }
        }
        body.journey-mode #stage-card { transform: translateX(0); }
        @media (max-width: 768px) { body.journey-mode #stage-card { transform: translateY(0); } }

        /* --- DETAIL PANEL (Bottom Right on Desktop, Bottom Sheet on Mobile) --- */
        #detail-panel {
            position: absolute; bottom: 90px; right: 30px; width: 400px;
            background: var(--card-bg); backdrop-filter: blur(20px);
            border-radius: 12px; padding: 20px;
            transform: translateY(150%); transition: transform 0.5s cubic-bezier(0.2, 1, 0.3, 1);
            box-shadow: 0 5px 30px rgba(0,0,0,0.15); z-index: 40;
        }
        @media (max-width: 768px) {
            #detail-panel { 
                bottom: 80px; left: 10px; right: 10px; width: auto; 
            }
        }
        #detail-panel.open { transform: translateY(0); }

        /* --- TIMELINE --- */
        .nav-bar {
            position: absolute; bottom: 0; left: 0; width: 100%; height: 70px;
            background: white; border-top: 1px solid #eee;
            display: flex; align-items: center; justify-content: center;
            transform: translateY(100%); transition: transform 0.6s ease;
        }
        body.journey-mode .nav-bar { transform: translateY(0); }
        .timeline { position: relative; width: 80%; height: 4px; background: #e2e8f0; border-radius: 2px; }
        .timeline-fill { position: absolute; top: 0; left: 0; height: 100%; width: 0%; background: var(--accent); border-radius: 2px; transition: width 0.5s; }
        .nav-dot {
            position: absolute; top: -6px; width: 16px; height: 16px; 
            background: #94a3b8; border: 3px solid white; border-radius: 50%; 
            cursor: pointer; transition: 0.3s;
        }
        .nav-dot.active { background: var(--accent); transform: scale(1.3); }
        .dot-tooltip {
            position: absolute; bottom: 25px; left: 50%; transform: translateX(-50%);
            background: #1e293b; color: white; padding: 4px 10px; font-size: 11px;
            border-radius: 4px; opacity: 0; pointer-events: none; transition: 0.2s; white-space: nowrap;
        }
        @media (min-width: 768px) { .nav-dot:hover .dot-tooltip { opacity: 1; bottom: 35px; } }

        /* --- THUMBNAILS & LIGHTBOX --- */
        .thumb-grid { display: flex; gap: 8px; margin-top: 15px; overflow-x: auto; scrollbar-width: none; -webkit-overflow-scrolling: touch; }
        .thumb-wrap { flex: 0 0 100px; height: 70px; border-radius: 6px; overflow: hidden; cursor: pointer; position: relative; }
        .thumb-wrap img, .thumb-wrap video { width: 100%; height: 100%; object-fit: cover; }
        .play-icon { position: absolute; inset: 0; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; }
        .play-icon:after { content: '▶'; color: white; }

        #lightbox { position: fixed; inset: 0; z-index: 5000; background: rgba(255,255,255,0.98); display: none; align-items: center; justify-content: center; }
        #lightbox img, #lightbox video { max-height: 85vh; max-width: 90vw; box-shadow: 0 20px 50px rgba(0,0,0,0.2); display: none; }
        .lb-btn { position: absolute; top: 50%; transform: translateY(-50%); padding: 20px; font-size: 30px; cursor: pointer; color: #333; user-select: none; }
        .lb-prev { left: 10px; } .lb-next { right: 10px; }
        .lb-close { position: absolute; top: 20px; right: 20px; font-size: 40px; cursor: pointer; }

        .chart-toggle { cursor: pointer; padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; background: #eee; color: #666; }
        .chart-toggle.active { background: var(--accent); color: white; }
        .home-btn { position: fixed; top: 20px; right: 20px; z-index: 500; width: 40px; height: 40px; background: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
    </style>
</head>
<body>

    <div id="map-container"><div id="map"></div></div>
    <div class="hero-gradient"></div>
    <div class="home-btn interactive" onclick="resetView()">&#8635;</div>

    <div class="ui-layer">
        <div id="hero" class="hero">
            <div class="hero-content">
                <h1 class="italic text-slate-800 mb-4">Cycling East</h1>
                <p class="text-sm uppercase tracking-[0.3em] text-slate-500">Leeds → Hong Kong &bull; {{ distance }} KM</p>
            </div>
        </div>
        <div class="start-btn-container">
            <button onclick="startJourney()" class="start-btn">Explore The Journey</button>
        </div>
    </div>

    <div class="ui-layer">
        <div id="stage-card" class="interactive">
            <h2 id="st-title" class="text-3xl text-accent mb-1 italic">Title</h2>
            <p id="st-date" class="text-xs text-slate-400 mono mb-2 uppercase border-l-2 border-slate-300 pl-3">Date</p>
            <p id="st-desc" class="text-slate-600 text-sm leading-relaxed mb-4 line-clamp-3">Description.</p>
            <div id="st-thumbs" class="thumb-grid"></div>
        </div>
    </div>

    <div class="ui-layer">
        <div id="detail-panel" class="interactive">
            <div class="flex justify-between items-start mb-2">
                <div><h2 id="p-day" class="text-xl text-accent italic">Day X</h2><p id="p-date" class="text-[10px] mono uppercase">Date</p></div>
                <button onclick="closePanel()" class="text-slate-400 text-xl">&times;</button>
            </div>
            <div class="flex justify-between items-end mb-2 pb-2 border-b border-slate-100">
                <div class="flex gap-4 mono text-[10px] text-slate-500"><span><b id="p-dist"></b> KM</span><span><b id="p-time"></b> RIDING</span></div>
                <div class="flex gap-1"><span id="btn-ele" class="chart-toggle active" onclick="switchChart('ele')">ELEV</span><span id="btn-speed" class="chart-toggle" onclick="switchChart('speed')">SPEED</span></div>
            </div>
            <div class="h-24 w-full"><canvas id="elChart"></canvas></div>
        </div>
    </div>

    <div class="ui-layer">
        <div id="nav-bar" class="nav-bar interactive">
            <div class="timeline" id="timeline-track">
                <div class="timeline-fill" id="timeline-fill"></div>
            </div>
        </div>
    </div>

    <div id="lightbox" class="interactive">
        <div class="lb-close" onclick="closeLB()">&times;</div>
        <div class="lb-btn lb-prev" onclick="changeSlide(-1)">&#10094;</div>
        <div class="lb-btn lb-next" onclick="changeSlide(1)">&#10095;</div>
        <img id="lb-img" src="">
        <video id="lb-vid" controls playsinline></video>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const routes = {{ routes|tojson }};
        const STAGES = {{ stages|tojson }};
        
        var map = L.map('map', { zoomControl: false, attributionControl: false }).setView([50, 0], 4);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', { maxZoom: 19 }).addTo(map);

        let activeChart = null, currentRouteData = null, chartType = 'ele', routeLayers = [];

        // --- INTRO ANIMATION ---
        function playIntroAnimation() {
            // Wait a moment for map tiles to load
            setTimeout(() => {
                routeLayers.forEach((layer, idx) => {
                    setTimeout(() => {
                        // Flash White then fade to Red
                        layer.setStyle({ opacity: 1, color: '#fff', weight: 4 });
                        setTimeout(() => layer.setStyle({ color: '#e63946', weight: 3 }), 150);
                    }, idx * 40); // 40ms delay between each segment
                });
            }, 500);
        }

        // --- SETUP ROUTES ---
        let allPoints = [];
        routes.forEach(route => {
            allPoints.push(...route.coords);
            
            // Visual Line (Initially Invisible)
            const visual = L.polyline(route.coords, { color: '#e63946', weight: 3, opacity: 0 }).addTo(map);
            routeLayers.push(visual);

            // Hit Box (Invisible Click Target)
            const hit = L.polyline(route.coords, { color: 'transparent', weight: 25, opacity: 0, zIndexOffset: 1000 }).addTo(map);
            
            hit.on('mouseover', () => { visual.setStyle({ color: '#1d3557', weight: 5, opacity: 1 }); hit.bindTooltip(`DAY ${route.day}`, { sticky: true, className: 'custom-tooltip' }).openTooltip(); });
            hit.on('mouseout', () => visual.setStyle({ color: '#e63946', weight: 3 }));
            hit.on('click', (e) => { showDetail(route); L.DomEvent.stopPropagation(e); });
        });

        // Trigger animation on load
        window.addEventListener('load', () => {
            if(allPoints.length) {
                // Adjust zoom padding for mobile vs desktop
                const isMobile = window.innerWidth < 768;
                const pads = isMobile ? [20, 20] : [50, 50];
                const topLeft = isMobile ? [0, 0] : [window.innerWidth * 0.4, 0];
                
                map.fitBounds(L.polyline(allPoints).getBounds(), { 
                    paddingTopLeft: topLeft, paddingBottomRight: pads, duration: 0 
                });
                playIntroAnimation();
            }
        });

        // --- INTERACTION ---
        map.on('mousedown dragstart', () => { if(!document.body.classList.contains('journey-mode')) document.body.classList.add('map-mode'); });
        function resetView() { document.body.classList.remove('map-mode', 'journey-mode'); closePanel(); }

        function startJourney() {
            document.body.classList.add('journey-mode');
            const track = document.getElementById('timeline-track');
            if(track.childElementCount <= 1) {
                STAGES.forEach((s, i) => {
                    const dot = document.createElement('div');
                    dot.className = 'nav-dot';
                    dot.style.left = `${(i / (STAGES.length - 1)) * 100}%`;
                    dot.onclick = () => setStage(i);
                    track.appendChild(dot);
                });
            }
            setStage(0);
        }

        function setStage(index) {
            const stage = STAGES[index];
            document.getElementById('st-title').innerText = stage.title;
            document.getElementById('st-date').innerText = stage.date_range;
            document.getElementById('st-desc').innerText = stage.description;
            
            const thumbContainer = document.getElementById('st-thumbs');
            thumbContainer.innerHTML = '';
            if(stage.images) stage.images.forEach((url, i) => {
                const isVid = url.match(/\.(mp4|mov)$/i);
                thumbContainer.innerHTML += `<div class="thumb-wrap" onclick="openLB(${index}, ${i})">${isVid ? '<div class="play-icon"></div><video src="'+url+'"></video>' : '<img src="'+url+'">'}</div>`;
            });

            document.getElementById('timeline-fill').style.width = `${(index / (STAGES.length - 1)) * 100}%`;
            document.querySelectorAll('.nav-dot').forEach((d, i) => d.classList.toggle('active', i === index));

            let pts = [];
            for(let i=stage.start_index; i<=stage.end_index; i++) { if(routes[i]) pts.push(...routes[i].coords); }
            if(pts.length) {
                const pad = window.innerWidth < 768 ? [20, 100] : [100, 100];
                map.flyToBounds(L.polyline(pts).getBounds(), { padding: pad, duration: 2 });
            }
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
            activeChart = new Chart(ctx, {
                type: 'line',
                data: { datasets: [{ data: isEle ? currentRouteData.elevation : currentRouteData.speed, borderColor: isEle ? '#e63946' : '#457b9d', backgroundColor: isEle ? 'rgba(230, 57, 70, 0.1)' : 'rgba(69, 123, 157, 0.1)', fill: true, pointRadius: 0, borderWidth: 2, tension: 0.2 }] },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { type: 'linear', display: false }, y: { ticks: { color: '#888', font: {size:9} }, grid: { borderDash:[4,4] } } } }
            });
        }

        let currStg = 0, currImg = 0;
        function openLB(sIdx, iIdx) { currStg = sIdx; currImg = iIdx; updateLB(); document.getElementById('lightbox').style.display = 'flex'; }
        function closeLB() { document.getElementById('lb-vid').pause(); document.getElementById('lightbox').style.display = 'none'; }
        function updateLB() {
            const url = STAGES[currStg].images[currImg];
            const isVid = url.match(/\.(mp4|mov)$/i);
            const v = document.getElementById('lb-vid'), i = document.getElementById('lb-img');
            if(isVid) { i.style.display='none'; v.style.display='block'; v.src=url; v.play(); } 
            else { v.pause(); v.style.display='none'; i.style.display='block'; i.src=url; }
        }
        function changeSlide(dir) { const imgs = STAGES[currStg].images; currImg = (currImg + dir + imgs.length) % imgs.length; updateLB(); }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, routes=CACHED_ROUTES, stages=CACHED_STAGES, distance=CACHED_DIST)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)