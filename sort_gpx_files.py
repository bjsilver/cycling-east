#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Feb 11 11:12:46 2026

@author: ben
"""

import gpxpy
from glob import glob
import pandas as pd
import os

gpx_path = '/home/ben/scripts/leedstohk/data/gpx/'


def get_gpx_date(file_path):
    try:
        with open(file_path, 'r') as gpx_file:
            gpx = gpxpy.parse(gpx_file)

        # Strategy 1: Check the global metadata timestamp
        start_time = gpx.time
        
        # Strategy 2: If metadata is missing, get time from the first point
        if not start_time:
            for track in gpx.tracks:
                for segment in track.segments:
                    if segment.points:
                        start_time = segment.points[0].time
                        break
                if start_time: break

        if start_time:
            # Format: YYYY-MM-DD HH:MM:SS
            return start_time.strftime('%Y-%m-%d %H:%M:%S')
        else:
            return "No date found in file."

    except Exception as e:
        return f"Error reading file: {e}"

#%%
gpx_files = glob(gpx_path+'*.gpx')

def check_if_in_range(date, start_date, end_date):
    timestamp = pd.Timestamp(date)
    
    if (timestamp >= start_date) & (timestamp <= end_date):
        return True
    else:
        return False
    
#%% 
start_date = pd.Timestamp(2025, 4, 1)
end_date = pd.Timestamp(2025, 12, 24)
    
for fpath in gpx_files:
    date = get_gpx_date(fpath)
    in_journey = check_if_in_range(date, start_date, end_date)
    
    if not in_journey:
        os.remove(fpath)
        print('removed', fpath, 'from', date)

#%%