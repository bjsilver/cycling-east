import os
import json

# --- CONFIGURATION ---
# Path to the "trip" folder containing the numbered subfolders
POLARSTEPS_TRIP_DIR = "/home/ben/scripts/leedstohk/data/polarsteps/user_data/trip/leeds-hk_17059867/"

# Path to your trip.json file
TRIP_JSON_FILE = POLARSTEPS_TRIP_DIR+"trip.json" # Update if needed

# Output
OUTPUT_FILE = "photo_map.json"

def process():
    print("--- Starting Method 3 (Folder Matching) ---")
    
    # 1. Load Trip Steps
    if not os.path.exists(TRIP_JSON_FILE):
        print(f"Error: Could not find {TRIP_JSON_FILE}")
        return

    with open(TRIP_JSON_FILE, 'r') as f:
        trip_data = json.load(f)
    
    # Create a lookup map: Step ID -> [Lat, Lon]
    step_locations = {}
    for step in trip_data['all_steps']:
        if step.get('location'):
            step_locations[step['id']] = [step['location']['lat'], step['location']['lon']]
    
    print(f"Loaded {len(step_locations)} step locations from trip.json")

    # 2. Scan Folders
    photo_map = {}
    
    # Walk through the Polarsteps directory
    for root, dirs, files in os.walk(POLARSTEPS_TRIP_DIR):
        # We are looking for folders. The photos might be in '.../step_ID/photos/'
        # So we look at the parent folder name to find the ID.
        
        current_folder = os.path.basename(root)
        parent_folder = os.path.basename(os.path.dirname(root))
        
        # Check if we are in a 'photos' folder, or directly in the step folder
        target_folder_name = current_folder
        if current_folder == "photos":
            target_folder_name = parent_folder
            
        # Try to extract the ID (e.g., "varciorog_157898908" -> 157898908)
        try:
            # Split by underscore and take the last part
            parts = target_folder_name.split('_')
            step_id = int(parts[-1])
        except ValueError:
            continue # This folder doesn't have an ID in its name, skip it
            
        # Check if we have a location for this ID
        if step_id in step_locations:
            lat, lon = step_locations[step_id]
            
            # Map every image in this folder to that location
            for file in files:
                if file.lower().endswith(('jpg', 'jpeg', 'png', 'webp')):
                    # We map the FILENAME to the COORDINATES
                    photo_map[file] = [lat, lon]
                    # print(f"Mapped {file} -> Step {step_id}")
        
    # 3. Save Result
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(photo_map, f)
    
    print(f"--- Success! Mapped {len(photo_map)} photos. Saved to {OUTPUT_FILE} ---")

if __name__ == "__main__":
    process()