#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Death Star Forensic Scraper Initialization ===${NC}"

# 1. Check/Create Virtual Environment
if [ ! -d "venv" ]; then
    echo -e "${GREEN}Creating virtual environment...${NC}"
    python3 -m venv venv
else
    echo -e "${GREEN}Virtual environment found.${NC}"
fi

# 2. Activate Virtual Environment
source venv/bin/activate

# 3. Install Dependencies
echo -e "${GREEN}Checking dependencies...${NC}"
pip install -r requirements.txt > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Dependencies installed.${NC}"
else
    echo -e "${GREEN}Installing dependencies (this may take a minute)...${NC}"
    pip install -r requirements.txt
fi

# 4. Install Playwright Browsers (Required for scraping)
if [ ! -d ~/.cache/ms-playwright ] && [ ! -d "venv/lib/python3.12/site-packages/playwright/driver/package/.local-browsers" ]; then
     echo -e "${GREEN}Installing browser binaries...${NC}"
     playwright install chromium
else
     echo -e "${GREEN}Browsers appear to be installed (running check anyway)...${NC}"
     playwright install chromium
fi

# 5. Launch Dashboard
echo -e "${BLUE}=== Launching Mission Control ===${NC}"
echo -e "${GREEN}Dashboard available at: http://localhost:8765${NC}"

# Try to open browser automatically
if command -v wslview &> /dev/null; then
    wslview http://localhost:8765 &
elif command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:8765 &
fi

# Run the server
uvicorn dashboard:app --host 0.0.0.0 --port 8765 --reload
