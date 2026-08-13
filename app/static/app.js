        let currentAgency = '';
        let currentCategory = '';
        let searchQuery = '';
        let currentViewTab = 'completed'; // 'completed' | 'failed'
        let currentSort = 'date_desc';    // 'date_desc' | 'date_asc' | 'vtuber_asc' | 'duration_desc' | 'duration_asc'

        const isStaticHost = window.location.hostname.includes('github.io') || window.location.protocol === 'file:';
        const isDevEnvironment = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
        const PROD_BACKEND_URL = 'https://vtuber-digest-backend-467039506910.us-central1.run.app';

        function getActiveBackendUrl() {
            if (!isDevEnvironment) {
                return PROD_BACKEND_URL;
            }
            return localStorage.getItem('backend_api_url') || 'http://127.0.0.1:8000';
        }

        function getStaticPath(path) {
            let basePath = window.location.pathname;
            if (!basePath.endsWith('/')) {
                basePath += '/';
            }
            return basePath + path;
        }

        let cachedStreams = [];

        async function fetchStreams() {
            if (isStaticHost) {
                // Step 1: Render static streams INSTANTLY (<50ms)
                try {
                    const res = await fetch(getStaticPath('api/streams.json'));
                    if (res.ok) {
                        cachedStreams = await res.json();
                        applyFiltersAndRender();
                    }
                } catch (e) {
                    console.warn("Failed to load static streams.json:", e);
                }

                // Step 2: Non-blocking background fetch for live Cloud Run streams
                (async () => {
                    try {
                        const controller = new AbortController();
                        const timeoutId = setTimeout(() => controller.abort(), 3000);
                        const liveRes = await fetch(`${PROD_BACKEND_URL}/api/streams`, { signal: controller.signal });
                        clearTimeout(timeoutId);
                        
                        if (liveRes.ok) {
                            const liveStreams = await liveRes.json();
                            if (Array.isArray(liveStreams) && liveStreams.length > 0) {
                                const existingIds = new Set(cachedStreams.map(s => s.video_id || String(s.id)));
                                let merged = false;
                                for (const ls of liveStreams) {
                                    const key = ls.video_id || String(ls.id);
                                    if (!existingIds.has(key)) {
                                        cachedStreams.unshift(ls);
                                        existingIds.add(key);
                                        merged = true;
                                    }
                                }
                                if (merged) {
                                    applyFiltersAndRender();
                                }
                            }
                        }
                    } catch (e) {
                        // Background merge failed or timed out
                    }
                })();
            } else {
                let url = '/api/streams?';
                if (currentCategory) url += `category=${encodeURIComponent(currentCategory)}&`;
                if (currentAgency) url += `agency=${encodeURIComponent(currentAgency)}&`;
                if (searchQuery) url += `q=${encodeURIComponent(searchQuery)}`;
                
                try {
                    const res = await fetch(url);
                    if (res.ok) {
                        cachedStreams = await res.json();
                        applyFiltersAndRender();
                    }
                } catch (err) {
                    console.error("Failed to fetch streams:", err);
                    applyFiltersAndRender();
                }
            }
        }

        function setViewTab(tab) {
            currentViewTab = tab;
            const tabComp = document.getElementById('tabCompleted');
            const tabFail = document.getElementById('tabFailed');
            
            if (tabComp && tabFail) {
                tabComp.style.background = tab === 'completed' ? 'rgba(139, 92, 246, 0.2)' : 'rgba(255, 255, 255, 0.05)';
                tabComp.style.borderColor = tab === 'completed' ? 'rgba(139, 92, 246, 0.5)' : 'var(--border-color)';
                tabComp.style.color = tab === 'completed' ? '#fff' : 'var(--text-muted)';
                
                tabFail.style.background = tab === 'failed' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(255, 255, 255, 0.05)';
                tabFail.style.borderColor = tab === 'failed' ? 'rgba(239, 68, 68, 0.5)' : 'var(--border-color)';
                tabFail.style.color = tab === 'failed' ? '#fff' : 'var(--text-muted)';
            }
            
            const filterBar = document.getElementById('filterControlsBar');
            if (filterBar) {
                filterBar.style.display = tab === 'failed' ? 'none' : 'grid';
            }
            applyFiltersAndRender();
        }

        function handleSortChange() {
            currentSort = document.getElementById('sortSelect').value;
            applyFiltersAndRender();
        }

        function getCategoryTagBadge(s) {
            const titleLower = (s.title || '').toLowerCase();
            const cat = (s.stream_category || '').toLowerCase();
            
            let tagLabel = '💬 Chatting';
            let tagStyle = 'background: rgba(56, 189, 248, 0.18); border: 1px solid rgba(56, 189, 248, 0.35); color: #38bdf8;';
            
            if (titleLower.includes('collab') || titleLower.includes('with @') || titleLower.includes('with shiori')) {
                tagLabel = '🤝 Collab';
                tagStyle = 'background: rgba(236, 72, 153, 0.18); border: 1px solid rgba(236, 72, 153, 0.35); color: #f472b6;';
            } else if (titleLower.includes('anniversary') || titleLower.includes('mini live') || titleLower.includes('graduation') || titleLower.includes('concert') || titleLower.includes('3rd')) {
                tagLabel = '🎂 Event / Milestone';
                tagStyle = 'background: rgba(251, 191, 36, 0.18); border: 1px solid rgba(251, 191, 36, 0.35); color: #fbbf24;';
            } else if (titleLower.includes('karaoke') || titleLower.includes('singing') || titleLower.includes('cover') || titleLower.includes('song')) {
                tagLabel = '🎤 Music / Karaoke';
                tagStyle = 'background: rgba(239, 68, 68, 0.18); border: 1px solid rgba(239, 68, 68, 0.35); color: #f87171;';
            } else if (cat === 'gaming' || titleLower.includes('game') || titleLower.includes('zelda') || titleLower.includes('minecraft') || titleLower.includes('uno') || titleLower.includes('phogs') || titleLower.includes('home sweet home') || titleLower.includes('elsword') || titleLower.includes('oblivion') || titleLower.includes('splatoon') || titleLower.includes('frontline') || titleLower.includes('eronoctosis') || titleLower.includes('berlin apartment') || titleLower.includes('hololive dreams') || titleLower.includes('kamen rider')) {
                tagLabel = '🎮 Gaming';
                tagStyle = 'background: rgba(168, 85, 247, 0.18); border: 1px solid rgba(168, 85, 247, 0.35); color: #c084fc;';
            }
            
            return `<span class="vtuber-agency-pill" style="${tagStyle}">${tagLabel}</span>`;
        }

        function applyFiltersAndRender() {
            if (!Array.isArray(cachedStreams)) return;
            
            const completedStreams = cachedStreams.filter(s => s.status === 'COMPLETED' || !s.status);
            const failedStreams = cachedStreams.filter(s => s.status === 'FAILED');
            
            const elComp = document.getElementById('countCompleted');
            const elFail = document.getElementById('countFailed');
            if (elComp) elComp.textContent = completedStreams.length;
            if (elFail) elFail.textContent = failedStreams.length;
            
            let targetList = currentViewTab === 'failed' ? [...failedStreams] : [...completedStreams];
            
            if (currentViewTab === 'completed') {
                if (currentCategory) {
                    targetList = targetList.filter(s => {
                        const titleLower = (s.title || '').toLowerCase();
                        const cat = (s.stream_category || '').toLowerCase();
                        
                        if (currentCategory === 'gaming') {
                            return cat === 'gaming' || titleLower.includes('game') || titleLower.includes('zelda') || titleLower.includes('minecraft') || titleLower.includes('uno') || titleLower.includes('phogs') || titleLower.includes('home sweet home') || titleLower.includes('elsword') || titleLower.includes('oblivion') || titleLower.includes('splatoon') || titleLower.includes('frontline') || titleLower.includes('eronoctosis') || titleLower.includes('berlin apartment') || titleLower.includes('hololive dreams') || titleLower.includes('kamen rider');
                        } else if (currentCategory === 'chatting') {
                            return (cat === 'chatting' || !cat) && !titleLower.includes('collab') && !titleLower.includes('anniversary') && !titleLower.includes('mini live') && !titleLower.includes('concert') && !titleLower.includes('karaoke') && !titleLower.includes('singing');
                        } else if (currentCategory === 'collab') {
                            return titleLower.includes('collab') || titleLower.includes('with @') || titleLower.includes('with shiori');
                        } else if (currentCategory === 'anniversary') {
                            return titleLower.includes('anniversary') || titleLower.includes('mini live') || titleLower.includes('graduation') || titleLower.includes('concert') || titleLower.includes('3rd');
                        } else if (currentCategory === 'karaoke') {
                            return titleLower.includes('karaoke') || titleLower.includes('singing') || titleLower.includes('cover') || titleLower.includes('song');
                        }
                        return cat === currentCategory;
                    });
                }
                if (currentAgency) {
                    targetList = targetList.filter(s => s.vtuber && s.vtuber.agency === currentAgency);
                }
                if (searchQuery) {
                    const qLower = searchQuery.toLowerCase();
                    targetList = targetList.filter(s => s.title && s.title.toLowerCase().includes(qLower));
                }
            }

            // Apply Sorting
            targetList.sort((a, b) => {
                if (currentSort === 'date_desc') {
                    return new Date(b.published_at || 0) - new Date(a.published_at || 0);
                } else if (currentSort === 'date_asc') {
                    return new Date(a.published_at || 0) - new Date(b.published_at || 0);
                } else if (currentSort === 'vtuber_asc') {
                    const nameA = (a.vtuber ? a.vtuber.name : '').toLowerCase();
                    const nameB = (b.vtuber ? b.vtuber.name : '').toLowerCase();
                    return nameA.localeCompare(nameB);
                } else if (currentSort === 'duration_desc') {
                    return (b.duration_seconds || 0) - (a.duration_seconds || 0);
                } else if (currentSort === 'duration_asc') {
                    return (a.duration_seconds || 0) - (b.duration_seconds || 0);
                }
                return 0;
            });

            renderStreams(targetList);
        }

        function formatDateDisplay(publishedAt) {
            if (!publishedAt) return 'Recent Stream';
            try {
                const d = new Date(publishedAt);
                if (isNaN(d.getTime())) return 'Recent Stream';
                return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
            } catch (e) {
                return 'Recent Stream';
            }
        }

        function renderStreams(streams) {
            const grid = document.getElementById('streamGrid');
            if (!streams.length) {
                grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 3rem;">
                    ${currentViewTab === 'failed' ? '🎉 No failed ingestion logs! All streams processed cleanly.' : 'No VTuber stream summaries found for these filter settings.'}
                </div>`;
                return;
            }

            if (currentViewTab === 'failed') {
                grid.innerHTML = streams.map(s => `
                    <div class="stream-card" style="border-color: rgba(239, 68, 68, 0.3);">
                        <div class="thumbnail-container">
                            <img src="${s.thumbnail_url || 'https://via.placeholder.com/640x360'}" class="thumbnail-img" alt="${s.title}">
                            <span class="status-badge status-FAILED">FAILED</span>
                        </div>
                        <div class="card-content">
                            <div class="vtuber-meta">
                                <span class="vtuber-agency-pill" style="background: rgba(239, 68, 68, 0.15); border-color: rgba(239, 68, 68, 0.3); color: #f87171;">⚠️ ${s.vtuber ? s.vtuber.name : 'VTuber'}</span>
                            </div>
                            <div class="stream-title">${s.title}</div>
                            <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 8px; padding: 0.6rem; font-size: 0.8rem; color: #fca5a5;">
                                <strong>Failure Cause:</strong> ${s.error_message || 'Could not fetch auto-captions or subtitles from YouTube.'}
                            </div>
                            <div class="stream-footer" style="margin-top: 0.5rem; justify-content: space-between;">
                                <span>📅 ${formatDateDisplay(s.published_at)}</span>
                                <button class="btn" style="padding: 0.25rem 0.6rem; font-size: 0.75rem; background: rgba(139, 92, 246, 0.2);" onclick="event.stopPropagation(); retryFailedStream('${s.video_id}')">
                                    🔄 Retry Summarizing
                                </button>
                            </div>
                        </div>
                    </div>
                `).join('');
                return;
            }

            grid.innerHTML = streams.map(s => `
                <div class="stream-card" onclick="openStreamDetail(${s.id})">
                    <div class="thumbnail-container">
                        <img src="${s.thumbnail_url || 'https://via.placeholder.com/640x360'}" class="thumbnail-img" alt="${s.title}">
                        <span class="status-badge status-${s.status}">${s.status}</span>
                    </div>
                    <div class="card-content">
                        <div class="vtuber-meta" style="flex-wrap: wrap; gap: 6px;">
                            <span class="vtuber-agency-pill">${s.vtuber ? s.vtuber.agency : 'VTuber'}</span>
                            ${getCategoryTagBadge(s)}
                            <span class="vtuber-name" style="margin-left: auto;">${s.vtuber ? s.vtuber.name : ''}</span>
                        </div>
                        <div class="stream-title">${s.title}</div>
                        <div class="stream-footer">
                            <span>📅 ${formatDateDisplay(s.published_at)}</span>
                            <span>⏱️ ${s.duration_seconds ? Math.round(s.duration_seconds/60) + ' mins' : ''}</span>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        function retryFailedStream(videoId) {
            const url = `https://www.youtube.com/watch?v=${videoId}`;
            openTriggerModal();
            const input = document.getElementById('triggerUrlInput');
            if (input) {
                input.value = url;
            }
        }

        function setCategoryFilter(category) {
            currentCategory = category;
            document.querySelectorAll('#categoryFilters .pill').forEach(btn => {
                const text = btn.textContent.toLowerCase();
                btn.classList.toggle('active', 
                    (category === 'chatting' && text.includes('chatting')) ||
                    (category === 'gaming' && text.includes('gaming')) ||
                    (category === 'collab' && text.includes('collab')) ||
                    (category === 'anniversary' && text.includes('event')) ||
                    (category === 'karaoke' && text.includes('music')) ||
                    (!category && text.includes('all'))
                );
            });
            applyFiltersAndRender();
        }

        function setAgencyFilter(agency) {
            currentAgency = agency;
            document.querySelectorAll('#agencyFilters .pill').forEach(btn => {
                btn.classList.toggle('active', btn.textContent.includes(agency) || (!agency && btn.textContent.includes('All')));
            });
            fetchStreams();
        }

        function handleSearch() {
            searchQuery = document.getElementById('searchInput').value;
            fetchStreams();
        }

        let currentModalVideoId = '';

        async function openStreamDetail(streamId) {
            const modal = document.getElementById('detailModal');
            modal.classList.add('active');
            
            try {
                let url = isStaticHost ? `${PROD_BACKEND_URL}/api/streams/${streamId}` : `/api/streams/${streamId}`;
                let res = await fetch(url);
                if (!res.ok && isStaticHost) {
                    res = await fetch(getStaticPath(`api/streams/${streamId}.json`));
                }
                const data = await res.json();
                
                currentModalVideoId = data.video_id;
                document.getElementById('modalStreamTitle').textContent = data.title;
                document.getElementById('ytPlayer').src = `https://www.youtube.com/embed/${data.video_id}?enablejsapi=1`;
                
                if (data.summary && data.summary.master_summary) {
                    let rawMarkdown = data.summary.master_summary;
                    
                    // Transform [HH:MM:SS] or [MM:SS] tags in raw Markdown into markdown timestamp links
                    rawMarkdown = rawMarkdown.replace(/\[(?:⏱️\s*)?(\d{1,2}:\d{2}(?::\d{2})?)\]/g, (match, p1) => {
                        return `[⏱️ ${p1}](#t=${p1})`;
                    });

                    let htmlContent = marked.parse(rawMarkdown);
                    
                    // Convert generated #t=HH:MM:SS links into interactive video seeking links
                    htmlContent = htmlContent.replace(/href="#t=([^"]+)"/g, (match, p1) => {
                        return `href="javascript:void(0)" class="timestamp-link" style="color: #38bdf8; font-weight: 700; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 6px; padding: 2px 8px; text-decoration: none; cursor: pointer; display: inline-block; margin-right: 4px;" onclick="jumpToTime('${p1}', '${data.video_id}')"`;
                    });

                    const summaryContainer = document.getElementById('modalSummaryText');
                    summaryContainer.innerHTML = htmlContent;
                } else {
                    document.getElementById('modalSummaryText').innerHTML = `<p style="color: var(--text-muted);">Status: ${data.status}... Summary is being generated.</p>`;
                }

                const chipsContainer = document.getElementById('highlightChips');
                if (data.summary && data.summary.standout_highlights) {
                    chipsContainer.innerHTML = data.summary.standout_highlights.map(h => `
                        <span class="timestamp-tag" onclick="jumpToTime('${h.timestamp}', '${data.video_id}')">
                            ⏱️ ${h.timestamp} - ${h.title}
                        </span>
                    `).join('');
                } else {
                    chipsContainer.innerHTML = '<span style="color: var(--text-muted); font-size: 0.85rem;">Processing timestamps...</span>';
                }
            } catch (err) {
                console.error("Error loading stream detail:", err);
            }
        }

        // Global Event Delegation listener for any timestamp click inside modalSummaryText
        document.getElementById('modalSummaryText').addEventListener('click', function(e) {
            let target = e.target;
            while (target && target !== this) {
                const text = target.textContent || '';
                const match = text.match(/\b\d{1,2}:\d{2}:\d{2}\b|\b\d{1,2}:\d{2}\b/);
                if (match && currentModalVideoId) {
                    e.preventDefault();
                    e.stopPropagation();
                    jumpToTime(match[0], currentModalVideoId);
                    return;
                }
                target = target.parentElement;
            }
        });

        function jumpToTime(timeStr, videoId) {
            const parts = timeStr.split(':').map(Number);
            let totalSecs = 0;
            if (parts.length === 3) totalSecs = parts[0]*3600 + parts[1]*60 + parts[2];
            else if (parts.length === 2) totalSecs = parts[0]*60 + parts[1];

            document.getElementById('ytPlayer').src = `https://www.youtube.com/embed/${videoId}?start=${totalSecs}&autoplay=1`;
        }
        window.jumpToTime = jumpToTime;

        function closeDetailModal() {
            document.getElementById('detailModal').classList.remove('active');
            document.getElementById('ytPlayer').src = '';
        }

        let pollInterval = null;

        function openTriggerModal() {
            document.getElementById('triggerInputGroup').style.display = 'block';
            document.getElementById('triggerProgressGroup').style.display = 'none';
            document.getElementById('triggerSuccessBox').style.display = 'none';
            document.getElementById('triggerErrorBox').style.display = 'none';
            document.getElementById('streamUrlInput').value = '';
            document.getElementById('triggerModal').classList.add('active');
        }

        // Surface a failure inside the modal instead of a browser alert().
        function showTriggerError(message) {
            if (pollInterval) clearInterval(pollInterval);
            document.getElementById('triggerInputGroup').style.display = 'none';
            document.getElementById('triggerProgressGroup').style.display = 'none';
            document.getElementById('triggerSuccessBox').style.display = 'none';
            document.getElementById('triggerErrorText').textContent = message;
            document.getElementById('triggerErrorBox').style.display = 'block';
        }

        function closeTriggerModal() {
            if (pollInterval) clearInterval(pollInterval);
            document.getElementById('triggerModal').classList.remove('active');
            fetchStreams();
        }

        async function openSettingsModal() {
            document.getElementById('settingsModal').classList.add('active');
            
            // Only show backend URL override input on dev environment (localhost / 127.0.0.1)
            const devGroup = document.getElementById('devBackendSettingGroup');
            if (devGroup) {
                devGroup.style.display = isDevEnvironment ? 'block' : 'none';
                if (isDevEnvironment) {
                    document.getElementById('backendApiUrlInput').value = localStorage.getItem('backend_api_url') || 'http://127.0.0.1:8000';
                }
            }

            try {
                const baseUrl = getActiveBackendUrl().replace(/\/$/, '');
                const res = await fetch(`${baseUrl}/api/settings`);
                if (!res.ok) return;
                const data = await res.json();
                document.getElementById('discordWebhookInput').value = data.discord_webhook_url || '';
                document.getElementById('discordEnableToggle').checked = data.is_discord_enabled;
                if (data.summary_style) {
                    document.getElementById('summaryStyleSelect').value = data.summary_style;
                }
            } catch (err) {
                console.error("Failed to load settings:", err);
            }
        }

        function closeSettingsModal() {
            document.getElementById('settingsModal').classList.remove('active');
        }

        async function saveSettings() {
            if (isDevEnvironment) {
                const backendUrl = document.getElementById('backendApiUrlInput').value.trim();
                if (backendUrl) {
                    localStorage.setItem('backend_api_url', backendUrl);
                }
            }
            
            const webhookUrl = document.getElementById('discordWebhookInput').value.trim();
            const enabled = document.getElementById('discordEnableToggle').checked;
            const style = document.getElementById('summaryStyleSelect').value;

            try {
                const baseUrl = getActiveBackendUrl().replace(/\/$/, '');
                await fetch(`${baseUrl}/api/settings`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        discord_webhook_url: webhookUrl,
                        is_discord_enabled: enabled,
                        summary_style: style
                    })
                });
            } catch (err) {
                console.error("Backend settings update info:", err);
            }
            closeSettingsModal();
            alert("Settings saved successfully!");
        }

        async function submitStreamUrl() {
            const url = document.getElementById('streamUrlInput').value.trim();
            if (!url) return;
            
            // Show loading & progress UI
            document.getElementById('triggerInputGroup').style.display = 'none';
            document.getElementById('triggerProgressGroup').style.display = 'block';
            document.getElementById('triggerSuccessBox').style.display = 'none';
            
            updateProgressUI('PENDING', 'Step 1/3: Dispatching stream URL to FastAPI backend worker...', 15);

            // Determine active backend endpoint
            const baseUrl = getActiveBackendUrl().replace(/\/$/, '');
            const targetEndpoint = `${baseUrl}/api/streams/trigger`;

            try {
                const res = await fetch(targetEndpoint, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url})
                });
                
                const rawText = await res.text();
                let data = null;
                try {
                    data = JSON.parse(rawText);
                } catch (e) {
                    let snippet = rawText.slice(0, 120);
                    if (snippet.includes('<html')) {
                        snippet = "Static host 404 response received instead of backend endpoint.";
                    }
                    throw new Error(`Invalid response from server (${res.status}): ${snippet}`);
                }

                if (!res.ok) {
                    const errMsg = (data && data.detail) ? data.detail : `HTTP Error ${res.status}`;
                    throw new Error(errMsg);
                }
                
                if (data && data.stream_id) {
                    startStreamProgressPolling(data.stream_id, baseUrl);
                } else {
                    alert("Stream job queued: " + (data ? data.message : "Processing started"));
                    closeTriggerModal();
                }
            } catch (err) {
                showTriggerError(err.message + " — ensure the live backend is reachable (or run locally on :8000).");
            }
        }

        function updateProgressUI(status, message, percent) {
            document.getElementById('triggerStatusBadge').textContent = `⏳ ${status}`;
            document.getElementById('triggerStatusText').textContent = message;
            document.getElementById('triggerProgressPercent').textContent = `${percent}%`;
            document.getElementById('progressBarFill').style.width = `${percent}%`;
        }

        function startStreamProgressPolling(streamId, baseUrl = '') {
            if (pollInterval) clearInterval(pollInterval);

            pollInterval = setInterval(async () => {
                try {
                    const endpoint = (baseUrl ? baseUrl.replace(/\/$/, '') : '') + `/api/streams/${streamId}`;
                    const res = await fetch(endpoint);
                    const rawText = await res.text();
                    let stream = null;
                    try {
                        stream = JSON.parse(rawText);
                    } catch (e) {
                        return; // Retry next interval if transient response
                    }
                    
                    if (stream && stream.status === 'PENDING') {
                        updateProgressUI('PENDING', 'Step 1/3: Queuing stream & fetching video info...', 25);
                    } else if (stream && stream.status === 'FETCHING_TRANSCRIPT') {
                        updateProgressUI('FETCHING TRANSCRIPT', 'Step 2/3: Downloading auto-subtitles via yt-dlp & parsing VTT cues...', 55);
                    } else if (stream && stream.status === 'SUMMARIZING') {
                        updateProgressUI('SUMMARIZING', 'Step 3/3: Executing Map-Reduce LLM summarization via Gemini 2.5...', 85);
                    } else if (stream && stream.status === 'COMPLETED') {
                        clearInterval(pollInterval);
                        updateProgressUI('COMPLETED', '🎉 Summary generated successfully!', 100);
                        
                        // Show success box after short delay
                        setTimeout(() => {
                            document.getElementById('triggerProgressGroup').style.display = 'none';
                            document.getElementById('triggerSuccessBox').style.display = 'block';
                            document.getElementById('viewSummaryBtn').onclick = () => {
                                closeTriggerModal();
                                openStreamDetail(streamId);
                            };
                            fetchStreams();
                        }, 600);
                    } else if (stream && stream.status === 'FAILED') {
                        clearInterval(pollInterval);
                        showTriggerError(stream.error_message || "Could not process captions.");
                    }
                } catch (err) {
                    console.error("Polling error:", err);
                }
            }, 2000);
        }

        // Read-only gallery: on the static site there is no backend to accept
        // POSTs, so hide the live "Summarize Stream" / "Settings" actions.
        if (isStaticHost) {
            const actions = document.getElementById('headerActions');
            if (actions) actions.style.display = 'none';
        }

        // Initial fetch
        fetchStreams();
        // Auto-refresh main grid every 6 seconds to show active progress badges
        if (!isStaticHost) {
            setInterval(fetchStreams, 6000);
        }
