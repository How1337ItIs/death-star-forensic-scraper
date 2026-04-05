# How to Export X (Twitter) Cookies for Scraping

X/Twitter requires authentication to access community content. Here's how to export your login cookies.

## Method 1: EditThisCookie (Chrome - Easiest)

1. **Install Extension**
   - Go to: https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfbg
   - Click "Add to Chrome"

2. **Log into X**
   - Go to https://x.com
   - Log in with your account

3. **Export Cookies**
   - Click the cookie icon in your toolbar
   - Click the export button (looks like: `[↓]`)
   - This copies cookies to clipboard as JSON

4. **Save to File**
   - Create a new file: `x_cookies.json`
   - Paste the clipboard content
   - Save the file

5. **Run Scraper**
   ```bash
   python src/scraping/x_community_scraper.py \
       --target https://x.com/i/communities/2012672579388022846 \
       --cookies x_cookies.json
   ```

## Method 2: Browser DevTools (Any Browser)

1. **Open DevTools**
   - Go to https://x.com and log in
   - Press F12 to open DevTools
   - Go to "Application" tab (Chrome) or "Storage" tab (Firefox)

2. **Find Cookies**
   - Expand "Cookies" in the left sidebar
   - Click on `https://x.com`

3. **Find auth_token**
   - Look for a cookie named `auth_token`
   - Copy its value

4. **Run Scraper**
   ```bash
   python src/scraping/x_community_scraper.py \
       --target https://x.com/i/communities/2012672579388022846 \
       --auth-token YOUR_AUTH_TOKEN_VALUE
   ```

## Method 3: Cookie-Editor Extension (Firefox/Chrome)

1. Install Cookie-Editor:
   - Chrome: https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm
   - Firefox: https://addons.mozilla.org/firefox/addon/cookie-editor/

2. Log into X

3. Click Cookie-Editor icon → Export → JSON

4. Save to file and use with `--cookies`

## Important Notes

- **Cookies expire!** If scraping fails after a while, re-export cookies
- **Don't share your cookies** - they give full access to your account
- **Use a burner account** if doing heavy scraping (risk of ban)
- **Rate limit yourself** - X will throttle/ban aggressive scraping

## Target Community

Your competitor's community:
```
https://x.com/i/communities/2012672579388022846
```

Community ID: `2012672579388022846`

## Full Command

```bash
cd c:\Users\natha\sol-cannabis
python src/scraping/x_community_scraper.py \
    --target https://x.com/i/communities/2012672579388022846 \
    --cookies x_cookies.json \
    --max-posts 200 \
    --max-scrolls 30
```

## Output

Results saved to: `data/x_communities/2012672579388022846/`
- `community_data.json` - Full structured data
- `posts.md` - Human-readable posts
- `raw_api_responses.json` - Raw API data for analysis
- `*_screenshot.png` - Screenshot of community page
