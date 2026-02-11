# Push this repo to GitHub

The folder is already a git repo with one commit on `main`. To publish it:

## 1. Create a new repository on GitHub

1. Go to **https://github.com/new**
2. **Repository name:** `death-star-forensic-scraper`
3. **Description:** `Full forensic web scraper – WARC, HAR, DOM, assets. One command, any target.`
4. Choose **Public**
5. **Do not** add a README, .gitignore, or license (this repo already has them)
6. Click **Create repository**

## 2. Push from this folder

Replace `YOUR_GITHUB_USERNAME` with your GitHub username (or org):

```bash
cd death-star-forensic-scraper
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/death-star-forensic-scraper.git
git push -u origin main
```

If you use SSH:

```bash
git remote add origin git@github.com:YOUR_GITHUB_USERNAME/death-star-forensic-scraper.git
git push -u origin main
```

Done. The repo will be public and cloneable.
