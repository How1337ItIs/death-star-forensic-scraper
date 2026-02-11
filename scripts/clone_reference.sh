#!/usr/bin/env bash
# Clone all reference scrapers/archivers for pattern study.
# Run from repo root: ./scripts/clone_reference.sh
# reference/ is in .gitignore.

set -e
cd "$(dirname "$0")/.."
mkdir -p reference

repos=(
  "https://github.com/webrecorder/warcio.git:warcio"
  "https://github.com/webrecorder/py-wacz.git:py-wacz"
  "https://github.com/webrecorder/browsertrix-crawler.git:browsertrix-crawler"
  "https://github.com/ArchiveBox/ArchiveBox.git:ArchiveBox"
  "https://github.com/gildas-lormeau/SingleFile.git:SingleFile"
  "https://github.com/internetarchive/heritrix3.git:heritrix3"
  "https://github.com/scrapy/scrapy.git:scrapy"
  "https://github.com/q-m/scrapy-webarchive.git:scrapy-webarchive"
  "https://github.com/N0taN3rd/Squidwarc.git:Squidwarc"
  "https://github.com/webrecorder/archiveweb.page.git:archiveweb.page"
  "https://github.com/ganapativs/puppeteer-warc.git:puppeteer-warc"
  "https://github.com/turicas/crau.git:crau"
  "https://github.com/webrecorder/warcit.git:warcit"
  "https://github.com/ArchiveTeam/grab-site.git:grab-site"
  "https://github.com/webrecorder/pywb.git:pywb"
  "https://github.com/reprozip-news-apps/reprozip-web.git:reprozip-web"
  "https://github.com/rhizome-conifer/conifer.git:conifer"
  "https://github.com/harvard-lil/perma.git:perma"
  "https://github.com/go-shiori/shiori.git:shiori"
)

for spec in "${repos[@]}"; do
  url="${spec%%:*}"
  name="${spec##*:}"
  if [ -d "reference/$name" ]; then
    echo "skip (exists): reference/$name"
  else
    echo "clone: $name"
    git clone --depth 1 "$url" "reference/$name"
  fi
done

echo "done. reference/" && ls reference
