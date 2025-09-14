import os
import hashlib
import json
import datetime

# You can add multiple directories here
directories_to_check = [
    r"C:\Users\Manoj\OneDrive\Desktop\ddas_project\download_files",
    r"C:\Users\Manoj\Downloads"  # example second directory
]

metadata_file = "file_metadata.json"

def get_file_hash(file_path):
    """Generate SHA256 hash for a given file"""
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def load_metadata():
    """Load JSON metadata if exists, else return empty dict"""
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r') as f:
            return json.load(f)
    return {}

def save_metadata(metadata):
    """Save metadata dictionary to file"""
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=4)

def check_for_duplicates(file_name):
    metadata = load_metadata()
    found_any = False  

    for directory in directories_to_check:
        file_path = os.path.join(directory, file_name)
        
        if os.path.exists(file_path):
            found_any = True
            file_hash = get_file_hash(file_path)

            if file_hash in metadata:
                existing_info = metadata[file_hash]
                if existing_info['location'] == file_path:
                    print(f"Duplicate found!\n"
                          f"File Name: {file_name}\n"
                          f"Location: {existing_info['location']}\n"
                          f"Downloaded at: {existing_info['timestamp']}")
                else:
                    print(f"Same content already exists in another location:\n"
                          f"{existing_info['location']}")
            else:
                current_time = str(datetime.datetime.now())
                metadata[file_hash] = {
                    'location': file_path,
                    'timestamp': current_time
                }
                save_metadata(metadata)
                print(f"File '{file_name}' added to metadata at {current_time}.")

    if not found_any:
        print(f"File '{file_name}' not found in any of the directories.")

# Example run
check_for_duplicates("namma_kalvi_12th_chemistry_model_question_papers_tm_2020_217204.pdf")
