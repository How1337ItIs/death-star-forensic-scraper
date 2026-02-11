# Push this repo to GitHub

The folder is already a git repo on `main`. Two ways to publish:

---

## Option A: Copy token from deadhead-llm (sister project)

If you use **deadhead-llm**, put your GitHub token there once and reuse it here:

1. In **deadhead-llm**, add to `deadhead-llm\.env` (create if needed):
   ```bash
   GITHUB_TOKEN=your_github_personal_access_token
   ```
2. From this folder run:
   ```powershell
   .\copy_token_from_deadhead_llm.ps1
   ```
   That copies the token to `%USERPROFILE%\.github-mcp-token` and runs the create/push script.

---

## Option B: Script (uses same token as Cursor GitHub MCP)

If you use the Cursor GitHub MCP, your token is in **`%USERPROFILE%\.github-mcp-token`** (one line, no quotes). From this folder:

```powershell
.\create_and_push_repo.ps1
```

The script will create the public repo and push. If GitHub CLI (`gh`) is in your PATH, it uses that instead; otherwise it uses the token file.

If the token file is missing, create it:

1. GitHub → Settings → Developer settings → Personal access tokens → Generate new token (classic).
2. Give it `repo` scope.
3. Put the token in `C:\Users\natha\.github-mcp-token` (one line, no quotes).

---

## Option C: Manual (create repo in browser, then push)

### 1. Create the repo on GitHub

1. Go to **https://github.com/new**
2. **Repository name:** `death-star-forensic-scraper`
3. **Description:** `Full forensic web scraper – WARC, HAR, DOM, assets. One command, any target.`
4. **Public**; do **not** add README / .gitignore / license.
5. **Create repository**

### 2. Push from this folder

Replace `YOUR_GITHUB_USERNAME` with your GitHub username:

```bash
cd death-star-forensic-scraper
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/death-star-forensic-scraper.git
git push -u origin main
```

SSH:

```bash
git remote add origin git@github.com:YOUR_GITHUB_USERNAME/death-star-forensic-scraper.git
git push -u origin main
```

---

**GitHub CLI:** If you prefer `gh`, install with `winget install GitHub.cli`, run `gh auth login`, then from this folder: `gh repo create death-star-forensic-scraper --public --source . --remote origin --push`.
