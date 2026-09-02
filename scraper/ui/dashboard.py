"""Web UI HTML Dashboard Renderer (§58 Minimal Truthful Dashboard, DS-22).

Provides honest observability, real health/capability matrix, live crawl/research job
execution, progress tracking, result visualization, and cooperative cancellation.
Zero external CDN dependencies (works fully offline with system fonts).
"""


def render_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DeepSearch Platform - Control & Observability Dashboard</title>
    <style>
        :root {
            --bg-dark: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.75);
            --border-color: rgba(255, 255, 255, 0.12);
            --primary: #6366f1;
            --primary-hover: #4f46e5;
            --accent-green: #10b981;
            --accent-yellow: #f59e0b;
            --accent-red: #ef4444;
            --accent-cyan: #06b6d4;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }

        body {
            background-color: var(--bg-dark);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 2rem;
            background: rgba(15, 23, 42, 0.95);
            border-bottom: 1px solid var(--border-color);
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 1.25rem;
            font-weight: 700;
            color: #818cf8;
        }

        nav {
            display: flex;
            gap: 0.5rem;
        }

        .nav-btn {
            background: transparent;
            border: 1px solid transparent;
            color: var(--text-muted);
            padding: 0.5rem 1rem;
            border-radius: 0.375rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s ease;
        }

        .nav-btn:hover, .nav-btn.active {
            color: var(--text-main);
            background: rgba(255, 255, 255, 0.08);
            border-color: var(--border-color);
        }

        .container {
            padding: 1.5rem 2rem;
            max-width: 1300px;
            margin: 0 auto;
            width: 100%;
            flex: 1;
        }

        .health-bar {
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
            margin-bottom: 1.5rem;
        }

        .health-chip {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            padding: 0.75rem 1.25rem;
            flex: 1;
            min-width: 200px;
        }

        .health-chip-title {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 0.25rem;
        }

        .health-chip-val {
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-main);
        }

        .section-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 0.75rem;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }

        .section-title {
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 1rem;
            color: var(--text-main);
        }

        .form-row {
            display: flex;
            gap: 0.75rem;
            margin-bottom: 1rem;
            flex-wrap: wrap;
        }

        input[type="text"], select {
            flex: 1;
            min-width: 220px;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid var(--border-color);
            border-radius: 0.375rem;
            padding: 0.6rem 0.8rem;
            color: var(--text-main);
            font-size: 0.95rem;
        }

        input[type="text"]:focus, select:focus {
            outline: none;
            border-color: var(--primary);
        }

        .btn {
            background: var(--primary);
            color: #fff;
            border: none;
            padding: 0.6rem 1.25rem;
            border-radius: 0.375rem;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.15s ease;
        }

        .btn:hover {
            background: var(--primary-hover);
        }

        .btn-danger {
            background: var(--accent-red);
        }

        .btn-danger:hover {
            background: #dc2626;
        }

        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        pre {
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            padding: 1rem;
            overflow-x: auto;
            color: #38bdf8;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            font-size: 0.85rem;
            max-height: 400px;
        }

        .badge-stable { color: var(--accent-green); }
        .badge-experimental { color: var(--accent-yellow); }
        .badge-disabled { color: var(--accent-red); }
    </style>
</head>
<body>
    <header>
        <div class="logo">⚡ DeepSearch Platform Control Plane</div>
        <nav>
            <button class="nav-btn active" onclick="switchTab('jobs')">Job Runner</button>
            <button class="nav-btn" onclick="switchTab('inspector')">Inspector</button>
            <button class="nav-btn" onclick="switchTab('capabilities')">Capabilities & Health</button>
        </nav>
    </header>

    <div class="container">
        <!-- System Health Bar -->
        <div class="health-bar">
            <div class="health-chip">
                <div class="health-chip-title">Platform Status</div>
                <div class="health-chip-val" id="health-status">Checking...</div>
            </div>
            <div class="health-chip">
                <div class="health-chip-title">Storage Backend</div>
                <div class="health-chip-val" id="health-storage">Checking...</div>
            </div>
            <div class="health-chip">
                <div class="health-chip-title">Version</div>
                <div class="health-chip-val" id="health-version">-</div>
            </div>
        </div>

        <!-- Tab 1: Job Runner -->
        <div id="tab-jobs" class="tab-content active">
            <div class="section-card">
                <div class="section-title">Submit Crawl / Acquisition Job</div>
                <div class="form-row">
                    <input type="text" id="crawl-url" placeholder="https://example.com">
                    <select id="crawl-mode">
                        <option value="balanced">Balanced Mode</option>
                        <option value="fast">Fast Mode</option>
                        <option value="complete">Complete Mode</option>
                        <option value="archive">Archive Mode</option>
                    </select>
                    <button class="btn" id="btn-submit-crawl" onclick="submitCrawl()">Submit Crawl</button>
                    <button class="btn btn-danger" id="btn-cancel-job" style="display:none;" onclick="cancelActiveJob()">Cancel</button>
                </div>
                <pre id="job-output">// Job progress and status events will be rendered here...</pre>
            </div>
        </div>

        <!-- Tab 2: Inspector -->
        <div id="tab-inspector" class="tab-content">
            <div class="section-card">
                <div class="section-title">Inspect URL Metrics & Strategy Recommendation</div>
                <div class="form-row">
                    <input type="text" id="inspect-url" placeholder="https://example.com/target-page">
                    <button class="btn" id="btn-inspect" onclick="inspectUrl()">Inspect URL</button>
                </div>
                <pre id="inspect-output">// Inspection result report will appear here...</pre>
            </div>
        </div>

        <!-- Tab 3: Capabilities -->
        <div id="tab-capabilities" class="tab-content">
            <div class="section-card">
                <div class="section-title">Capability Matrix & Health Details</div>
                <pre id="capabilities-output">// Loading capabilities from API...</pre>
            </div>
        </div>
    </div>

    <script>
        let activeJobId = null;
        let pollTimer = null;

        function switchTab(tabId) {
            document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));

            if (event && event.target) {
                event.target.classList.add('active');
            }
            const el = document.getElementById('tab-' + tabId);
            if (el) el.classList.add('active');
        }

        async function fetchHealth() {
            try {
                const res = await fetch('/api/v1/health');
                if (res.ok) {
                    const data = await res.json();
                    document.getElementById('health-status').innerText = data.status || 'OK';
                    document.getElementById('health-storage').innerText = data.storage || 'SQLite / FS';
                    document.getElementById('health-version').innerText = data.version || '1.0.0';
                } else {
                    document.getElementById('health-status').innerText = 'Degraded';
                }
            } catch (err) {
                document.getElementById('health-status').innerText = 'Offline';
            }
        }

        async function fetchCapabilities() {
            try {
                const res = await fetch('/api/v1/capabilities');
                if (res.ok) {
                    const data = await res.json();
                    document.getElementById('capabilities-output').innerText = JSON.stringify(data, null, 2);
                }
            } catch (err) {
                document.getElementById('capabilities-output').innerText = 'Failed to fetch capabilities: ' + err;
            }
        }

        async function submitCrawl() {
            const url = document.getElementById('crawl-url').value.trim();
            const mode = document.getElementById('crawl-mode').value;
            if (!url) return;

            const out = document.getElementById('job-output');
            out.innerText = 'Submitting crawl job for ' + url + '...';

            try {
                const res = await fetch('/api/v1/crawl', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url, mode: mode, max_depth: 2, max_pages: 10 })
                });

                if (!res.ok) {
                    const err = await res.json();
                    out.innerText = 'Error submitting job: ' + JSON.stringify(err, null, 2);
                    return;
                }

                const handle = await res.json();
                activeJobId = handle.job_id;
                document.getElementById('btn-cancel-job').style.display = 'inline-block';
                out.innerText = 'Job submitted successfully!\nJob ID: ' + activeJobId + '\nPolling status...\n';

                pollCrawlJob(activeJobId);
            } catch (err) {
                out.innerText = 'Network error: ' + err;
            }
        }

        function pollCrawlJob(jobId) {
            if (pollTimer) clearInterval(pollTimer);
            const out = document.getElementById('job-output');

            pollTimer = setInterval(async () => {
                try {
                    const res = await fetch('/api/v1/crawl/' + jobId);
                    if (!res.ok) return;

                    const st = await res.json();
                    out.innerText = 'Status: ' + st.status + '\nPages Processed: ' + st.pages_processed + '\n' + JSON.stringify(st, null, 2);

                    if (st.status === 'SUCCEEDED' || st.status === 'FAILED' || st.status === 'CANCELLED' || st.status === 'PARTIAL') {
                        clearInterval(pollTimer);
                        document.getElementById('btn-cancel-job').style.display = 'none';

                        if (st.status === 'SUCCEEDED') {
                            const resOutcome = await fetch('/api/v1/crawl/' + jobId + '/result');
                            if (resOutcome.ok) {
                                const resultData = await resOutcome.json();
                                out.innerText += '\n\n=== Final Result ===\n' + JSON.stringify(resultData, null, 2);
                            }
                        }
                    }
                } catch (e) {
                    out.innerText += '\n[Polling error: ' + e + ']';
                }
            }, 1000);
        }

        async function cancelActiveJob() {
            if (!activeJobId) return;
            try {
                await fetch('/api/v1/crawl/' + activeJobId + '/cancel', { method: 'POST' });
                document.getElementById('job-output').innerText += '\nCancellation requested.';
            } catch (err) {
                document.getElementById('job-output').innerText += '\nCancel error: ' + err;
            }
        }

        async function inspectUrl() {
            const url = document.getElementById('inspect-url').value.trim();
            if (!url) return;
            const out = document.getElementById('inspect-output');
            out.innerText = 'Inspecting ' + url + '...';

            try {
                const res = await fetch('/api/v1/inspect', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url })
                });
                const data = await res.json();
                out.innerText = JSON.stringify(data, null, 2);
            } catch (err) {
                out.innerText = 'Inspection error: ' + err;
            }
        }

        fetchHealth();
        fetchCapabilities();
    </script>
</body>
</html>"""
