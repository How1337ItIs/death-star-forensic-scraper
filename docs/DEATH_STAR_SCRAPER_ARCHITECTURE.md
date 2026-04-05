# Death Star Scraper Architecture

**Date:** 2026-01-05  
**Status:** ✅ IMPLEMENTED  
**Philosophy:** "Brew the whole thing up from space" - Everything automatic, no manual phases

## Core Principle

**The scraper should automatically capture and download EVERYTHING during network interception. No manual phases. No post-processing. Everything flows through the response handler.**

## Architecture

### 1. Network Interception Layer (Death Star Core)

**Request Handler:**
- Categorizes ALL assets as they're requested (images, videos, audio, fonts, CSS, JS)
- Tracks everything in manifest
- No blocking - just categorization

**Response Handler (THE DEATH STAR):**
- **Automatic Asset Downloading**: Uses `response.buffer()` to get authenticated response bodies
- **Direct Asset Capture**: Images, videos, audio, fonts, CSS, JS downloaded immediately
- **API Response Parsing**: Extracts embedded URLs from JSON responses (like beetle-cards)
- **Automatic Image Download**: When beetle-cards API is captured, immediately extracts all image URLs and downloads them through authenticated session
- **Zero Manual Phases**: Everything happens automatically during network flow

### 2. Key Features

#### Automatic Asset Downloading
```javascript
// Response handler automatically downloads ALL assets using authenticated session
page.on('response', async response => {
  // Videos - download immediately
  if (isVideo) {
    const buffer = await response.buffer(); // Uses authenticated session
    fs.writeFileSync(filepath, buffer);
  }
  
  // Images - download immediately (including beetle cards)
  if (isImage) {
    const buffer = await response.buffer(); // Uses authenticated session
    fs.writeFileSync(filepath, buffer);
  }
  
  // Audio, fonts, CSS, JS - all automatic
});
```

#### API Response Parsing & Auto-Download
```javascript
// When beetle-cards API is captured, automatically extract and download images
if (url.includes('beetle-cards') && body) {
  // Extract all image URLs
  const imageUrls = extractImageUrls(body);
  
  // Download each through authenticated session
  for (const imageUrl of imageUrls) {
    const imageData = await page.evaluate(async (url) => {
      const resp = await fetch(url); // Uses browser's cookies/session
      const arrayBuffer = await resp.arrayBuffer();
      // Convert to base64 and return
    }, imageUrl);
    
    // Save immediately
    fs.writeFileSync(filepath, Buffer.from(imageData.base64, 'base64'));
  }
}
```

### 3. What Gets Captured Automatically

✅ **All Direct Assets** (via response.buffer()):
- Images (including authenticated beetle card images)
- Videos
- Audio
- Fonts
- CSS
- JavaScript

✅ **Embedded URLs from API Responses**:
- Beetle card images (icon, background, character) from beetle-cards API
- Any other image URLs found in JSON responses

✅ **Network Requests**:
- All requests logged
- All responses captured
- API calls with retry logic

✅ **WebSocket Messages**:
- Real-time chat data
- All WebSocket frames

✅ **Storage Data**:
- localStorage
- sessionStorage
- Cookies

✅ **DOM Snapshots**:
- Full HTML for each route
- Screenshots
- Computed styles

### 4. No Manual Phases

**REMOVED:**
- ❌ Phase 6.5: Manual beetle image download
- ❌ Post-scrape asset download phase
- ❌ Manual API response parsing

**AUTOMATIC:**
- ✅ Assets downloaded during response handler
- ✅ API responses parsed and images downloaded immediately
- ✅ Everything flows through network interception

### 5. Benefits

1. **Fully Automatic**: No manual intervention needed
2. **Authenticated Session**: All downloads use browser's authenticated session
3. **Real-time**: Assets captured as they're requested
4. **Complete**: Nothing missed - everything flows through interception
5. **Efficient**: No duplicate downloads, no post-processing

### 6. Implementation Details

#### Response Handler Structure
```javascript
page.on('response', async response => {
  // 1. Check status (skip 4xx/5xx)
  // 2. Download direct assets (videos, audio, images, fonts, CSS, JS)
  // 3. Capture API responses
  // 4. Parse API responses for embedded URLs
  // 5. Download embedded URLs through authenticated session
  // All automatic, no manual phases
});
```

#### Asset Organization
```
assets/
├── videos/          # All video files
├── audio/           # All audio files
├── images/
│   ├── beetle_cards/
│   │   ├── icons/
│   │   ├── backgrounds/
│   │   └── characters/
│   └── [domain]/     # Other images by domain
├── fonts/           # All font files
├── css/             # All CSS files
└── js/              # All JavaScript files
```

### 7. Comparison: Before vs After

**BEFORE (Manual Phases):**
- Request handler: Categorize assets
- Response handler: Capture API calls
- Phase 6.5: Manually download beetle images
- Post-scrape: Download all assets
- ❌ Multiple phases, manual intervention

**AFTER (Death Star):**
- Request handler: Categorize assets
- Response handler: Download ALL assets + Parse APIs + Download embedded URLs
- ✅ Single automatic flow, zero manual phases

### 8. Key Insight

**The "Death Star" pattern:**
1. Intercept everything at the network level
2. Download assets immediately using authenticated session
3. Parse API responses automatically
4. Extract and download embedded URLs automatically
5. Everything happens during network flow - no post-processing

**Result:** The scraper "brews the whole thing up from space" - everything is automatic, comprehensive, and uses the authenticated session throughout.

---

*"The scraper should already be a death star scraper that already brews the whole thing up from space."* - User directive 2026-01-05
