import os
import json
import gpxpy
from datetime import datetime
from flask import Flask, render_template_string

app = Flask(__name__)

# --- CONFIGURATION ---
DATA_DIR = "./data"
GPX_DIR = os.path.join(DATA_DIR, "gpx")
STAGES_DIR = os.path.join(DATA_DIR, "stages")
STATIC_IMG_DIR = os.path.join("static", "images") 
TRIP_START_DATE = datetime(2025, 4, 1)
# ---------------------

def format_duration(seconds):
    if not seconds: return "N/A"
    hours, remainder = divmod(int(seconds), 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}m"

def load_data():
    print("\n--- LOADING DATA V11 ---")
    routes = []
    total_distance = 0
    
    if not os.path.exists(GPX_DIR): os.makedirs(GPX_DIR, exist_ok=True)
    if not os.path.exists(STAGES_DIR): os.makedirs(STAGES_DIR, exist_ok=True)

    gpx_files = sorted([f for f in os.listdir(GPX_DIR) if f.endswith('.gpx')])
    file_dates = {} 

    # 1. Parse GPX
    for idx, filename in enumerate(gpx_files):
        filepath = os.path.join(GPX_DIR, filename)
        try:
            with open(filepath, 'r') as gf:
                gpx = gpxpy.parse(gf)
                for track in gpx.tracks:
                    for segment in track.segments:
                        if not segment.points: continue
                        
                        points = []
                        ele_data = []
                        speed_data = []
                        curr_dist = 0
                        
                        start_time = segment.points[0].time.replace(tzinfo=None) if segment.points[0].time else TRIP_START_DATE
                        day_num = (start_time - TRIP_START_DATE).days + 1
                        file_dates[idx] = start_time.strftime("%b %d")

                        for i, pt in enumerate(segment.points):
                            points.append([pt.latitude, pt.longitude])
                            
                            speed_val = 0
                            if i > 0:
                                dist_delta = pt.distance_3d(segment.points[i-1])
                                curr_dist += dist_delta / 1000
                                time_delta = 0
                                if pt.time and segment.points[i-1].time:
                                    time_delta = (pt.time - segment.points[i-1].time).total_seconds()
                                if time_delta > 0:
                                    speed_val = (dist_delta / time_delta) * 3.6
                                    if speed_val > 80: speed_val = 0 

                            if i % 5 == 0 or i == len(segment.points)-1:
                                ele_data.append({"x": round(curr_dist, 2), "y": int(pt.elevation) if pt.elevation else 0})
                                speed_data.append({"x": round(curr_dist, 2), "y": round(speed_val, 1)})

                        dist_km = segment.length_3d() / 1000
                        total_distance += dist_km
                        
                        dur_str = "N/A"
                        dur_val = segment.get_duration()
                        if dur_val: dur_str = format_duration(dur_val)

                        routes.append({
                            "id": idx,
                            "day": day_num,
                            "date": start_time.strftime("%d %b %Y"),
                            "coords": points,
                            "elevation": ele_data,
                            "speed": speed_data,
                            "distance": round(dist_km, 1),
                            "duration": dur_str
                        })
        except Exception: pass

    # 2. Load Stages
    stages = []
    if os.path.exists(STAGES_DIR):
        stage_files = sorted([f for f in os.listdir(STAGES_DIR) if f.endswith('.json')])
        for i, sf in enumerate(stage_files):
            try:
                with open(os.path.join(STAGES_DIR, sf), 'r') as f:
                    data = json.load(f)
                    s_idx = data.get('start_index', 0)
                    e_idx = data.get('end_index', 0)
                    start_str = file_dates.get(s_idx, "Unknown")
                    end_str = file_dates.get(e_idx, "Unknown")
                    data['date_range'] = f"{start_str} - {end_str}"

                    stage_folder = f"{i+1:02d}" 
                    local_img_path = os.path.join(STATIC_IMG_DIR, stage_folder)
                    found_imgs = []
                    if os.path.exists(local_img_path):
                        for img_file in sorted(os.listdir(local_img_path)):
                            if img_file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                                found_imgs.append(f"/static/images/{stage_folder}/{img_file}")
                    
                    if found_imgs: data['images'] = found_imgs
                    elif 'images' not in data: data['images'] = []
                    stages.append(data)
            except Exception: pass

    return routes, stages, round(total_distance)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
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
            --bg-color: #f1f5f9;
            --card-bg: rgba(255, 255, 255, 0.95);
        }
        body { background: var(--bg-color); color: var(--text); font-family: 'Inter', sans-serif; overflow: hidden; margin: 0; }
        h1, h2 { font-family: 'Playfair Display', serif; }
        .mono { font-family: 'Space Mono', monospace; }

        /* Map */
        #map-container { position: fixed; inset: 0; z-index: 0; }
        #map { width: 100%; height: 100%; outline: none; }
        
        .ui-layer { position: absolute; inset: 0; pointer-events: none; z-index: 10; }
        .interactive { pointer-events: auto; }

        /* --- GRADIENT --- */
        .hero-gradient {
            position: fixed; top: 0; left: 0; width: 45%; height: 100%;
            background: linear-gradient(to right, rgba(241, 245, 249, 0.98), rgba(241, 245, 249, 0));
            pointer-events: none; z-index: 5; transition: all 1.2s ease;
        }

        /* --- HERO TEXT (RE-ENGINEERED ANIMATION) --- */
        .hero { 
            position: fixed; inset: 0; pointer-events: none; z-index: 20;
            user-select: none; /* Prevents text highlighting bug */
        }
        
        .hero-content { 
            position: absolute;
            top: 50%; left: 5vw; /* Start Centered Vertically */
            transform: translateY(-50%); 
            transform-origin: top left;
            pointer-events: auto; 
            transition: all 1.2s cubic-bezier(0.16, 1, 0.3, 1); /* Ultra Smooth Bezier */
        }

        /* MAP MODE: Smoothly float to top left */
        body.map-mode .hero-content {
            top: 30px; left: 30px;
            transform: translateY(0) scale(0.65); /* Scale down smoothly */
            background: rgba(255,255,255,0.85); backdrop-filter: blur(10px);
            padding: 20px; border-radius: 12px; 
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }
        
        /* Fade out gradient when moving title */
        body.map-mode .hero-gradient { opacity: 0; width: 0; }
        
        /* JOURNEY MODE: Hide completely */
        body.journey-mode .hero { opacity: 0; pointer-events: none; }
        body.journey-mode .hero-content { transform: translateY(-50px); }
        body.journey-mode .hero-gradient { opacity: 0; }

        /* --- START BUTTON (Bottom Center) --- */
        .start-btn-container {
            position: absolute; bottom: 80px; left: 50%; transform: translateX(-50%);
            z-index: 30; pointer-events: auto;
            transition: opacity 0.5s ease, transform 0.5s ease;
        }
        /* KEY FIX: We DO NOT hide this in map-mode anymore, only in journey-mode */
        body.journey-mode .start-btn-container { 
            opacity: 0; pointer-events: none; transform: translate(-50%, 50px); 
        }

        .start-btn {
            background: white; color: var(--text); 
            border: 1px solid var(--text); padding: 15px 40px;
            font-family: 'Inter', sans-serif; font-size: 12px; font-weight: 600;
            text-transform: uppercase; letter-spacing: 3px; cursor: pointer;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            transition: all 0.3s;
        }
        .start-btn:hover { background: var(--text); color: white; transform: translateY(-3px); }

        /* --- STAGE CARD --- */
        #stage-card {
            position: absolute; top: 30px; left: 30px; width: 400px;
            background: var(--card-bg); backdrop-filter: blur(20px);
            border-radius: 12px; padding: 25px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            transform: translateX(-150%); transition: transform 0.6s cubic-bezier(0.2, 1, 0.3, 1);
        }
        body.journey-mode #stage-card { transform: translateX(0); }

        /* --- DETAIL PANEL --- */
        #detail-panel {
            position: absolute; bottom: 90px; right: 30px; width: 400px;
            background: var(--card-bg); backdrop-filter: blur(20px);
            border-radius: 12px; padding: 20px;
            transform: translateY(150%); transition: transform 0.5s cubic-bezier(0.2, 1, 0.3, 1);
            box-shadow: 0 5px 30px rgba(0,0,0,0.15);
        }
        #detail-panel.open { transform: translateY(0); }

        /* --- BOTTOM NAV BAR --- */
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
            cursor: pointer; transition: all 0.3s; box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .nav-dot:hover, .nav-dot.active { background: var(--accent); transform: scale(1.3); }
        .dot-tooltip {
            position: absolute; bottom: 25px; left: 50%; transform: translateX(-50%);
            background: #1e293b; color: white; padding: 4px 10px; font-size: 11px;
            border-radius: 4px; opacity: 0; pointer-events: none; transition: 0.2s; white-space: nowrap;
        }
        .nav-dot:hover .dot-tooltip { opacity: 1; bottom: 35px; }

        /* Thumbnails */
        .thumb-grid { display: flex; gap: 8px; margin-top: 15px; overflow-x: auto; scrollbar-width: none; }
        .thumb-wrap { 
            flex: 0 0 100px; height: 70px; border-radius: 6px; overflow: hidden; 
            cursor: pointer; transition: 0.2s; 
        }
        .thumb-wrap img { width: 100%; height: 100%; object-fit: cover; }
        .thumb-wrap:hover { transform: scale(1.05); }

        /* Lightbox */
        #lightbox { 
            position: fixed; inset: 0; z-index: 5000; background: rgba(255,255,255,0.98); 
            display: none; align-items: center; justify-content: center; 
        }
        #lightbox img { max-height: 85vh; max-width: 90vw; box-shadow: 0 20px 50px rgba(0,0,0,0.2); }
        .lb-btn { 
            position: absolute; top: 50%; transform: translateY(-50%); padding: 20px;
            font-size: 30px; cursor: pointer; color: #333; transition: 0.2s; user-select: none;
        }
        .lb-btn:hover { color: var(--accent); transform: translateY(-50%) scale(1.2); }
        .lb-prev { left: 30px; } .lb-next { right: 30px; }
        .lb-close { position: absolute; top: 30px; right: 40px; font-size: 40px; cursor: pointer; color: #333; }

        /* Misc */
        .chart-toggle { cursor: pointer; padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; background: #eee; color: #666; }
        .chart-toggle.active { background: var(--accent); color: white; }
        .chart-toggle.active.blue { background: var(--speed); }
        .custom-tooltip { background: white; border: 1px solid #ddd; color: #333; font-family: monospace; font-size: 11px; padding: 5px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        
        .home-btn {
            position: fixed; top: 30px; right: 30px; z-index: 500;
            width: 45px; height: 45px; background: white; 
            border: 1px solid rgba(0,0,0,0.1); border-radius: 50%; color: var(--accent);
            display: flex; align-items: center; justify-content: center; cursor: pointer;
            transition: 0.3s; font-size: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);
        }
        .home-btn:hover { background: var(--accent); color: white; transform: rotate(45deg); }
    </style>
</head>
<body>

    <div id="map-container"><div id="map"></div></div>
    
    <div class="hero-gradient"></div>

    <div class="home-btn interactive" onclick="resetView()" title="Reset View">&#8635;</div>

    <div class="ui-layer">
        <div id="hero" class="hero">
            <div class="hero-content">
                <h1 class="text-8xl italic text-slate-800 mb-8">Cycling East</h1>
                <p class="text-sm uppercase tracking-[0.4em] text-slate-500">Leeds → Hong Kong &bull; {{ distance }} KM</p>
            </div>
        </div>
        <div class="start-btn-container">
            <button onclick="startJourney()" class="start-btn">Explore The Journey</button>
        </div>
    </div>

    <div class="ui-layer">
        <div id="stage-card" class="interactive">
            <h2 id="st-title" class="text-3xl text-accent mb-1 italic">Stage Title</h2>
            <p id="st-date" class="text-xs text-slate-400 mono mb-4 tracking-widest uppercase border-l-2 border-slate-300 pl-3">Date Range</p>
            <p id="st-desc" class="text-slate-600 text-sm leading-relaxed mb-4">Description text goes here.</p>
            <div id="st-thumbs" class="thumb-grid"></div>
        </div>
    </div>

    <div class="ui-layer">
        <div id="detail-panel" class="interactive">
            <div class="flex justify-between items-start mb-2">
                <div>
                    <h2 id="p-day" class="text-xl text-accent italic">Day X</h2>
                    <p id="p-date" class="text-[10px] text-slate-400 mono uppercase tracking-widest">Date</p>
                </div>
                <button onclick="closePanel()" class="text-slate-400 hover:text-slate-800 text-xl">&times;</button>
            </div>
            <div class="flex justify-between items-end mb-2 pb-2 border-b border-slate-100">
                <div class="flex gap-4 mono text-[10px] text-slate-500">
                    <span><b id="p-dist" class="text-slate-800"></b> KM</span>
                    <span><b id="p-time" class="text-slate-800"></b> RIDING</span>
                </div>
                <div class="flex gap-1">
                    <span id="btn-ele" class="chart-toggle active" onclick="switchChart('ele')">ELEV</span>
                    <span id="btn-speed" class="chart-toggle" onclick="switchChart('speed')">SPEED</span>
                </div>
            </div>
            <div class="h-32 w-full"><canvas id="elChart"></canvas></div>
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
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const routes = {{ routes|tojson }};
        const STAGES = {{ stages|tojson }};
        
        var map = L.map('map', { zoomControl: false, attributionControl: false }).setView([50, 0], 4);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', { maxZoom: 19 }).addTo(map);

        let activeChart = null;
        let currentRouteData = null;
        let chartType = 'ele';
        let isMapMode = false;

        // --- INTERACTION LOGIC ---
        map.on('mousedown dragstart', function() {
            if(!document.body.classList.contains('journey-mode')) {
                document.body.classList.add('map-mode');
            }
        });

        function resetView() {
            document.body.classList.remove('map-mode');
            document.body.classList.remove('journey-mode');
            window.scrollTo({ top: 0, behavior: 'smooth' });
            closePanel();
            zoomToAll();
        }

        function startJourney() {
            document.body.classList.add('journey-mode');
            
            const track = document.getElementById('timeline-track');
            if(track.childElementCount <= 1) {
                STAGES.forEach((s, i) => {
                    const dot = document.createElement('div');
                    dot.className = 'nav-dot';
                    dot.style.left = `${(i / (STAGES.length - 1)) * 100}%`;
                    dot.onclick = () => setStage(i);
                    dot.innerHTML = `<div class="dot-tooltip">${s.title}</div>`;
                    track.appendChild(dot);
                });
            }
            setStage(0);
        }

        // --- DRAW ROUTES ---
        let allPoints = [];
        routes.forEach(route => {
            allPoints.push(...route.coords);
            const line = L.polyline(route.coords, { color: '#e63946', weight: 3, opacity: 0.9, lineCap: 'round' }).addTo(map);
            const hit = L.polyline(route.coords, { color: 'transparent', weight: 25, opacity: 0, zIndexOffset: 1000 }).addTo(map);

            hit.on('mouseover', () => {
                line.setStyle({ color: '#1d3557', weight: 5 });
                hit.bindTooltip(`DAY ${route.day}`, { sticky: true, className: 'custom-tooltip' }).openTooltip();
            });
            hit.on('mouseout', () => line.setStyle({ color: '#e63946', weight: 3 }));
            hit.on('click', (e) => {
                showDetail(route);
                L.DomEvent.stopPropagation(e);
            });
        });

        // --- STAGE LOGIC ---
        function setStage(index) {
            const stage = STAGES[index];
            document.getElementById('st-title').innerText = stage.title;
            document.getElementById('st-date').innerText = stage.date_range;
            document.getElementById('st-desc').innerText = stage.description;
            
            const thumbContainer = document.getElementById('st-thumbs');
            thumbContainer.innerHTML = '';
            if(stage.images) {
                stage.images.forEach((img, imgIdx) => {
                    thumbContainer.innerHTML += `<div class="thumb-wrap" onclick="openLB(${index}, ${imgIdx})"><img src="${img}"></div>`;
                });
            }

            document.getElementById('timeline-fill').style.width = `${(index / (STAGES.length - 1)) * 100}%`;
            document.querySelectorAll('.nav-dot').forEach((d, i) => d.classList.toggle('active', i === index));

            let pts = [];
            for(let i=stage.start_index; i<=stage.end_index; i++) {
                if(routes[i]) pts.push(...routes[i].coords);
            }
            if(pts.length) map.flyToBounds(L.polyline(pts).getBounds(), { padding: [100, 100], duration: 2 });
        }

        // --- DETAILS PANEL ---
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

        function switchChart(type) {
            chartType = type;
            document.getElementById('btn-ele').className = `chart-toggle ${type==='ele'?'active':''}`;
            document.getElementById('btn-speed').className = `chart-toggle ${type==='speed'?'active blue':''}`;
            renderChart();
        }

        function renderChart() {
            if(!currentRouteData) return;
            const ctx = document.getElementById('elChart').getContext('2d');
            if(activeChart) activeChart.destroy();
            
            const isEle = chartType === 'ele';
            const dataset = isEle ? currentRouteData.elevation : currentRouteData.speed;
            const color = isEle ? '#e63946' : '#457b9d';
            const bg = isEle ? 'rgba(230, 57, 70, 0.1)' : 'rgba(69, 123, 157, 0.1)';

            activeChart = new Chart(ctx, {
                type: 'line',
                data: {
                    datasets: [{
                        data: dataset, borderColor: color, backgroundColor: bg,
                        fill: true, pointRadius: 0, borderWidth: 2, tension: 0.2
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { 
                        x: { type: 'linear', display: false }, 
                        y: { ticks: { color: '#888', font: {size:9} }, grid: { borderDash:[4,4] } } 
                    }
                }
            });
        }

        // --- LIGHTBOX ---
        let currStg = 0, currImg = 0;
        function openLB(sIdx, iIdx) {
            currStg = sIdx; currImg = iIdx;
            updateLB();
            document.getElementById('lightbox').style.display = 'flex';
        }
        function closeLB() { document.getElementById('lightbox').style.display = 'none'; }
        function updateLB() {
            document.getElementById('lb-img').src = STAGES[currStg].images[currImg];
        }
        function changeSlide(dir) {
            const imgs = STAGES[currStg].images;
            currImg = (currImg + dir + imgs.length) % imgs.length;
            updateLB();
        }
        document.addEventListener('keydown', e => {
            if(document.getElementById('lightbox').style.display === 'flex') {
                if(e.key === 'ArrowLeft') changeSlide(-1);
                if(e.key === 'ArrowRight') changeSlide(1);
                if(e.key === 'Escape') closeLB();
            }
        });

        function zoomToAll() {
            if(allPoints.length) {
                map.fitBounds(L.polyline(allPoints).getBounds(), { 
                    paddingTopLeft: [window.innerWidth * 0.4, 0], 
                    paddingBottomRight: [50, 50],
                    duration: 1.5 
                });
            }
        }
        setTimeout(zoomToAll, 500);

    </script>
</body>
</html>
"""

@app.route('/')
def index():
    routes, stages, total_km = load_data()
    return render_template_string(HTML_TEMPLATE, routes=routes, stages=stages, distance=total_km)

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5000)