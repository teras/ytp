// YouTube Web App

const searchInput = document.getElementById('search-input');
const searchBtn = document.getElementById('search-btn');
const videoGrid = document.getElementById('video-grid');
const playerContainer = document.getElementById('player-container');
const videoPlayer = document.getElementById('video-player');
const videoTitle = document.getElementById('video-title');
const videoMeta = document.getElementById('video-meta');
const closePlayerBtn = document.getElementById('close-player');
const noResults = document.getElementById('no-results');
const loadMoreContainer = document.getElementById('load-more-container');
const cancelDownloadBtn = document.getElementById('cancel-download-btn');
const progressRingFill = document.querySelector('.progress-ring-fill');
const downloadPill = document.getElementById('download-pill');
const downloadAction = document.getElementById('download-action');
const downloadGear = document.getElementById('download-gear');
const downloadQualityMenu = document.getElementById('download-quality-menu');

let maxDownloadQuality = 1080; // Default max quality setting

let currentQuery = '';
let currentCount = 10;
const BATCH_SIZE = 10;
let progressInterval = null;
let isLoadingMore = false;
let hasMoreResults = true;
let currentVideoId = null;
let autoDownloadThreshold = 15 * 60; // 15 minutes in seconds (default)
let loadedVideoIds = new Set(); // Track already loaded videos

// Settings dropdown
const settingsBtn = document.getElementById('settings-btn');
const settingsMenu = document.getElementById('settings-menu');

settingsBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    settingsMenu.classList.toggle('show');
});

// Close dropdowns when clicking outside
document.addEventListener('click', () => {
    settingsMenu.classList.remove('show');
    downloadQualityMenu.classList.add('hidden');
});

settingsMenu.addEventListener('click', (e) => {
    e.stopPropagation(); // Keep open when clicking inside
});

// Auto-download settings chips
const autoDlChips = document.getElementById('auto-dl-chips');
autoDlChips.addEventListener('click', (e) => {
    if (e.target.classList.contains('chip')) {
        // Update active state
        autoDlChips.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
        e.target.classList.add('active');
        // Update threshold (value is in minutes, convert to seconds)
        const minutes = parseInt(e.target.dataset.value);
        autoDownloadThreshold = minutes * 60;
        // Save to localStorage
        localStorage.setItem('autoDownloadMinutes', minutes);
    }
});

// Load saved auto-download setting
const savedMinutes = localStorage.getItem('autoDownloadMinutes');
if (savedMinutes !== null) {
    autoDownloadThreshold = parseInt(savedMinutes) * 60;
    autoDlChips.querySelectorAll('.chip').forEach(c => {
        c.classList.toggle('active', c.dataset.value === savedMinutes);
    });
}

// Max quality setting chips
const qualityChips = document.getElementById('quality-chips');
qualityChips.addEventListener('click', (e) => {
    if (e.target.classList.contains('chip')) {
        qualityChips.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
        e.target.classList.add('active');
        maxDownloadQuality = parseInt(e.target.dataset.value);
        localStorage.setItem('maxDownloadQuality', maxDownloadQuality);
    }
});

// Load saved quality setting
const savedQuality = localStorage.getItem('maxDownloadQuality');
if (savedQuality !== null) {
    maxDownloadQuality = parseInt(savedQuality);
    qualityChips.querySelectorAll('.chip').forEach(c => {
        c.classList.toggle('active', c.dataset.value === savedQuality);
    });
}

// Infinite scroll - load more when sentinel becomes visible
const loadMoreObserver = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && !isLoadingMore && hasMoreResults && currentQuery) {
        loadMore();
    }
}, { threshold: 0.1 });

async function searchVideos(query) {
    if (!query.trim()) return;

    currentQuery = query;
    currentCount = BATCH_SIZE;
    hasMoreResults = true;
    loadedVideoIds.clear();

    videoGrid.innerHTML = '';
    noResults.classList.add('hidden');
    showLoadingCard(true);

    await fetchVideos(true);

    // Start observing for infinite scroll
    loadMoreObserver.observe(loadMoreContainer);
}

async function loadMore() {
    if (isLoadingMore || !hasMoreResults) return;

    isLoadingMore = true;
    currentCount += BATCH_SIZE;
    showLoadingCard(true);
    await fetchVideos(false);
    isLoadingMore = false;
}

function showLoadingCard(show) {
    const existingLoader = document.getElementById('loading-card');
    if (existingLoader) existingLoader.remove();

    if (show) {
        const loadingCard = document.createElement('div');
        loadingCard.id = 'loading-card';
        loadingCard.className = 'video-card loading-card';
        loadingCard.innerHTML = `
            <div class="thumbnail-container">
                <div class="loading-spinner"></div>
            </div>
            <div class="video-info">
                <div class="skeleton-text"></div>
                <div class="skeleton-text short"></div>
            </div>
        `;
        videoGrid.appendChild(loadingCard);
    }
}

async function fetchVideos(isNewSearch) {
    try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(currentQuery)}&count=${currentCount}`);
        const data = await response.json();

        if (!response.ok) {
            const msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
            throw new Error(msg || 'Search failed');
        }

        showLoadingCard(false);

        if (data.results.length === 0) {
            noResults.classList.remove('hidden');
            hasMoreResults = false;
        } else {
            // Filter out already loaded videos
            const newVideos = data.results.filter(v => !loadedVideoIds.has(v.id));

            if (isNewSearch) {
                renderVideos(data.results);
                data.results.forEach(v => loadedVideoIds.add(v.id));
            } else {
                // Append only new videos
                appendVideos(newVideos);
                newVideos.forEach(v => loadedVideoIds.add(v.id));
            }

            // Check if we got fewer NEW results = no more results
            hasMoreResults = newVideos.length > 0;
            loadMoreContainer.classList.toggle('hidden', !hasMoreResults);
        }
    } catch (error) {
        showLoadingCard(false);
        videoGrid.innerHTML = `<p class="error">Error: ${error.message}</p>`;
        hasMoreResults = false;
    }
}

function createVideoCard(video) {
    return `<div class="video-card" data-id="${video.id}" data-title="${escapeAttr(video.title)}" data-channel="${escapeAttr(video.channel)}" data-duration="${video.duration}">
        <div class="thumbnail-container">
            <img src="${video.thumbnail}" alt="${escapeHtml(video.title)}" loading="lazy">
            <span class="duration">${video.duration_str}</span>
        </div>
        <div class="video-info">
            <h3 class="video-title">${escapeHtml(video.title)}</h3>
            <p class="channel">${escapeHtml(video.channel)}</p>
        </div>
    </div>`;
}

function attachCardListeners(container) {
    container.querySelectorAll('.video-card:not([data-attached])').forEach(card => {
        card.dataset.attached = 'true';
        card.addEventListener('click', () => playVideo(
            card.dataset.id,
            card.dataset.title,
            card.dataset.channel,
            parseInt(card.dataset.duration) || 0
        ));
    });
}

function renderVideos(videos) {
    videoGrid.innerHTML = videos.map(createVideoCard).join('');
    attachCardListeners(videoGrid);
}

function appendVideos(videos) {
    if (videos.length === 0) return;
    videoGrid.insertAdjacentHTML('beforeend', videos.map(createVideoCard).join(''));
    attachCardListeners(videoGrid);
}

let hlsPlayer = null;

async function playVideo(videoId, title, channel, duration) {
    // Stop any previous progress polling
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }

    // Destroy previous HLS player
    if (hlsPlayer) {
        hlsPlayer.destroy();
        hlsPlayer = null;
    }

    // Reset cancel flag for new video
    downloadCancelled = false;

    videoTitle.textContent = title || 'Loading...';
    videoMeta.textContent = channel || '';
    downloadPill.classList.add('hidden');
    downloadQualityMenu.classList.add('hidden');

    // Fetch extra info in background
    fetch(`/api/info/${videoId}`)
        .then(r => r.json())
        .then(info => {
            const parts = [info.channel || channel];
            if (info.upload_date) parts.push(`📅 ${info.upload_date}`);
            if (info.views) parts.push(`👁 ${info.views}`);
            if (info.likes) parts.push(`👍 ${info.likes}`);
            videoMeta.textContent = parts.join('  •  ');
        })
        .catch(() => {});
    playerContainer.classList.remove('hidden');

    // Store duration to set on video when metadata loads
    videoPlayer.dataset.expectedDuration = duration || 0;
    playerContainer.scrollIntoView({ behavior: 'smooth' });

    try {
        // Check if HD is already cached
        const response = await fetch(`/api/progress/${videoId}`);
        const data = await response.json();

        cancelDownloadBtn.classList.add('hidden');
        downloadPill.classList.add('hidden');

        if (data.status === 'ready') {
            // HD already cached - play from file
            videoPlayer.src = `/api/stream/${videoId}`;
            videoPlayer.play();
        } else {
            // Try HLS first (best quality), fallback to direct stream
            if (Hls.isSupported()) {
                hlsPlayer = new Hls();
                hlsPlayer.loadSource(`/api/hls/${videoId}`);
                hlsPlayer.attachMedia(videoPlayer);
                hlsPlayer.on(Hls.Events.MANIFEST_PARSED, () => {
                    videoPlayer.play();
                });
                hlsPlayer.on(Hls.Events.ERROR, (event, data) => {
                    if (data.fatal) {
                        console.log('HLS failed, falling back to direct stream');
                        hlsPlayer.destroy();
                        hlsPlayer = null;
                        videoPlayer.src = `/api/stream-live/${videoId}`;
                        videoPlayer.play();
                    }
                });
            } else {
                // Fallback for browsers without HLS support
                videoPlayer.src = `/api/stream-live/${videoId}`;
                videoPlayer.play();
            }

            // Store for later quality check
            currentVideoId = videoId;
            // Download check happens in loadedmetadata when we know actual quality
        }
    } catch (error) {
        videoTitle.textContent = 'Error: ' + error.message;
        cancelDownloadBtn.classList.add('hidden');
    }
}

function hidePlayer() {
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    if (hlsPlayer) {
        hlsPlayer.destroy();
        hlsPlayer = null;
    }
    playerContainer.classList.add('hidden');
    cancelDownloadBtn.classList.add('hidden');
    downloadPill.classList.add('hidden');
    downloadQualityMenu.classList.add('hidden');
    currentVideoId = null;
    videoPlayer.pause();
    videoPlayer.removeAttribute('src');
    videoPlayer.load();
}

const PROGRESS_CIRCUMFERENCE = 62.83; // 2 * PI * 10

function setProgress(percent) {
    const offset = PROGRESS_CIRCUMFERENCE - (percent / 100) * PROGRESS_CIRCUMFERENCE;
    progressRingFill.style.strokeDashoffset = offset;
}

function startHdDownload(videoId, quality = 0) {
    cancelDownloadBtn.classList.remove('hidden');
    downloadPill.classList.add('hidden');
    downloadQualityMenu.classList.add('hidden');
    setProgress(0);

    // Start HD download
    const url = quality ? `/api/play/${videoId}?quality=${quality}` : `/api/play/${videoId}`;
    fetch(url);

    // Poll for HD completion
    progressInterval = setInterval(async () => {
        try {
            const prog = await fetch(`/api/progress/${videoId}`);
            const progData = await prog.json();

            setProgress(progData.progress);

            if (progData.status === 'finished' || progData.status === 'ready') {
                clearInterval(progressInterval);
                progressInterval = null;
                setProgress(100);

                // Switch to HD
                const currentTime = videoPlayer.currentTime;
                const wasPlaying = !videoPlayer.paused;

                if (hlsPlayer) {
                    hlsPlayer.destroy();
                    hlsPlayer = null;
                }

                // Pause first, then switch source
                videoPlayer.pause();
                videoPlayer.src = `/api/stream/${videoId}`;

                // Wait for new source to load before seeking
                videoPlayer.onloadedmetadata = () => {
                    videoPlayer.currentTime = currentTime;
                    if (wasPlaying) videoPlayer.play();
                    videoPlayer.onloadedmetadata = null;
                };
                videoPlayer.load();

                setTimeout(() => cancelDownloadBtn.classList.add('hidden'), 800);
            } else if (progData.status === 'error' || progData.status === 'cancelled') {
                clearInterval(progressInterval);
                progressInterval = null;
                setTimeout(() => cancelDownloadBtn.classList.add('hidden'), 500);
            }
        } catch (e) {
            // Ignore progress errors
        }
    }, 500);
}

let availableQualities = []; // Store for current video
let selectedDownloadQuality = 0; // Currently selected quality for download

async function checkDownloadOffer(videoId, currentHeight) {
    try {
        const response = await fetch(`/api/formats/${videoId}`);
        const data = await response.json();

        // Filter to qualities BETTER than current streaming
        const betterOptions = data.options.filter(opt => opt.height > currentHeight);

        if (betterOptions.length > 0) {
            availableQualities = betterOptions;

            // Find the best quality that matches user's setting (or nearest available >= setting)
            let targetQuality = betterOptions.find(opt => opt.height >= maxDownloadQuality);
            if (!targetQuality) {
                // If no quality >= setting, use highest available
                targetQuality = betterOptions[betterOptions.length - 1];
            }
            selectedDownloadQuality = targetQuality.height;

            // Update download button text with size
            const sizeText = targetQuality.size_str ? ` (${targetQuality.size_str})` : '';
            downloadAction.textContent = `Download${sizeText}`;

            // Populate quality menu (highest first for dropdown)
            updateQualityMenu();

            // Show the pill button
            downloadPill.classList.remove('hidden');
        }
    } catch (e) {
        // Ignore errors
    }
}

function updateQualityMenu() {
    downloadQualityMenu.innerHTML = [...availableQualities].reverse().map(opt => {
        const sizeInfo = opt.size_str ? `<span class="size">${opt.size_str}</span>` : '';
        const selected = opt.height === selectedDownloadQuality ? ' selected' : '';
        return `<div class="quality-option${selected}" data-quality="${opt.height}">
            <span>${opt.label}</span>
            ${sizeInfo}
        </div>`;
    }).join('');

    // Add click handlers to quality options
    downloadQualityMenu.querySelectorAll('.quality-option').forEach(opt => {
        opt.addEventListener('click', () => {
            const quality = parseInt(opt.dataset.quality);
            selectedDownloadQuality = quality;
            const selected = availableQualities.find(q => q.height === quality);
            const sizeText = selected?.size_str ? ` (${selected.size_str})` : '';
            downloadAction.textContent = `Download${sizeText}`;
            updateQualityMenu(); // Update selection highlight
            downloadQualityMenu.classList.add('hidden');
        });
    });
}

// Download pill handlers
downloadAction.addEventListener('click', () => {
    if (currentVideoId && selectedDownloadQuality > 0) {
        startHdDownload(currentVideoId, selectedDownloadQuality);
    }
});

downloadGear.addEventListener('click', (e) => {
    e.stopPropagation();
    downloadQualityMenu.classList.toggle('hidden');
});

downloadQualityMenu.addEventListener('click', (e) => {
    e.stopPropagation();
});

let downloadCancelled = false;

cancelDownloadBtn.addEventListener('click', async () => {
    if (currentVideoId) {
        downloadCancelled = true;
        await fetch(`/api/cancel/${currentVideoId}`, { method: 'POST' });
        if (progressInterval) {
            clearInterval(progressInterval);
            progressInterval = null;
        }
        cancelDownloadBtn.classList.add('hidden');
        // Re-show download pill if we have quality options
        if (availableQualities.length > 0) {
            downloadPill.classList.remove('hidden');
        }
    }
});

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeAttr(text) {
    return text.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

searchBtn.addEventListener('click', () => searchVideos(searchInput.value));
searchInput.addEventListener('keypress', e => e.key === 'Enter' && searchVideos(searchInput.value));
closePlayerBtn.addEventListener('click', hidePlayer);

videoPlayer.addEventListener('error', () => {
    // Don't show errors to user - they're usually transient
    // Just log for debugging
    console.log('Video error:', videoPlayer.error?.message);
});

// Smart download check when metadata loads
videoPlayer.addEventListener('loadedmetadata', () => {
    const h = videoPlayer.videoHeight;
    const duration = parseInt(videoPlayer.dataset.expectedDuration) || 0;

    // Skip if already playing downloaded file or download in progress
    if (!currentVideoId || progressInterval) return;
    if (videoPlayer.src && videoPlayer.src.includes('/api/stream/') && !videoPlayer.src.includes('/api/stream-live/')) {
        return; // Already playing downloaded file
    }

    const shouldAutoDownload = autoDownloadThreshold > 0 &&
                               duration > 0 &&
                               duration < autoDownloadThreshold &&
                               !downloadCancelled &&
                               h < maxDownloadQuality;

    if (shouldAutoDownload) {
        // Auto-download at user's max quality setting
        startHdDownload(currentVideoId, maxDownloadQuality);
    } else {
        // Show download options if better quality exists
        checkDownloadOffer(currentVideoId, h);
    }
});
