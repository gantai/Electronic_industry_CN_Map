# zslib newspaper downloader

Downloads scanned newspaper pages from the Zhongshan Library digital memory
archive (`memory.zslib.cn`) and assembles **one PDF per issue date**, filed into
a folder named after the newspaper.

Pure PowerShell — no ImageMagick, Ghostscript, Python or NuGet packages.
Runs on Windows PowerShell 5.1 and PowerShell 7+.

## Quick start

```powershell
cd <this folder>

# 1. Confirm the URL patterns work from your machine (~30 seconds)
.\Get-ZslibNewspapers.ps1 -SelfTest

# 2. Build the catalogue: which titles have which dates (~15-25 minutes, no images)
.\Get-ZslibNewspapers.ps1 -OutputRoot D:\zslib -DiscoverOnly

# 3. Open D:\zslib\papers.csv, type the newspaper names into the Title column,
#    save as UTF-8, then do the real run
.\Get-ZslibNewspapers.ps1 -OutputRoot D:\zslib
```

If PowerShell refuses to run the file:

```powershell
Unblock-File .\Get-ZslibNewspapers.ps1
powershell -ExecutionPolicy Bypass -File .\Get-ZslibNewspapers.ps1 -SelfTest
```

## What it produces

```
D:\zslib\
    papers.csv                     BookId -> newspaper name  (you fill this in)
    index.csv                      BookId,Date,Pages         (discovery cache)
    scanned.csv                    which date range was probed per title
    logs\run-20260915-004512.log
    中山日報\
        1949-10-23.pdf             <- 4 pages, one JPEG per PDF page
        1949-10-24.pdf
        pages\19491023\001.jpg 002.jpg 003.jpg 004.jpg
        pages\19491024\001.jpg 002.jpg
```

Fill in `papers.csv` **before** the main run. Titles left blank fall back to the
BookId as the folder name; if you rename later, the old folders stay behind and
the pages are downloaded again into the new ones.

## URL scheme

```
http://memory.zslib.cn/profile/jpg50/<BookId>/<yyyyMMdd>/<nnn>.jpg
```

| Family | BookIds | Count |
|---|---|---|
| unpadded suffix | `21221909_1` … `21221909_19` | 19 |
| 3-digit suffix  | `21211909_001` … `21211909_028` | 28 |

Known-good samples, used by `-SelfTest`:

```
.../jpg50/21211909_014/19490209/001.jpg
.../jpg50/21221909_7/19491023/002.jpg
```

## How it works

1. **Discover** — a `HEAD` on page `001.jpg` for every date in the window tells
   the script which dates have an issue; it then walks page numbers upward until
   one is missing to get the page count. Results are cached in `index.csv`, so
   later runs skip this entirely.
2. **Download** — pages are fetched in parallel batches with retries and
   exponential backoff. A `404` is final; timeouts and 5xx are retried. A page
   already on disk that still parses as JPEG is not re-fetched, so an
   interrupted run resumes where it stopped.
3. **Assemble** — each JPEG is embedded directly into the PDF as a `DCTDecode`
   image XObject. The image bytes are copied verbatim: **no recompression, no
   quality loss**, and the PDF is barely larger than the JPEGs it holds.
   Page size comes from the JPEG's JFIF density when present, otherwise `-Dpi`
   (default 200).

## Parameters

| Parameter | Default | Notes |
|---|---|---|
| `-OutputRoot` | `.\zslib-newspapers` | Everything is written here |
| `-StartDate` / `-EndDate` | `1949-01-01` / `1949-12-31` | Date window to probe — **widen this if the collection spans other years** |
| `-Papers` | all 47 | e.g. `-Papers 21221909_7,21211909_014` |
| `-Concurrency` | `6` | Simultaneous requests. It is a public library server — please do not crank this |
| `-DelayMs` | `150` | Pause between batches, milliseconds |
| `-DelaySeconds` | off | Same pause in seconds; overrides `-DelayMs` |
| `-Retries` | `3` | Retry attempts for timeouts/5xx |
| `-MaxPages` | `60` | Ceiling on pages per issue |
| `-Dpi` | `200` | Assumed scan resolution when the JPEG has no density tag |
| `-DiscoverOnly` | off | Build the catalogue, download nothing |
| `-RefreshIndex` | off | Ignore `index.csv` and re-probe |
| `-Force` | off | Rebuild PDFs that already exist |
| `-RemovePagesAfterPdf` | off | Delete JPEGs once the PDF is written |
| `-SelfTest` | off | Fetch the two sample pages, report dimensions, build a test PDF |

## Pacing

The pause sits **between batches of `-Concurrency` requests**. So for a literal
*one download every 5 seconds*:

```powershell
.\Get-ZslibNewspapers.ps1 -OutputRoot D:\zslib -Concurrency 1 -DelaySeconds 5
```

Discovery is one request per title per day — 47 titles × 365 days ≈ 17,155
`HEAD` requests — so the pacing choice dominates the run. The script prints its
own estimate at startup before doing any work:

| Setting | Discovery phase |
|---|---|
| `-Concurrency 6` (default `-DelayMs 150`) | ~21 minutes |
| `-Concurrency 6 -DelaySeconds 5` | ~4h 15m |
| `-Concurrency 1 -DelaySeconds 5` | ~25 hours |

Discovery only happens once — `index.csv` is written after **each title**, so
Ctrl-C and re-run resumes rather than restarting. Downloading afterwards is far
smaller: only the dates that actually have issues.

A reasonable middle ground is `-Concurrency 2 -DelaySeconds 2` (~3 hours of
discovery, one request per second average). Narrowing `-StartDate`/`-EndDate`
cuts the probe count proportionally and helps more than anything else.

## Troubleshooting

**`-SelfTest` fails on both URLs.** The site is unreachable from this machine, or
the pattern has changed. Open one sample URL in a browser first.

**"every probe failed — the server was not reachable".** Network or proxy
problem, not an empty archive. The script deliberately refuses to cache this as
"no issues"; fix the connection and re-run — nothing was lost.

**"no issues in this date window" for every title.** The URL pattern is right but
your date window is wrong. Try one title across a wide window:
`-Papers 21221909_7 -StartDate 1940-01-01 -EndDate 1955-12-31`.

**Chinese folder names come out as garbage.** `papers.csv` was saved in ANSI or
GB2312. Re-save it as UTF-8 (in Excel: *Save As → CSV UTF-8*).

**An issue is missing its last pages.** Raise `-MaxPages`. The page walk stops at
the first gap, so a genuinely missing middle page truncates the issue.

**A PDF opens but a page is blank in an old reader.** That page is a progressive
JPEG (the log warns which). Current Acrobat, Edge, Chrome and SumatraPDF all
render these; very old readers may not.

## Please be considerate

This points at a public library's server holding digitised 1949 newspapers. The
defaults are deliberately gentle. Leave `-Concurrency` at 6 or below, keep
`-DelayMs`, and run discovery once rather than repeatedly with `-RefreshIndex`.
Check the archive's own terms for how the scans may be used.
