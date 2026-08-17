"""Web UI HTML Dashboard Renderer (§58 Dashboard, Live Crawl, Page Inspector, §59 Extraction Studio, Visual Search)."""

def render_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DeepSearch - Adaptive Web Scraping & Retrieval Platform</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.7);
            --border-color: rgba(255, 255, 255, 0.1);
            --primary: #6366f1;
            --primary-gradient: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
            --accent-cyan: #06b6d4;
            --accent-green: #10b981;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Outfit', sans-serif;
        }

        body {
            background-color: var(--bg-dark);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            background-image: 
                radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.15) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(168, 85, 247, 0.15) 0px, transparent 50%);
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.25rem 2rem;
            background: rgba(15, 23, 42, 0.8);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border-color);
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-size: 1.5rem;
            font-weight: 700;
            background: var(--primary-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        nav {
            display: flex;
            gap: 0.5rem;
        }

        .nav-btn {
            background: transparent;
            border: 1px solid transparent;
            color: var(--text-muted);
            padding: 0.6rem 1.2rem;
            border-radius: 0.5rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .nav-btn:hover, .nav-btn.active {
            color: var(--text-main);
            background: rgba(255, 255, 255, 0.05);
            border-color: var(--border-color);
        }

        .container {
            padding: 2rem;
            max-width: 1400px;
            margin: 0 auto;
            width: 100%;
            flex: 1;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }

        .stat-card {
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: 1rem;
            padding: 1.5rem;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .stat-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
        }

        .stat-label {
            color: var(--text-muted);
            font-size: 0.875rem;
            margin-bottom: 0.5rem;
        }

        .stat-val {
            font-size: 2rem;
            font-weight: 700;
            color: var(--text-main);
        }

        .stat-badge {
            display: inline-block;
            margin-top: 0.5rem;
            padding: 0.25rem 0.6rem;
            border-radius: 2rem;
            font-size: 0.75rem;
            font-weight: 600;
            background: rgba(16, 185, 129, 0.15);
            color: var(--accent-green);
        }

        .section-card {
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: 1rem;
            padding: 1.75rem;
            margin-bottom: 2rem;
        }

        .section-title {
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1.25rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .input-group {
            display: flex;
            gap: 1rem;
            margin-bottom: 1.5rem;
        }

        input[type="text"] {
            flex: 1;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            padding: 0.8rem 1.2rem;
            color: var(--text-main);
            font-size: 1rem;
            outline: none;
        }

        input[type="text"]:focus {
            border-color: var(--primary);
        }

        .btn {
            background: var(--primary-gradient);
            color: #fff;
            border: none;
            padding: 0.8rem 1.75rem;
            border-radius: 0.5rem;
            font-weight: 600;
            cursor: pointer;
            transition: opacity 0.2s ease;
        }

        .btn:hover {
            opacity: 0.9;
        }

        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        .inspector-split {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
            min-height: 400px;
        }

        pre {
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            padding: 1rem;
            overflow-x: auto;
            color: var(--accent-cyan);
            font-size: 0.875rem;
            max-height: 450px;
        }
    </style>
</head>
<body>
    <header>
        <div class="logo">⚡ DeepSearch Platform</div>
        <nav>
            <button class="nav-btn active" onclick="switchTab('dashboard')">Dashboard</button>
            <button class="nav-btn" onclick="switchTab('inspector')">Page Inspector</button>
            <button class="nav-btn" onclick="switchTab('studio')">Extraction Studio</button>
            <button class="nav-btn" onclick="switchTab('search')">Visual Search</button>
        </nav>
    </header>

    <div class="container">
        <!-- Tab 1: Dashboard -->
        <div id="tab-dashboard" class="tab-content active">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Pages Acquired</div>
                    <div class="stat-val" id="stat-pages">-</div>
                    <div class="stat-badge">Live System Metric</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Evidence Claims Stored</div>
                    <div class="stat-val" id="stat-claims">-</div>
                    <div class="stat-badge">Live Graph Metric</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Active Research Runs</div>
                    <div class="stat-val" id="stat-jobs">-</div>
                    <div class="stat-badge">Durable ADGO Control Plane</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Vector Store Status</div>
                    <div class="stat-val" id="stat-qdrant">Ready</div>
                    <div class="stat-badge">Qdrant Indexed</div>
                </div>
            </div>

            <div class="section-card">
                <div class="section-title">🚀 Launch Durable Research Job</div>
                <div class="input-group">
                    <input type="text" id="crawl-url-input" placeholder="Enter research query (e.g. 'Deep Learning in Medicine')">
                    <button class="btn" onclick="startResearch()">Start Research</button>
                </div>
                <pre id="job-status-pre">// Research job progress and telemetry will appear here...</pre>
            </div>
        </div>

        <!-- Tab 2: Page Inspector -->
        <div id="tab-inspector" class="tab-content">
            <div class="section-card">
                <div class="section-title">🔍 Inspect Mode (§57)</div>
                <div class="input-group">
                    <input type="text" id="inspect-url-input" placeholder="https://example.com/target-page">
                    <button class="btn" onclick="inspectUrl()">Inspect Page</button>
                </div>
                <div class="inspector-split">
                    <div>
                        <h3>Diagnostic Report</h3>
                        <pre id="inspect-result">// Run inspection to view static score, JS score, and recommended strategy...</pre>
                    </div>
                    <div>
                        <h3>Markdown Pipeline</h3>
                        <pre id="inspect-markdown">// Clean & Fit Markdown Output will appear here...</pre>
                    </div>
                </div>
            </div>
        </div>

        <!-- Tab 3: Extraction Studio -->
        <div id="tab-studio" class="tab-content">
            <div class="section-card">
                <div class="section-title">✨ Extraction Studio & Schema Editor (§59)</div>
                <p style="color: var(--text-muted); margin-bottom: 1rem;">Visual element selector fingerprinting and JSON Schema builder.</p>
                <pre>{
  "name": "Product Schema",
  "selectors": {
    "title": "h1.product-title",
    "price": "span.price-amount"
  }
}</pre>
            </div>
        </div>

        <!-- Tab 4: Visual Search -->
        <div id="tab-search" class="tab-content">
            <div class="section-card">
                <div class="section-title">👁️ PixelRAG Visual & Hybrid Search (§41)</div>
                <div class="input-group">
                    <input type="text" id="search-query-input" placeholder="Enter query (e.g. 'pump pressure diagram' or 'pricing table')">
                    <button class="btn" onclick="searchHybrid()">Search</button>
                </div>
                <pre id="search-results">// Hybrid retrieval results will be rendered here...</pre>
            </div>
        </div>
    </div>

    <script>
        function switchTab(tabId) {
            document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
            
            event.target.classList.add('active');
            document.getElementById('tab-' + tabId).classList.add('active');
        }

        async function inspectUrl() {
            const url = document.getElementById('inspect-url-input').value;
            if(!url) return;
            document.getElementById('inspect-result').innerText = "Inspecting page metrics...";
            try {
                const res = await fetch('/api/v1/inspect', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: url})
                });
                const data = await res.json();
                document.getElementById('inspect-result').innerText = JSON.stringify(data, null, 2);
            } catch(e) {
                document.getElementById('inspect-result').innerText = "Error: " + e;
            }
        }

        async function searchHybrid() {
            const q = document.getElementById('search-query-input').value;
            if(!q) return;
            document.getElementById('search-results').innerText = "Searching text & visual multivector indices...";
            try {
                const res = await fetch('/api/v1/search/hybrid', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({query: q, limit: 10})
                });
                const data = await res.json();
                document.getElementById('search-results').innerText = JSON.stringify(data, null, 2);
            } catch(e) {
                document.getElementById('search-results').innerText = "Error: " + e;
            }
        }

        let currentEventSource = null;

        async function startResearch() {
            const q = document.getElementById('crawl-url-input').value;
            if(!q) return;
            document.getElementById('job-status-pre').innerText = "Launching research job...";
            try {
                const res = await fetch('/api/v1/research', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({query: q})
                });
                const data = await res.json();
                document.getElementById('job-status-pre').innerText = JSON.stringify(data, null, 2);
                if (data.run_id) {
                    streamJobEvents(data.run_id);
                }
            } catch(e) {
                document.getElementById('job-status-pre').innerText = "Error: " + e;
            }
        }

        function streamJobEvents(runId) {
            if (currentEventSource) {
                currentEventSource.close();
            }
            const logArea = document.getElementById('job-status-pre');
            logArea.innerText = `[SSE Stream Connected for Run: ${runId}]\nWaiting for telemetry events...\n`;

            currentEventSource = new EventSource(`/api/v1/research/${runId}/events`);
            
            currentEventSource.onmessage = function(e) {
                try {
                    const parsed = JSON.parse(e.data);
                    logArea.innerText += `\n[${new Date(parsed.timestamp * 1000).toLocaleTimeString()}] [${parsed.event_type}]: ${JSON.stringify(parsed.data || parsed)}`;
                    logArea.scrollTop = logArea.scrollHeight;
                } catch(err) {
                    logArea.innerText += `\n${e.data}`;
                }
            };

            currentEventSource.addEventListener('stage_change', function(e) {
                const ev = JSON.parse(e.data);
                logArea.innerText += `\n⚡ STAGE: ${ev.data.stage || ev.event_type}`;
            });

            currentEventSource.addEventListener('completed', function(e) {
                logArea.innerText += `\n✅ RESEARCH COMPLETED! Ready for Obsidian / Zotero Export.`;
                currentEventSource.close();
            });

            currentEventSource.onerror = function() {
                // Fallback to polling if SSE closes or completes
                pollJob(runId);
            };
        }

        async function exportObsidian(runId) {
            if(!runId) return;
            const res = await fetch(`/api/v1/research/${runId}/export/obsidian`, {method: 'POST'});
            const data = await res.json();
            alert(`Obsidian Vault Exported to: ${data.vault_dir}`);
        }

        async function exportZotero(runId) {
            if(!runId) return;
            const res = await fetch(`/api/v1/research/${runId}/export/zotero`, {method: 'POST'});
            const data = await res.json();
            alert(`Zotero CSL-JSON and RIS Exported to: ${data.output_dir}`);
        }

        async function pollJob(runId) {
            const timer = setInterval(async () => {
                try {
                    const res = await fetch('/api/v1/research/' + runId);
                    const status = await res.json();
                    document.getElementById('job-status-pre').innerText = JSON.stringify(status, null, 2);
                    if(status.status === 'COMPLETED' || status.status === 'FAILED' || status.status === 'CANCELLED') {
                        clearInterval(timer);
                    }
                } catch(e) {}
            }, 1500);
        }

        async function refreshMetrics() {
            try {
                const res = await fetch('/api/v1/metrics/summary');
                if(res.ok) {
                    const m = await res.json();
                    if(m.pages_processed !== undefined) document.getElementById('stat-pages').innerText = m.pages_processed;
                    if(m.active_jobs !== undefined) document.getElementById('stat-jobs').innerText = m.active_jobs;
                }
            } catch(e) {}
        }
        setInterval(refreshMetrics, 5000);
        refreshMetrics();
    </script>
</body>
</html>"""
