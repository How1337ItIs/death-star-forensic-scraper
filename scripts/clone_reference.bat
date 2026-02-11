@echo off
REM Clone all reference scrapers/archivers for pattern study.
REM Run from repo root: scripts\clone_reference.bat
REM reference/ is in .gitignore.

cd /d "%~dp0\.."
if not exist reference mkdir reference

call :clone "https://github.com/webrecorder/warcio.git" "warcio"
call :clone "https://github.com/webrecorder/py-wacz.git" "py-wacz"
call :clone "https://github.com/webrecorder/browsertrix-crawler.git" "browsertrix-crawler"
call :clone "https://github.com/ArchiveBox/ArchiveBox.git" "ArchiveBox"
call :clone "https://github.com/gildas-lormeau/SingleFile.git" "SingleFile"
call :clone "https://github.com/internetarchive/heritrix3.git" "heritrix3"
call :clone "https://github.com/scrapy/scrapy.git" "scrapy"
call :clone "https://github.com/q-m/scrapy-webarchive.git" "scrapy-webarchive"
call :clone "https://github.com/N0taN3rd/Squidwarc.git" "Squidwarc"
call :clone "https://github.com/webrecorder/archiveweb.page.git" "archiveweb.page"
call :clone "https://github.com/ganapativs/puppeteer-warc.git" "puppeteer-warc"
call :clone "https://github.com/turicas/crau.git" "crau"
call :clone "https://github.com/webrecorder/warcit.git" "warcit"
call :clone "https://github.com/ArchiveTeam/grab-site.git" "grab-site"
call :clone "https://github.com/webrecorder/pywb.git" "pywb"
call :clone "https://github.com/reprozip-news-apps/reprozip-web.git" "reprozip-web"
call :clone "https://github.com/rhizome-conifer/conifer.git" "conifer"
call :clone "https://github.com/harvard-lil/perma.git" "perma"
call :clone "https://github.com/go-shiori/shiori.git" "shiori"

echo done. reference/
dir reference
exit /b 0

:clone
if exist "reference\%~2" (
  echo skip ^(exists^): reference\%~2
) else (
  echo clone: %~2
  git clone --depth 1 "%~1" "reference\%~2"
)
exit /b 0
