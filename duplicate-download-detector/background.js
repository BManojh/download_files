// Store for tracking downloads
let downloadDatabase = {};
let isLoaded = false;
let isLoading = false;
const pendingChecks = new Map(); // Maps downloadId -> timeoutId
const bypassCheck = new Map(); // Maps downloadId -> boolean

// Load existing database on startup
chrome.runtime.onStartup.addListener(loadDatabase);
chrome.runtime.onInstalled.addListener(loadDatabase);

async function loadDatabase() {
    if (isLoading) return;
    isLoading = true;

    try {
        const result = await chrome.storage.local.get(['downloadDatabase']);
        downloadDatabase = result.downloadDatabase || {};
        isLoaded = true;
        console.log('Database loaded:', Object.keys(downloadDatabase).length, 'files');
        console.log('Existing files in database:');
        Object.entries(downloadDatabase).forEach(([id, file]) => {
            console.log(` ID ${id}: "${file.name}" (${file.size} bytes) - ${file.date}`);
        });
    } catch (error) {
        console.error('Error loading database:', error);
        downloadDatabase = {};
        isLoaded = true;
    } finally {
        isLoading = false;
    }
}

// Monitor download creation — trigger check when filename is assigned
chrome.downloads.onCreated.addListener(async (downloadItem) => {
    console.log('Download created:', downloadItem);

    if (!isLoaded) {
        await loadDatabase();
    }

    // Check if this download should bypass the duplicate check
    if (bypassCheck.has(downloadItem.id)) {
        console.log('Bypassing duplicate check for download:', downloadItem.id);
        bypassCheck.delete(downloadItem.id);
        return;
    }

    // Set a fallback timeout in case filename never appears via onChanged
    const timeoutId = setTimeout(async () => {
        if (pendingChecks.has(downloadItem.id)) {
            console.warn(`Fallback check for download ${downloadItem.id}: filename still not set.`);
            const downloads = await chrome.downloads.search({
                id: downloadItem.id
            });
            if (downloads.length > 0 && downloads[0].filename) {
                await handleNewDownload(downloadItem.id, downloads[0].filename, downloads[0].totalBytes);
            }
            pendingChecks.delete(downloadItem.id);
        }
    }, 3000); // 3 seconds fallback

    pendingChecks.set(downloadItem.id, timeoutId);
});

async function handleNewDownload(downloadId, filename, size) {
    const fileName = getFileName(filename);
    if (!fileName || fileName.includes('CANCELLED_DUPLICATE')) {
        return;
    }

    console.log('Checking for duplicate:', fileName);

    // Clean up pending check
    if (pendingChecks.has(downloadId)) {
        clearTimeout(pendingChecks.get(downloadId));
        pendingChecks.delete(downloadId);
    }

    // Step 1: Cancel the download to allow for hashing
    try {
        await chrome.downloads.cancel(downloadId);
        console.log('Download cancelled for hash check');
    } catch (e) {
        console.error('Could not cancel download:', e);
        return;
    }

    // Step 2: Use native messaging to get the file hash
    try {
        const port = chrome.runtime.connectNative('com.notification.duplicate_detector');
        port.onMessage.addListener(async (response) => {
            console.log('Received hash from native app:', response);
            if (response.hash) {
                // Store the hash temporarily to be used later by registerDownload
                await chrome.storage.local.set({
                    [`downloadHash_${downloadId}`]: response.hash
                });

                const existingFile = findDuplicateByHash(response.hash, fileName);
                if (existingFile) {
                    console.log('DUPLICATE DETECTED by hash:', fileName);
                    chrome.notifications.create(`duplicate_${downloadId}`, {
                        type: 'basic',
                        iconUrl: 'icons/icon48.png',
                        title: 'Duplicate Download Blocked!',
                        message: `"${fileName}" was already downloaded on ${existingFile.date}`,
                        buttons: [{
                            title: 'View Files'
                        }, {
                            title: 'Download Anyway'
                        }]
                    });
                    const downloads = await chrome.downloads.search({
                        id: downloadId
                    });
                    const url = downloads.length > 0 ? downloads[0].url : '';
                    const pendingKey = `pendingDownload_${downloadId}`;
                    await chrome.storage.local.set({
                        [pendingKey]: {
                            url,
                            filename: fileName,
                            originalId: downloadId
                        }
                    });
                } else {
                    console.log('No duplicate found by hash. Re-initiating download.');
                    // Mark this download to bypass future checks
                    bypassCheck.set(downloadId, true);
                    const downloads = await chrome.downloads.search({
                        id: downloadId
                    });
                    if (downloads.length > 0) {
                        // Re-initiate the download. The bypassCheck map will prevent a new check.
                        await chrome.downloads.download({
                            url: downloads[0].url
                        });
                    }
                }
            }
        });

        port.postMessage({
            filePath: filename
        });
    } catch (e) {
        console.error('Error connecting to native app:', e);
        // Fallback: If native messaging fails, re-initiate the download without the hash check
        const downloads = await chrome.downloads.search({
            id: downloadId
        });
        if (downloads.length > 0) {
            bypassCheck.set(downloadId, true);
            await chrome.downloads.download({
                url: downloads[0].url
            });
        }
    }
}

// Monitor download changes — filename assignment and completion
chrome.downloads.onChanged.addListener(async (delta) => {
    console.log('Download changed:', delta);

    if (delta.filename?.current && pendingChecks.has(delta.id)) {
        const download = (await chrome.downloads.search({
            id: delta.id
        }))[0];
        await handleNewDownload(delta.id, delta.filename.current, download.totalBytes);
    }

    // Register completed downloads
    if (delta.state?.current === 'complete') {
        await registerDownload(delta.id);
    }
});

function getFileName(filepath) {
    if (!filepath) return '';

    const parts = filepath.split(/[/\\]/);
    let fileName = parts[parts.length - 1] || filepath;

    try {
        fileName = decodeURIComponent(fileName);
    } catch (e) {
        console.log('Could not decode filename:', fileName);
    }

    return fileName;
}

function findDuplicateByHash(fileHash, fileName) {
    for (let id in downloadDatabase) {
        const file = downloadDatabase[id];
        if (file.hash && file.hash === fileHash) {
            console.log('Found exact hash match!');
            return file;
        }
    }
    // Fallback to filename comparison if no hash match is found
    return findDuplicateByName(fileName, 0);
}

function findDuplicateByName(fileName, fileSize) {
    if (!fileName) return null;

    const normalizedName = fileName.toLowerCase().trim()
        .replace(/\s+/g, ' ')
        .replace(/[^\w\s.-]/g, '');

    console.log('Looking for duplicates of normalized name:', normalizedName);

    for (let id in downloadDatabase) {
        const file = downloadDatabase[id];
        if (!file.name) continue;

        const existingName = file.name.toLowerCase().trim()
            .replace(/\s+/g, ' ')
            .replace(/[^\w\s.-]/g, '');

        console.log('Comparing with existing normalized file:', existingName);

        if (existingName === normalizedName) {
            console.log('Found exact name match!');
            if (fileSize > 0 && file.size > 0) {
                const sizeDifference = Math.abs(file.size - fileSize);
                const sizeThreshold = Math.max(1024, Math.min(file.size, fileSize) * 0.1);
                if (sizeDifference <= sizeThreshold) {
                    console.log('Size match confirmed duplicate');
                    return file;
                } else {
                    console.log('Size mismatch, not a duplicate');
                }
            } else {
                console.log('No size info, matching by name');
                return file;
            }
        }
        const similarityThreshold = 0.8;
        const similarity = calculateSimilarity(existingName, normalizedName);
        if (similarity >= similarityThreshold) {
            console.log(`Found similar filename (${Math.round(similarity * 100)}% match)`);
            return file;
        }
    }
    console.log('No duplicate found');
    return null;
}

function calculateSimilarity(str1, str2) {
    const longer = str1.length > str2.length ? str1 : str2;
    const shorter = str1.length > str2.length ? str2 : str1;

    if (longer.length === 0) return 1.0;

    return (longer.length - editDistance(longer, shorter)) / parseFloat(longer.length);
}

function editDistance(s1, s2) {
    s1 = s1.toLowerCase();
    s2 = s2.toLowerCase();
    const costs = [];
    for (let i = 0; i <= s1.length; i++) {
        let lastValue = i;
        for (let j = 0; j <= s2.length; j++) {
            if (i === 0) {
                costs[j] = j;
            } else {
                if (j > 0) {
                    let newValue = costs[j - 1];
                    if (s1.charAt(i - 1) !== s2.charAt(j - 1)) {
                        newValue = Math.min(Math.min(newValue, lastValue), costs[j]) + 1;
                    }
                    costs[j - 1] = lastValue;
                    lastValue = newValue;
                }
            }
        }
        if (i > 0) costs[s2.length] = lastValue;
    }
    return costs[s2.length];
}

async function registerDownload(downloadId) {
    try {
        const downloads = await chrome.downloads.search({
            id: downloadId
        });
        if (downloads.length === 0) return;

        const download = downloads[0];
        const fileName = getFileName(download.filename);

        if (download.state !== 'complete' || download.error || fileName.includes('CANCELLED_DUPLICATE')) {
            return;
        }

        // Retrieve the hash from temporary storage
        const result = await chrome.storage.local.get([`downloadHash_${downloadId}`]);
        const fileHash = result[`downloadHash_${downloadId}`] || '';

        downloadDatabase[downloadId] = {
            name: fileName,
            size: download.totalBytes || download.fileSize || 0,
            path: download.filename,
            url: download.url,
            date: new Date().toLocaleDateString(),
            time: new Date().toLocaleTimeString(),
            timestamp: Date.now(),
            hash: fileHash
        };

        await chrome.storage.local.set({
            downloadDatabase
        });
        // Clean up the temporary storage
        await chrome.storage.local.remove([`downloadHash_${downloadId}`]);

        console.log('Registered download:', fileName, 'Total files:', Object.keys(downloadDatabase).length);
        updateBadge();
    } catch (error) {
        console.error('Error registering download:', error);
    }
}

function updateBadge() {
    const count = Object.keys(downloadDatabase).length;
    if (count > 0) {
        chrome.action.setBadgeText({
            text: count.toString()
        });
        chrome.action.setBadgeBackgroundColor({
            color: '#4285f4'
        });
    } else {
        chrome.action.setBadgeText({
            text: ''
        });
    }
}

// Handle notification button clicks
chrome.notifications.onButtonClicked.addListener(async (notificationId, buttonIndex) => {
    try {
        console.log('Notification button clicked:', notificationId, buttonIndex);
        if (buttonIndex === 0) {
            chrome.action.openPopup();
        } else if (buttonIndex === 1) {
            const downloadId = notificationId.replace('duplicate_', '');
            const pendingKey = `pendingDownload_${downloadId}`;
            const result = await chrome.storage.local.get([pendingKey]);

            if (result[pendingKey]) {
                console.log('Retrying download:', result[pendingKey]);
                bypassCheck.set(result[pendingKey].originalId, true);
                await chrome.downloads.download({
                    url: result[pendingKey].url,
                    filename: result[pendingKey].filename
                });
                await chrome.storage.local.remove([pendingKey]);
            }
        }
        chrome.notifications.clear(notificationId);
    } catch (error) {
        console.error('Error handling notification click:', error);
    }
});

// Initialize on script load
loadDatabase();