#!/usr/bin/env python3
"""
Death Star Forensic Scraper - Command Console
Run: uvicorn dashboard:app --reload --host 0.0.0.0 --port 8765
Access: http://localhost:8765
"""
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Death Star Console", version="2.1")

# --- Configuration ---
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"

# Ensure output directory exists for static mounting
DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Mount the output directory to serve captured artifacts (screenshots, PDFs, etc.)
app.mount("/files", StaticFiles(directory=str(DEFAULT_OUTPUT_DIR)), name="files")

MODES = [
    ("forensic", "Forensic – single page, full capture (WARC, HAR, DOM, assets)"),
    ("planetary", "Planetary – whole site, maximum destruction"),
    ("ultimate", "Ultimate – everything + WebSockets, forms, tech stack"),
    ("smart", "Smart – adaptive crawl (default)"),
    ("stealth", "Stealth – JS-heavy / bot-protected sites"),
    ("quick", "Quick – fast static mirror"),
]

# --- Models ---
class ScrapeRequest(BaseModel):
    url: str
    mode: str = "forensic"
    output: str = "output"
    depth: int = 5
    max_pages: int = 10000
    delay: float = 1.0
    polite: bool = False
    wacz: bool = False
    block_ads: bool = False
    save_wayback: bool = False

# --- Helper Functions ---
def find_captures(base_dir: Path) -> List[Dict]:
    """
    Recursively find all 'metadata.json' (forensic) and '*_manifest.json' (crawl) files
    to identify valid capture folders.
    """
    captures: List[Dict] = []
    base_resolved = base_dir.resolve()

    def to_static_rel(root: Path, path_val: Optional[str]) -> Optional[str]:
        if not path_val:
            return None
        p = Path(path_val)
        candidates = [p] if p.is_absolute() else [root / p, base_dir / p, SCRIPT_DIR / p]
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except Exception:
                continue
            if not resolved.exists():
                continue
            try:
                return str(resolved.relative_to(base_resolved))
            except Exception:
                continue
        return None

    # 1. Forensic captures (metadata.json)
    for root, _, files in os.walk(base_dir):
        if "metadata.json" not in files:
            continue
        root_path = Path(root)
        meta_path = root_path / "metadata.json"
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            rel_path = root_path.relative_to(base_dir)
            nested_meta = data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {}

            assets = {
                "screenshot": to_static_rel(root_path, data.get("screenshot_path")) or (str(rel_path / "screenshot.png") if (root_path / "screenshot.png").exists() else None),
                "pdf": to_static_rel(root_path, data.get("pdf_path")) or (str(rel_path / "capture.pdf") if (root_path / "capture.pdf").exists() else None),
                "warc": to_static_rel(root_path, data.get("warc_path")) or (str(rel_path / "archive.warc.gz") if (root_path / "archive.warc.gz").exists() else None),
                "wacz": to_static_rel(root_path, data.get("wacz_path")),
                "mhtml": to_static_rel(root_path, data.get("mhtml_path")),
                "favicon": to_static_rel(root_path, data.get("favicon_path")),
                "har": str(rel_path / "network.har") if (root_path / "network.har").exists() else None,
                "dom": str(rel_path / "dom_snapshot.html") if (root_path / "dom_snapshot.html").exists() else None,
                "article_html": to_static_rel(root_path, data.get("article_html_path")),
                "article_txt": to_static_rel(root_path, data.get("article_text_path")),
            }

            captures.append({
                "id": str(rel_path),
                "path": str(rel_path),
                "timestamp": data.get("timestamp", "Unknown"),
                "url": data.get("url", "Unknown"),
                "mode": data.get("mode", "forensic"),
                "title": data.get("title") or nested_meta.get("title") or "",
                "stats": data.get("stats") or {
                    "requests": data.get("requests_count", 0),
                    "assets": data.get("assets_count", 0),
                },
                "assets": assets,
            })
        except Exception as e:
            print(f"Error parsing {meta_path}: {e}")

    # 2. General crawls (*_manifest.json)
    for root, _, files in os.walk(base_dir):
        root_path = Path(root)
        for file in files:
            if not file.endswith("_manifest.json"):
                continue
            manifest_path = root_path / file
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                outputs = data.get("outputs", {})
                assets = {}
                if isinstance(outputs, dict):
                    for key, val in outputs.items():
                        if not isinstance(val, str) or not val:
                            continue
                        rel_asset = to_static_rel(root_path, val)
                        if rel_asset:
                            assets[key] = rel_asset

                captures.append({
                    "id": file,
                    "path": str(root_path.relative_to(base_dir)),
                    "timestamp": data.get("started_at", "Unknown"),
                    "url": data.get("target", "Unknown"),
                    "mode": data.get("mode", "crawl"),
                    "title": f"Crawl: {data.get('target')}",
                    "stats": {"pages": data.get("pages_scraped", 0), "errors": data.get("errors", 0)},
                    "assets": assets,
                })
            except Exception as e:
                print(f"Error parsing {manifest_path}: {e}")

    # Deduplicate by timestamp + URL, preferring forensic entries.
    unique: Dict[str, Dict] = {}
    for capture in captures:
        key = f"{capture.get('timestamp')}_{capture.get('url')}"
        existing = unique.get(key)
        if existing is None:
            unique[key] = capture
            continue
        if capture.get("mode") == "forensic" and existing.get("mode") != "forensic":
            unique[key] = capture

    def sort_key(item: Dict) -> float:
        ts = item.get("timestamp", "")
        try:
            parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
            return parsed.timestamp()
        except Exception:
            return 0.0

    return sorted(list(unique.values()), key=sort_key, reverse=True)

# --- Endpoints ---

@app.get("/", response_class=HTMLResponse)
def index():
    return get_html()

@app.get("/api/history")
def get_history():
    return find_captures(DEFAULT_OUTPUT_DIR)

@app.post("/api/run")
async def run_scrape(req: ScrapeRequest):
    if not req.url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    # Validate mode
    if req.mode not in [m[0] for m in MODES]:
        req.mode = "forensic"

    async def stream():
        # Construct command
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "death_star_v2.py"),
            "--target", req.url,
            "--mode", req.mode,
            "--output", req.output,
            "--depth", str(req.depth),
            "--max-pages", str(req.max_pages),
            "--delay", str(req.delay),
        ]
        if req.polite:
            cmd.append("--polite")
        if req.wacz:
            cmd.append("--wacz")
        if req.block_ads:
            cmd.append("--block-ads")
        if req.save_wayback:
            cmd.append("--save-wayback")

        command_preview = " ".join(cmd)
        yield f"🚀 Launching Death Star V2...\nCommand: {command_preview}\n\n"

        proc = subprocess.Popen(
            cmd,
            cwd=str(SCRIPT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        
        try:
            for line in proc.stdout:
                yield line
        except Exception as e:
            yield f"\n[ERROR] Stream interrupted: {e}\n"
        finally:
            proc.wait()
            yield f"\n[STATUS] Process finished with exit code {proc.returncode}\n"
            if proc.returncode == 0:
                yield "[SUCCESS] Mission Complete. Check Archives.\n"
            else:
                yield "[FAILURE] Mission Failed.\n"

    return StreamingResponse(
        stream(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# --- Frontend Template ---
def get_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DEATH STAR CONSOLE</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Orbitron:wght@500;700;900&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #050505;
            --bg-panel: #0f1115;
            --border: #2a2f3a;
            --accent: #ff4757; /* Red for Death Star */
            --accent-glow: rgba(255, 71, 87, 0.3);
            --text-main: #e0e0e0;
            --text-dim: #7f8c8d;
            --success: #2ed573;
            --terminal-bg: #1e1e1e;
        }
        
        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body {
            background-color: var(--bg-dark);
            color: var(--text-main);
            font-family: 'JetBrains Mono', monospace;
            height: 100vh;
            display: flex;
            overflow: hidden;
        }

        aside {
            width: 260px;
            background: var(--bg-panel);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            padding: 1.5rem;
            flex-shrink: 0;
        }

        h1 {
            font-family: 'Orbitron', sans-serif;
            font-size: 1.4rem;
            color: var(--accent);
            margin-bottom: 2rem;
            text-shadow: 0 0 10px var(--accent-glow);
            letter-spacing: 1px;
        }

        nav button {
            background: transparent;
            border: 1px solid transparent;
            color: var(--text-dim);
            width: 100%;
            padding: 1rem;
            text-align: left;
            cursor: pointer;
            font-family: 'Orbitron', sans-serif;
            font-size: 0.9rem;
            transition: all 0.2s;
            margin-bottom: 0.5rem;
            border-radius: 4px;
        }

        nav button:hover {
            color: var(--text-main);
            background: rgba(255, 255, 255, 0.05);
        }

        nav button.active {
            color: var(--accent);
            border-color: var(--accent);
            background: rgba(255, 71, 87, 0.1);
            box-shadow: 0 0 15px var(--accent-glow);
        }

        main {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            position: relative;
        }

        .view {
            display: none;
            height: 100%;
            padding: 2rem;
            overflow-y: auto;
            animation: fadeIn 0.3s ease;
        }
        
        .view.active { display: block; }

        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        .panel {
            background: var(--bg-panel);
            border: 1px solid var(--border);
            padding: 2rem;
            border-radius: 8px;
            max-width: 800px;
            margin: 0 auto;
        }

        .form-group { margin-bottom: 1.5rem; }
        
        label {
            display: block;
            color: var(--text-dim);
            margin-bottom: 0.5rem;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        input, select {
            width: 100%;
            background: var(--bg-dark);
            border: 1px solid var(--border);
            color: var(--text-main);
            padding: 0.8rem;
            font-family: 'JetBrains Mono', monospace;
            border-radius: 4px;
        }
        
        input:focus, select:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 8px var(--accent-glow);
        }

        .row { display: flex; gap: 1rem; }
        .col { flex: 1; }
        .checkbox-row { flex-wrap: wrap; margin-bottom: 1.5rem; }
        .checkbox-row label {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin: 0;
            text-transform: none;
            letter-spacing: normal;
            font-size: 0.9rem;
            color: var(--text-main);
        }
        .checkbox-row input[type="checkbox"] {
            width: auto;
            padding: 0;
            accent-color: var(--accent);
        }

        .btn-action {
            width: 100%;
            padding: 1rem;
            background: var(--accent);
            color: #000;
            border: none;
            font-family: 'Orbitron', sans-serif;
            font-weight: 900;
            font-size: 1rem;
            cursor: pointer;
            border-radius: 4px;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            transition: transform 0.1s;
        }
        
        .btn-action:active { transform: scale(0.98); }
        .btn-action:disabled { opacity: 0.5; cursor: wait; }

        #terminal {
            background: var(--terminal-bg);
            border: 1px solid var(--border);
            color: #ccc;
            padding: 1rem;
            height: 400px;
            overflow-y: auto;
            margin-top: 2rem;
            font-size: 0.85rem;
            white-space: pre-wrap;
            border-radius: 4px;
        }

        .history-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 1.5rem;
        }

        .card {
            background: var(--bg-panel);
            border: 1px solid var(--border);
            border-radius: 6px;
            overflow: hidden;
            transition: transform 0.2s, border-color 0.2s;
            cursor: pointer;
        }

        .card:hover {
            transform: translateY(-2px);
            border-color: var(--accent);
        }

        .card-img {
            height: 160px;
            background: #000;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            position: relative;
        }
        
        .card-img img { width: 100%; height: 100%; object-fit: cover; }
        .card-img .placeholder { color: var(--text-dim); font-size: 0.8rem; }

        .card-body { padding: 1rem; }
        .card-title { font-weight: bold; margin-bottom: 0.5rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .card-meta { font-size: 0.75rem; color: var(--text-dim); display: flex; justify-content: space-between; }
        
        .badge {
            display: inline-block;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.7rem;
            background: #333;
            color: #aaa;
            margin-right: 0.5rem;
        }

        .modal-overlay {
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.8);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 100;
            backdrop-filter: blur(5px);
        }
        
        .modal-overlay.open { display: flex; }
        
        .modal {
            background: var(--bg-panel);
            width: 90%;
            max-width: 1000px;
            height: 90vh;
            border: 1px solid var(--accent);
            display: flex;
            flex-direction: column;
            border-radius: 8px;
            box-shadow: 0 0 30px rgba(0,0,0,0.5);
        }
        
        .modal-header {
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .modal-body {
            flex: 1;
            padding: 1.5rem;
            overflow-y: auto;
            display: flex;
            gap: 2rem;
        }
        
        .modal-close {
            background: none;
            border: none;
            color: var(--text-dim);
            font-size: 1.5rem;
            cursor: pointer;
        }
        
        .preview-col { flex: 2; display: flex; flex-direction: column; gap: 1rem; }
        .info-col { flex: 1; border-left: 1px solid var(--border); padding-left: 1.5rem; }
        
        .preview-img { width: 100%; border: 1px solid var(--border); border-radius: 4px; }
        
        .asset-list { list-style: none; margin-top: 1rem; }
        .asset-list li { margin-bottom: 0.5rem; }
        .asset-list a {
            display: block;
            padding: 0.8rem;
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-main);
            text-decoration: none;
            border-radius: 4px;
            border: 1px solid transparent;
            font-size: 0.9rem;
        }
        .asset-list a:hover {
            border-color: var(--accent);
            color: var(--accent);
        }

    </style>
</head>
<body>

<aside>
    <h1>DEATH STAR<br><span style="font-size: 0.8em; color: var(--text-dim);">CONSOLE v2.0</span></h1>
    <nav>
        <button class="active" onclick="switchView('mission')">⚡ NEW MISSION</button>
        <button onclick="switchView('archives')">🗄️ ARCHIVES</button>
    </nav>
</aside>

<main>
    <!-- MISSION VIEW -->
    <div id="mission" class="view active">
        <div class="panel">
            <div class="form-group">
                <label>Target URL</label>
                <input type="url" id="targetUrl" placeholder="https://target-system.com" required>
            </div>
            
            <div class="row">
                <div class="col form-group">
                    <label>Mode</label>
                    <select id="modeSelect">
                        <option value="forensic">FORENSIC (Single Page Full)</option>
                        <option value="planetary">PLANETARY (Whole Site)</option>
                        <option value="ultimate">ULTIMATE (Deep Scan)</option>
                        <option value="smart">SMART (Adaptive)</option>
                        <option value="stealth">STEALTH (Anti-Bot)</option>
                        <option value="quick">QUICK (Static)</option>
                    </select>
                </div>
                <div class="col form-group">
                    <label>Output Dir (Optional)</label>
                    <input type="text" id="outputDir" placeholder="output">
                </div>
            </div>

            <div class="row">
                <div class="col form-group">
                    <label>Depth</label>
                    <input type="number" id="depth" value="5" min="1">
                </div>
                <div class="col form-group">
                    <label>Max Pages</label>
                    <input type="number" id="maxPages" value="10000">
                </div>
            </div>

            <div class="row checkbox-row">
                <label><input type="checkbox" id="optWacz"> Generate WACZ</label>
                <label><input type="checkbox" id="optBlockAds"> Block ads/trackers</label>
                <label><input type="checkbox" id="optWayback"> Save to Wayback</label>
            </div>

            <button class="btn-action" id="launchBtn">INITIATE SEQUENCE</button>
        </div>

        <div id="terminal">Waiting for commands...</div>
    </div>

    <!-- ARCHIVES VIEW -->
    <div id="archives" class="view">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem;">
            <h2>MISSION LOGS</h2>
            <button onclick="loadArchives()" style="background:none; border:1px solid var(--border); color:var(--text-dim); padding:0.5rem 1rem; cursor:pointer; border-radius:4px;">REFRESH</button>
        </div>
        <div id="historyGrid" class="history-grid">
            <!-- Populated via JS -->
            <div style="color: var(--text-dim);">Loading archives...</div>
        </div>
    </div>
</main>

<!-- DETAIL MODAL -->
<div class="modal-overlay" id="detailModal">
    <div class="modal">
        <div class="modal-header">
            <h3 id="modalTitle">Mission Detail</h3>
            <button class="modal-close" onclick="closeModal()">×</button>
        </div>
        <div class="modal-body">
            <div class="preview-col">
                <label>Visual Confirm</label>
                <div id="modalPreview"></div>
            </div>
            <div class="info-col">
                <label>Mission Data</label>
                <p style="margin-bottom: 1rem; font-size: 0.9rem; color: var(--text-dim);" id="modalMeta"></p>
                
                <label>Artifacts</label>
                <ul class="asset-list" id="modalAssets"></ul>
            </div>
        </div>
    </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', () => {

    // --- STATE ---
    const state = {
        captures: []
    };

    // --- NAVIGATION ---
    window.switchView = function(viewId) {
        document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('nav button').forEach(el => el.classList.remove('active'));
        
        document.getElementById(viewId).classList.add('active');
        
        // Find button that calls this function and add active class
        const btn = Array.from(document.querySelectorAll('nav button')).find(b => b.getAttribute('onclick').includes(viewId));
        if (btn) btn.classList.add('active');

        if (viewId === 'archives') loadArchives();
    }

    // --- ACTION: RUN ---
    const launchBtn = document.getElementById('launchBtn');
    const terminal = document.getElementById('terminal');

    if (launchBtn) {
        launchBtn.addEventListener('click', async () => {
            const url = document.getElementById('targetUrl').value.trim();
            if (!url) return alert("Target URL required.");
            
            console.log("Launching scrape for:", url);
            launchBtn.disabled = true;
            launchBtn.textContent = "SEQUENCE RUNNING...";
            launchBtn.style.opacity = "0.7";
            terminal.textContent = "Initializing sequence...\n";
            
            const payload = {
                url,
                mode: document.getElementById('modeSelect').value,
                output: document.getElementById('outputDir').value || "output",
                depth: parseInt(document.getElementById('depth').value),
                max_pages: parseInt(document.getElementById('maxPages').value),
                wacz: document.getElementById('optWacz').checked,
                block_ads: document.getElementById('optBlockAds').checked,
                save_wayback: document.getElementById('optWayback').checked,
            };

            try {
                const res = await fetch('/api/run', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                
                if (!res.ok) throw new Error(`Server returned ${res.status}`);

                const reader = res.body.getReader();
                const dec = new TextDecoder();
                
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    const chunk = dec.decode(value, {stream: true});
                    terminal.textContent += chunk;
                    terminal.scrollTop = terminal.scrollHeight;
                }
            } catch (e) {
                console.error("Scrape failed:", e);
                terminal.textContent += `\n[CRITICAL ERROR]: ${e.message}`;
                alert(`Mission Failed: ${e.message}`);
            } finally {
                launchBtn.disabled = false;
                launchBtn.textContent = "INITIATE SEQUENCE";
                launchBtn.style.opacity = "1";
                loadArchives(); 
            }
        });
    }

    // --- ACTION: ARCHIVES ---
    window.loadArchives = async function() {
        const grid = document.getElementById('historyGrid');
        try {
            const res = await fetch('/api/history');
            const data = await res.json();
            state.captures = data;
            
            grid.innerHTML = '';
            
            if (data.length === 0) {
                grid.innerHTML = '<div style="color:var(--text-dim); grid-column: 1/-1; text-align:center; padding: 2rem;">No archives found in output directory.</div>';
                return;
            }

            data.forEach(item => {
                const card = document.createElement('div');
                card.className = 'card';
                card.onclick = () => openDetail(item);
                
                let thumb = null;
                if (item.assets && item.assets.screenshot) {
                    thumb = `/files/${item.assets.screenshot}`;
                }
                
                const imgHtml = thumb 
                    ? `<img src="${thumb}" loading="lazy">` 
                    : `<div class="placeholder">NO VISUAL</div>`;

                const ts = String(item.timestamp || "Unknown");
                const tsDate = ts.includes('T') ? ts.split('T')[0] : ts;

                card.innerHTML = `
                    <div class="card-img">${imgHtml}</div>
                    <div class="card-body">
                        <div class="card-title" title="${item.url}">${item.url}</div>
                        <div class="card-meta">
                            <span>${tsDate}</span>
                            <span class="badge">${(item.mode || 'unknown').toUpperCase()}</span>
                        </div>
                    </div>
                `;
                grid.appendChild(card);
            });
        } catch (e) {
            console.error("Load archives failed:", e);
            grid.innerHTML = `<div style="color:red">Failed to load archives: ${e.message}</div>`;
        }
    }

    // --- MODAL ---
    window.openDetail = function(item) {
        document.getElementById('modalTitle').textContent = item.url;
        
        // Meta
        const metaHtml = `
            <strong>Time:</strong> ${item.timestamp}<br>
            <strong>Mode:</strong> ${item.mode}<br>
            <strong>Path:</strong> ${item.path}<br>
        `;
        document.getElementById('modalMeta').innerHTML = metaHtml;

        // Preview
        const previewEl = document.getElementById('modalPreview');
        if (item.assets && item.assets.screenshot) {
            previewEl.innerHTML = `<img src="/files/${item.assets.screenshot}" class="preview-img">`;
        } else {
            previewEl.innerHTML = `<div style="padding:2rem; border:1px solid var(--border); color:var(--text-dim); text-align:center;">No Screenshot Available</div>`;
        }

        // Assets
        const list = document.getElementById('modalAssets');
        list.innerHTML = '';
        
        // Standard links
        const standardLinks = [
            { k: 'dom', l: 'DOM Snapshot (HTML)', i: '📄' },
            { k: 'article_html', l: 'Article HTML', i: '📰' },
            { k: 'article_txt', l: 'Article Text', i: '📝' },
            { k: 'pdf', l: 'PDF Capture', i: '📕' },
            { k: 'mhtml', l: 'MHTML Single File', i: '🧩' },
            { k: 'favicon', l: 'Favicon', i: '⭐' },
            { k: 'warc', l: 'WARC Archive', i: '📦' },
            { k: 'wacz', l: 'WACZ Package', i: '🗜️' },
            { k: 'har', l: 'HAR Network Log', i: '🌐' },
        ];

        if (item.assets) {
            // Add standard assets
            standardLinks.forEach(link => {
                if (item.assets[link.k]) {
                    const li = document.createElement('li');
                    li.innerHTML = `<a href="/files/${item.assets[link.k]}" target="_blank">${link.i} ${link.l}</a>`;
                    list.appendChild(li);
                }
            });
            
            // Add other assets dynamically
            for (const [key, val] of Object.entries(item.assets)) {
                if (standardLinks.some(sl => sl.k === key) || key === 'screenshot') continue;
                // Avoid showing nulls or non-strings
                if (!val || typeof val !== 'string') continue;
                
                const li = document.createElement('li');
                li.innerHTML = `<a href="/files/${val}" target="_blank">📂 ${key.toUpperCase()}</a>`;
                list.appendChild(li);
            }
        }

        document.getElementById('detailModal').classList.add('open');
    }

    window.closeModal = function() {
        document.getElementById('detailModal').classList.remove('open');
    }

    // Close on click outside
    document.getElementById('detailModal').addEventListener('click', (e) => {
        if (e.target.id === 'detailModal') closeModal();
    });

});
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)
