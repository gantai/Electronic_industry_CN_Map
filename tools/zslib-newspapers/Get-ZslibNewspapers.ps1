<#
.SYNOPSIS
    Downloads scanned newspaper pages from memory.zslib.cn (Zhongshan Library
    digital memory archive) and assembles one PDF per issue date, filed into a
    folder named after the newspaper.

.DESCRIPTION
    Page images live at:
        http://memory.zslib.cn/profile/jpg50/<BookId>/<yyyyMMdd>/<nnn>.jpg

    Two BookId families are covered by default:
        21221909_1  .. 21221909_19    (19 titles, unpadded suffix)
        21211909_001 .. 21211909_028  (28 titles, 3-digit padded suffix)

    The script:
      1. probes which dates exist for each title (HEAD on page 001) and how many
         pages each issue has, caching the result in index.csv;
      2. downloads the pages in parallel with retries and resume;
      3. embeds the JPEGs losslessly into a PDF (DCTDecode) with no external
         tools - no ImageMagick, Ghostscript, Python or NuGet required.

    Output layout:
        <OutputRoot>\
            papers.csv                     BookId -> newspaper name (edit this)
            index.csv                      BookId,Date,Pages (discovery cache)
            scanned.csv                    which date range was probed per title
            logs\run-<timestamp>.log
            <NewspaperName>\
                1949-02-09.pdf
                pages\19490209\001.jpg ...

    Requires Windows PowerShell 5.1 or PowerShell 7+.

.EXAMPLE
    # 1. Verify the URL patterns and the PDF writer (fast, ~30 seconds)
    .\Get-ZslibNewspapers.ps1 -SelfTest

.EXAMPLE
    # 2. Build the catalogue only (no image downloads)
    .\Get-ZslibNewspapers.ps1 -DiscoverOnly

.EXAMPLE
    # 3. Download everything for 1949
    .\Get-ZslibNewspapers.ps1 -OutputRoot D:\zslib

.EXAMPLE
    # One title, wider date range
    .\Get-ZslibNewspapers.ps1 -Papers 21221909_7 -StartDate 1945-01-01 -EndDate 1949-12-31
#>
[CmdletBinding()]
param(
    # Where everything is written.
    [string]$OutputRoot = (Join-Path $PSScriptRoot 'zslib-newspapers'),

    # Root of the image tree on the server.
    [string]$BaseUrl = 'http://memory.zslib.cn/profile/jpg50',

    # Sent as Referer; also the human-facing catalogue page.
    [string]$RefererUrl = 'http://memory.zslib.cn/book/',

    # Inclusive date window to probe for issues.
    [datetime]$StartDate = '1949-01-01',
    [datetime]$EndDate   = '1949-12-31',

    # Limit the run to specific BookIds. Default: all 47.
    [string[]]$Papers,

    # Highest page number an issue may have.
    [int]$MaxPages = 60,

    # Simultaneous HTTP requests. Keep this modest - it is a public library server.
    [ValidateRange(1, 32)][int]$Concurrency = 6,

    # Retry attempts for network errors / 5xx (404 is never retried).
    [ValidateRange(0, 8)][int]$Retries = 3,

    # Pause between request batches, milliseconds.
    [int]$DelayMs = 150,

    # Same pause expressed in seconds; overrides -DelayMs when supplied.
    # The pause sits between batches of -Concurrency requests, so for a literal
    # "one download every 5 seconds" use -Concurrency 1 -DelaySeconds 5.
    [double]$DelaySeconds = 0,

    # Assumed scan resolution when the JPEG carries no JFIF density.
    # Only affects the PDF page dimensions, never the image data.
    [ValidateRange(36, 1200)][int]$Dpi = 200,

    # Probe and cache the catalogue, download nothing.
    [switch]$DiscoverOnly,

    # Ignore index.csv and re-probe every date.
    [switch]$RefreshIndex,

    # Rebuild PDFs that already exist.
    [switch]$Force,

    # Delete the JPEGs once the PDF is written.
    [switch]$RemovePagesAfterPdf,

    # Fetch the two known-good sample URLs, report what came back, build a test PDF.
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
[System.Net.ServicePointManager]::DefaultConnectionLimit = 64

if ($DelaySeconds -gt 0) { $DelayMs = [int][Math]::Round($DelaySeconds * 1000) }

# ---------------------------------------------------------------- logging ----

$script:LogPath = $null

function Write-Log {
    param([string]$Message, [ValidateSet('INFO','WARN','ERROR','OK')][string]$Level = 'INFO')
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'HH:mm:ss'), $Level, $Message
    switch ($Level) {
        'ERROR' { Write-Host $line -ForegroundColor Red }
        'WARN'  { Write-Host $line -ForegroundColor Yellow }
        'OK'    { Write-Host $line -ForegroundColor Green }
        default { Write-Host $line }
    }
    if ($script:LogPath) { Add-Content -LiteralPath $script:LogPath -Value $line -Encoding UTF8 }
}

# ------------------------------------------------------------------ http -----

function New-HttpClient {
    param([int]$TimeoutSec = 90)
    Add-Type -AssemblyName System.Net.Http | Out-Null
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.AllowAutoRedirect = $true
    try {
        $handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
    } catch { }
    $client = New-Object System.Net.Http.HttpClient -ArgumentList $handler
    $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSec)
    $client.DefaultRequestHeaders.UserAgent.ParseAdd('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    try { $client.DefaultRequestHeaders.Referrer = [uri]$RefererUrl } catch { }
    return $client
}

function Test-JpegBytes {
    param([byte[]]$Bytes)
    return ($null -ne $Bytes -and $Bytes.Length -gt 512 -and
            $Bytes[0] -eq 0xFF -and $Bytes[1] -eq 0xD8 -and $Bytes[2] -eq 0xFF)
}

# Issues one batch of requests. $Items are objects carrying at least .Url.
function Invoke-HttpBatch {
    param(
        [object[]]$Items,
        [ValidateSet('Head','Get')][string]$Method = 'Get',
        $Client,
        [int]$Concurrency = 6,
        [int]$DelayMs = 150,
        [string]$Activity
    )

    $results = New-Object System.Collections.ArrayList
    if (-not $Items -or $Items.Count -eq 0) { return ,([object[]]@()) }

    $httpMethod = if ($Method -eq 'Head') { [System.Net.Http.HttpMethod]::Head } else { [System.Net.Http.HttpMethod]::Get }
    $done = 0

    for ($i = 0; $i -lt $Items.Count; $i += $Concurrency) {
        $upper = [Math]::Min($i + $Concurrency - 1, $Items.Count - 1)
        $chunk = @($Items[$i..$upper])

        $pending = @()
        foreach ($item in $chunk) {
            $req = New-Object System.Net.Http.HttpRequestMessage -ArgumentList $httpMethod, $item.Url
            $pending += [pscustomobject]@{
                Item = $item
                Req  = $req
                Task = $Client.SendAsync($req)
            }
        }

        foreach ($p in $pending) {
            $r = [pscustomobject]@{
                Item   = $p.Item
                Ok     = $false
                Status = 0
                Length = 0L
                Bytes  = $null
                Error  = $null
            }
            try {
                $resp = $p.Task.GetAwaiter().GetResult()
                $r.Status = [int]$resp.StatusCode
                if ($resp.IsSuccessStatusCode) {
                    if ($Method -eq 'Get') {
                        $r.Bytes = $resp.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
                        $r.Length = [long]$r.Bytes.Length
                        if (Test-JpegBytes $r.Bytes) { $r.Ok = $true }
                        else { $r.Error = "HTTP 200 but payload is not JPEG ($($r.Length) bytes)"; $r.Bytes = $null }
                    } else {
                        if ($null -ne $resp.Content.Headers.ContentLength) { $r.Length = [long]$resp.Content.Headers.ContentLength }
                        $r.Ok = $true
                    }
                }
                $resp.Dispose()
            } catch {
                $r.Error = $_.Exception.GetBaseException().Message
            } finally {
                $p.Req.Dispose()
            }
            [void]$results.Add($r)
        }

        $done += $chunk.Count
        if ($Activity) {
            Write-Progress -Activity $Activity -Status "$done / $($Items.Count)" `
                           -PercentComplete ([int](100 * $done / $Items.Count))
        }
        if ($DelayMs -gt 0) { Start-Sleep -Milliseconds $DelayMs }
    }

    if ($Activity) { Write-Progress -Activity $Activity -Completed }
    return ,([object[]]$results.ToArray())
}

# Same, but retries transient failures. 404/403/410 are treated as definitive.
function Invoke-HttpBatchWithRetry {
    param(
        [object[]]$Items,
        [ValidateSet('Head','Get')][string]$Method = 'Get',
        $Client,
        [int]$Concurrency = 6,
        [int]$DelayMs = 150,
        [int]$Retries = 3,
        [string]$Activity
    )

    if (-not $Items -or $Items.Count -eq 0) { return ,([object[]]@()) }

    $best      = @{}   # Url -> best result seen so far
    $remaining = @($Items)
    $attempt   = 0

    while ($remaining.Count -gt 0 -and $attempt -le $Retries) {
        if ($attempt -gt 0) {
            $wait = [Math]::Min(16, [Math]::Pow(2, $attempt))
            Write-Log ("retry {0}/{1} for {2} request(s) in {3}s" -f $attempt, $Retries, $remaining.Count, $wait) 'WARN'
            Start-Sleep -Seconds $wait
        }

        $label = if ($Activity -and $attempt -gt 0) { "$Activity (retry $attempt)" } else { $Activity }
        $res = Invoke-HttpBatch -Items $remaining -Method $Method -Client $Client `
                                -Concurrency $Concurrency -DelayMs $DelayMs -Activity $label

        $next = @()
        foreach ($r in $res) {
            $best[$r.Item.Url] = $r
            $definitive = $r.Ok -or ($r.Status -eq 404) -or ($r.Status -eq 403) -or ($r.Status -eq 410)
            if (-not $definitive) { $next += $r.Item }
        }
        $remaining = @($next)
        $attempt++
    }

    $final = foreach ($item in $Items) { $best[$item.Url] }
    return ,([object[]]$final)
}

# ------------------------------------------------------------- jpeg probe ----

function Get-JpegInfo {
    param([byte[]]$Bytes)

    if (-not (Test-JpegBytes $Bytes)) { return $null }

    $info = [pscustomobject]@{
        Width = 0; Height = 0; Components = 3
        DpiX = 0; DpiY = 0
        Progressive = $false; Adobe = $false
    }

    $i = 2
    while ($i -lt ($Bytes.Length - 1)) {
        if ($Bytes[$i] -ne 0xFF) { $i++; continue }
        $m = $Bytes[$i + 1]
        if ($m -eq 0xFF) { $i++; continue }
        # standalone markers
        if ($m -eq 0xD8 -or $m -eq 0x01 -or ($m -ge 0xD0 -and $m -le 0xD7)) { $i += 2; continue }
        # start of scan / end of image - header section is over
        if ($m -eq 0xDA -or $m -eq 0xD9) { break }
        if (($i + 3) -ge $Bytes.Length) { break }

        $len = ([int]$Bytes[$i + 2] -shl 8) -bor [int]$Bytes[$i + 3]
        if ($len -lt 2) { break }
        $seg = $i + 4

        if ($m -eq 0xE0 -and ($seg + 12) -le $Bytes.Length) {
            # APP0 / JFIF pixel density
            if ($Bytes[$seg] -eq 0x4A -and $Bytes[$seg+1] -eq 0x46 -and
                $Bytes[$seg+2] -eq 0x49 -and $Bytes[$seg+3] -eq 0x46 -and $Bytes[$seg+4] -eq 0x00) {
                $units = [int]$Bytes[$seg + 7]
                $dx = ([int]$Bytes[$seg + 8]  -shl 8) -bor [int]$Bytes[$seg + 9]
                $dy = ([int]$Bytes[$seg + 10] -shl 8) -bor [int]$Bytes[$seg + 11]
                if     ($units -eq 1) { $info.DpiX = $dx; $info.DpiY = $dy }
                elseif ($units -eq 2) { $info.DpiX = [int][Math]::Round($dx * 2.54); $info.DpiY = [int][Math]::Round($dy * 2.54) }
            }
        }
        elseif ($m -eq 0xEE) {
            $info.Adobe = $true
        }
        elseif ($m -ge 0xC0 -and $m -le 0xCF -and $m -ne 0xC4 -and $m -ne 0xC8 -and $m -ne 0xCC) {
            # start of frame
            if (($seg + 5) -lt $Bytes.Length) {
                $info.Height     = ([int]$Bytes[$seg + 1] -shl 8) -bor [int]$Bytes[$seg + 2]
                $info.Width      = ([int]$Bytes[$seg + 3] -shl 8) -bor [int]$Bytes[$seg + 4]
                $info.Components = [int]$Bytes[$seg + 5]
                if ($m -eq 0xC2 -or $m -eq 0xC6 -or $m -eq 0xCA -or $m -eq 0xCE) { $info.Progressive = $true }
            }
            break
        }

        $i += 2 + $len
    }

    if ($info.Width -le 0 -or $info.Height -le 0) { return $null }
    # reject nonsense densities
    if ($info.DpiX -lt 36 -or $info.DpiX -gt 2400) { $info.DpiX = 0 }
    if ($info.DpiY -lt 36 -or $info.DpiY -gt 2400) { $info.DpiY = 0 }
    return $info
}

# -------------------------------------------------------------- pdf writer ---

function Write-Bytes {
    param($Stream, [byte[]]$Data)
    $Stream.Write($Data, 0, $Data.Length)
}

# Embeds each JPEG as a DCTDecode image XObject - no recompression, one page each.
function New-PdfFromJpegs {
    param(
        [string[]]$JpegPaths,
        [string]$OutPath,
        [int]$FallbackDpi = 200,
        [string]$Title
    )

    if (-not $JpegPaths -or $JpegPaths.Count -eq 0) { throw "No pages supplied for $OutPath" }

    $ascii = [System.Text.Encoding]::ASCII
    $dir = Split-Path -Parent $OutPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $tmp = "$OutPath.part"

    $n         = $JpegPaths.Count
    $objCount  = 2 + 3 * $n          # catalog + pages + (image, content, page) * n
    $offsets   = New-Object 'long[]' ($objCount + 1)
    $skipped   = @()

    $fs = [System.IO.File]::Open($tmp, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        Write-Bytes $fs $ascii.GetBytes("%PDF-1.4`n")
        Write-Bytes $fs ([byte[]](0x25, 0xE2, 0xE3, 0xCF, 0xD3, 0x0A))

        $offsets[1] = $fs.Position
        Write-Bytes $fs $ascii.GetBytes("1 0 obj`n<< /Type /Catalog /Pages 2 0 R >>`nendobj`n")

        $kids = (0..($n - 1) | ForEach-Object { '{0} 0 R' -f (5 + 3 * $_) }) -join ' '
        $offsets[2] = $fs.Position
        Write-Bytes $fs $ascii.GetBytes("2 0 obj`n<< /Type /Pages /Count $n /Kids [$kids] >>`nendobj`n")

        for ($i = 0; $i -lt $n; $i++) {
            $imgNo = 3 + 3 * $i
            $cntNo = 4 + 3 * $i
            $pgNo  = 5 + 3 * $i

            $bytes = [System.IO.File]::ReadAllBytes($JpegPaths[$i])
            $info  = Get-JpegInfo $bytes
            if ($null -eq $info) { throw "Not a readable JPEG: $($JpegPaths[$i])" }
            if ($info.Progressive) { $skipped += (Split-Path -Leaf $JpegPaths[$i]) }

            $colorSpace = switch ($info.Components) {
                1 { '/DeviceGray' }
                4 { '/DeviceCMYK' }
                default { '/DeviceRGB' }
            }
            $decode = if ($info.Components -eq 4 -and $info.Adobe) { ' /Decode [1 0 1 0 1 0 1 0]' } else { '' }

            $dpiX = if ($info.DpiX -gt 0) { $info.DpiX } else { $FallbackDpi }
            $dpiY = if ($info.DpiY -gt 0) { $info.DpiY } else { $dpiX }
            $wPt  = [Math]::Round($info.Width  * 72.0 / $dpiX, 2)
            $hPt  = [Math]::Round($info.Height * 72.0 / $dpiY, 2)
            $wStr = $wPt.ToString([System.Globalization.CultureInfo]::InvariantCulture)
            $hStr = $hPt.ToString([System.Globalization.CultureInfo]::InvariantCulture)

            # image XObject
            $offsets[$imgNo] = $fs.Position
            Write-Bytes $fs $ascii.GetBytes(
                "$imgNo 0 obj`n<< /Type /XObject /Subtype /Image /Width $($info.Width) /Height $($info.Height)" +
                " /ColorSpace $colorSpace /BitsPerComponent 8 /Filter /DCTDecode$decode /Length $($bytes.Length) >>`nstream`n")
            Write-Bytes $fs $bytes
            Write-Bytes $fs $ascii.GetBytes("`nendstream`nendobj`n")

            # content stream
            $content = "q $wStr 0 0 $hStr 0 0 cm /Im0 Do Q`n"
            $cBytes  = $ascii.GetBytes($content)
            $offsets[$cntNo] = $fs.Position
            Write-Bytes $fs $ascii.GetBytes("$cntNo 0 obj`n<< /Length $($cBytes.Length) >>`nstream`n")
            Write-Bytes $fs $cBytes
            Write-Bytes $fs $ascii.GetBytes("endstream`nendobj`n")

            # page
            $offsets[$pgNo] = $fs.Position
            Write-Bytes $fs $ascii.GetBytes(
                "$pgNo 0 obj`n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 $wStr $hStr]" +
                " /Resources << /ProcSet [/PDF /ImageC /ImageB] /XObject << /Im0 $imgNo 0 R >> >>" +
                " /Contents $cntNo 0 R >>`nendobj`n")
        }

        # cross-reference table
        $xrefPos = $fs.Position
        $sb = New-Object System.Text.StringBuilder
        [void]$sb.Append("xref`n0 $($objCount + 1)`n")
        [void]$sb.Append("0000000000 65535 f `n")
        for ($o = 1; $o -le $objCount; $o++) {
            [void]$sb.Append(('{0:D10} 00000 n ' -f $offsets[$o]))
            [void]$sb.Append("`n")
        }
        [void]$sb.Append("trailer`n<< /Size $($objCount + 1) /Root 1 0 R >>`nstartxref`n$xrefPos`n%%EOF`n")
        Write-Bytes $fs $ascii.GetBytes($sb.ToString())
    }
    finally {
        $fs.Dispose()
    }

    Move-Item -LiteralPath $tmp -Destination $OutPath -Force
    if ($skipped.Count -gt 0) {
        Write-Log ("progressive JPEG(s) embedded in $(Split-Path -Leaf $OutPath): " +
                   ($skipped -join ', ') + " - most readers handle these, a few old ones do not") 'WARN'
    }
}

# ------------------------------------------------------------- catalogue -----

function Get-DefaultPaperIds {
    $ids = New-Object System.Collections.ArrayList
    foreach ($i in 1..19)  { [void]$ids.Add("21221909_$i") }
    foreach ($i in 1..28)  { [void]$ids.Add(('21211909_{0:D3}' -f $i)) }
    return ,([string[]]$ids.ToArray())
}

function Get-SafeName {
    param([string]$Name)
    $invalid = [System.IO.Path]::GetInvalidFileNameChars()
    $sb = New-Object System.Text.StringBuilder
    foreach ($ch in $Name.ToCharArray()) {
        if ($invalid -contains $ch) { [void]$sb.Append('_') } else { [void]$sb.Append($ch) }
    }
    return $sb.ToString().Trim().TrimEnd('.')
}

# papers.csv maps BookId -> folder name. Missing/blank titles fall back to the BookId.
function Import-TitleMap {
    param([string]$Path, [string[]]$AllIds)

    $map = @{}
    if (Test-Path -LiteralPath $Path) {
        foreach ($row in (Import-Csv -LiteralPath $Path -Encoding UTF8)) {
            if ($row.BookId -and $row.Title -and $row.Title.Trim()) {
                $map[$row.BookId.Trim()] = $row.Title.Trim()
            }
        }
    } else {
        $rows = foreach ($id in $AllIds) { [pscustomobject]@{ BookId = $id; Title = '' } }
        $rows | Export-Csv -LiteralPath $Path -NoTypeInformation -Encoding UTF8
        Write-Log "wrote title template: $Path  (fill in the Title column to name the folders)" 'WARN'
    }
    return $map
}

function Import-IndexCache {
    param([string]$IndexPath, [string]$ScannedPath)
    $issues  = @{}   # BookId -> (yyyyMMdd -> pageCount)
    $scanned = @{}   # BookId -> "start-end"

    if (Test-Path -LiteralPath $IndexPath) {
        foreach ($row in (Import-Csv -LiteralPath $IndexPath -Encoding UTF8)) {
            if (-not $issues.ContainsKey($row.BookId)) { $issues[$row.BookId] = @{} }
            $issues[$row.BookId][$row.Date] = [int]$row.Pages
        }
    }
    if (Test-Path -LiteralPath $ScannedPath) {
        foreach ($row in (Import-Csv -LiteralPath $ScannedPath -Encoding UTF8)) {
            $scanned[$row.BookId] = '{0}-{1}' -f $row.Start, $row.End
        }
    }
    return @{ Issues = $issues; Scanned = $scanned }
}

function Export-IndexCache {
    param([hashtable]$Issues, [hashtable]$Scanned, [string]$IndexPath, [string]$ScannedPath)

    $rows = foreach ($bookId in ($Issues.Keys | Sort-Object)) {
        foreach ($date in ($Issues[$bookId].Keys | Sort-Object)) {
            [pscustomobject]@{ BookId = $bookId; Date = $date; Pages = $Issues[$bookId][$date] }
        }
    }
    if ($rows) { $rows | Export-Csv -LiteralPath $IndexPath -NoTypeInformation -Encoding UTF8 }

    $srows = foreach ($bookId in ($Scanned.Keys | Sort-Object)) {
        $parts = $Scanned[$bookId] -split '-'
        [pscustomobject]@{ BookId = $bookId; Start = $parts[0]; End = $parts[1] }
    }
    if ($srows) { $srows | Export-Csv -LiteralPath $ScannedPath -NoTypeInformation -Encoding UTF8 }
}

# Probes every date in the window for page 001, then walks up the page numbers.
function Find-Issues {
    param(
        $Client, [string]$BookId,
        [datetime]$Start, [datetime]$End,
        [int]$MaxPages, [int]$Concurrency, [int]$DelayMs, [int]$Retries
    )

    $probes = New-Object System.Collections.ArrayList
    for ($d = $Start; $d -le $End; $d = $d.AddDays(1)) {
        $ds = $d.ToString('yyyyMMdd')
        [void]$probes.Add([pscustomobject]@{ Url = "$BaseUrl/$BookId/$ds/001.jpg"; Date = $ds })
    }

    $res = Invoke-HttpBatchWithRetry -Items ([object[]]$probes.ToArray()) -Method Head -Client $Client `
              -Concurrency $Concurrency -DelayMs $DelayMs -Retries $Retries `
              -Activity "$BookId  scanning $($Start.ToString('yyyy-MM-dd')) .. $($End.ToString('yyyy-MM-dd'))"

    # A 404 is a real "no issue that day". Anything else (DNS, refused, timeout,
    # 5xx) means we never got an answer - never let that masquerade as an empty
    # archive, or the empty result gets cached and the title is silently lost.
    $probed = $res.Count
    $failed = @($res | Where-Object { -not $_.Ok -and $_.Status -ne 404 }).Count
    $dates  = @($res | Where-Object { $_.Ok } | ForEach-Object { $_.Item.Date } | Sort-Object)

    if ($failed -gt 0) {
        $sample = @($res | Where-Object { -not $_.Ok -and $_.Status -ne 404 })[0]
        $why = if ($sample.Error) { $sample.Error } else { "HTTP $($sample.Status)" }
        Write-Log "$BookId  $failed of $probed probes did not get an answer (e.g. $why)" 'ERROR'
    }
    if ($dates.Count -eq 0) {
        return [pscustomobject]@{ Issues = @{}; Probed = $probed; Failed = $failed }
    }

    Write-Log "$BookId  found $($dates.Count) issue date(s); counting pages"

    $issues = @{}
    foreach ($ds in $dates) {
        $count = 1
        $page  = 2
        while ($page -le $MaxPages) {
            $block = New-Object System.Collections.ArrayList
            $upper = [Math]::Min($page + $Concurrency - 1, $MaxPages)
            for ($p = $page; $p -le $upper; $p++) {
                [void]$block.Add([pscustomobject]@{ Url = ('{0}/{1}/{2}/{3:D3}.jpg' -f $BaseUrl, $BookId, $ds, $p); Page = $p })
            }
            $br = Invoke-HttpBatchWithRetry -Items ([object[]]$block.ToArray()) -Method Head -Client $Client `
                     -Concurrency $Concurrency -DelayMs $DelayMs -Retries $Retries
            $stop = $false
            foreach ($r in ($br | Sort-Object { $_.Item.Page })) {
                if ($r.Ok) { $count = $r.Item.Page } else { $stop = $true; break }
            }
            if ($stop) { break }
            $page = $upper + 1
        }
        $issues[$ds] = $count
    }
    return [pscustomobject]@{ Issues = $issues; Probed = $probed; Failed = $failed }
}

# ---------------------------------------------------------------- issue ------

function Save-Issue {
    param(
        $Client, [string]$BookId, [string]$Date, [int]$PageCount,
        [string]$PaperDir, [int]$Concurrency, [int]$DelayMs, [int]$Retries,
        [int]$Dpi, [switch]$Force, [switch]$RemovePagesAfterPdf
    )

    $pretty  = '{0}-{1}-{2}' -f $Date.Substring(0,4), $Date.Substring(4,2), $Date.Substring(6,2)
    $pdfPath = Join-Path $PaperDir "$pretty.pdf"
    if ((Test-Path -LiteralPath $pdfPath) -and -not $Force) {
        return [pscustomobject]@{ Status = 'skipped'; Pdf = $pdfPath; Pages = $PageCount }
    }

    $pageDir = Join-Path (Join-Path $PaperDir 'pages') $Date
    if (-not (Test-Path -LiteralPath $pageDir)) { New-Item -ItemType Directory -Path $pageDir -Force | Out-Null }

    $wanted = New-Object System.Collections.ArrayList
    $paths  = New-Object System.Collections.ArrayList
    for ($p = 1; $p -le $PageCount; $p++) {
        $file = Join-Path $pageDir ('{0:D3}.jpg' -f $p)
        [void]$paths.Add($file)
        $have = $false
        if (Test-Path -LiteralPath $file) {
            try { $have = Test-JpegBytes ([System.IO.File]::ReadAllBytes($file)) } catch { $have = $false }
        }
        if (-not $have) {
            [void]$wanted.Add([pscustomobject]@{
                Url  = ('{0}/{1}/{2}/{3:D3}.jpg' -f $BaseUrl, $BookId, $Date, $p)
                Path = $file
            })
        }
    }

    if ($wanted.Count -gt 0) {
        $res = Invoke-HttpBatchWithRetry -Items ([object[]]$wanted.ToArray()) -Method Get -Client $Client `
                  -Concurrency $Concurrency -DelayMs $DelayMs -Retries $Retries `
                  -Activity "$BookId $pretty  downloading $($wanted.Count) page(s)"
        foreach ($r in $res) {
            if ($r.Ok) { [System.IO.File]::WriteAllBytes($r.Item.Path, $r.Bytes) }
            else {
                $why = if ($r.Error) { $r.Error } else { "HTTP $($r.Status)" }
                Write-Log "$BookId $pretty  page $(Split-Path -Leaf $r.Item.Path) failed: $why" 'ERROR'
            }
        }
    }

    $present = @($paths | Where-Object { Test-Path -LiteralPath $_ })
    if ($present.Count -eq 0) {
        return [pscustomobject]@{ Status = 'failed'; Pdf = $pdfPath; Pages = 0 }
    }

    New-PdfFromJpegs -JpegPaths $present -OutPath $pdfPath -FallbackDpi $Dpi

    if ($RemovePagesAfterPdf) { Remove-Item -LiteralPath $pageDir -Recurse -Force -ErrorAction SilentlyContinue }

    $status = if ($present.Count -eq $PageCount) { 'ok' } else { 'partial' }
    return [pscustomobject]@{ Status = $status; Pdf = $pdfPath; Pages = $present.Count }
}

# ----------------------------------------------------------------- main ------

if (-not (Test-Path -LiteralPath $OutputRoot)) { New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null }
$logDir = Join-Path $OutputRoot 'logs'
if (-not (Test-Path -LiteralPath $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$script:LogPath = Join-Path $logDir ('run-{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

$client = New-HttpClient

try {
    if ($SelfTest) {
        Write-Log 'self test: fetching the two documented sample pages'
        $samples = @(
            [pscustomobject]@{ Url = "$BaseUrl/21211909_014/19490209/001.jpg" },
            [pscustomobject]@{ Url = "$BaseUrl/21221909_7/19491023/002.jpg" }
        )
        $res = Invoke-HttpBatchWithRetry -Items $samples -Method Get -Client $client `
                  -Concurrency 2 -DelayMs 200 -Retries 2
        $testDir = Join-Path $OutputRoot '_selftest'
        if (-not (Test-Path -LiteralPath $testDir)) { New-Item -ItemType Directory -Path $testDir -Force | Out-Null }
        $files = @()
        $k = 0
        foreach ($r in $res) {
            $k++
            if ($r.Ok) {
                $info = Get-JpegInfo $r.Bytes
                $f = Join-Path $testDir ('sample{0:D2}.jpg' -f $k)
                [System.IO.File]::WriteAllBytes($f, $r.Bytes)
                $files += $f
                Write-Log ("OK  {0}  {1}x{2}px, {3} comp, {4} KB, dpi={5}" -f `
                           $r.Item.Url, $info.Width, $info.Height, $info.Components,
                           [int]($r.Length / 1KB), $(if ($info.DpiX -gt 0) { $info.DpiX } else { "unset -> using -Dpi $Dpi" })) 'OK'
            } else {
                $why = if ($r.Error) { $r.Error } else { "HTTP $($r.Status)" }
                Write-Log "FAIL  $($r.Item.Url)  $why" 'ERROR'
            }
        }
        if ($files.Count -gt 0) {
            $testPdf = Join-Path $testDir 'selftest.pdf'
            New-PdfFromJpegs -JpegPaths $files -OutPath $testPdf -FallbackDpi $Dpi
            Write-Log "wrote $testPdf  - open it; if the pages render, the PDF writer is good" 'OK'
        } else {
            Write-Log 'no sample downloaded - check network access to memory.zslib.cn before a full run' 'ERROR'
        }
        return
    }

    $allIds    = Get-DefaultPaperIds
    $titleMap  = Import-TitleMap -Path (Join-Path $OutputRoot 'papers.csv') -AllIds $allIds
    # tolerate -Papers a,b,c arriving as one string (happens with powershell.exe -File)
    $targetIds = if ($Papers) {
        @(@($Papers) | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    } else { $allIds }

    $indexPath   = Join-Path $OutputRoot 'index.csv'
    $scannedPath = Join-Path $OutputRoot 'scanned.csv'
    $cache       = Import-IndexCache -IndexPath $indexPath -ScannedPath $scannedPath
    $issuesAll   = $cache.Issues
    $scannedAll  = $cache.Scanned

    $rangeKey = '{0}-{1}' -f $StartDate.ToString('yyyyMMdd'), $EndDate.ToString('yyyyMMdd')
    $days     = [int]($EndDate - $StartDate).TotalDays + 1
    $toScan   = @($targetIds | Where-Object {
                    $RefreshIndex -or -not $scannedAll.ContainsKey($_) -or $scannedAll[$_] -ne $rangeKey })

    Write-Log "output root : $OutputRoot"
    Write-Log "titles       : $($targetIds.Count)  ($($toScan.Count) still need probing)"
    Write-Log "date window  : $($StartDate.ToString('yyyy-MM-dd')) .. $($EndDate.ToString('yyyy-MM-dd'))  ($days days)"
    Write-Log ("pacing       : {0} at a time, {1:N1}s between batches" -f $Concurrency, ($DelayMs / 1000.0))

    if ($toScan.Count -gt 0) {
        # one HEAD per title per day, plus ~0.3s of round trip per batch
        $batches = [Math]::Ceiling(($toScan.Count * $days) / [double]$Concurrency)
        $est     = [TimeSpan]::FromSeconds($batches * (($DelayMs / 1000.0) + 0.3))
        $pretty  = if ($est.TotalHours -ge 1) { '{0:0}h {1:00}m' -f [Math]::Floor($est.TotalHours), $est.Minutes }
                   else { '{0:0}m' -f [Math]::Ceiling($est.TotalMinutes) }
        $level   = if ($est.TotalHours -ge 3) { 'WARN' } else { 'INFO' }
        Write-Log ("discovery    : ~{0:N0} probes, roughly {1} at this pacing" -f ($toScan.Count * $days), $pretty) $level
        if ($est.TotalHours -ge 3) {
            Write-Log "             raise -Concurrency or lower -DelaySeconds to shorten it; index.csv is saved after each title, so Ctrl-C and resume is safe" 'WARN'
        }
    }

    $tally = [pscustomobject]@{ Ok = 0; Partial = 0; Skipped = 0; Failed = 0; Issues = 0; Unreachable = 0 }

    foreach ($bookId in $targetIds) {
        $needScan = $RefreshIndex -or -not $scannedAll.ContainsKey($bookId) -or $scannedAll[$bookId] -ne $rangeKey
        if ($needScan) {
            $scan = Find-Issues -Client $client -BookId $bookId -Start $StartDate -End $EndDate `
                        -MaxPages $MaxPages -Concurrency $Concurrency -DelayMs $DelayMs -Retries $Retries

            if ($scan.Failed -eq $scan.Probed -and $scan.Probed -gt 0) {
                $tally.Unreachable++
                Write-Log "$bookId  every probe failed - the server was not reachable, not an empty archive" 'ERROR'
                if ($tally.Unreachable -ge 2 -and $tally.Issues -eq 0) {
                    throw ("Cannot reach $BaseUrl - no title returned a single answer. " +
                           "Check the site in a browser, then confirm the URL pattern with -SelfTest.")
                }
                continue    # leave the cache untouched so the next run re-probes
            }

            $issuesAll[$bookId] = $scan.Issues
            if ($scan.Failed -eq 0) {
                $scannedAll[$bookId] = $rangeKey
            } else {
                Write-Log "$bookId  partial scan - not cached, this title will be re-probed next run" 'WARN'
            }
            Export-IndexCache -Issues $issuesAll -Scanned $scannedAll -IndexPath $indexPath -ScannedPath $scannedPath
        }

        $issues = $issuesAll[$bookId]
        if (-not $issues -or $issues.Count -eq 0) {
            Write-Log "$bookId  no issues in this date window" 'WARN'
            continue
        }
        $tally.Issues += $issues.Count

        $title = if ($titleMap.ContainsKey($bookId)) { $titleMap[$bookId] } else { $bookId }
        $paperDir = Join-Path $OutputRoot (Get-SafeName $title)
        if (-not (Test-Path -LiteralPath $paperDir)) { New-Item -ItemType Directory -Path $paperDir -Force | Out-Null }

        Write-Log "$bookId  '$title'  $($issues.Count) issue(s)"
        if ($DiscoverOnly) { continue }

        foreach ($date in ($issues.Keys | Sort-Object)) {
            $r = Save-Issue -Client $client -BookId $bookId -Date $date -PageCount $issues[$date] `
                    -PaperDir $paperDir -Concurrency $Concurrency -DelayMs $DelayMs -Retries $Retries `
                    -Dpi $Dpi -Force:$Force -RemovePagesAfterPdf:$RemovePagesAfterPdf
            switch ($r.Status) {
                'ok'      { $tally.Ok++;      Write-Log "  $(Split-Path -Leaf $r.Pdf)  $($r.Pages) page(s)" 'OK' }
                'partial' { $tally.Partial++; Write-Log "  $(Split-Path -Leaf $r.Pdf)  $($r.Pages)/$($issues[$date]) page(s) - some downloads failed" 'WARN' }
                'skipped' { $tally.Skipped++ }
                'failed'  { $tally.Failed++;  Write-Log "  $(Split-Path -Leaf $r.Pdf)  no pages downloaded" 'ERROR' }
            }
        }
    }

    Write-Log '--------------------------------------------------'
    $clean = ($tally.Failed -eq 0 -and $tally.Partial -eq 0 -and $tally.Unreachable -eq 0)
    Write-Log ("issues indexed {0} | pdf ok {1} | partial {2} | already present {3} | failed {4} | unreachable titles {5}" -f `
               $tally.Issues, $tally.Ok, $tally.Partial, $tally.Skipped, $tally.Failed, $tally.Unreachable) `
              $(if ($clean) { 'OK' } else { 'WARN' })
    Write-Log "catalogue cache: $indexPath"
    Write-Log "log            : $script:LogPath"
}
finally {
    if ($client) { $client.Dispose() }
}
