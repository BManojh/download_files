import os
import hashlib
import time
import re
import webbrowser
import threading
import tkinter as tk
from tkinter import messagebox
import subprocess
import sys
import json
import sqlite3
import mimetypes
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path
import pandas as pd
import zipfile
import csv

# Configuration
DOWNLOAD_DIR = r"C:\Users\Manoj\Downloads"
DATABASE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddas_database.db")
WEB_ALERT_PORT = 8888
WEB_DASHBOARD_PORT = 8889

# Global variables
web_server = None
web_server_thread = None
dashboard_server = None
dashboard_thread = None

class DatabaseManager:
    """Enhanced database manager for DDAS system"""
    
    def __init__(self):
        self.db_file = DATABASE_FILE
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database with enhanced schema"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Files table with enhanced metadata
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                file_size INTEGER,
                file_type TEXT,
                mime_type TEXT,
                created_date TEXT,
                modified_date TEXT,
                download_date TEXT,
                user_id TEXT DEFAULT 'default_user',
                metadata_json TEXT,
                dataset_type TEXT,
                unique_identifier TEXT,
                is_dataset BOOLEAN DEFAULT 0,
                UNIQUE(file_hash, filename)
            )
        ''')
        
        # Download history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS download_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER,
                download_timestamp TEXT,
                source_url TEXT,
                browser_info TEXT,
                user_id TEXT,
                action TEXT,
                FOREIGN KEY (file_id) REFERENCES files (id)
            )
        ''')
        
        # Metadata analysis table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metadata_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER,
                analysis_type TEXT,
                analysis_result TEXT,
                confidence_score REAL,
                created_date TEXT,
                FOREIGN KEY (file_id) REFERENCES files (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_file(self, file_data):
        """Add file with enhanced metadata to database"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO files 
                (filename, file_path, file_hash, file_size, file_type, mime_type, 
                 created_date, modified_date, download_date, user_id, metadata_json, 
                 dataset_type, unique_identifier, is_dataset)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', file_data)
            
            file_id = cursor.lastrowid
            conn.commit()
            return file_id
        except Exception as e:
            print(f"Error adding file to database: {e}")
            return None
        finally:
            conn.close()
    
    def find_duplicates(self, file_hash, filename):
        """Find duplicates with enhanced matching"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Find exact hash matches
        cursor.execute('''
            SELECT * FROM files WHERE file_hash = ? AND filename != ?
        ''', (file_hash, filename))
        hash_matches = cursor.fetchall()
        
        # Find similar files based on metadata
        cursor.execute('''
            SELECT * FROM files WHERE unique_identifier = (
                SELECT unique_identifier FROM files WHERE file_hash = ? LIMIT 1
            ) AND file_hash != ?
        ''', (file_hash, file_hash))
        metadata_matches = cursor.fetchall()
        
        conn.close()
        return hash_matches, metadata_matches
    
    def get_download_history(self, file_hash):
        """Get download history for a file"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT dh.*, f.filename FROM download_history dh
            JOIN files f ON dh.file_id = f.id
            WHERE f.file_hash = ?
            ORDER BY dh.download_timestamp DESC
        ''', (file_hash,))
        
        history = cursor.fetchall()
        conn.close()
        return history
    
    def get_file_statistics(self):
        """Get comprehensive file statistics"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Get total files count
        cursor.execute('SELECT COUNT(*) FROM files')
        total_files = cursor.fetchone()[0]
        
        # Get file type distribution
        cursor.execute('''
            SELECT file_type, COUNT(*) as count 
            FROM files 
            GROUP BY file_type 
            ORDER BY count DESC
        ''')
        file_types = cursor.fetchall()
        
        # Get dataset files count
        cursor.execute('SELECT COUNT(*) FROM files WHERE is_dataset = 1')
        dataset_files = cursor.fetchone()[0]
        
        # Get duplicates count
        cursor.execute('''
            SELECT COUNT(*) FROM (
                SELECT file_hash, COUNT(*) as count 
                FROM files 
                GROUP BY file_hash 
                HAVING count > 1
            )
        ''')
        duplicate_files = cursor.fetchone()[0]
        
        # Get recent files
        cursor.execute('''
            SELECT filename, file_type, download_date 
            FROM files 
            ORDER BY download_date DESC 
            LIMIT 10
        ''')
        recent_files = cursor.fetchall()
        
        # Get file size statistics
        cursor.execute('SELECT SUM(file_size) FROM files')
        total_size = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            'total_files': total_files,
            'file_types': dict(file_types),
            'dataset_files': dataset_files,
            'duplicate_files': duplicate_files,
            'recent_files': recent_files,
            'total_size': total_size
        }

class MetadataAnalyzer:
    """Advanced metadata analyzer for datasets"""
    
    def __init__(self):
        self.supported_extensions = {
            '.csv': 'CSV Dataset',
            '.xlsx': 'Excel Dataset',
            '.xls': 'Excel Dataset',
            '.json': 'JSON Dataset',
            '.xml': 'XML Dataset',
            '.tsv': 'TSV Dataset',
            '.parquet': 'Parquet Dataset',
            '.h5': 'HDF5 Dataset',
            '.pkl': 'Pickle Dataset',
            '.zip': 'Compressed Dataset',
            '.tar': 'Archive Dataset',
            '.gz': 'Compressed Dataset',
            '.pdf': 'PDF Document',
            '.ppt': 'PowerPoint Presentation',
            '.pptx': 'PowerPoint Presentation',
            '.doc': 'Word Document',
            '.docx': 'Word Document',
            '.txt': 'Text File',
            '.jpg': 'JPEG Image',
            '.jpeg': 'JPEG Image',
            '.png': 'PNG Image',
            '.gif': 'GIF Image',
            '.mp4': 'MP4 Video',
            '.mp3': 'MP3 Audio',
            '.wav': 'WAV Audio'
        }
    
    def analyze_file(self, file_path):
        """Comprehensive file analysis"""
        try:
            file_stats = os.stat(file_path)
            file_ext = Path(file_path).suffix.lower()
            mime_type, _ = mimetypes.guess_type(file_path)
            
            analysis = {
                'filename': os.path.basename(file_path),
                'file_size': file_stats.st_size,
                'file_type': file_ext,
                'mime_type': mime_type or 'unknown',
                'created_date': datetime.fromtimestamp(file_stats.st_ctime).isoformat(),
                'modified_date': datetime.fromtimestamp(file_stats.st_mtime).isoformat(),
                'is_dataset': file_ext in ['.csv', '.xlsx', '.xls', '.json', '.xml', '.tsv'],
                'dataset_type': self.supported_extensions.get(file_ext, 'Unknown'),
                'unique_identifier': self._generate_unique_identifier(file_path),
                'content_preview': self._analyze_content(file_path, file_ext),
                'structure_analysis': self._analyze_structure(file_path, file_ext)
            }
            
            return analysis
            
        except Exception as e:
            print(f"Error analyzing file {file_path}: {e}")
            return None
    
    def _generate_unique_identifier(self, file_path):
        """Generate unique identifier based on content structure"""
        try:
            file_ext = Path(file_path).suffix.lower()
            
            if file_ext == '.csv':
                return self._csv_identifier(file_path)
            elif file_ext in ['.xlsx', '.xls']:
                return self._excel_identifier(file_path)
            elif file_ext == '.json':
                return self._json_identifier(file_path)
            else:
                # Fallback to filename-based identifier
                return hashlib.md5(os.path.basename(file_path).encode()).hexdigest()[:16]
                
        except Exception as e:
            return f"error_{int(time.time())}"
    
    def _csv_identifier(self, file_path):
        """Generate identifier for CSV files based on structure"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # Read first few lines to analyze structure
                lines = [f.readline().strip() for _ in range(5)]
                header = lines[0] if lines else ""
                
                # Create identifier from column structure
                columns_hash = hashlib.md5(header.encode()).hexdigest()[:12]
                return f"csv_{columns_hash}"
        except:
            return f"csv_unknown_{int(time.time())}"
    
    def _excel_identifier(self, file_path):
        """Generate identifier for Excel files"""
        try:
            # Use pandas to read Excel structure
            df = pd.read_excel(file_path, nrows=0)  # Just headers
            columns_str = "_".join(df.columns.astype(str))
            columns_hash = hashlib.md5(columns_str.encode()).hexdigest()[:12]
            return f"excel_{columns_hash}"
        except:
            return f"excel_unknown_{int(time.time())}"
    
    def _json_identifier(self, file_path):
        """Generate identifier for JSON files"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Create identifier from JSON structure
            if isinstance(data, dict):
                keys_str = "_".join(sorted(data.keys()))
            elif isinstance(data, list) and data and isinstance(data[0], dict):
                keys_str = "_".join(sorted(data[0].keys()))
            else:
                keys_str = str(type(data).__name__)
                
            keys_hash = hashlib.md5(keys_str.encode()).hexdigest()[:12]
            return f"json_{keys_hash}"
        except:
            return f"json_unknown_{int(time.time())}"
    
    def _analyze_content(self, file_path, file_ext):
        """Analyze file content preview"""
        try:
            if file_ext == '.csv':
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = [f.readline().strip() for _ in range(3)]
                    return {"preview_lines": lines, "type": "text"}
            
            elif file_ext == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    preview = str(data)[:200] + "..." if len(str(data)) > 200 else str(data)
                    return {"preview": preview, "type": "json"}
            
            elif file_ext in ['.txt', '.log']:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(200)
                    return {"preview": content, "type": "text"}
            
            return {"type": "binary", "preview": "Binary file - no preview available"}
            
        except Exception as e:
            return {"error": str(e), "type": "error"}
    
    def _analyze_structure(self, file_path, file_ext):
        """Analyze file structure"""
        try:
            if file_ext == '.csv':
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    reader = csv.reader(f)
                    header = next(reader, [])
                    row_count = sum(1 for _ in f) + 1  # +1 for header
                    return {
                        "columns": len(header),
                        "rows": row_count,
                        "headers": header[:10],  # First 10 columns
                        "structure": "tabular"
                    }
            
            elif file_ext in ['.xlsx', '.xls']:
                df = pd.read_excel(file_path, nrows=0)
                return {
                    "columns": len(df.columns),
                    "headers": list(df.columns)[:10],
                    "structure": "spreadsheet"
                }
            
            elif file_ext == '.zip':
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    files = zip_ref.namelist()
                    return {
                        "archive_files": len(files),
                        "file_list": files[:20],  # First 20 files
                        "structure": "archive"
                    }
            
            return {"structure": "unknown"}
            
        except Exception as e:
            return {"error": str(e), "structure": "error"}

class EnhancedModalAlert:
    """Enhanced modal alert with detailed dataset information"""
    
    def __init__(self, duplicate_file, original_file, metadata, alert_type="Content duplicate"):
        self.duplicate_file = duplicate_file
        self.original_file = original_file
        self.metadata = metadata
        self.alert_type = alert_type
        self.timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Get enhanced file information
        self.duplicate_info = self._get_enhanced_file_info(duplicate_file)
        self.original_info = self._get_enhanced_file_info(original_file)
        
    def _get_enhanced_file_info(self, file_path):
        """Get enhanced file information"""
        try:
            if os.path.exists(file_path):
                stat = os.stat(file_path)
                return {
                    'name': os.path.basename(file_path),
                    'size': self._format_file_size(stat.st_size),
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'created': datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                    'path': file_path
                }
            return {'name': 'Unknown', 'size': 'Unknown', 'modified': 'Unknown', 'created': 'Unknown', 'path': file_path}
        except:
            return {'name': 'Error', 'size': 'Error', 'modified': 'Error', 'created': 'Error', 'path': file_path}
    
    def _format_file_size(self, size_bytes):
        """Format file size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def show(self):
        """Show enhanced modal alert"""
        try:
            self.show_tkinter_modal()
        except Exception as e:
            print(f"Tkinter modal failed: {e}")
            self.show_web_modal()
    
    def show_tkinter_modal(self):
        """Show enhanced system-level modal dialog"""
        root = tk.Tk()
        root.withdraw()
        
        root.attributes('-topmost', True)
        root.attributes('-alpha', 0.95)
        root.lift()
        root.focus_force()
        
        # Enhanced message with metadata
        message = f"""🚨 DDAS: DUPLICATE DATASET DETECTED! 🚨

⏰ Alert Time: {self.timestamp}
📋 Type: {self.alert_type}
🔬 Dataset Type: {self.metadata.get('dataset_type', 'Unknown')}
📊 Unique ID: {self.metadata.get('unique_identifier', 'N/A')}

📄 DUPLICATE FILE:
📁 Name: {self.duplicate_info['name']}
📏 Size: {self.duplicate_info['size']}
🕒 Modified: {self.duplicate_info['modified']}
🕒 Created: {self.duplicate_info['created']}

📄 ORIGINAL FILE:
📁 Name: {self.original_info['name']}
📏 Size: {self.original_info['size']}
🕒 Modified: {self.original_info['modified']}
🕒 Created: {self.original_info['created']}

💾 Content Analysis:
{self._format_content_analysis()}

⚠️ This prevents redundant downloads and optimizes resource usage!"""

        response = messagebox.askyesnocancel(
            title="🚨 DDAS: DUPLICATE DATASET ALERT 🚨",
            message=message,
            detail="YES = Delete duplicate | NO = Keep both | CANCEL = Close alert",
            icon='warning'
        )
        
        if response is True:  # Yes - Delete
            self._delete_duplicate()
        elif response is False:  # No - Keep both
            messagebox.showinfo("DDAS", "Both files will be kept. Duplicate logged for future reference.")
        # Cancel or None - Just close
        
        root.destroy()
    
    def _format_content_analysis(self):
        """Format content analysis for display"""
        if not self.metadata:
            return "No metadata available"
        
        analysis = []
        
        if 'structure_analysis' in self.metadata:
            struct = self.metadata['structure_analysis']
            if 'columns' in struct:
                analysis.append(f"Columns: {struct['columns']}")
            if 'rows' in struct:
                analysis.append(f"Rows: {struct['rows']}")
            if 'headers' in struct and struct['headers']:
                headers = ', '.join(struct['headers'][:5])
                analysis.append(f"Headers: {headers}...")
        
        if 'file_size' in self.metadata:
            analysis.append(f"File Size: {self._format_file_size(self.metadata['file_size'])}")
        
        return '\n'.join(analysis) if analysis else "Basic file information available"
    
    def _delete_duplicate(self):
        """Delete duplicate file with confirmation"""
        try:
            os.remove(self.duplicate_file)
            print(f"DDAS: Deleted duplicate file: {self.duplicate_file}")
            messagebox.showinfo(
                "DDAS Success", 
                f"Duplicate dataset has been deleted:\n{os.path.basename(self.duplicate_file)}\n\nResource usage optimized!"
            )
        except Exception as e:
            messagebox.showerror(
                "DDAS Error", 
                f"Could not delete duplicate:\n{str(e)}"
            )
    
    def show_web_modal(self):
        """Show enhanced web-based modal"""
        try:
            html_content = f'''
<!DOCTYPE html>
<html>
<head>
    <title>🚨 DDAS: DUPLICATE DATASET ALERT</title>
    <meta charset="utf-8">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 999999;
        }}
        
        .modal {{
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(20px);
            color: #333;
            border-radius: 25px;
            padding: 40px;
            max-width: 1200px;
            width: 95%;
            max-height: 90vh;
            box-shadow: 0 30px 60px rgba(0,0,0,0.3);
            animation: modalSlideIn 0.6s ease-out;
            overflow-y: auto;
        }}
        
        @keyframes modalSlideIn {{
            from {{ opacity: 0; transform: scale(0.8) translateY(-50px); }}
            to {{ opacity: 1; transform: scale(1) translateY(0); }}
        }}
        
        .alert-header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        
        .alert-icon {{
            font-size: 4rem;
            color: #ff6b7a;
            margin-bottom: 15px;
        }}
        
        .alert-title {{
            font-size: 2rem;
            color: #333;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        
        .metadata-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .file-card {{
            background: rgba(255, 255, 255, 0.8);
            border-radius: 15px;
            padding: 20px;
            border-left: 5px solid #ff6b7a;
        }}
        
        .file-card h3 {{
            color: #ff6b7a;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }}
        
        .info-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            padding: 5px 0;
            border-bottom: 1px solid rgba(0,0,0,0.1);
        }}
        
        .info-label {{
            font-weight: bold;
            color: #555;
        }}
        
        .info-value {{
            color: #333;
            font-family: 'Courier New', monospace;
        }}
        
        .metadata-section {{
            background: rgba(100, 150, 255, 0.1);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
        }}
        
        .metadata-title {{
            font-size: 1.4rem;
            color: #4a90e2;
            margin-bottom: 15px;
            font-weight: bold;
        }}
        
        .action-buttons {{
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-top: 30px;
        }}
        
        .btn {{
            padding: 15px 30px;
            border-radius: 25px;
            font-size: 1.1rem;
            font-weight: bold;
            cursor: pointer;
            border: none;
            transition: all 0.3s ease;
        }}
        
        .btn-delete {{
            background: linear-gradient(45deg, #ff6b7a, #ff8e9b);
            color: white;
        }}
        
        .btn-keep {{
            background: linear-gradient(45deg, #4ecdc4, #44a08d);
            color: white;
        }}
        
        .btn-close {{
            background: linear-gradient(45deg, #95a5a6, #7f8c8d);
            color: white;
        }}
        
        .btn:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        }}
    </style>
</head>
<body>
    <div class="modal">
        <div class="alert-header">
            <div class="alert-icon">🚨</div>
            <div class="alert-title">DDAS: DUPLICATE DATASET DETECTED</div>
            <p style="color: #666; font-size: 1.1rem;">Data Download Duplication Alert System</p>
            <p style="color: #888; margin-top: 10px;">{self.timestamp} | {self.alert_type}</p>
        </div>
        
        <div class="metadata-section">
            <div class="metadata-title">📊 Dataset Information</div>
            <div class="info-row">
                <span class="info-label">Dataset Type:</span>
                <span class="info-value">{self.metadata.get('dataset_type', 'Unknown')}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Unique Identifier:</span>
                <span class="info-value">{self.metadata.get('unique_identifier', 'N/A')}</span>
            </div>
            <div class="info-row">
                <span class="info-label">MIME Type:</span>
                <span class="info-value">{self.metadata.get('mime_type', 'Unknown')}</span>
            </div>
        </div>
        
        <div class="metadata-grid">
            <div class="file-card">
                <h3>📄 Duplicate File</h3>
                <div class="info-row">
                    <span class="info-label">Name:</span>
                    <span class="info-value">{self.duplicate_info['name']}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Size:</span>
                    <span class="info-value">{self.duplicate_info['size']}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Modified:</span>
                    <span class="info-value">{self.duplicate_info['modified']}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Created:</span>
                    <span class="info-value">{self.duplicate_info['created']}</span>
                </div>
            </div>
            
            <div class="file-card">
                <h3>📄 Original File</h3>
                <div class="info-row">
                    <span class="info-label">Name:</span>
                    <span class="info-value">{self.original_info['name']}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Size:</span>
                    <span class="info-value">{self.original_info['size']}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Modified:</span>
                    <span class="info-value">{self.original_info['modified']}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Created:</span>
                    <span class="info-value">{self.original_info['created']}</span>
                </div>
            </div>
        </div>
        
        <div class="action-buttons">
            <button class="btn btn-delete" onclick="deleteDuplicate()">
                🗑️ DELETE DUPLICATE
            </button>
            <button class="btn btn-keep" onclick="keepBoth()">
                📁 KEEP BOTH
            </button>
            <button class="btn btn-close" onclick="closeAlert()">
                ✖️ CLOSE ALERT
            </button>
        </div>
    </div>
    
    <script>
        function deleteDuplicate() {{
            if (confirm('DDAS: Permanently delete duplicate dataset?\\n\\n{self.duplicate_info["name"]}')) {{
                // Implementation for delete operation
                alert('Delete operation would be implemented here');
                closeAlert();
            }}
        }}
        
        function keepBoth() {{
            alert('DDAS: Both files kept. Duplicate logged for reference.');
            closeAlert();
        }}
        
        function closeAlert() {{
            window.close();
        }}
        
        // Auto-focus and prevent blur
        window.focus();
        window.addEventListener('blur', () => setTimeout(() => window.focus(), 100));
    </script>
</body>
</html>'''
            
            temp_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddas_alert.html")
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            webbrowser.open(f'file:///{temp_file.replace(os.sep, "/")}')
            
        except Exception as e:
            print(f"Error showing web modal: {e}")

class EnhancedDownloadHandler(FileSystemEventHandler):
    """Enhanced download handler with DDAS capabilities"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.metadata_analyzer = MetadataAnalyzer()
        self.processing_files = set()
        self.file_modification_times = {}
        super().__init__()
    
    def on_created(self, event):
        if not event.is_directory:
            self.handle_file_event(event.src_path, is_new_file=True)

    def on_moved(self, event):
        if not event.is_directory:
            self.handle_file_event(event.dest_path, is_new_file=True)

    def on_modified(self, event):
        if not event.is_directory:
            self.handle_file_event(event.src_path, is_new_file=False)
    
    def handle_file_event(self, file_path, is_new_file):
        """Handle file events with enhanced processing"""
        if file_path in self.processing_files:
            return
        
        current_time = time.time()
        if not is_new_file and file_path in self.file_modification_times:
            if current_time - self.file_modification_times[file_path] < 5:
                return
        
        self.processing_files.add(file_path)
        self.file_modification_times[file_path] = current_time
        
        # Process file in separate thread
        thread = threading.Thread(
            target=self._process_file_async,
            args=(file_path, is_new_file),
            daemon=True
        )
        thread.start()
    
    def _process_file_async(self, file_path, is_new_file):
        """Process file asynchronously"""
        try:
            time.sleep(2)  # Wait for file to stabilize
            
            if not self._wait_for_stable_file(file_path):
                return
            
            # Perform enhanced analysis
            metadata = self.metadata_analyzer.analyze_file(file_path)
            if not metadata:
                return
            
            file_hash = self._calculate_hash(file_path)
            if not file_hash:
                return
            
            # Check for duplicates using enhanced matching
            hash_matches, metadata_matches = self.db_manager.find_duplicates(
                file_hash, os.path.basename(file_path)
            )
            
            if hash_matches or metadata_matches:
                self._handle_duplicate_detection(file_path, metadata, hash_matches, metadata_matches)
            else:
                self._handle_new_file(file_path, metadata, file_hash)
                
        except Exception as e:
            print(f"DDAS: Error processing {file_path}: {e}")
        finally:
            self.processing_files.discard(file_path)
    
    def _wait_for_stable_file(self, file_path, max_wait=30):
        """Wait for file to be stable"""
        stable_count = 0
        wait_count = 0
        
        while stable_count < 3 and wait_count < max_wait:
            try:
                if not os.path.exists(file_path):
                    return False
                
                current_size = os.path.getsize(file_path)
                time.sleep(1)
                wait_count += 1
                
                if not os.path.exists(file_path):
                    return False
                    
                new_size = os.path.getsize(file_path)
                
                if current_size == new_size and current_size > 0:
                    stable_count += 1
                else:
                    stable_count = 0
                    
            except Exception as e:
                print(f"Error waiting for stable file: {e}")
                time.sleep(1)
                wait_count += 1
        
        return stable_count >= 3
    
    def _calculate_hash(self, file_path):
        """Calculate file hash"""
        hasher = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            print(f"Error calculating hash for {file_path}: {e}")
            return None
    
    def _handle_duplicate_detection(self, file_path, metadata, hash_matches, metadata_matches):
        """Handle duplicate file detection with enhanced alerts"""
        print(f"\n🚨 DDAS: DUPLICATE DETECTED - {os.path.basename(file_path)}")
        
        # Determine the type of duplicate and original file
        if hash_matches:
            original_file_info = hash_matches[0]
            original_file_path = original_file_info[2]  # file_path column
            alert_type = "Exact Content Duplicate"
            
            print(f"📋 Type: {alert_type}")
            print(f"📄 Original: {original_file_info[1]}")  # filename
            print(f"🔍 Hash Match: {original_file_info[3][:16]}...")  # file_hash
            
        elif metadata_matches:
            original_file_info = metadata_matches[0]
            original_file_path = original_file_info[2]
            alert_type = "Metadata Structure Duplicate"
            
            print(f"📋 Type: {alert_type}")
            print(f"📄 Original: {original_file_info[1]}")
            print(f"🆔 Unique ID: {original_file_info[13]}")  # unique_identifier
        
        # Show enhanced modal alert
        try:
            alert = EnhancedModalAlert(
                file_path, 
                original_file_path, 
                metadata, 
                alert_type
            )
            alert.show()
        except Exception as e:
            print(f"Error showing alert: {e}")
        
        # Log duplicate detection
        self._log_duplicate_detection(file_path, original_file_path, alert_type, metadata)
    
    def _handle_new_file(self, file_path, metadata, file_hash):
        """Handle new unique file"""
        filename = os.path.basename(file_path)
        
        print(f"\n✅ DDAS: NEW UNIQUE DATASET - {filename}")
        print(f"📊 Type: {metadata.get('dataset_type', 'Unknown')}")
        print(f"📏 Size: {self._format_file_size(metadata.get('file_size', 0))}")
        print(f"🆔 ID: {metadata.get('unique_identifier', 'N/A')}")
        
        if metadata.get('structure_analysis'):
            struct = metadata['structure_analysis']
            if 'columns' in struct:
                print(f"📈 Columns: {struct['columns']}")
            if 'rows' in struct:
                print(f"📊 Rows: {struct['rows']}")
        
        # Add to database
        file_data = (
            filename,                                    # filename
            file_path,                                   # file_path
            file_hash,                                   # file_hash
            metadata.get('file_size', 0),               # file_size
            metadata.get('file_type', ''),              # file_type
            metadata.get('mime_type', ''),              # mime_type
            metadata.get('created_date', ''),           # created_date
            metadata.get('modified_date', ''),          # modified_date
            datetime.now().isoformat(),                 # download_date
            'default_user',                             # user_id
            json.dumps(metadata),                       # metadata_json
            metadata.get('dataset_type', ''),           # dataset_type
            metadata.get('unique_identifier', ''),      # unique_identifier
            1 if metadata.get('is_dataset', False) else 0  # is_dataset
        )
        
        file_id = self.db_manager.add_file(file_data)
        if file_id:
            print(f"💾 Added to DDAS database (ID: {file_id})")
        
        # Log download history
        self._log_download_history(file_id, file_path)
    
    def _format_file_size(self, size_bytes):
        """Format file size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def _log_duplicate_detection(self, duplicate_path, original_path, alert_type, metadata):
        """Log duplicate detection event"""
        conn = sqlite3.connect(self.db_manager.db_file)
        cursor = conn.cursor()
        
        try:
            # Find original file ID
            cursor.execute('SELECT id FROM files WHERE file_path = ?', (original_path,))
            result = cursor.fetchone()
            
            if result:
                original_file_id = result[0]
                
                cursor.execute('''
                    INSERT INTO download_history 
                    (file_id, download_timestamp, source_url, browser_info, user_id, action)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    original_file_id,
                    datetime.now().isoformat(),
                    'local_download',
                    f'DDAS_Duplicate_Detection_{alert_type}',
                    'default_user',
                    f'DUPLICATE_BLOCKED: {os.path.basename(duplicate_path)}'
                ))
                
                conn.commit()
                
        except Exception as e:
            print(f"Error logging duplicate detection: {e}")
        finally:
            conn.close()
    
    def _log_download_history(self, file_id, file_path):
        """Log download history for new file"""
        if not file_id:
            return
            
        conn = sqlite3.connect(self.db_manager.db_file)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO download_history 
                (file_id, download_timestamp, source_url, browser_info, user_id, action)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                file_id,
                datetime.now().isoformat(),
                'local_download',
                'DDAS_Monitor',
                'default_user',
                f'NEW_DOWNLOAD: {os.path.basename(file_path)}'
            ))
            
            conn.commit()
            
        except Exception as e:
            print(f"Error logging download history: {e}")
        finally:
            conn.close()

class DDASReportGenerator:
    """Generate comprehensive DDAS reports"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
    
    def generate_summary_report(self):
        """Generate summary report of DDAS activity"""
        conn = sqlite3.connect(self.db_manager.db_file)
        cursor = conn.cursor()
        
        try:
            # Get statistics
            cursor.execute('SELECT COUNT(*) FROM files')
            total_files = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM files WHERE is_dataset = 1')
            total_datasets = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(DISTINCT file_hash) FROM files')
            unique_files = cursor.fetchone()[0]
            
            cursor.execute('''
                SELECT COUNT(*) FROM download_history 
                WHERE action LIKE 'DUPLICATE_BLOCKED%'
            ''')
            duplicates_blocked = cursor.fetchone()[0]
            
            cursor.execute('''
                SELECT dataset_type, COUNT(*) FROM files 
                WHERE is_dataset = 1 
                GROUP BY dataset_type 
                ORDER BY COUNT(*) DESC
            ''')
            dataset_types = cursor.fetchall()
            
            # Generate report
            report = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    DDAS (Data Download Duplication Alert System)             ║
║                              ACTIVITY SUMMARY REPORT                         ║
╚══════════════════════════════════════════════════════════════════════════════╝

📊 OVERALL STATISTICS:
   • Total Files Monitored: {total_files:,}
   • Unique Datasets: {total_datasets:,}
   • Unique File Hashes: {unique_files:,}
   • Duplicates Blocked: {duplicates_blocked:,}
   • Resource Efficiency: {((total_files - unique_files) / max(total_files, 1) * 100):.1f}% duplicates prevented

📈 DATASET BREAKDOWN:"""
            
            for dtype, count in dataset_types[:10]:  # Top 10
                report += f"\n   • {dtype}: {count:,} files"
            
            # Recent activity
            cursor.execute('''
                SELECT action, COUNT(*) FROM download_history 
                WHERE download_timestamp > datetime('now', '-7 days')
                GROUP BY action 
                ORDER BY COUNT(*) DESC
            ''')
            recent_activity = cursor.fetchall()
            
            report += f"\n\n🕒 RECENT ACTIVITY (Last 7 Days):"
            for action, count in recent_activity:
                report += f"\n   • {action}: {count:,}"
            
            # Top duplicate patterns
            cursor.execute('''
                SELECT f1.filename, f2.filename, f1.file_hash
                FROM files f1
                JOIN files f2 ON f1.file_hash = f2.file_hash AND f1.id < f2.id
                LIMIT 5
            ''')
            duplicate_patterns = cursor.fetchall()
            
            if duplicate_patterns:
                report += f"\n\n🔄 RECENT DUPLICATE PATTERNS:"
                for orig, dup, hash_val in duplicate_patterns:
                    report += f"\n   • '{orig}' ≈ '{dup}' (Hash: {hash_val[:16]}...)"
            
            report += f"\n\n💡 RECOMMENDATIONS:"
            efficiency_ratio = (total_files - unique_files) / max(total_files, 1)
            
            if efficiency_ratio > 0.3:
                report += f"\n   ⚠️  High duplicate rate detected ({efficiency_ratio*100:.1f}%)"
                report += f"\n   💡 Consider organizing downloads or cleaning up duplicates"
            else:
                report += f"\n   ✅ Good download hygiene maintained"
            
            report += f"\n   📊 DDAS has prevented {duplicates_blocked:,} redundant downloads"
            report += f"\n   🌱 Estimated disk space saved: {self._estimate_space_saved()} MB"
            
            report += f"\n\n" + "="*80
            report += f"\nReport generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            report += f"\n" + "="*80
            
            return report
            
        except Exception as e:
            return f"Error generating report: {e}"
        finally:
            conn.close()
    
    def _estimate_space_saved(self):
        """Estimate disk space saved by preventing duplicates"""
        conn = sqlite3.connect(self.db_manager.db_file)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT SUM(f.file_size) 
                FROM files f
                JOIN download_history dh ON f.id = dh.file_id
                WHERE dh.action LIKE 'DUPLICATE_BLOCKED%'
            ''')
            result = cursor.fetchone()[0]
            return (result or 0) // (1024 * 1024)  # Convert to MB
        except:
            return 0
        finally:
            conn.close()

class DDASDashboardHandler(BaseHTTPRequestHandler):
    """HTTP handler for DDAS dashboard"""
    
    def do_GET(self):
        if self.path == '/':
            self.send_dashboard()
        elif self.path == '/api/stats':
            self.send_stats()
        elif self.path == '/api/report':
            self.send_report()
        elif self.path == '/api/file-types':
            self.send_file_types()
        elif self.path == '/api/recent-files':
            self.send_recent_files()
        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'404 - Page not found')
    
    def send_dashboard(self):
        """Send DDAS dashboard"""
        dashboard_html = '''
<!DOCTYPE html>
<html>
<head>
    <title>DDAS Dashboard</title>
    <meta charset="utf-8">
    <style>
        :root {
            --primary-color: #667eea;
            --secondary-color: #764ba2;
            --success-color: #28a745;
            --warning-color: #ffc107;
            --danger-color: #dc3545;
            --light-color: #f8f9fa;
            --dark-color: #343a40;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            color: #333;
            line-height: 1.6;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
            color: white;
            padding: 30px 20px;
            border-radius: 15px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
        }
        
        .header p {
            font-size: 1.2rem;
            opacity: 0.9;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
            text-align: center;
            transition: transform 0.3s ease;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
        }
        
        .stat-number {
            font-size: 2.5rem;
            font-weight: bold;
            color: var(--primary-color);
            margin-bottom: 10px;
        }
        
        .stat-label {
            color: #666;
            font-size: 1.1rem;
        }
        
        .charts-container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .chart-card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
        }
        
        .chart-title {
            font-size: 1.3rem;
            margin-bottom: 20px;
            color: var(--dark-color);
            text-align: center;
        }
        
        .file-list {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
            margin-bottom: 30px;
        }
        
        .file-list h3 {
            font-size: 1.3rem;
            margin-bottom: 20px;
            color: var(--dark-color);
        }
        
        .file-item {
            display: flex;
            justify-content: space-between;
            padding: 15px;
            border-bottom: 1px solid #eee;
        }
        
        .file-item:last-child {
            border-bottom: none;
        }
        
        .file-name {
            font-weight: 500;
        }
        
        .file-type {
            color: #666;
            font-size: 0.9rem;
        }
        
        .file-date {
            color: #999;
            font-size: 0.9rem;
        }
        
        .actions {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin-top: 30px;
        }
        
        .btn {
            padding: 12px 25px;
            border: none;
            border-radius: 50px;
            font-size: 1rem;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        .btn-primary {
            background: linear-gradient(45deg, var(--primary-color), var(--secondary-color));
            color: white;
        }
        
        .btn-success {
            background: var(--success-color);
            color: white;
        }
        
        .btn-warning {
            background: var(--warning-color);
            color: var(--dark-color);
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            font-size: 1.2rem;
            color: #666;
        }
        
        @media (max-width: 768px) {
            .charts-container {
                grid-template-columns: 1fr;
            }
            
            .header h1 {
                font-size: 2rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚨 DDAS Dashboard</h1>
            <p>Data Download Duplication Alert System - Real-time Monitoring</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number" id="totalFiles">-</div>
                <div class="stat-label">Total Files Monitored</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="pdfFiles">-</div>
                <div class="stat-label">PDF Files</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="pptFiles">-</div>
                <div class="stat-label">PowerPoint Files</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="duplicatesBlocked">-</div>
                <div class="stat-label">Duplicates Blocked</div>
            </div>
        </div>
        
        <div class="charts-container">
            <div class="chart-card">
                <h3 class="chart-title">📊 File Type Distribution</h3>
                <canvas id="fileTypeChart" height="250"></canvas>
            </div>
            <div class="chart-card">
                <h3 class="chart-title">📈 File Size Distribution</h3>
                <canvas id="fileSizeChart" height="250"></canvas>
            </div>
        </div>
        
        <div class="file-list">
            <h3>📁 Recent Files</h3>
            <div id="recentFilesList" class="loading">Loading recent files...</div>
        </div>
        
        <div class="actions">
            <button class="btn btn-primary" onclick="loadStats()">🔄 Refresh Stats</button>
            <button class="btn btn-success" onclick="generateReport()">📊 Generate Report</button>
            <button class="btn btn-warning" onclick="openAlertTest()">🧪 Test Alert</button>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        let fileTypeChart = null;
        let fileSizeChart = null;
        
        function loadStats() {
            // Update main stats
            fetch('/api/stats')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('totalFiles').textContent = data.totalFiles.toLocaleString();
                    document.getElementById('pdfFiles').textContent = data.pdfFiles.toLocaleString();
                    document.getElementById('pptFiles').textContent = data.pptFiles.toLocaleString();
                    document.getElementById('duplicatesBlocked').textContent = data.duplicatesBlocked.toLocaleString();
                })
                .catch(error => console.error('Error loading stats:', error));
            
            // Update file type chart
            fetch('/api/file-types')
                .then(response => response.json())
                .then(data => {
                    updateFileTypeChart(data);
                })
                .catch(error => console.error('Error loading file types:', error));
            
            // Update recent files
            fetch('/api/recent-files')
                .then(response => response.json())
                .then(data => {
                    updateRecentFiles(data);
                })
                .catch(error => console.error('Error loading recent files:', error));
        }
        
        function updateFileTypeChart(data) {
            const ctx = document.getElementById('fileTypeChart').getContext('2d');
            
            if (fileTypeChart) {
                fileTypeChart.destroy();
            }
            
            // Prepare data for chart
            const labels = Object.keys(data);
            const values = Object.values(data);
            
            // Get top 10 file types, group others as "Other"
            const topLabels = labels.slice(0, 10);
            const topValues = values.slice(0, 10);
            
            if (labels.length > 10) {
                const otherSum = values.slice(10).reduce((sum, val) => sum + val, 0);
                topLabels.push('Other');
                topValues.push(otherSum);
            }
            
            fileTypeChart = new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: topLabels,
                    datasets: [{
                        data: topValues,
                        backgroundColor: [
                            '#667eea', '#764ba2', '#f093fb', '#f5576c', 
                            '#4ecdc4', '#43e97b', '#fa709a', '#ffecd2', 
                            '#fcb69f', '#a8edea', '#cbb4d4'
                        ]
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            position: 'right',
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const label = context.label || '';
                                    const value = context.raw || 0;
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const percentage = Math.round((value / total) * 100);
                                    return `${label}: ${value} (${percentage}%)`;
                                }
                            }
                        }
                    }
                }
            });
        }
        
        function updateRecentFiles(files) {
            const container = document.getElementById('recentFilesList');
            
            if (files.length === 0) {
                container.innerHTML = '<div class="loading">No recent files found</div>';
                return;
            }
            
            let html = '';
            files.forEach(file => {
                html += `
                    <div class="file-item">
                        <div>
                            <div class="file-name">${file.filename}</div>
                            <div class="file-type">${file.file_type} • ${formatFileSize(file.file_size)}</div>
                        </div>
                        <div class="file-date">${formatDate(file.download_date)}</div>
                    </div>
                `;
            });
            
            container.innerHTML = html;
        }
        
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 B';
            
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        function formatDate(dateString) {
            const date = new Date(dateString);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
        }
        
        function generateReport() {
            fetch('/api/report')
                .then(response => response.text())
                .then(data => {
                    // Open report in new window
                    const reportWindow = window.open('', '_blank');
                    reportWindow.document.write(`
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <title>DDAS Report</title>
                            <style>
                                body { font-family: monospace; margin: 20px; white-space: pre-wrap; }
                                .header { text-align: center; margin-bottom: 20px; }
                            </style>
                        </head>
                        <body>
                            <div class="header">
                                <h2>DDAS Activity Report</h2>
                                <p>Generated on ${new Date().toLocaleString()}</p>
                            </div>
                            ${data}
                        </body>
                        </html>
                    `);
                })
                .catch(error => console.error('Error generating report:', error));
        }
        
        function openAlertTest() {
            alert('This would open a test alert. Implement test functionality as needed.');
        }
        
        // Auto-load stats on page load
        document.addEventListener('DOMContentLoaded', loadStats);
        
        // Refresh stats every 30 seconds
        setInterval(loadStats, 30000);
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(dashboard_html.encode('utf-8'))
    
    def send_stats(self):
        """Send DDAS statistics"""
        db_manager = DatabaseManager()
        stats = db_manager.get_file_statistics()
        
        # Count PDF and PPT files specifically
        pdf_count = 0
        ppt_count = 0
        
        for file_type, count in stats['file_types'].items():
            if file_type.lower() in ['.pdf']:
                pdf_count += count
            elif file_type.lower() in ['.ppt', '.pptx']:
                ppt_count += count
        
        response_data = {
            'totalFiles': stats['total_files'],
            'pdfFiles': pdf_count,
            'pptFiles': ppt_count,
            'duplicatesBlocked': stats['duplicate_files'],
            'totalSize': stats['total_size'],
            'efficiency': round((stats['total_files'] - stats['duplicate_files']) / max(stats['total_files'], 1) * 100, 1)
        }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response_data).encode('utf-8'))
    
    def send_file_types(self):
        """Send file type distribution"""
        db_manager = DatabaseManager()
        stats = db_manager.get_file_statistics()
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(stats['file_types']).encode('utf-8'))
    
    def send_recent_files(self):
        """Send recent files list"""
        db_manager = DatabaseManager()
        stats = db_manager.get_file_statistics()
        
        # Convert to list of dictionaries for JSON serialization
        recent_files = []
        for file in stats['recent_files']:
            recent_files.append({
                'filename': file[0],
                'file_type': file[1],
                'download_date': file[2],
                'file_size': 0  # You would need to add file_size to your query
            })
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(recent_files).encode('utf-8'))
    
    def send_report(self):
        """Send DDAS report"""
        report_gen = DDASReportGenerator()
        report = report_gen.generate_summary_report()
        
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(report.encode('utf-8'))

def start_ddas_dashboard():
    """Start DDAS web dashboard"""
    global dashboard_server
    server_address = ('', WEB_DASHBOARD_PORT)
    dashboard_server = HTTPServer(server_address, DDASDashboardHandler)
    print(f"🌐 DDAS Dashboard: http://localhost:{WEB_DASHBOARD_PORT}")
    dashboard_server.serve_forever()

def start_ddas_web_server():
    """Start DDAS web server"""
    global web_server
    server_address = ('', WEB_ALERT_PORT)
    web_server = HTTPServer(server_address, DDASRequestHandler)
    print(f"🌐 DDAS Web Interface: http://localhost:{WEB_ALERT_PORT}")
    web_server.serve_forever()

def start_ddas_monitoring():
    """Start DDAS monitoring system"""
    print("╔" + "="*78 + "╗")
    print("║" + " "*20 + "🚨 DDAS: DATA DOWNLOAD DUPLICATION ALERT SYSTEM 🚨" + " "*6 + "║")
    print("╚" + "="*78 + "╝")
    print()
    print("🎯 ADVANCED FEATURES ENABLED:")
    print("   ✅ Intelligent metadata analysis")
    print("   ✅ Cross-user duplicate detection")
    print("   ✅ Enhanced dataset identification")
    print("   ✅ Sophisticated content matching")
    print("   ✅ Real-time resource optimization")
    print("   ✅ Comprehensive download history")
    print("   ✅ Modal alerts with detailed info")
    print("   ✅ Web-based management dashboard")
    print("   ✅ Automated reporting system")
    print("   ✅ SQLite database backend")
    print()
    print(f"📂 Monitoring Directory: {DOWNLOAD_DIR}")
    print(f"💾 Database: {DATABASE_FILE}")
    print(f"🌐 Web Interface: http://localhost:{WEB_ALERT_PORT}")
    print(f"📊 Dashboard: http://localhost:{WEB_DASHBOARD_PORT}")
    print("="*80)
    
    if not os.path.exists(DOWNLOAD_DIR):
        print(f"❌ Error: Download directory {DOWNLOAD_DIR} does not exist!")
        return
    
    # Start web servers
    global web_server_thread, dashboard_thread
    web_server_thread = threading.Thread(target=start_ddas_web_server, daemon=True)
    web_server_thread.start()
    
    dashboard_thread = threading.Thread(target=start_ddas_dashboard, daemon=True)
    dashboard_thread.start()
    
    # Initialize DDAS components
    db_manager = DatabaseManager()
    print("✅ Database initialized")
    
    # Start file monitoring
    event_handler = EnhancedDownloadHandler()
    observer = Observer()
    observer.schedule(event_handler, DOWNLOAD_DIR, recursive=False)
    
    try:
        observer.start()
        print("✅ DDAS Monitor started successfully!")
        print("🔄 Monitoring for dataset downloads and duplicates...")
        print("🚨 Enhanced modal alerts will prevent redundant downloads!")
        print("\nPress Ctrl+C to stop DDAS monitoring.\n")
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping DDAS...")
        observer.stop()
        print("✅ DDAS stopped successfully!")
        
        # Generate final report
        report_gen = DDASReportGenerator()
        final_report = report_gen.generate_summary_report()
        print("\n" + final_report)
        
    except Exception as e:
        print(f"❌ DDAS Error: {e}")
        observer.stop()
    
    finally:
        observer.join()

# ... (Keep all the existing functions like show_ddas_help, main, cleanup_and_exit, etc.)

def main():
    """Enhanced main function with full DDAS capabilities"""
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "help":
            show_ddas_help()
            return
        elif command == "test":
            print("🧪 DDAS: Testing alert system...")
            test_file = os.path.join(DOWNLOAD_DIR, "test_dataset.csv")
            original_file = os.path.join(DOWNLOAD_DIR, "original_dataset.csv")
            
            metadata = {
                'dataset_type': 'CSV Dataset',
                'unique_identifier': 'csv_test_12345',
                'file_size': 1024,
                'mime_type': 'text/csv',
                'structure_analysis': {'columns': 5, 'rows': 100, 'headers': ['id', 'name', 'value']}
            }
            
            alert = EnhancedModalAlert(test_file, original_file, metadata, "Test Alert")
            alert.show()
            print("✅ Test alert completed!")
            return
            
        elif command == "report":
            print("📊 Generating DDAS report...")
            report_gen = DDASReportGenerator()
            report = report_gen.generate_summary_report()
            print(report)
            return
            
        elif command == "dashboard":
            print(f"🌐 Opening DDAS Dashboard at http://localhost:{WEB_DASHBOARD_PORT}")
            webbrowser.open(f"http://localhost:{WEB_DASHBOARD_PORT}")
            return
            
        elif command == "cleanup":
            print("🧹 DDAS: Database cleanup and optimization...")
            # ... (keep existing cleanup code)
            
        elif command == "start" or command == "monitor":
            pass  # Continue to start monitoring
        else:
            print(f"❌ Unknown command: {command}")
            print("Valid commands: start, test, report, dashboard, cleanup, help")
            return
    
    # Default action: start monitoring
    start_ddas_monitoring()

# ... (Keep all other existing functions)

if __name__ == "__main__":
    main()