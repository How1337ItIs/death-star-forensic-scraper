# Forum Acquisition Status

**Last Updated:** 2026-01-10 by HUNTER

## Indexed Collections Overview

| Collection | Vectors | Primary Sources |
|------------|---------|-----------------|
| `forum_posts` | 637,997 | Terrapin Nation, RuKind Songs, Reddit, misc |
| `fan_discussions` | 1,187,638 | Usenet rec.music.gdead |

---

## Indexed (Qdrant `forum_posts` collection: 637,997 vectors)

### Terrapin Nation (via Wayback Machine)
- **Status:** ✅ COMPLETE (2026-01-10)
- **Posts:** 6,780 indexed
- **Topics:** 410 (from 422 available in Wayback)
- **Source:** `data/raw/forum_posts/terrapin_nation_wayback/`
- **Scraper:** `scripts/scraping/forums/terrapin_wayback_scraper.py`
- **Indexer:** `scripts/indexing/community/index_terrapin_nation_v17.py`
- **Notes:** Live site has CAPTCHA protection. Used Wayback Machine archives (2015-2025).

### Reddit r/gratefuldead
- **Status:** ✅ COMPLETE
- **Posts:** 257 indexed
- **Source:** `data/community/forums/reddit_gratefuldead/`
- **Script:** `scripts/indexing/community/index_reddit_posts.py`
- **Notes:** Top posts (all-time + yearly), tour discussions

## Not Indexed (Gaps)

### The WELL (Dead Songs Conference)
- **Status:** ❌ LOGIN PAGES - Auth wall
- **Files:** 196 topic files in `data/community/forums/well_deadsongs/`
- **Problem:** All files contain login form HTML, not actual discussions
- **Script:** `scripts/acquisition/community/scrape_well_iterative.py`
  - Current: Tries unauthenticated access to `people.well.com/conf/deadsongs.vue`
  - Missing: Cookie/session authentication
- **Action Needed:**
  1. Obtain WELL membership (requires paid subscription: ~$15/month)
  2. Add session auth to scraper (cookie-based login)
  3. Add env vars: `WELL_USERNAME`, `WELL_PASSWORD` or `WELL_SESSION_COOKIE`
- **URL Format:** `https://people.well.com/conf/deadsongs.vue/topics/{num}.html`
- **Potential Value:** HIGH - Original Dead community discussions from 1980s-present
- **Historical Significance:** One of oldest online Dead communities (since 1985)

### RuKind Song Forums
- **Status:** ✅ COMPLETE (2026-01-10)
- **Posts:** 7,230 indexed
- **Threads:** 1,293 (from 321 song-specific subforums)
- **Source:** `data/community/forums/rukind/songs/all_song_threads.jsonl`
- **Scraper:** `scripts/scraping/forums/rukind_song_forums.py` (HEALY)
- **Indexer:** `scripts/indexing/community/index_rukind_songs.py` (BILLY)
- **Notes:** phpBB3 forum with dedicated subforum per song. Guitar techniques, Jerry tone, version comparisons.

### RuKind Equipment Forum
- **Status:** ⚠️ PARTIALLY SCRAPED - Equipment threads separate from song forums
- **Files:** Index HTML + ~500 threads in `data/community/forums/rukind/threads.jsonl`
- **Script:** `scripts/acquisition/community/scrape_rukind_threads.py` (HUNTER V12-ACQUIRE-001)
- **Topics Available:** 105 unique equipment topics
- **Potential Value:** MEDIUM - Equipment/tech discussions (gear details, Wall of Sound)

## Indexed (Qdrant `fan_discussions` collection: 1,187,638 vectors)

### Usenet rec.music.gdead
- **Status:** ✅ COMPLETE (indexed to fan_discussions)
- **Posts:** 850,427 in JSONL → 1,187,638 vectors indexed
- **Coverage:** 2003-2009 (note: 1987-2002 gap from archive.org source)
- **Source:** `data/community/forums/usenet_rec_music_gdead/usenet_gdead.jsonl`
- **Raw Archives:**
  - `mbox/rec.music.gdead.20140725.mbox.gz` (995MB)
  - `mbox/rec.music.gdead.20141207.mbox.gz` (325MB)
  - `mbox/rec.music.gdead.20150117.mbox.gz` (317MB)
  - `archive_org/*.csv` (original metadata exports)
- **Indexer:** `scripts/indexing/community/index_usenet_v16.py`
- **Quality Metrics:**
  - Spam/off-topic: 0.1% (very clean)
  - Short posts (<100 chars): 6.4%
- **Remaining Gap:** 1987-2002 posts not in current archive
  - These early years may be available via Google Groups scraping
  - WELL/early forums may fill this gap

## Acquisition Priority

1. **The WELL** (HIGH) - Authentic community voice, historical significance (1985-present)
2. **Usenet 1987-2002** (MEDIUM) - Pre-2003 posts missing from archive.org source
3. **RuKind Full Scrape** (MEDIUM) - 100+ topics waiting, scraper ready

## Related Files

- Topic index: `data/community/forums/WELL_ALL_TOPICS.json`
- Reddit summary: `data/community/forums/reddit_gratefuldead/_summary.json`
- Usenet JSONL: `data/community/forums/usenet_rec_music_gdead/usenet_gdead.jsonl`
- Usenet indexer: `scripts/indexing/community/index_usenet_v16.py`

---

*Last verified by HUNTER 2026-01-10: Usenet fully indexed (1.19M vectors), document corrected from outdated "METADATA ONLY" status.*
