# Death Star Forensic Scraper

**The "Nuke From Orbit" Web Capture Tool.**  
Full forensic archival of any website. One click. No technical skills required.

---

## 🚀 Easy Start (For Everyone)

**You do not need to use the command line.** We have a Mission Control Dashboard.

### 1. Run the App
- **Linux/Mac**: Open a terminal and run `./start.sh`
- **Windows**: Double-click `run_mission_control.bat`

### 2. Use the Dashboard
1.  **Browser opens automatically** to `http://localhost:8765`.
2.  **Enter URL**: Type the website you want to capture (e.g., `https://example.com`).
3.  **Select Mode**:
    *   **FORENSIC** (Recommended): Captures *everything* on a single page: Screenshots, PDF, Text, Network Traffic (HAR), and Web Archive (WARC).
    *   **PLANETARY**: Crawls the entire website (use with caution).
    *   **STEALTH**: For hard-to-scrape sites with bot protection.
4.  **Click "INITIATE SEQUENCE"**.
5.  Watch the logs. When finished, click **ARCHIVES** to view and download your files.

---

## 🛠️ Advanced Usage (Developers)

**Full forensic capture of any website.** One command, no config. WARC, HAR, screenshots, DOM, assets, cookies, certificates, and more.

Use for: archival, compliance, research, reverse engineering, or “nuke from orbit” site capture.

---

## Quick start (any target)

```bash
# 1. Clone or download this folder, then:
cd death-star-forensic-scraper
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate   # Linux/macOS

# 2. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 3. Run a full forensic scrape (single page, everything captured)
#    Run from this directory so all modules load correctly.
python death_star_v2.py --target https://example.com --mode forensic --output ./my-capture
```

Output goes to `./my-capture` (or `./output` if you omit `--output`): WARC, HAR, HTML, screenshots, PDF, assets, cookies, TLS certs.

---

## Modes

| Mode       | Use case                    | What you get |
|-----------|-----------------------------|--------------|
| **forensic** | One page, full forensics   | WARC, HAR, DOM, assets, storage, certs, screenshot, PDF. **Best for “capture this URL completely.”** |
| **planetary** | Whole site, maximum      | Discovery + forensic + media + crawl + wget + ArchiveBox (if installed). |
| **ultimate**  | Everything + extras       | Forensic + WebSockets, forms, tech stack, Wayback, source maps. |
| **smart**     | Normal crawl (default)    | Adaptive HTTP + browser fallback, markdown + HTML. |
| **stealth**   | JS-heavy / bot‑protected  | Browser-only, anti‑bot evasion. |
| **quick**     | Fast static mirror        | wget-style download. |

**Recommended for “full forensic of one target”:**

```bash
python death_star_v2.py --target https://your-target.com --mode forensic --output ./forensic-out
```

**Recommended for “entire site, everything”:**

```bash
python death_star_v2.py --target https://your-target.com --mode planetary --output ./site-out
```

---

## Options

```bash
# Output directory (default: ./output)
--output, -o DIR

# Max crawl depth (planetary/smart/stealth)
--depth, -d N          # default 5

# Max pages to scrape
--max-pages N          # default 10000

# Resume after interrupt
--resume, -r

# Respect robots.txt
--polite, -p

# Delay between requests (seconds)
--delay N              # default 1.0

# Multiple URLs from file
--targets urls.txt     # one URL per line

# Proxy (single)
--proxy http://host:port

# Cookies (e.g. from browser export)
--cookies cookies.json

# HTTP auth
--auth-user USER --auth-pass PASS
```

---

## Output layout (forensic mode)

```
output/
  forensic/
    results/
      example.com_2026-02-10T.../
        metadata.json
        raw.html
        dom_snapshot.html
        clean_text.txt
        network.har
    warc/          # Web ARChive
    har/            # HTTP Archive
    screenshots/
    pdfs/
    assets/
    certificates/
  data/
    scraping_state/   # checkpoint DB (resume)
```

---

## Requirements

- **Python 3.10+**
- **Chromium** (via Playwright) for forensic/stealth/planetary/ultimate

Optional:

- **wget** – for `quick` and `full`/`planetary` mirroring
- **ArchiveBox** – for archival mode in `full`/`planetary`
- **yt-dlp** – for video/audio in media extraction (planetary/ultimate)

---

## Install (detailed)

```bash
cd death-star-forensic-scraper
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
playwright install chromium
```

To print install hints from the script:

```bash
python death_star_v2.py --install
```

---

## Examples

```bash
# Single page, full forensic
python death_star_v2.py -t https://example.com -m forensic -o ./cap1

# Whole site, maximum capture
python death_star_v2.py -t https://example.com -m planetary -o ./cap2 -d 5 --max-pages 2000

# Stealth (JS / bot protection)
python death_star_v2.py -t https://hard-to-scrape.com -m stealth -o ./cap3

# Multiple targets
echo https://a.com > urls.txt
echo https://b.com >> urls.txt
python death_star_v2.py --targets urls.txt -m forensic -o ./multi

# Resume after Ctrl+C
python death_star_v2.py -t https://example.com -m planetary -o ./out --resume
```

---

## License

MIT. Use responsibly; respect robots.txt and site terms when applicable.

---

## Credits

Death Star V2 – “Nuke From Orbit” web scraper. Forensic capture, WARC/HAR, and multi-tool orchestration from the Deadhead-LLM / Grok & Mon acquisition pipeline. This folder is a standalone, public-release subset so anyone can run a full forensic scrape of any target.
