#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Feb 11 10:51:51 2026

@author: ben
"""

import gzip
import fitparse
import gpxpy
import gpxpy.gpx
from glob import glob
#%%

def convert_fit_gz_to_gpx(input_path, output_path):
    # 1. Decompress the .fit.gz file
    with gzip.open(input_path, 'rb') as f_in:
        fit_data = f_in.read()

    # 2. Parse the FIT data
    fit_file = fitparse.FitFile(fit_data)
    
    # 3. Initialize GPX structure
    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)
    gpx_segment = gpxpy.gpx.GPXTrackSegment()
    gpx_track.segments.append(gpx_segment)

    # 4. Extract data points
    for record in fit_file.get_messages('record'):
        data = record.get_values()
        
        # Check if essential coordinates exist
        if 'position_lat' in data and 'position_long' in data:
            # FIT coordinates are often in semicircles; convert to degrees
            lat = data['position_lat'] * (180.0 / 2**31)
            lon = data['position_long'] * (180.0 / 2**31)
            alt = data.get('enhanced_altitude', data.get('altitude'))
            timestamp = data.get('timestamp')

            gpx_segment.points.append(
                gpxpy.gpx.GPXTrackPoint(lat, lon, elevation=alt, time=timestamp)
            )

    # 5. Save the output
    with open(output_path, 'w') as f_out:
        f_out.write(gpx.to_xml())
    
    print(f"Successfully converted: {output_path}")
    
#%%
activities_path = '/home/ben/scripts/leedstohk/data/activities/'
gpx_path = '/home/ben/scripts/leedstohk/data/gpx/'

files_to_convert = glob(activities_path+'*.fit.gz')

for fpath in files_to_convert:
    
    fname = fpath.split('/')[-1].split('.')[0]

    convert_fit_gz_to_gpx(input_path=fpath,
                          output_path=gpx_path+fname+'.gpx')