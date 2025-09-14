// Store for tracking downloads
let downloadDatabase = {};

// Load existing database on startup
chrome.runtime.onStartup.addListener(loadDatabase);
chrome.runtime.onInstalled.addListener(loadDatabase);

async function loadDatabase() {
  const result = await chrome.storage.local.get(['downloadDatabase']);
  downloadDatabase = result.downloadDatabase || {};
}

// Listen for download events
chrome.downloads.onCreated.addListener(async (downloadItem) => {
  await checkForDuplicate(downloadItem);
});

chrome.downloads.onChanged.addListener(async (delta) => {
  if (delta.state && delta.state.current === 'complete') {
    await registerDownload(delta.id);
  }
});

async function checkForDuplicate(downloadItem) {
  const fileName = downloadItem.filename.split('/').pop();
  const fileSize = downloadItem.totalBytes;
  
  // Check if we have this file already
  const existingFile = findDuplicate(fileName, fileSize);
  
  if (existingFile) {
    // Cancel the download
    chrome.downloads.cancel(downloadItem.id);
    
    // Show notification
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon48.png',
      title: 'Duplicate Download Detected!',
      message: `File "${fileName}" was already downloaded on ${existingFile.date}`,
      buttons: [
        { title: 'View Files' },
        { title: 'Download Anyway' }
      ]
    });
    
    // Store the cancelled download info for potential retry
    chrome.storage.local.set({
      pendingDownload: {
        url: downloadItem.url,
        filename: fileName,
        originalId: downloadItem.id
      }
    });
  }
}

function findDuplicate(fileName, fileSize) {
  for (let id in downloadDatabase) {
    const file = downloadDatabase[id];
    if (file.name === fileName && Math.abs(file.size - fileSize) < 1024) {
      return file;
    }
  }
  return null;
}

async function registerDownload(downloadId) {
  try {
    const downloads = await chrome.downloads.search({ id: downloadId });
    if (downloads.length > 0) {
      const download = downloads[0];
      const fileName = download.filename.split('/').pop();
      
      // Add to our database
      downloadDatabase[downloadId] = {
        name: fileName,
        size: download.totalBytes,
        path: download.filename,
        url: download.url,
        date: new Date().toLocaleDateString(),
        time: new Date().toLocaleTimeString()
      };
      
      // Save to chrome storage
      await chrome.storage.local.set({ downloadDatabase });
      
      // Update badge
      updateBadge();
    }
  } catch (error) {
    console.error('Error registering download:', error);
  }
}

function updateBadge() {
  const count = Object.keys(downloadDatabase).length;
  chrome.action.setBadgeText({
    text: count > 0 ? count.toString() : ''
  });
  chrome.action.setBadgeBackgroundColor({ color: '#4285f4' });
}

// Handle notification button clicks
chrome.notifications.onButtonClicked.addListener(async (notificationId, buttonIndex) => {
  if (buttonIndex === 0) {
    // View Files - open popup
    chrome.action.openPopup();
  } else if (buttonIndex === 1) {
    // Download Anyway
    const result = await chrome.storage.local.get(['pendingDownload']);
    if (result.pendingDownload) {
      chrome.downloads.download({
        url: result.pendingDownload.url,
        filename: result.pendingDownload.filename
      });
      chrome.storage.local.remove(['pendingDownload']);
    }
  }
  chrome.notifications.clear(notificationId);
});