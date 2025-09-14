document.addEventListener('DOMContentLoaded', async function() {
  await loadAndDisplayFiles();
  setupEventListeners();
});

let allFiles = {};

async function loadAndDisplayFiles() {
  try {
    const result = await chrome.storage.local.get(['downloadDatabase']);
    allFiles = result.downloadDatabase || {};
    displayFiles(allFiles);
    updateFileCount();
  } catch (error) {
    console.error('Error loading files:', error);
  }
}

function displayFiles(files) {
  const fileList = document.getElementById('fileList');
  const fileEntries = Object.entries(files);
  
  if (fileEntries.length === 0) {
    fileList.innerHTML = '<div class="no-files">No files tracked yet</div>';
    return;
  }
  
  // Sort by date (newest first)
  fileEntries.sort((a, b) => {
    const dateA = new Date(a[1].date + ' ' + a[1].time);
    const dateB = new Date(b[1].date + ' ' + b[1].time);
    return dateB - dateA;
  });
  
  fileList.innerHTML = fileEntries.map(([id, file]) => `
    <div class="file-item" data-id="${id}">
      <div class="file-name">${file.name}</div>
      <div class="file-details">
        <span>📦 ${formatFileSize(file.size)}</span>
        <span>📅 ${file.date} ${file.time}</span>
        <button class="delete-btn" onclick="deleteFile('${id}')">🗑️</button>
      </div>
      <div class="file-path">${file.path}</div>
    </div>
  `).join('');
}

function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function updateFileCount() {
  const count = Object.keys(allFiles).length;
  document.getElementById('fileCount').textContent = `${count} files tracked`;
}

function setupEventListeners() {
  // Search functionality
  document.getElementById('searchBox').addEventListener('input', function(e) {
    const searchTerm = e.target.value.toLowerCase();
    const filteredFiles = {};
    
    for (let id in allFiles) {
      const file = allFiles[id];
      if (file.name.toLowerCase().includes(searchTerm) || 
          file.path.toLowerCase().includes(searchTerm)) {
        filteredFiles[id] = file;
      }
    }
    
    displayFiles(filteredFiles);
  });
  
  // Clear all files
  document.getElementById('clearAllBtn').addEventListener('click', async function() {
    if (confirm('Are you sure you want to clear all tracked files?')) {
      await chrome.storage.local.set({ downloadDatabase: {} });
      allFiles = {};
      displayFiles(allFiles);
      updateFileCount();
      
      // Clear badge
      chrome.action.setBadgeText({ text: '' });
    }
  });
  
  // Export file list
  document.getElementById('exportBtn').addEventListener('click', function() {
    exportFileList();
  });
}

async function deleteFile(fileId) {
  if (confirm('Remove this file from tracking?')) {
    delete allFiles[fileId];
    await chrome.storage.local.set({ downloadDatabase: allFiles });
    displayFiles(allFiles);
    updateFileCount();
    
    // Update badge
    const count = Object.keys(allFiles).length;
    chrome.action.setBadgeText({
      text: count > 0 ? count.toString() : ''
    });
  }
}

function exportFileList() {
  const fileEntries = Object.entries(allFiles);
  const csvContent = "data:text/csv;charset=utf-8," + 
    "File Name,Size,Download Date,Time,Path,URL\n" +
    fileEntries.map(([id, file]) => 
      `"${file.name}","${formatFileSize(file.size)}","${file.date}","${file.time}","${file.path}","${file.url}"`
    ).join("\n");
  
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", "downloaded_files.csv");
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}