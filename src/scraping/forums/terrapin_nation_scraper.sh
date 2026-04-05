#!/bin/bash
# Terrapin Nation Forum Bulk Scraper
# Scrapes entire terrapinnation.com forum (5,500+ topics)
# 
# Usage: ./terrapin_nation_scraper.sh
# Runs in background - check logs for progress

set -e

# Configuration
BASE_URL="https://www.terrapinnation.com"
OUTPUT_DIR="data/forums/terrapin_nation"
RAW_DIR="${OUTPUT_DIR}/raw"
LOG_DIR="${OUTPUT_DIR}/logs"
LOG_FILE="${LOG_DIR}/scrape_$(date +%Y%m%d_%H%M%S).log"

# Create directories
mkdir -p "$RAW_DIR" "$LOG_DIR"

# Logging function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Terrapin Nation Forum Scraper Started ==="
log "Target: $BASE_URL"
log "Output: $RAW_DIR"
log "Log: $LOG_FILE"

# wget recursive download with proper rate limiting
# Flags:
#   -r, --recursive          : Follow links recursively
#   -l5                      : Depth limit 5 levels
#   -np, --no-parent         : Don't ascend to parent directory
#   -p, --page-requisites    : Get all assets (CSS, JS, images)
#   -k, --convert-links      : Convert links for offline viewing
#   -w1, --wait=1            : Wait 1 second between requests
#   --random-wait            : Randomize wait time (0.5-1.5x)
#   --limit-rate=1M          : Rate limit to 1MB/s
#   --user-agent             : Polite user agent
#   --no-clobber             : Don't re-download existing files
#   --timeout=30             : 30 second timeout per request
#   --tries=3                : Retry 3 times on failure
#   -A "*.html,*.htm,*.php"  : Accept HTML/PHP files
#   -R "*.jpg,*.png,*.gif"   : Reject images (optional - remove if you want images)

log "Starting wget recursive download..."

wget \
    --recursive \
    --level=5 \
    --no-parent \
    --page-requisites \
    --convert-links \
    --adjust-extension \
    --wait=1 \
    --random-wait \
    --limit-rate=1M \
    --user-agent="DeadheadLLM-Research/1.0 (Academic Research; Contact: research@deadhead.ai)" \
    --directory-prefix="$RAW_DIR" \
    --no-clobber \
    --timeout=30 \
    --tries=3 \
    --accept="*.html,*.htm,*.php" \
    --reject="*.jpg,*.png,*.gif,*.jpeg,*.css,*.js" \
    --no-check-certificate \
    -o "${LOG_DIR}/wget.log" \
    "$BASE_URL" 2>&1 &

WGET_PID=$!
log "wget started with PID: $WGET_PID"
echo "$WGET_PID" > "${LOG_DIR}/wget.pid"

log "=== Scraper running in background ==="
log "Monitor progress: tail -f ${LOG_DIR}/wget.log"
log "Check PID: cat ${LOG_DIR}/wget.pid"
log "Stop scraper: kill \$(cat ${LOG_DIR}/wget.pid)"

# Wait for wget to complete (or run in background)
wait $WGET_PID
WGET_EXIT=$?

if [ $WGET_EXIT -eq 0 ]; then
    log "=== Scraping completed successfully ==="
    
    # Count downloaded files
    FILE_COUNT=$(find "$RAW_DIR" -type f \( -name "*.html" -o -name "*.htm" -o -name "*.php" \) | wc -l)
    TOTAL_SIZE=$(du -sh "$RAW_DIR" | cut -f1)
    
    log "Files downloaded: $FILE_COUNT"
    log "Total size: $TOTAL_SIZE"
    log "Output directory: $RAW_DIR"
else
    log "=== Scraping completed with errors (exit code: $WGET_EXIT) ==="
    log "Check ${LOG_DIR}/wget.log for details"
fi

log "=== Scraper finished ==="
