import os
import hashlib
import time
import re
import threading
import tkinter as tk
from tkinter import messagebox
import sys
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import webbrowser
from pathlib import Path
import urllib.parse
import subprocess
import sqlite3
from typing import Dict, List, Tuple, Optional
import base64
import io

# Advanced libraries for duplicate detection
try:
    from PIL import Image  # Remove ImageHash from this line
    import imagehash
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️  PIL/Pillow not available. Image similarity detection disabled.")
    print("   Install with: pip install Pillow imagehash")

try:
    import librosa
    import numpy as np
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    print("⚠️  librosa not available. Audio fingerprinting disabled.")
    print("   Install with: pip install librosa")

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("⚠️  OpenCV not available. Video thumbnail comparison disabled.")
    print("   Install with: pip install opencv-python")

try:
    import ssdeep
    SSDEEP_AVAILABLE = True
except ImportError:
    SSDEEP_AVAILABLE = False
    print("⚠️  ssdeep not available. Fuzzy hash matching disabled.")
    print("   Install with: pip install ssdeep-windows (Windows) or ssdeep (Linux/Mac)")

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("⚠️  PyMuPDF not available. PDF content analysis disabled.")
    print("   Install with: pip install PyMuPDF")

try:
    from difflib import SequenceMatcher
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    print("⚠️  python-docx not available. Word document analysis disabled.")
    print("   Install with: pip install python-docx")

# Configuration
DOWNLOAD_DIR = r"C:\Users\Manoj\Downloads"
HASH_STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "file_hashes.txt")
MODIFICATION_DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "file_modifications.txt")
ADVANCED_DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "advanced_duplicates.db")
WEB_SERVER_PORT = 8080

# Advanced detection configuration
SIMILARITY_THRESHOLDS = {
    'image_hash': 10,      # Lower = more similar (0-64)
    'audio_similarity': 0.85,  # Higher = more similar (0-1)
    'text_similarity': 0.85,   # Higher = more similar (0-1)
    'video_similarity': 0.8,   # Higher = more similar (0-1)
    'fuzzy_similarity': 80     # Higher = more similar (0-100)
}

# File type categories
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.ico', '.svg'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma'}
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm', '.m4v'}
DOCUMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt'}

SUPPORTED_FILE_TYPES = IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | VIDEO_EXTENSIONS | DOCUMENT_EXTENSIONS | {
    '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar', '.7z', '.tar', '.gz'
}

# File size filtering (in bytes)
MIN_FILE_SIZE = 1024  # 1KB
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

# Ignored file patterns
IGNORED_EXTENSIONS = {'.tmp', '.temp', '.crdownload', '.part', '.download', '.partial'}
IGNORED_NAME_PATTERNS = [r'^~\$', r'^\.', r'Thumbs\.db$']
EXCLUDED_PATTERNS = [r'^desktop\.ini$', r'^folder\.jpg$', r'^thumbs\.db$']

# Global variables
file_type_stats = {}
web_server = None
web_server_thread = None

class AdvancedDuplicateDetector:
    """Advanced duplicate detection using various techniques"""
    
    def __init__(self):
        self.init_database()
        
    def init_database(self):
        """Initialize SQLite database for advanced duplicate detection"""
        try:
            self.conn = sqlite3.connect(ADVANCED_DB_FILE)
            self.cursor = self.conn.cursor()
            
            # Create tables for different types of fingerprints
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS image_hashes (
                    file_path TEXT PRIMARY KEY,
                    perceptual_hash TEXT,
                    average_hash TEXT,
                    difference_hash TEXT,
                    wavelet_hash TEXT,
                    file_size INTEGER,
                    modification_time REAL
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS audio_fingerprints (
                    file_path TEXT PRIMARY KEY,
                    spectral_centroid BLOB,
                    mfcc_features BLOB,
                    tempo REAL,
                    duration REAL,
                    file_size INTEGER,
                    modification_time REAL
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS document_content (
                    file_path TEXT PRIMARY KEY,
                    content_hash TEXT,
                    text_content TEXT,
                    word_count INTEGER,
                    file_size INTEGER,
                    modification_time REAL
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS video_thumbnails (
                    file_path TEXT PRIMARY KEY,
                    thumbnail_hash TEXT,
                    duration REAL,
                    resolution TEXT,
                    file_size INTEGER,
                    modification_time REAL
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS fuzzy_hashes (
                    file_path TEXT PRIMARY KEY,
                    fuzzy_hash TEXT,
                    file_size INTEGER,
                    modification_time REAL
                )
            ''')
            
            self.conn.commit()
            print("✅ Advanced duplicate detection database initialized")
            
        except Exception as e:
            print(f"❌ Error initializing advanced database: {e}")
            self.conn = None
            self.cursor = None
    
    def close_database(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
    
    def calculate_image_hashes(self, file_path: str) -> Optional[Dict]:
        """Calculate multiple image hashes for similarity detection"""
        if not PIL_AVAILABLE:
            return None
            
        try:
            with Image.open(file_path) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Calculate different types of hashes
                perceptual = str(imagehash.phash(img))
                average = str(imagehash.average_hash(img))
                difference = str(imagehash.dhash(img))
                wavelet = str(imagehash.whash(img))
                
                return {
                    'perceptual_hash': perceptual,
                    'average_hash': average,
                    'difference_hash': difference,
                    'wavelet_hash': wavelet
                }
                
        except Exception as e:
            print(f"Error calculating image hashes for {file_path}: {e}")
            return None
    
    def calculate_audio_fingerprint(self, file_path: str) -> Optional[Dict]:
        """Calculate audio fingerprint for music similarity detection"""
        if not LIBROSA_AVAILABLE:
            return None
            
        try:
            # Load audio file
            y, sr = librosa.load(file_path, duration=30)  # Load first 30 seconds
            
            # Extract features
            spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
            mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            duration = librosa.get_duration(y=y, sr=sr)
            
            return {
                'spectral_centroid': spectral_centroid.tobytes(),
                'mfcc_features': mfcc.tobytes(),
                'tempo': float(tempo),
                'duration': float(duration)
            }
            
        except Exception as e:
            print(f"Error calculating audio fingerprint for {file_path}: {e}")
            return None
    
    def extract_document_content(self, file_path: str) -> Optional[str]:
        """Extract text content from documents"""
        file_ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if file_ext == '.pdf' and PYMUPDF_AVAILABLE:
                doc = fitz.open(file_path)
                text = ""
                for page in doc:
                    text += page.get_text()
                doc.close()
                return text.strip()
                
            elif file_ext == '.docx' and DOCX_AVAILABLE:
                import docx
                doc = docx.Document(file_path)
                text = ""
                for paragraph in doc.paragraphs:
                    text += paragraph.text + "\n"
                return text.strip()
                
            elif file_ext == '.txt':
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read().strip()
                    
        except Exception as e:
            print(f"Error extracting content from {file_path}: {e}")
            
        return None
    
    def calculate_video_thumbnail_hash(self, file_path: str) -> Optional[str]:
        """Extract video thumbnail and calculate its hash"""
        if not CV2_AVAILABLE:
            return None
            
        try:
            cap = cv2.VideoCapture(file_path)
            ret, frame = cap.read()
            
            if ret:
                # Convert frame to PIL Image
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                
                # Calculate hash
                thumbnail_hash = str(imagehash.phash(img))
                
                # Get video info
                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                duration = frame_count / fps if fps > 0 else 0
                
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                
                cap.release()
                
                return {
                    'thumbnail_hash': thumbnail_hash,
                    'duration': duration,
                    'resolution': f"{width}x{height}"
                }
            
            cap.release()
            
        except Exception as e:
            print(f"Error extracting video thumbnail from {file_path}: {e}")
            
        return None
    
    def calculate_fuzzy_hash(self, file_path: str) -> Optional[str]:
        """Calculate fuzzy hash (ssdeep) for similarity detection"""
        if not SSDEEP_AVAILABLE:
            return None
            
        try:
            return ssdeep.hash_from_file(file_path)
        except Exception as e:
            print(f"Error calculating fuzzy hash for {file_path}: {e}")
            return None
    
    def store_fingerprints(self, file_path: str):
        """Store all applicable fingerprints for a file"""
        if not self.cursor:
            return
            
        file_ext = os.path.splitext(file_path)[1].lower()
        file_size = os.path.getsize(file_path)
        mod_time = os.path.getmtime(file_path)
        
        try:
            # Image fingerprints
            if file_ext in IMAGE_EXTENSIONS:
                hashes = self.calculate_image_hashes(file_path)
                if hashes:
                    self.cursor.execute('''
                        INSERT OR REPLACE INTO image_hashes 
                        (file_path, perceptual_hash, average_hash, difference_hash, wavelet_hash, file_size, modification_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (file_path, hashes['perceptual_hash'], hashes['average_hash'], 
                          hashes['difference_hash'], hashes['wavelet_hash'], file_size, mod_time))
            
            # Audio fingerprints
            elif file_ext in AUDIO_EXTENSIONS:
                fingerprint = self.calculate_audio_fingerprint(file_path)
                if fingerprint:
                    self.cursor.execute('''
                        INSERT OR REPLACE INTO audio_fingerprints 
                        (file_path, spectral_centroid, mfcc_features, tempo, duration, file_size, modification_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (file_path, fingerprint['spectral_centroid'], fingerprint['mfcc_features'],
                          fingerprint['tempo'], fingerprint['duration'], file_size, mod_time))
            
            # Document content
            elif file_ext in DOCUMENT_EXTENSIONS:
                content = self.extract_document_content(file_path)
                if content:
                    content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
                    word_count = len(content.split())
                    self.cursor.execute('''
                        INSERT OR REPLACE INTO document_content 
                        (file_path, content_hash, text_content, word_count, file_size, modification_time)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (file_path, content_hash, content, word_count, file_size, mod_time))
            
            # Video thumbnails
            elif file_ext in VIDEO_EXTENSIONS:
                video_data = self.calculate_video_thumbnail_hash(file_path)
                if video_data:
                    self.cursor.execute('''
                        INSERT OR REPLACE INTO video_thumbnails 
                        (file_path, thumbnail_hash, duration, resolution, file_size, modification_time)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (file_path, video_data['thumbnail_hash'], video_data['duration'],
                          video_data['resolution'], file_size, mod_time))
            
            # Fuzzy hash for all supported files
            if file_ext in SUPPORTED_FILE_TYPES:
                fuzzy_hash = self.calculate_fuzzy_hash(file_path)
                if fuzzy_hash:
                    self.cursor.execute('''
                        INSERT OR REPLACE INTO fuzzy_hashes 
                        (file_path, fuzzy_hash, file_size, modification_time)
                        VALUES (?, ?, ?, ?)
                    ''', (file_path, fuzzy_hash, file_size, mod_time))
            
            self.conn.commit()
            
        except Exception as e:
            print(f"Error storing fingerprints for {file_path}: {e}")
    
    def find_similar_images(self, file_path: str) -> List[Tuple[str, float]]:
        """Find similar images using perceptual hashing"""
        if not self.cursor or not PIL_AVAILABLE:
            return []
        
        similar_files = []
        hashes = self.calculate_image_hashes(file_path)
        
        if not hashes:
            return []
        
        try:
            self.cursor.execute('SELECT file_path, perceptual_hash FROM image_hashes WHERE file_path != ?', (file_path,))
            stored_hashes = self.cursor.fetchall()
            
            current_hash = imagehash.hex_to_hash(hashes['perceptual_hash'])
            
            for stored_path, stored_hash_str in stored_hashes:
                if os.path.exists(stored_path):
                    stored_hash = imagehash.hex_to_hash(stored_hash_str)
                    difference = current_hash - stored_hash
                    
                    if difference <= SIMILARITY_THRESHOLDS['image_hash']:
                        similarity = 1.0 - (difference / 64.0)  # Convert to 0-1 scale
                        similar_files.append((stored_path, similarity))
            
        except Exception as e:
            print(f"Error finding similar images for {file_path}: {e}")
        
        return sorted(similar_files, key=lambda x: x[1], reverse=True)
    
    def find_similar_audio(self, file_path: str) -> List[Tuple[str, float]]:
        """Find similar audio files using audio fingerprinting"""
        if not self.cursor or not LIBROSA_AVAILABLE:
            return []
        
        similar_files = []
        fingerprint = self.calculate_audio_fingerprint(file_path)
        
        if not fingerprint:
            return []
        
        try:
            self.cursor.execute('SELECT file_path, spectral_centroid, mfcc_features FROM audio_fingerprints WHERE file_path != ?', (file_path,))
            stored_fingerprints = self.cursor.fetchall()
            
            current_centroid = np.frombuffer(fingerprint['spectral_centroid'], dtype=np.float32)
            current_mfcc = np.frombuffer(fingerprint['mfcc_features'], dtype=np.float32)
            
            for stored_path, stored_centroid_bytes, stored_mfcc_bytes in stored_fingerprints:
                if os.path.exists(stored_path):
                    try:
                        stored_centroid = np.frombuffer(stored_centroid_bytes, dtype=np.float32)
                        stored_mfcc = np.frombuffer(stored_mfcc_bytes, dtype=np.float32)
                        
                        # Calculate similarity using cosine similarity
                        if len(current_centroid) == len(stored_centroid) and len(current_mfcc) == len(stored_mfcc):
                            centroid_sim = np.dot(current_centroid, stored_centroid) / (np.linalg.norm(current_centroid) * np.linalg.norm(stored_centroid))
                            mfcc_sim = np.dot(current_mfcc, stored_mfcc) / (np.linalg.norm(current_mfcc) * np.linalg.norm(stored_mfcc))
                            
                            # Average similarity
                            similarity = (centroid_sim + mfcc_sim) / 2
                            
                            if similarity >= SIMILARITY_THRESHOLDS['audio_similarity']:
                                similar_files.append((stored_path, float(similarity)))
                    except Exception as e:
                        print(f"Error comparing audio fingerprints: {e}")
                        continue
            
        except Exception as e:
            print(f"Error finding similar audio for {file_path}: {e}")
        
        return sorted(similar_files, key=lambda x: x[1], reverse=True)
    
    def find_similar_documents(self, file_path: str) -> List[Tuple[str, float]]:
        """Find similar documents using text content analysis"""
        if not self.cursor:
            return []
        
        similar_files = []
        content = self.extract_document_content(file_path)
        
        if not content or len(content.strip()) < 100:  # Skip very short documents
            return []
        
        try:
            self.cursor.execute('SELECT file_path, text_content FROM document_content WHERE file_path != ?', (file_path,))
            stored_contents = self.cursor.fetchall()
            
            for stored_path, stored_content in stored_contents:
                if os.path.exists(stored_path) and stored_content:
                    similarity = SequenceMatcher(None, content, stored_content).ratio()
                    
                    if similarity >= SIMILARITY_THRESHOLDS['text_similarity']:
                        similar_files.append((stored_path, similarity))
            
        except Exception as e:
            print(f"Error finding similar documents for {file_path}: {e}")
        
        return sorted(similar_files, key=lambda x: x[1], reverse=True)
    
    def find_similar_videos(self, file_path: str) -> List[Tuple[str, float]]:
        """Find similar videos using thumbnail comparison"""
        if not self.cursor or not CV2_AVAILABLE:
            return []
        
        similar_files = []
        video_data = self.calculate_video_thumbnail_hash(file_path)
        
        if not video_data:
            return []
        
        try:
            self.cursor.execute('SELECT file_path, thumbnail_hash FROM video_thumbnails WHERE file_path != ?', (file_path,))
            stored_thumbnails = self.cursor.fetchall()
            
            current_hash = imagehash.hex_to_hash(video_data['thumbnail_hash'])
            
            for stored_path, stored_hash_str in stored_thumbnails:
                if os.path.exists(stored_path):
                    stored_hash = imagehash.hex_to_hash(stored_hash_str)
                    difference = current_hash - stored_hash
                    
                    if difference <= SIMILARITY_THRESHOLDS['image_hash']:  # Same threshold as images
                        similarity = 1.0 - (difference / 64.0)
                        similar_files.append((stored_path, similarity))
            
        except Exception as e:
            print(f"Error finding similar videos for {file_path}: {e}")
        
        return sorted(similar_files, key=lambda x: x[1], reverse=True)
    
    def find_fuzzy_similar(self, file_path: str) -> List[Tuple[str, float]]:
        """Find similar files using fuzzy hashing (ssdeep)"""
        if not self.cursor or not SSDEEP_AVAILABLE:
            return []
        
        similar_files = []
        fuzzy_hash = self.calculate_fuzzy_hash(file_path)
        
        if not fuzzy_hash:
            return []
        
        try:
            self.cursor.execute('SELECT file_path, fuzzy_hash FROM fuzzy_hashes WHERE file_path != ?', (file_path,))
            stored_hashes = self.cursor.fetchall()
            
            for stored_path, stored_hash in stored_hashes:
                if os.path.exists(stored_path):
                    similarity = ssdeep.compare(fuzzy_hash, stored_hash)
                    
                    if similarity >= SIMILARITY_THRESHOLDS['fuzzy_similarity']:
                        similar_files.append((stored_path, similarity / 100.0))  # Convert to 0-1 scale
            
        except Exception as e:
            print(f"Error finding fuzzy similar files for {file_path}: {e}")
        
        return sorted(similar_files, key=lambda x: x[1], reverse=True)
    
    def find_all_similarities(self, file_path: str) -> Dict[str, List[Tuple[str, float]]]:
        """Find all types of similarities for a file"""
        results = {}
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # Store fingerprints first
        self.store_fingerprints(file_path)
        
        # Find similarities based on file type
        if file_ext in IMAGE_EXTENSIONS:
            results['image_similarity'] = self.find_similar_images(file_path)
        
        if file_ext in AUDIO_EXTENSIONS:
            results['audio_similarity'] = self.find_similar_audio(file_path)
        
        if file_ext in DOCUMENT_EXTENSIONS:
            results['document_similarity'] = self.find_similar_documents(file_path)
        
        if file_ext in VIDEO_EXTENSIONS:
            results['video_similarity'] = self.find_similar_videos(file_path)
        
        # Always check fuzzy similarity for supported files
        if file_ext in SUPPORTED_FILE_TYPES:
            results['fuzzy_similarity'] = self.find_fuzzy_similar(file_path)
        
        return results

# Initialize global detector
advanced_detector = AdvancedDuplicateDetector()

class EnhancedModalAlert:
    def __init__(self, duplicate_file, original_file, alert_type="Content duplicate", similarity_score=None, similarity_details=None):
        self.duplicate_file = duplicate_file
        self.original_file = original_file
        self.alert_type = alert_type
        self.similarity_score = similarity_score
        self.similarity_details = similarity_details or {}
        self.timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.response = None

        # Get file timestamps
        self.original_timestamp = self.get_file_timestamp(original_file)
        self.duplicate_timestamp = self.get_file_timestamp(duplicate_file)

    def get_file_timestamp(self, file_path):
        """Get formatted timestamp of a file"""
        try:
            if os.path.exists(file_path):
                mtime = os.path.getmtime(file_path)
                return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            return "Unknown"
        except Exception as e:
            print(f"Error getting timestamp for {file_path}: {e}")
            return "Error"

    def show(self):
        """Show enhanced modal alert with similarity information"""
        try:
            self.show_enhanced_modal()
        except Exception as e:
            print(f"Modal failed: {e}")
            self.show_console_alert()

    def show_enhanced_modal(self):
        """Show enhanced modal using tkinter messagebox"""
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        similarity_info = ""
        if self.similarity_score:
            similarity_info = f"Similarity: {self.similarity_score:.1%}\n"
        
        details_info = ""
        if self.similarity_details:
            for key, value in self.similarity_details.items():
                details_info += f"{key.replace('_', ' ').title()}: {value}\n"
        
        message = f"""ADVANCED DUPLICATE DETECTED!

Time: {self.timestamp}
Detection Type: {self.alert_type}
{similarity_info}
Duplicate: {os.path.basename(self.duplicate_file)}
Modified: {self.duplicate_timestamp}

Original: {os.path.basename(self.original_file)}
Modified: {self.original_timestamp}

{details_info}
Do you want to delete the duplicate file?"""
        
        response = messagebox.askyesno(
            "ADVANCED DUPLICATE ALERT",
            message
        )
        
        if response:
            try:
                os.remove(self.duplicate_file)
                print(f"Deleted duplicate file: {self.duplicate_file}")
                messagebox.showinfo("Success", f"Duplicate file has been deleted:\n{os.path.basename(self.duplicate_file)}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not delete file:\n{str(e)}")
        
        root.destroy()

    def show_console_alert(self):
        """Show enhanced alert in console as fallback"""
        print(f"\n{'='*80}")
        print("🚨 ADVANCED DUPLICATE DETECTED! 🚨")
        print(f"Time: {self.timestamp}")
        print(f"Detection Type: {self.alert_type}")
        if self.similarity_score:
            print(f"Similarity Score: {self.similarity_score:.1%}")
        print(f"Duplicate: {os.path.basename(self.duplicate_file)}")
        print(f"Modified: {self.duplicate_timestamp}")
        print(f"Original: {os.path.basename(self.original_file)}")
        print(f"Modified: {self.original_timestamp}")
        
        if self.similarity_details:
            print("\nSimilarity Details:")
            for key, value in self.similarity_details.items():
                print(f"  {key.replace('_', ' ').title()}: {value}")
        
        print(f"{'='*80}")

def show_enhanced_modal_alert(duplicate_file, original_file, alert_type="Content duplicate", similarity_score=None, similarity_details=None):
    """Show enhanced modal alert with similarity information"""
    alert = EnhancedModalAlert(duplicate_file, original_file, alert_type, similarity_score, similarity_details)
    alert.show()

def calculate_hash(file_path):
    """Calculate MD5 hash of a file"""
    hasher = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        print(f"Error calculating hash for {file_path}: {e}")
        return None

def load_existing_hashes():
    """Load existing file hashes from storage"""
    if not os.path.exists(HASH_STORE_FILE):
        return {}

    file_hashes = {}
    try:
        with open(HASH_STORE_FILE, "r", encoding='utf-8') as file:
            for line in file.readlines():
                if line.strip():
                    parts = line.strip().split(",", 1)
                    if len(parts) == 2:
                        file_hash, file_name = parts
                        file_hashes[file_hash] = file_name
    except Exception as e:
        print(f"Error loading hashes: {e}")
    return file_hashes

def save_hashes(hash_dict):
    """Save file hashes to storage"""
    try:
        with open(HASH_STORE_FILE, "w", encoding='utf-8') as file:
            for file_hash, file_name in hash_dict.items():
                file.write(f"{file_hash},{file_name}\n")
    except Exception as e:
        print(f"Error saving hashes: {e}")

def load_modification_db():
    """Load file modification tracking database"""
    if not os.path.exists(MODIFICATION_DB_FILE):
        return {}

    mod_db = {}
    try:
        with open(MODIFICATION_DB_FILE, "r", encoding='utf-8') as file:
            for line in file.readlines():
                if line.strip():
                    parts = line.strip().split(",", 2)
                    if len(parts) == 3:
                        file_name, file_hash, timestamp = parts
                        mod_db[file_name] = (file_hash, timestamp)
    except Exception as e:
        print(f"Error loading modification database: {e}")
    return mod_db

def save_modification_db(mod_db):
    """Save file modification tracking database"""
    try:
        with open(MODIFICATION_DB_FILE, "w", encoding='utf-8') as file:
            for file_name, (file_hash, timestamp) in mod_db.items():
                file.write(f"{file_name},{file_hash},{timestamp}\n")
    except Exception as e:
        print(f"Error saving modification database: {e}")

def is_similar_filename(file1, file2):
    """Check if two filenames are similar"""
    name1, ext1 = os.path.splitext(file1)
    name2, ext2 = os.path.splitext(file2)

    if ext1.lower() != ext2.lower():
        return False

    base1 = name1.lower().strip()
    base2 = name2.lower().strip()

    if base1 == base2:
        return True

    duplicate_patterns = [
    r'\s*\(\d+\)',      # Matches " (1)", " (2)", etc.
    r'\s*-\s*copy',     # Matches " - copy"
    r'\s*_copy',        # Matches "_copy"
    r'\s*-\s*v\d+\)',   # Matches " - v1)", " - v2)", etc.
    r'\s*_v\d+\)',      # Matches "_v1)", "_v2)", etc.
    r'\s*-\s*\d+',      # Matches " - 1", " - 2", etc.
    r'\s*_\d+',         # Matches "_1", "_2", etc.
    r'\s*-\s*duplicate', # Matches " - duplicate"
    r'\s*_duplicate',    # Matches "_duplicate"
    r'\s+copy',         # Matches " copy" (with spaces)
    ]

    clean1 = base1
    clean2 = base2

    for pattern in duplicate_patterns:
        clean1 = re.sub(pattern, '', clean1).strip()
        clean2 = re.sub(pattern, '', clean2).strip()

    if clean1 == clean2 and len(clean1) > 0:
        return True

    return False

def show_alert(message, is_error=False, is_modified=False):
    """Show alert in console output"""
    timestamp = time.strftime("%H:%M:%S")
    if is_modified:
        print(f"\n[{timestamp}] [FILE MODIFIED] {message}")
    elif is_error:
        print(f"\n[{timestamp}] [DUPLICATE DETECTED] {message}")
    else:
        print(f"\n[{timestamp}] [NEW FILE DETECTED] {message}")

def should_process_file(file_path):
    """
    Check if a file should be processed based on type, size, and name patterns
    Returns True if file should be processed, False otherwise
    """
    # Check if file exists
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return False
    
    filename = os.path.basename(file_path)
    
    # Check if file name matches excluded patterns
    for pattern in EXCLUDED_PATTERNS:
        if re.search(pattern, filename, re.IGNORECASE):
            print(f"Ignoring excluded file: {filename} (pattern: {pattern})")
            return False
    
    # Check file extension
    file_ext = os.path.splitext(file_path)[1].lower()
    
    # Ignore temporary/downloading files
    if file_ext in IGNORED_EXTENSIONS:
        print(f"Ignoring temporary file: {filename}")
        return False
    
    # Check if file name matches ignored patterns
    for pattern in IGNORED_NAME_PATTERNS:
        if re.search(pattern, filename):
            print(f"Ignoring system file: {filename} (pattern: {pattern})")
            return False
    
    # Check if file type is supported
    if file_ext not in SUPPORTED_FILE_TYPES:
        print(f"Ignoring unsupported file type: {filename} ({file_ext})")
        return False
    
    # Check file size
    try:
        file_size = os.path.getsize(file_path)
        if file_size < MIN_FILE_SIZE:
            print(f"Ignoring small file: {filename} ({file_size} bytes)")
            return False
        if file_size > MAX_FILE_SIZE:
            print(f"Ignoring large file: {filename} ({file_size/(1024*1024):.2f} MB)")
            return False
    except Exception as e:
        print(f"Error checking file size for {filename}: {e}")
        return False
    
    return True

def update_file_type_stats():
    """Update file type statistics for the download directory"""
    global file_type_stats
    file_type_stats = {}
    
    try:
        for filename in os.listdir(DOWNLOAD_DIR):
            file_path = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(file_path) and should_process_file(file_path):
                file_ext = os.path.splitext(filename)[1].lower()
                if file_ext in file_type_stats:
                    file_type_stats[file_ext] += 1
                else:
                    file_type_stats[file_ext] = 1
    except Exception as e:
        print(f"Error updating file type statistics: {e}")

def get_file_size_mb(file_path):
    """Get file size in MB"""
    try:
        size_bytes = os.path.getsize(file_path)
        return size_bytes / (1024 * 1024)
    except:
        return 0

def get_advanced_stats():
    """Get advanced duplicate detection statistics"""
    if not advanced_detector.cursor:
        return {}
    
    stats = {}
    try:
        # Count fingerprints by type
        tables = ['image_hashes', 'audio_fingerprints', 'document_content', 'video_thumbnails', 'fuzzy_hashes']
        for table in tables:
            advanced_detector.cursor.execute(f'SELECT COUNT(*) FROM {table}')
            count = advanced_detector.cursor.fetchone()[0]
            stats[table] = count
    except Exception as e:
        print(f"Error getting advanced stats: {e}")
    
    return stats

def generate_stats_html():
    """Generate enhanced HTML content for file statistics"""
    try:
        # Update stats first
        update_file_type_stats()
        advanced_stats = get_advanced_stats()
        
        html_content = """<!DOCTYPE html>
<html>
<head>
    <title>Enhanced Download Monitor - Advanced Duplicate Detection</title>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="30">
    <style>
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            margin: 0; 
            padding: 20px; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            overflow: hidden;
        }
        .header { 
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            color: white; 
            text-align: center; 
            padding: 30px;
            margin: 0;
        }
        .header h1 { margin: 0; font-size: 2.5em; font-weight: 300; }
        .header p { margin: 10px 0 0 0; opacity: 0.9; }
        .content { padding: 30px; }
        
        .feature-status {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .feature-card {
            background: linear-gradient(135deg, #ff6b6b, #feca57);
            color: white;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }
        .feature-card.enabled {
            background: linear-gradient(135deg, #4CAF50, #45a049);
        }
        .feature-card.disabled {
            background: linear-gradient(135deg, #ff6b6b, #ee5a52);
        }
        
        .stats-section { margin-bottom: 40px; }
        .stats-section h2 { 
            color: #333; 
            border-bottom: 3px solid #4facfe; 
            padding-bottom: 10px; 
            margin-bottom: 20px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .stat-card h3 { margin: 0 0 10px 0; font-size: 1.2em; }
        .stat-card .number { font-size: 2.5em; font-weight: bold; margin: 10px 0; }
        
        .advanced-stats {
            background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 50%, #fecfef 100%);
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
        }
        .advanced-stats h3 { margin: 0 0 15px 0; color: #333; }
        .advanced-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
        }
        .advanced-item {
            background: rgba(255,255,255,0.9);
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        
        .files-table { 
            width: 100%; 
            border-collapse: collapse; 
            margin: 20px 0; 
            background: white; 
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .files-table th { 
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            color: white; 
            padding: 15px; 
            text-align: left; 
            font-weight: 600;
        }
        .files-table td { 
            padding: 12px 15px; 
            border-bottom: 1px solid #eee; 
        }
        .files-table tr:hover { 
            background-color: #f8f9ff; 
        }
        .files-table tr:last-child td { 
            border-bottom: none; 
        }
        .file-type { 
            background: #667eea; 
            color: white; 
            padding: 4px 8px; 
            border-radius: 15px; 
            font-size: 0.8em; 
            font-weight: bold;
        }
        .file-type.image { background: #4CAF50; }
        .file-type.audio { background: #FF9800; }
        .file-type.video { background: #E91E63; }
        .file-type.document { background: #2196F3; }
        
        .file-size { 
            color: #666; 
            font-size: 0.9em; 
        }
        .open-btn { 
            background: linear-gradient(135deg, #4CAF50, #45a049); 
            color: white; 
            border: none; 
            padding: 8px 16px; 
            border-radius: 20px; 
            cursor: pointer; 
            font-size: 12px; 
            transition: all 0.3s ease;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        }
        .open-btn:hover { 
            transform: translateY(-2px); 
            box-shadow: 0 5px 15px rgba(0,0,0,0.3);
        }
        .refresh-info {
            text-align: center;
            color: #666;
            font-style: italic;
            margin-top: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
        }
        .no-files {
            text-align: center;
            color: #666;
            padding: 40px;
            font-style: italic;
        }
        .total-files { font-size: 1.1em; color: #4facfe; font-weight: bold; }
        .similarity-badge {
            background: #ff6b6b;
            color: white;
            padding: 2px 6px;
            border-radius: 10px;
            font-size: 0.7em;
            margin-left: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 Enhanced Download Monitor</h1>
            <p>Advanced Duplicate Detection with AI-Powered Similarity Analysis</p>
        </div>
        <div class="content">"""

        # Feature status section
        html_content += f"""
            <div class="stats-section">
                <h2>🚀 Advanced Detection Features</h2>
                <div class="feature-status">
                    <div class="feature-card {'enabled' if PIL_AVAILABLE else 'disabled'}">
                        <h4>📸 Image Similarity</h4>
                        <p>{'✅ Active' if PIL_AVAILABLE else '❌ Disabled'}</p>
                        <small>Perceptual hashing for similar images</small>
                    </div>
                    <div class="feature-card {'enabled' if LIBROSA_AVAILABLE else 'disabled'}">
                        <h4>🎵 Audio Fingerprinting</h4>
                        <p>{'✅ Active' if LIBROSA_AVAILABLE else '❌ Disabled'}</p>
                        <small>Music similarity detection</small>
                    </div>
                    <div class="feature-card {'enabled' if PYMUPDF_AVAILABLE else 'disabled'}">
                        <h4>📄 Document Analysis</h4>
                        <p>{'✅ Active' if PYMUPDF_AVAILABLE else '❌ Disabled'}</p>
                        <small>OCR and content comparison</small>
                    </div>
                    <div class="feature-card {'enabled' if CV2_AVAILABLE else 'disabled'}">
                        <h4>🎬 Video Thumbnails</h4>
                        <p>{'✅ Active' if CV2_AVAILABLE else '❌ Disabled'}</p>
                        <small>Video similarity detection</small>
                    </div>
                    <div class="feature-card {'enabled' if SSDEEP_AVAILABLE else 'disabled'}">
                        <h4>🧬 Fuzzy Hashing</h4>
                        <p>{'✅ Active' if SSDEEP_AVAILABLE else '❌ Disabled'}</p>
                        <small>Similar file detection</small>
                    </div>
                </div>
            </div>
        """

        # Statistics overview
        total_files = sum(file_type_stats.values())
        total_types = len(file_type_stats)
        
        html_content += f"""
            <div class="stats-section">
                <h2>📊 Overview</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <h3>Total Files</h3>
                        <div class="number">{total_files}</div>
                    </div>
                    <div class="stat-card">
                        <h3>File Types</h3>
                        <div class="number">{total_types}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Images</h3>
                        <div class="number">{sum(file_type_stats.get(ext, 0) for ext in IMAGE_EXTENSIONS)}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Audio Files</h3>
                        <div class="number">{sum(file_type_stats.get(ext, 0) for ext in AUDIO_EXTENSIONS)}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Videos</h3>
                        <div class="number">{sum(file_type_stats.get(ext, 0) for ext in VIDEO_EXTENSIONS)}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Documents</h3>
                        <div class="number">{sum(file_type_stats.get(ext, 0) for ext in DOCUMENT_EXTENSIONS)}</div>
                    </div>
                </div>
            </div>
        """

        # Advanced detection statistics
        if advanced_stats:
            html_content += f"""
            <div class="advanced-stats">
                <h3>🔬 Advanced Detection Database</h3>
                <div class="advanced-grid">
                    <div class="advanced-item">
                        <strong>Image Hashes</strong><br>
                        <span style="font-size: 1.5em;">{advanced_stats.get('image_hashes', 0)}</span>
                    </div>
                    <div class="advanced-item">
                        <strong>Audio Prints</strong><br>
                        <span style="font-size: 1.5em;">{advanced_stats.get('audio_fingerprints', 0)}</span>
                    </div>
                    <div class="advanced-item">
                        <strong>Text Content</strong><br>
                        <span style="font-size: 1.5em;">{advanced_stats.get('document_content', 0)}</span>
                    </div>
                    <div class="advanced-item">
                        <strong>Video Thumbs</strong><br>
                        <span style="font-size: 1.5em;">{advanced_stats.get('video_thumbnails', 0)}</span>
                    </div>
                    <div class="advanced-item">
                        <strong>Fuzzy Hashes</strong><br>
                        <span style="font-size: 1.5em;">{advanced_stats.get('fuzzy_hashes', 0)}</span>
                    </div>
                </div>
            </div>
            """

        if total_files > 0:
            # File type statistics
            html_content += """
            <div class="stats-section">
                <h2>📈 File Types</h2>
                <table class="files-table">
                    <tr>
                        <th>File Type</th>
                        <th>Count</th>
                        <th>Percentage</th>
                        <th>Detection Method</th>
                    </tr>
            """
            
            for file_type, count in sorted(file_type_stats.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / total_files) * 100
                
                # Determine detection method
                detection_method = "MD5 Hash"
                if file_type in IMAGE_EXTENSIONS:
                    detection_method = "Perceptual Hash" if PIL_AVAILABLE else "MD5 Hash"
                elif file_type in AUDIO_EXTENSIONS:
                    detection_method = "Audio Fingerprint" if LIBROSA_AVAILABLE else "MD5 Hash"
                elif file_type in VIDEO_EXTENSIONS:
                    detection_method = "Thumbnail Hash" if CV2_AVAILABLE else "MD5 Hash"
                elif file_type in DOCUMENT_EXTENSIONS:
                    detection_method = "Content Analysis" if PYMUPDF_AVAILABLE else "MD5 Hash"
                
                html_content += f"""
                    <tr>
                        <td><span class="file-type">{file_type.upper()}</span></td>
                        <td>{count}</td>
                        <td>{percentage:.1f}%</td>
                        <td><small>{detection_method}</small></td>
                    </tr>
                """
            
            html_content += """
                </table>
            </div>
            """

            # File listing with enhanced information
            html_content += """
            <div class="stats-section">
                <h2>📄 File Analysis</h2>
                <table class="files-table">
                    <tr>
                        <th>File Name</th>
                        <th>Type</th>
                        <th>Size</th>
                        <th>Modified</th>
                        <th>Detection</th>
                        <th>Action</th>
                    </tr>
            """
            
            # Get all files and sort by modification time (newest first)
            all_files = []
            try:
                for filename in os.listdir(DOWNLOAD_DIR):
                    file_path = os.path.join(DOWNLOAD_DIR, filename)
                    if os.path.isfile(file_path) and should_process_file(file_path):
                        mtime = os.path.getmtime(file_path)
                        all_files.append((filename, file_path, mtime))
                
                all_files.sort(key=lambda x: x[2], reverse=True)  # Sort by modification time
                
                for filename, file_path, mtime in all_files:
                    file_ext = os.path.splitext(filename)[1].lower()
                    file_size = get_file_size_mb(file_path)
                    mod_time = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
                    
                    # Format file size
                    if file_size < 1:
                        size_str = f"{file_size*1024:.0f} KB"
                    else:
                        size_str = f"{file_size:.1f} MB"
                    
                    # Determine file type class for styling
                    type_class = "other"
                    if file_ext in IMAGE_EXTENSIONS:
                        type_class = "image"
                    elif file_ext in AUDIO_EXTENSIONS:
                        type_class = "audio"
                    elif file_ext in VIDEO_EXTENSIONS:
                        type_class = "video"
                    elif file_ext in DOCUMENT_EXTENSIONS:
                        type_class = "document"
                    
                    # Detection methods
                    detection_methods = ["MD5"]
                    if file_ext in IMAGE_EXTENSIONS and PIL_AVAILABLE:
                        detection_methods.append("pHash")
                    if file_ext in AUDIO_EXTENSIONS and LIBROSA_AVAILABLE:
                        detection_methods.append("Audio")
                    if file_ext in VIDEO_EXTENSIONS and CV2_AVAILABLE:
                        detection_methods.append("Thumb")
                    if file_ext in DOCUMENT_EXTENSIONS and PYMUPDF_AVAILABLE:
                        detection_methods.append("Content")
                    if SSDEEP_AVAILABLE:
                        detection_methods.append("Fuzzy")
                    
                    detection_str = " + ".join(detection_methods)
                    
                    html_content += f"""
                    <tr>
                        <td title="{filename}">{filename[:40]}{'...' if len(filename) > 40 else ''}</td>
                        <td><span class="file-type {type_class}">{file_ext.upper()}</span></td>
                        <td><span class="file-size">{size_str}</span></td>
                        <td>{mod_time}</td>
                        <td><small>{detection_str}</small></td>
                        <td><button class="open-btn" onclick="openFile('{file_path.replace(chr(92), '/')}')">Open</button></td>
                    </tr>
                    """
                    
            except Exception as e:
                html_content += f"""
                <tr>
                    <td colspan="6" class="no-files">Error loading files: {str(e)}</td>
                </tr>
                """
            
            html_content += """
                </table>
            </div>
            """
        else:
            html_content += """
            <div class="no-files">
                <h3>No monitored files found</h3>
                <p>Files will appear here when they are detected in the download directory.</p>
            </div>
            """

        html_content += f"""
            <div class="refresh-info">
                🔬 Advanced Duplicate Detection Active | 📡 Auto-refresh: 30s | ⏰ Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                <br><br>
                <span class="total-files">Monitoring {total_files} files with multi-algorithm similarity detection</span>
                <br><br>
                <strong>Detection Capabilities:</strong>
                {'✅ Image Similarity' if PIL_AVAILABLE else '❌ Image Similarity'} | 
                {'✅ Audio Fingerprinting' if LIBROSA_AVAILABLE else '❌ Audio Fingerprinting'} | 
                {'✅ Document Analysis' if PYMUPDF_AVAILABLE else '❌ Document Analysis'} | 
                {'✅ Video Comparison' if CV2_AVAILABLE else '❌ Video Comparison'} | 
                {'✅ Fuzzy Matching' if SSDEEP_AVAILABLE else '❌ Fuzzy Matching'}
            </div>
        </div>
    </div>
    
    <script>
        function openFile(filePath) {{
            fetch('/open?path=' + encodeURIComponent(filePath))
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        console.log('File opened successfully: ' + data.path);
                        showMessage('File opened successfully!', 'success');
                    }} else {{
                        console.error('Error opening file: ' + data.message);
                        showMessage('Error opening file: ' + data.message, 'error');
                    }}
                }})
                .catch(error => {{
                    console.error('Error: ' + error);
                    showMessage('Network error: ' + error, 'error');
                }});
        }}
        
        function showMessage(message, type) {{
            const msgDiv = document.createElement('div');
            msgDiv.style.cssText = `
                position: fixed; top: 20px; right: 20px; z-index: 1000;
                padding: 15px 20px; border-radius: 10px; color: white; font-weight: bold;
                background: ${{type === 'success' ? 'linear-gradient(135deg, #4CAF50, #45a049)' : 'linear-gradient(135deg, #f44336, #d32f2f)'}};
                box-shadow: 0 5px 15px rgba(0,0,0,0.3); animation: slideIn 0.3s ease;
            `;
            msgDiv.textContent = message;
            
            const style = document.createElement('style');
            style.textContent = `
                @keyframes slideIn {{
                    from {{ transform: translateX(100%); opacity: 0; }}
                    to {{ transform: translateX(0); opacity: 1; }}
                }}
            `;
            document.head.appendChild(style);
            
            document.body.appendChild(msgDiv);
            setTimeout(() => {{
                msgDiv.remove();
                style.remove();
            }}, 3000);
        }}
        
        // Add loading animations
        window.addEventListener('load', function() {{
            const cards = document.querySelectorAll('.stat-card, .feature-card');
            cards.forEach((card, index) => {{
                setTimeout(() => {{
                    card.style.animation = 'fadeInUp 0.6s ease forwards';
                }}, index * 50);
            }});
        }});
        
        const fadeStyle = document.createElement('style');
        fadeStyle.textContent = `
            @keyframes fadeInUp {{
                from {{ transform: translateY(30px); opacity: 0; }}
                to {{ transform: translateY(0); opacity: 1; }}
            }}
        `;
        document.head.appendChild(fadeStyle);
    </script>
</body>
</html>"""
        
        return html_content
        
    except Exception as e:
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>Enhanced Download Monitor - Error</title>
    <meta charset="utf-8">
</head>
<body>
    <h1>Error generating enhanced statistics</h1>
    <p>Error: {str(e)}</p>
    <p><a href="javascript:location.reload()">Retry</a></p>
</body>
</html>"""

class FileRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler for file operations with improved error handling"""
    
    def log_message(self, format, *args):
        """Override to reduce console spam"""
        pass
    
    def do_GET(self):
        try:
            parsed_path = urllib.parse.urlparse(self.path)
            
            if parsed_path.path == '/stats' or parsed_path.path == '/':
                # Serve the enhanced statistics page
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                self.end_headers()
                
                html_content = generate_stats_html()
                self.wfile.write(html_content.encode('utf-8'))
                
            elif parsed_path.path == '/open':
                # Handle file open requests
                query_params = urllib.parse.parse_qs(parsed_path.query)
                file_path = query_params.get('path', [''])[0]
                
                response = {'success': False, 'message': '', 'path': file_path}
                
                try:
                    if file_path and os.path.exists(file_path):
                        if os.name == 'nt':  # Windows
                            os.startfile(file_path)
                        elif os.name == 'posix':  # macOS and Linux
                            subprocess.call(('open', file_path))
                        else:
                            subprocess.call(('xdg-open', file_path))
                            
                        response['success'] = True
                        response['message'] = 'File opened successfully'
                        print(f"Opened file: {os.path.basename(file_path)}")
                    else:
                        response['message'] = f'File not found: {file_path}'
                        print(f"File not found: {file_path}")
                        
                except Exception as e:
                    response['message'] = f'Error opening file: {str(e)}'
                    print(f"Error opening file {file_path}: {e}")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode('utf-8'))
                
            else:
                # Handle other requests with 404
                self.send_response(404)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<h1>404 - Page Not Found</h1><p><a href="/stats">Go to Statistics</a></p>')
                
        except Exception as e:
            print(f"Web server error: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            error_html = f'<h1>500 - Internal Server Error</h1><p>{str(e)}</p><p><a href="/stats">Go to Statistics</a></p>'
            self.wfile.write(error_html.encode('utf-8'))

def start_web_server():
    """Start the web server for file statistics and operations"""
    global web_server
    try:
        server_address = ('localhost', WEB_SERVER_PORT)
        web_server = HTTPServer(server_address, FileRequestHandler)
        print(f"🌐 Web server started on http://localhost:{WEB_SERVER_PORT}")
        print(f"📊 View enhanced statistics at: http://localhost:{WEB_SERVER_PORT}/stats")
        web_server.serve_forever()
    except Exception as e:
        print(f"❌ Web server error: {e}")

def populate_initial_hashes():
    """Populate hash store with existing files and generate advanced fingerprints"""
    if not os.path.exists(DOWNLOAD_DIR):
        print(f"Download directory {DOWNLOAD_DIR} does not exist!")
        return {}, {}

    file_hashes = {}
    mod_db = {}
    print("🔍 Scanning existing files and generating advanced fingerprints...")
    processed_count = 0
    skipped_count = 0
    advanced_count = 0

    try:
        for filename in os.listdir(DOWNLOAD_DIR):
            file_path = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(file_path):
                if should_process_file(file_path):
                    # Generate basic MD5 hash
                    file_hash = calculate_hash(file_path)
                    if file_hash:
                        file_hashes[file_hash] = filename
                        mod_db[filename] = (file_hash, str(os.path.getmtime(file_path)))
                        print(f"📄 Added to database: {filename}")
                        processed_count += 1
                        
                        # Generate advanced fingerprints
                        try:
                            advanced_detector.store_fingerprints(file_path)
                            advanced_count += 1
                            print(f"🔬 Generated advanced fingerprints for: {filename}")
                        except Exception as e:
                            print(f"⚠️  Could not generate advanced fingerprints for {filename}: {e}")
                else:
                    skipped_count += 1
    except Exception as e:
        print(f"Error scanning directory: {e}")

    save_hashes(file_hashes)
    save_modification_db(mod_db)
    print(f"\n✅ Initial scan complete:")
    print(f"   📁 Processed {processed_count} files")
    print(f"   ⏭️  Skipped {skipped_count} files") 
    print(f"   🔬 Advanced fingerprints: {advanced_count} files")
    
    # Update file type statistics
    update_file_type_stats()
    
    return file_hashes, mod_db

class EnhancedDownloadHandler(FileSystemEventHandler):
    def __init__(self):
        self.file_hashes = load_existing_hashes()
        self.mod_db = load_modification_db()
        if not self.file_hashes or not self.mod_db:
            self.file_hashes, self.mod_db = populate_initial_hashes()

        self.processing_files = set()
        self.file_modification_times = {}
        super().__init__()

    def on_created(self, event):
        if not event.is_directory:
            time.sleep(1)
            self.handle_file_event(event.src_path, is_new_file=True)

    def on_moved(self, event):
        if not event.is_directory:
            time.sleep(1)
            self.handle_file_event(event.dest_path, is_new_file=True)

    def on_modified(self, event):
        if not event.is_directory:
            time.sleep(1)
            self.handle_file_event(event.src_path, is_new_file=False)

    def handle_file_event(self, file_path, is_new_file):
        file_name = os.path.basename(file_path)

        if not should_process_file(file_path):
            return

        if file_path in self.processing_files:
            return

        current_time = time.time()
        if not is_new_file and file_path in self.file_modification_times:
            if current_time - self.file_modification_times[file_path] < 2:
                return

        self.processing_files.add(file_path)
        self.file_modification_times[file_path] = current_time

        # Process the file with enhanced detection
        self.monitor_and_process_file(file_path, is_new_file)

    def monitor_and_process_file(self, file_path, is_new_file):
        file_name = os.path.basename(file_path)

        try:
            if not self.wait_for_stable_file(file_path):
                return

            # Calculate basic hash
            file_hash = calculate_hash(file_path)
            if file_hash is None:
                return

            if is_new_file:
                self.check_for_advanced_duplicates(file_path, file_name, file_hash)
            else:
                self.check_for_modifications(file_path, file_name, file_hash)

            # Update file type statistics after processing
            update_file_type_stats()

        except Exception as e:
            print(f"Error processing {file_name}: {e}")
        finally:
            self.processing_files.discard(file_path)

    def wait_for_stable_file(self, file_path, max_wait=30):
        """Wait for file to be stable (not changing size)"""
        stable_count = 0
        wait_count = 0
        last_size = -1

        while stable_count < 3 and wait_count < max_wait:
            try:
                if not os.path.exists(file_path):
                    return False

                current_size = os.path.getsize(file_path)
                
                if current_size == last_size and current_size > 0:
                    stable_count += 1
                else:
                    stable_count = 0
                    last_size = current_size

                time.sleep(0.5)
                wait_count += 1

            except Exception as e:
                print(f"Error waiting for stable file: {e}")
                time.sleep(0.5)
                wait_count += 1

        return stable_count >= 3

    def check_for_advanced_duplicates(self, file_path, file_name, file_hash):
        """Enhanced duplicate checking with multiple detection methods"""
        duplicates_found = False
        
        # First, check basic hash duplicates
        if file_hash in self.file_hashes:
            original_name = self.file_hashes[file_hash]
            if original_name != file_name:
                original_path = os.path.join(DOWNLOAD_DIR, original_name)
                show_alert(f"Exact duplicate: '{file_name}' matches '{original_name}'", is_error=True)
                show_enhanced_modal_alert(file_path, original_path, "Exact Content Match", 1.0)
                duplicates_found = True

        # Check filename similarity (existing functionality)
        if not duplicates_found:
            for existing_hash, existing_name in self.file_hashes.items():
                if existing_name != file_name and is_similar_filename(file_name, existing_name):
                    existing_path = os.path.join(DOWNLOAD_DIR, existing_name)
                    show_alert(f"Similar filename: '{file_name}' resembles '{existing_name}'", is_error=True)
                    show_enhanced_modal_alert(file_path, existing_path, "Similar Filename", 0.8)
                    duplicates_found = True
                    break

        # Advanced similarity detection
        if not duplicates_found:
            print(f"🔬 Running advanced similarity analysis for: {file_name}")
            similarities = advanced_detector.find_all_similarities(file_path)
            
            for similarity_type, similar_files in similarities.items():
                if similar_files:  # If any similar files found
                    for similar_path, similarity_score in similar_files[:3]:  # Show top 3 matches
                        if os.path.exists(similar_path) and similarity_score > 0.7:  # High similarity threshold
                            similar_name = os.path.basename(similar_path)
                            
                            # Create detailed similarity information
                            similarity_details = {
                                'detection_method': similarity_type.replace('_', ' ').title(),
                                'confidence': f"{similarity_score:.1%}",
                                'algorithm': self.get_algorithm_name(similarity_type)
                            }
                            
                            alert_type = f"{similarity_type.replace('_', ' ').title()} Similarity"
                            show_alert(f"{alert_type}: '{file_name}' similar to '{similar_name}' ({similarity_score:.1%})", is_error=True)
                            show_enhanced_modal_alert(file_path, similar_path, alert_type, similarity_score, similarity_details)
                            duplicates_found = True
                            break  # Only show the first high-confidence match per type
                
                if duplicates_found:
                    break  # Don't check other similarity types if we found a match

        # If no duplicates found, it's a new unique file
        if not duplicates_found:
            show_alert(f"New unique file: {file_name}")
            # Add to hash database
            self.file_hashes[file_hash] = file_name
            self.mod_db[file_name] = (file_hash, str(os.path.getmtime(file_path)))
            save_hashes(self.file_hashes)
            save_modification_db(self.mod_db)
            
            # Store advanced fingerprints for future comparisons
            try:
                advanced_detector.store_fingerprints(file_path)
                print(f"🔬 Generated fingerprints for: {file_name}")
            except Exception as e:
                print(f"⚠️  Could not generate fingerprints for {file_name}: {e}")

    def get_algorithm_name(self, similarity_type):
        """Get human-readable algorithm name"""
        algorithm_names = {
            'image_similarity': 'Perceptual Hashing (pHash)',
            'audio_similarity': 'Audio Fingerprinting (MFCC + Spectral)',
            'document_similarity': 'Text Content Analysis',
            'video_similarity': 'Video Thumbnail Comparison',
            'fuzzy_similarity': 'Fuzzy Hashing (ssdeep)'
        }
        return algorithm_names.get(similarity_type, 'Unknown Algorithm')

    def check_for_modifications(self, file_path, file_name, current_hash):
        """Check if an existing file has been modified with advanced detection"""
        if file_name not in self.mod_db:
            # File wasn't in our database, treat as new file
            self.check_for_advanced_duplicates(file_path, file_name, current_hash)
            return

        old_hash, old_timestamp = self.mod_db[file_name]

        if old_hash != current_hash:
            # File content has changed
            show_alert(f"File modified: {file_name}", is_modified=True)

            # Check if the new content matches any existing files using advanced detection
            print(f"🔄 Analyzing modified file: {file_name}")
            similarities = advanced_detector.find_all_similarities(file_path)
            
            match_found = False
            for similarity_type, similar_files in similarities.items():
                if similar_files:
                    for similar_path, similarity_score in similar_files[:1]:  # Check top match
                        if os.path.exists(similar_path) and similarity_score > 0.85:  # Very high threshold for modifications
                            similar_name = os.path.basename(similar_path)
                            if similar_name != file_name:  # Don't match with itself
                                similarity_details = {
                                    'detection_method': similarity_type.replace('_', ' ').title(),
                                    'confidence': f"{similarity_score:.1%}",
                                    'modification_type': 'Content Change Detection'
                                }
                                
                                alert_type = f"Modified File Now Matches ({similarity_type.replace('_', ' ').title()})"
                                show_alert(f"Modified file now similar to: '{file_name}' matches '{similar_name}' ({similarity_score:.1%})", is_error=True)
                                show_enhanced_modal_alert(file_path, similar_path, alert_type, similarity_score, similarity_details)
                                match_found = True
                                break
                if match_found:
                    break

            # Update the modification database
            self.mod_db[file_name] = (current_hash, str(os.path.getmtime(file_path)))
            save_modification_db(self.mod_db)

            # Update the hash database
            for h, name in list(self.file_hashes.items()):
                if name == file_name and h != current_hash:
                    del self.file_hashes[h]
            self.file_hashes[current_hash] = file_name
            save_hashes(self.file_hashes)
            
            # Update advanced fingerprints
            try:
                advanced_detector.store_fingerprints(file_path)
                print(f"🔄 Updated fingerprints for modified file: {file_name}")
            except Exception as e:
                print(f"⚠️  Could not update fingerprints for {file_name}: {e}")

def start_monitoring():
    """Start enhanced monitoring with advanced duplicate detection"""
    print("=" * 90)
    print("🚨 ENHANCED DOWNLOAD MONITOR WITH ADVANCED AI DUPLICATE DETECTION 🚨")
    print("=" * 90)
    print(f"📂 Monitoring directory: {DOWNLOAD_DIR}")
    print(f"💾 Hash database: {HASH_STORE_FILE}")
    print(f"🔄 Modification tracking: {MODIFICATION_DB_FILE}")
    print(f"🧠 Advanced database: {ADVANCED_DB_FILE}")
    print(f"🌐 Web server port: {WEB_SERVER_PORT}")
    print()
    print("🔍 ADVANCED DETECTION FEATURES:")
    print(f"   {'✅' if PIL_AVAILABLE else '❌'} Image similarity detection (Perceptual hashing)")
    print(f"   {'✅' if LIBROSA_AVAILABLE else '❌'} Audio fingerprinting (MFCC + spectral analysis)")  
    print(f"   {'✅' if PYMUPDF_AVAILABLE else '❌'} Document content analysis (OCR + text comparison)")
    print(f"   {'✅' if CV2_AVAILABLE else '❌'} Video thumbnail comparison")
    print(f"   {'✅' if SSDEEP_AVAILABLE else '❌'} Fuzzy hash matching (ssdeep)")
    print()
    print("🔧 TRADITIONAL FEATURES:")
    print("   ✅ MD5 content duplicate detection")
    print("   ✅ Similar filename detection")
    print("   ✅ File modification tracking")
    print("   ✅ Enhanced modal alerts with similarity scores")
    print("   ✅ File type filtering & size limits")
    print("   ✅ Web-based analytics dashboard")
    print("=" * 90)
    print(f"📄 Supported file types: {len(SUPPORTED_FILE_TYPES)} types")
    print(f"📏 File size limits: {MIN_FILE_SIZE/1024}KB to {MAX_FILE_SIZE/(1024*1024)}MB")
    print("=" * 90)

    if not os.path.exists(DOWNLOAD_DIR):
        print(f"❌ Error: Download directory {DOWNLOAD_DIR} does not exist!")
        return

    # Start web server in a separate thread
    global web_server_thread
    web_server_thread = threading.Thread(target=start_web_server, daemon=True)
    web_server_thread.start()
    
    # Give the web server a moment to start
    time.sleep(1)

    # Create enhanced event handler and observer
    event_handler = EnhancedDownloadHandler()
    observer = Observer()
    observer.schedule(event_handler, DOWNLOAD_DIR, recursive=False)

    try:
        # Start monitoring
        observer.start()
        print("✅ Enhanced monitor started successfully!")
        print("🔄 Watching for new downloads and modifications...")
        print("🧠 AI-powered similarity detection active!")
        print("⚠️  Enhanced modal alerts will show similarity scores!")
        print(f"🌐 Open http://localhost:{WEB_SERVER_PORT}/stats to view enhanced dashboard")
        print("\nPress Ctrl+C to stop monitoring.\n")
        
        # Try to open web browser to stats page
        try:
            webbrowser.open(f'http://localhost:{WEB_SERVER_PORT}/stats')
        except:
            pass

        # Keep the monitor running
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Stopping enhanced monitor...")
        observer.stop()
        advanced_detector.close_database()
        if web_server:
            web_server.shutdown()
        print("✅ Enhanced monitor stopped successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")
        observer.stop()
        advanced_detector.close_database()
        if web_server:
            web_server.shutdown()

    finally:
        observer.join()

def cleanup_temp_files():
    """Clean up temporary files"""
    try:
        temp_files = [
            "duplicate_alert.html",
            "duplicate_alert_modal.html"
        ]

        script_dir = os.path.dirname(os.path.abspath(__file__))
        for temp_file in temp_files:
            temp_path = os.path.join(script_dir, temp_file)
            if os.path.exists(temp_path):
                os.remove(temp_path)
                print(f"🧹 Cleaned up: {temp_file}")

    except Exception as e:
        print(f"Warning: Could not clean up temp files: {e}")

def test_advanced_detection():
    """Test the advanced detection system"""
    print("🧪 Testing advanced detection system...")
    
    # Test basic modal
    test_duplicate = os.path.join(DOWNLOAD_DIR, "test_duplicate.pdf")
    test_original = os.path.join(DOWNLOAD_DIR, "original_file.pdf")
    
    similarity_details = {
        'detection_method': 'Perceptual Hash',
        'confidence': '95.5%',
        'algorithm': 'Test Algorithm'
    }
    
    show_enhanced_modal_alert(test_duplicate, test_original, "Test Advanced Detection", 0.955, similarity_details)
    print("✅ Advanced test alert triggered!")

def install_dependencies():
    """Install missing dependencies"""
    print("📦 Installing missing dependencies for enhanced features...")
    
    dependencies = []
    if not PIL_AVAILABLE:
        dependencies.append("Pillow")
    if not LIBROSA_AVAILABLE:
        dependencies.append("librosa")
    if not CV2_AVAILABLE:
        dependencies.append("opencv-python")
    if not PYMUPDF_AVAILABLE:
        dependencies.append("PyMuPDF")
    if not DOCX_AVAILABLE:
        dependencies.append("python-docx")
    if not SSDEEP_AVAILABLE:
        if os.name == 'nt':
            dependencies.append("ssdeep-windows")
        else:
            dependencies.append("ssdeep")
    
    if dependencies:
        print(f"Missing dependencies: {', '.join(dependencies)}")
        print("\nTo install all dependencies, run:")
        print(f"pip install {' '.join(dependencies)}")
        
        response = input("\nWould you like to install them now? (y/n): ").lower().strip()
        if response == 'y':
            for dep in dependencies:
                try:
                    print(f"Installing {dep}...")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
                    print(f"✅ {dep} installed successfully")
                except Exception as e:
                    print(f"❌ Failed to install {dep}: {e}")
        else:
            print("⚠️  Some advanced features will be disabled without these dependencies.")
    else:
        print("✅ All dependencies are already installed!")

def show_help():
    """Show enhanced help information"""
    help_text = """
🚨 ENHANCED DOWNLOAD MONITOR WITH ADVANCED AI DUPLICATE DETECTION 🚨

USAGE:
    python enhanced_download_monitor.py [command]

COMMANDS:
    start       - Start enhanced monitoring (default)
    test        - Test advanced detection system  
    install     - Install missing dependencies
    cleanup     - Clean up temporary files
    help        - Show this help message

🔬 ADVANCED DETECTION FEATURES:
    ✅ Image Similarity Detection
       • Perceptual hashing (pHash, aHash, dHash, wHash)
       • Detects similar images even with different formats/quality
       • Configurable similarity thresholds
    
    ✅ Audio Fingerprinting
       • MFCC feature extraction
       • Spectral centroid analysis
       • Detects similar music regardless of quality/format
       
    ✅ Document Content Analysis
       • PDF text extraction with OCR
       • Word document analysis
       • Text similarity comparison using sequence matching
       
    ✅ Video Thumbnail Comparison
       • Extracts video thumbnails
       • Compares using perceptual hashing
       • Detects similar videos with different encodings
       
    ✅ Fuzzy Hash Matching (ssdeep)
       • Detects similar but not identical files
       • Great for detecting modified versions
       • Works across all file types

🔧 TRADITIONAL FEATURES:
    ✅ MD5 hash duplicate detection
    ✅ Smart filename similarity detection
    ✅ File modification tracking with change detection
    ✅ Enhanced modal alerts with similarity scores
    ✅ File type and size filtering
    ✅ Cross-platform support
    ✅ Persistent databases (SQLite + text files)
    ✅ Web-based analytics dashboard

📊 WEB DASHBOARD:
    • Real-time statistics with advanced metrics
    • Feature status indicators
    • Advanced detection database stats
    • File analysis with detection methods
    • Modern responsive design with animations
    • Auto-refresh every 30 seconds

⚙️ CONFIGURATION:
    Download Directory: C:\\Users\\Manoj\\Downloads
    Basic Hash DB: file_hashes.txt
    Modification DB: file_modifications.txt
    Advanced DB: advanced_duplicates.db (SQLite)
    Web Interface: http://localhost:8080/stats
    
    Similarity Thresholds:
    • Image Hash: ≤10 (lower = more similar)
    • Audio Similarity: ≥85% (higher = more similar)  
    • Text Similarity: ≥85% (higher = more similar)
    • Video Similarity: ≥80% (higher = more similar)
    • Fuzzy Similarity: ≥80% (higher = more similar)

📦 DEPENDENCIES:
    Required for full functionality:
    • Pillow (PIL) - Image processing
    • librosa - Audio analysis  
    • opencv-python - Video processing
    • PyMuPDF - PDF text extraction
    • python-docx - Word document analysis
    • ssdeep-windows/ssdeep - Fuzzy hashing

🚀 INSTALLATION:
    1. Run: python enhanced_download_monitor.py install
    2. Or manually: pip install Pillow librosa opencv-python PyMuPDF python-docx ssdeep-windows
    3. Start monitoring: python enhanced_download_monitor.py start

🔍 HOW IT WORKS:
    1. Traditional MD5 hashing for exact duplicates
    2. Advanced fingerprinting for similarity detection
    3. Multi-algorithm comparison with confidence scores
    4. SQLite database stores all fingerprints
    5. Real-time analysis of new downloads
    6. Enhanced alerts show similarity details
    7. Web dashboard provides comprehensive analytics

Press Ctrl+C to stop monitoring at any time.
    """
    print(help_text)

def main():
    """Enhanced main function with advanced features"""
    import sys

    # Handle command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == "help":
            show_help()
            return
        elif command == "test":
            test_advanced_detection()
            return
        elif command == "install":
            install_dependencies()
            return
        elif command == "cleanup":
            cleanup_temp_files()
            return
        elif command == "start":
            pass  # Continue to start monitoring
        else:
            print(f"❌ Unknown command: {command}")
            print("Use 'python enhanced_download_monitor.py help' for usage information.")
            return

    # Register cleanup function
    import atexit
    atexit.register(cleanup_temp_files)
    atexit.register(lambda: advanced_detector.close_database())

    try:
        # Start the enhanced monitoring system
        start_monitoring()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        cleanup_temp_files()
        advanced_detector.close_database()
    finally:
        print("\n👋 Thank you for using Enhanced Download Monitor!")

if __name__ == "__main__":
    main()  


    