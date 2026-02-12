#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 12 14:17:43 2026

@author: ben
"""

import os
import json
import gpxpy
from datetime import datetime

# --- CONFIG
DATA_DIR = "./data"
GPX_DIR = os.path.join(DATA_DIR, "gpx")
OUTPUT_FILE = "trip_data.json"
TRIP_START_DATE = datetime(2025, 4, 1)

def format_duration(seconds):
    if not seconds: return "N/A"
    hours, remainder = divmod(int(seconds), 3600)
    minutes = (remainder % 3600) // 60
    return f"{hours}h {minutes}m"

def process():
    print("--- STARTING PROCESSING ---")
    routes = []
    total_distance = 0
    file_dates = {}

    gpx_files = sorted([f for f in os.listdir(GPX_DIR) if f.endswith('.gpx')])
    
    for idx, filename in enumerate(gpx_files):
        filepath = os.path.join(GPX_DIR, filename)
        try:
            with open(filepath, 'r') as gf:
                gpx = gpxpy.parse(gf)
                for track in gpx.tracks:
                    for segment in track.segments:
                        if not segment.points: continue
                        
                        start_time = segment.points[0].time.replace(tzinfo=None) if segment.points[0].time else TRIP_START_DATE
                        file_dates[idx] = start_time.strftime("%b %d")
                        
                        # --- DOWNSAMPLING ---
                        # We only keep 1 in every 20 points. 
                        # This reduces file size by 95% while keeping the route looking perfect on a zoomed-out map.
                        STEP = 20 
                        
                        points = []
                        ele_data = []
                        speed_data = []
                        curr_dist = 0

                        for i, pt in enumerate(segment.points):
                            # Calculate speed/dist for ALL points before skipping
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
                            
                            # ONLY SAVE every 20th point
                            if i % STEP == 0 or i == len(segment.points)-1:
                                points.append([round(pt.latitude, 5), round(pt.longitude, 5)])
                                ele_data.append({"x": round(curr_dist, 2), "y": int(pt.elevation or 0)})
                                speed_data.append({"x": round(curr_dist, 2), "y": round(speed_val, 1)})

                        dist_km = segment.length_3d() / 1000
                        total_distance += dist_km
                        
                        dur_val = segment.get_duration()
                        dur_str = format_duration(dur_val) if dur_val else "N/A"

                        routes.append({
                            "id": idx,
                            "day": (start_time - TRIP_START_DATE).days + 1,
                            "date": start_time.strftime("%d %b %Y"),
                            "coords": points,
                            "elevation": ele_data,
                            "speed": speed_data,
                            "distance": round(dist_km, 1),
                            "duration": dur_str
                        })
            print(f"Processed {filename}")
        except Exception as e:
            print(f"Failed {filename}: {e}")

    # SAVE TO JSON
    final_data = {
        "routes": routes,
        "total_distance": round(total_distance),
        "file_dates": file_dates # Save dates to look up for stages
    }
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(final_data, f)
    print(f"--- SUCCESS! Saved to {OUTPUT_FILE} ---")

if __name__ == "__main__":
    process()