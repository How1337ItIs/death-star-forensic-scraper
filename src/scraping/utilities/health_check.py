"""
Scraper Health Check
====================

Monitors scraper health and logs status to shared_memory.
Runs continuously, checking every 5 minutes.

Usage:
    python health_check.py

    # Or via supervisor
    supervisorctl start scraper_health
"""

import json
import time
import logging
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.checkpoint import CheckpointManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper_health")

# Scrapers to monitor
SCRAPERS = [
    "rukind",
    # Add more as created
]

SHARED_MEMORY_PATH = Path("system/coordination/shared_memory/shared_memory.jsonl")
CHECK_INTERVAL = 300  # 5 minutes


def check_scraper_health(name: str) -> dict:
    """Check health of a single scraper."""
    try:
        cp = CheckpointManager(name)
        stats = cp.stats()
        cp.close()
        return {
            "name": name,
            "status": "healthy",
            "stats": stats
        }
    except Exception as e:
        return {
            "name": name,
            "status": "error",
            "error": str(e)
        }


def log_to_shared_memory(message: dict):
    """Log health status to shared memory."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "agent": "SCRAPER_HEALTH",
        "type": "health_check",
        "summary": message.get("summary", ""),
        "relevant_to": ["DONNA", "HUNTER", "KEITH"],
        "details": message
    }

    with open(SHARED_MEMORY_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def run_health_check():
    """Run a single health check cycle."""
    results = []
    for scraper in SCRAPERS:
        result = check_scraper_health(scraper)
        results.append(result)

    # Summarize
    healthy = sum(1 for r in results if r["status"] == "healthy")
    total = len(results)

    summary = f"Scraper health: {healthy}/{total} healthy"

    # Log any issues
    issues = [r for r in results if r["status"] != "healthy"]
    if issues:
        summary += f". Issues: {[r['name'] for r in issues]}"

    logger.info(summary)

    # Only log to shared memory if there are issues (reduce noise)
    if issues:
        log_to_shared_memory({
            "summary": summary,
            "results": results
        })

    return results


def main():
    """Main loop - runs continuously."""
    logger.info(f"Starting scraper health monitor. Checking every {CHECK_INTERVAL}s")

    while True:
        try:
            run_health_check()
        except Exception as e:
            logger.error(f"Health check error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    # Single check mode for testing
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run single check and exit")
    args = parser.parse_args()

    if args.once:
        results = run_health_check()
        print(json.dumps(results, indent=2))
    else:
        main()
