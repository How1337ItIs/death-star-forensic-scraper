# Old Scraper Techniques Analysis

**Date:** 2026-01-05  
**Source:** `remilianet-sounds/COMPLETE_SCRAPER.js`  
**Status:** ✅ Analysis Complete - Missing Techniques Identified

## Techniques We're Missing

### 1. ✅ **Hover Over Elements to Trigger Interactions** (CRITICAL)
**Location:** Phase 4 in old scraper  
**Purpose:** Triggers audio/sounds that only play on hover/click  
**Implementation:**
```javascript
// Hover over EVERY element to trigger sounds
const selectors = [
  'a', 'button', '[role="button"]', 'nav a', '.card',
  '[class*="friend"]', '[class*="profile"]', 'li',
  '[onclick]', 'img', 'svg', '[class*="icon"]'
];

for (const selector of selectors) {
  const elements = await page.$$(selector);
  for (let i = 0; i < Math.min(20, elements.length); i++) {
    await elements[i].hover();
    await new Promise(r => setTimeout(r, 50));
  }
}
```

**Why We Need It:**
- Many audio files only load/play on user interaction
- Hover effects trigger CSS transitions and JavaScript events
- Captures dynamic content that loads on interaction
- Essential for complete audio capture

---

### 2. ✅ **Computed Styles Extraction**
**Location:** Phase 6 in old scraper  
**Purpose:** Capture visual design information  
**Implementation:**
```javascript
const computedStyles = await page.evaluate(() => {
  const elements = document.querySelectorAll('button, a, .card, [class*="profile"]');
  const styles = [];
  
  elements.forEach((el, i) => {
    if (i < 50) {
      const computed = window.getComputedStyle(el);
      styles.push({
        selector: el.tagName + (el.className ? '.' + el.className.split(' ')[0] : ''),
        styles: {
          backgroundColor: computed.backgroundColor,
          color: computed.color,
          fontSize: computed.fontSize,
          fontFamily: computed.fontFamily,
          border: computed.border,
          borderRadius: computed.borderRadius,
          padding: computed.padding,
          margin: computed.margin
        }
      });
    }
  });
  
  return styles;
});
```

**Why We Need It:**
- Captures actual rendered styles (not just CSS files)
- Useful for understanding visual design
- Helps with reverse engineering UI components

---

### 3. ✅ **React Router Route Extraction from Scripts**
**Location:** Phase 3 DOM extraction  
**Purpose:** Discover routes by parsing JavaScript  
**Implementation:**
```javascript
// Try to extract React Router routes
const scripts = document.querySelectorAll('script');
scripts.forEach(script => {
  const text = script.textContent || '';
  const routeMatches = text.match(/path\s*:\s*["']([^"']+)["']/g);
  if (routeMatches) {
    routeMatches.forEach(m => {
      const route = m.match(/["']([^"']+)["']/)?.[1];
      if (route) data.allRoutes.push(route);
    });
  }
});
```

**Why We Need It:**
- Discovers routes that aren't visible in HTML
- Finds dynamic routes defined in JavaScript
- More complete route discovery

---

### 4. ✅ **Comprehensive DOM Extraction Structure**
**Location:** Phase 3  
**Purpose:** Structured extraction of all DOM elements  
**Implementation:**
```javascript
const domData = {
  allLinks: Array.from(document.querySelectorAll('a')).map(a => ({
    href: a.href,
    text: a.textContent?.trim(),
    classes: a.className
  })),
  allButtons: Array.from(document.querySelectorAll('button, [role="button"]')).map(b => ({
    text: b.textContent?.trim(),
    classes: b.className,
    id: b.id
  })),
  allImages: Array.from(document.querySelectorAll('img')).map(img => ({
    src: img.src,
    alt: img.alt
  })),
  allScripts: Array.from(document.querySelectorAll('script')).map(s => ({
    src: s.src,
    type: s.type,
    inline: !s.src
  })),
  allStyles: Array.from(document.querySelectorAll('link[rel="stylesheet"]')).map(l => ({
    href: l.href
  })),
  meta: Array.from(document.querySelectorAll('meta')).map(m => ({
    name: m.getAttribute('name'),
    content: m.getAttribute('content'),
    property: m.getAttribute('property')
  }))
};
```

**Why We Need It:**
- More structured than our current extraction
- Better organization for analysis
- Captures meta tags we might be missing

---

### 5. ✅ **Asset Download Limits**
**Location:** Phase 5  
**Purpose:** Prevent downloading too many large files  
**Implementation:**
```javascript
// Limit JS downloads to 50, CSS to 20
const uniqueJS = [...new Set(manifest.assets.javascript)];
for (const url of uniqueJS.slice(0, 50)) {
  await downloadAsset(url, 'js');
}

const uniqueCSS = [...new Set(manifest.assets.css)];
for (const url of uniqueCSS.slice(0, 20)) {
  await downloadAsset(url, 'css');
}
```

**Why We Need It:**
- Prevents downloading hundreds of JS/CSS files
- Saves time and storage
- Still captures essential assets

---

### 6. ✅ **Reusable Download Asset Function**
**Location:** Phase 5  
**Purpose:** Cleaner code for downloading assets  
**Implementation:**
```javascript
const downloadAsset = async (url, category) => {
  try {
    const urlObj = new URL(url);
    const filename = path.basename(urlObj.pathname) || `index_${Date.now()}`;
    const dir = path.join(ASSETS_DIR, category);
    const filepath = path.join(dir, filename);
    
    await downloadFile(url, filepath);
    console.log(`  ✓ ${filename}`);
    return filepath;
  } catch (err) {
    console.log(`  ✗ Failed: ${path.basename(url)}`);
    return null;
  }
};
```

**Why We Need It:**
- Cleaner, more maintainable code
- Consistent error handling
- Better logging

---

### 7. ✅ **Final State Extraction After All Interactions**
**Location:** Phase 8  
**Purpose:** Capture state after all interactions  
**Implementation:**
```javascript
const finalState = await page.evaluate(() => ({
  currentUrl: window.location.href,
  localStorage: Object.assign({}, localStorage),
  sessionStorage: Object.assign({}, sessionStorage),
  audioInterceptions: window.___audioInterceptions || []
}));
```

**Why We Need It:**
- Captures state changes from interactions
- Gets final audio interceptions after all hovers
- Complete snapshot of final state

---

## Techniques We Already Have

✅ Audio interception hooks (Audio, HTMLAudioElement, AudioContext, blob URLs)  
✅ Network request/response monitoring  
✅ DOM extraction (though less structured)  
✅ Asset downloading (though no limits)  
✅ Screenshots  
✅ Storage capture  
✅ API call capture  

---

## Priority Implementation Order

1. **🔴 CRITICAL:** Hover over elements to trigger interactions
2. **🟡 HIGH:** React Router route extraction from scripts
3. **🟡 HIGH:** Comprehensive DOM extraction structure
4. **🟢 MEDIUM:** Computed styles extraction
5. **🟢 MEDIUM:** Asset download limits
6. **🟢 MEDIUM:** Reusable download asset function
7. **🟢 LOW:** Final state extraction (we already do this)

---

## Implementation Plan

1. Add hover interaction phase after DOM extraction
2. Enhance DOM extraction with structured format
3. Add React Router route extraction
4. Add computed styles extraction
5. Add asset download limits
6. Refactor download logic into reusable function

---

*Analysis complete: 2026-01-05*
