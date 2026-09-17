<#
.SYNOPSIS
    抓取按序号编排的一套 PDF(默认:清华计算机系《AlumniExpress》校友通讯)。

.DESCRIPTION
    https://www.cs.tsinghua.edu.cn/fujian/AlumniExpress001.pdf
    https://www.cs.tsinghua.edu.cn/fujian/AlumniExpress002.pdf
    ...                                                  ???

    刊物共几期未知,故用「连续缺号 N 期即停」的规则收尾:中间断号跨得过去,
    末尾自然停住。每期都校验 %PDF 魔数,挡住返回 200 的伪 404 页面。
    传输层故障(断网、超时)与缺号分开计,一段网络抖动不至于被当成刊物到头。

    Windows PowerShell 5.1(系统自带)与 PowerShell 7 都能跑。

.EXAMPLE
    .\pull_pdf_series.ps1 -DryRun
    干跑:只探测远端出到第几期,不落盘。

.EXAMPLE
    .\pull_pdf_series.ps1 -OutDir D:\资料\AlumniExpress
    落盘到指定目录;重跑会跳过已抓下且校验通过的。

.EXAMPLE
    .\pull_pdf_series.ps1 -Start 40 -End 120 -DelaySeconds 5
    只取 040-120,每次间隔 5 秒。
#>
#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$BaseUrl      = 'https://www.cs.tsinghua.edu.cn/fujian/AlumniExpress',
    [string]$Suffix       = '.pdf',
    [string]$OutDir       = 'AlumniExpress',
    [int]   $Start        = 1,
    [int]   $End          = 0,     # 0 = 自动,靠 MissLimit 收尾
    [int]   $MissLimit    = 8,     # 连续缺这么多期就认为刊物到头了
    [int]   $Ceiling      = 999,   # 自动模式下的硬上限,防跑飞
    [int]   $Pad          = 3,     # 序号补零位数 → 001
    [int]   $DelaySeconds = 3,     # 每次请求之间歇多久,别把人家站点打疼了
    [switch]$Force,                # 已存在的文件也重下
    [switch]$DryRun                # 只探测,不保存
)

# 进度条在 PS 5.1 里能把下载拖慢几倍;中文输出要靠 UTF-8 才不乱码。
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
try {
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.SecurityProtocolType]::Tls12 -bor [Net.ServicePointManager]::SecurityProtocol
} catch { }

$UserAgent = 'Mozilla/5.0 (compatible; pull_pdf_series/1.0; +archival use)'
$Prefix    = Split-Path -Leaf $BaseUrl          # AlumniExpress
$Last      = if ($End -gt 0) { $End } else { $Ceiling }
$Manifest  = Join-Path $OutDir 'manifest.csv'

function Test-Pdf {
    # 只认开头四个字节 %PDF —— 该站缺件时会回 200 加一页 HTML,
    # 光看状态码会把一堆错误页当刊物存下来。
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $stream = $null
    try {
        $stream = [System.IO.File]::OpenRead($Path)
        $buf = New-Object byte[] 4
        if ($stream.Read($buf, 0, 4) -lt 4) { return $false }
        return ($buf[0] -eq 0x25 -and $buf[1] -eq 0x50 -and $buf[2] -eq 0x44 -and $buf[3] -eq 0x46)
    } catch { return $false }
    finally { if ($stream) { $stream.Dispose() } }
}

function Get-HttpStatus {
    # 拿得到状态码 = 服务器答了(缺号);拿不到 = 根本没连上(传输层故障)。
    param($ErrorRecord)
    $response = $ErrorRecord.Exception.Response
    if ($null -eq $response) { return $null }
    try { return [int]$response.StatusCode } catch { return $null }
}

if (-not $DryRun) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    if (-not (Test-Path -LiteralPath $Manifest)) {
        Set-Content -LiteralPath $Manifest -Value 'no,file,bytes,sha256,url' -Encoding UTF8
    }
}

$hits = 0; $misses = 0; $skipped = 0; $streak = 0; $highest = 0
$stoppedEarly = $false
$n = $Start

while ($n -le $Last) {
    $num  = $n.ToString('D' + $Pad)
    $url  = '{0}{1}{2}' -f $BaseUrl, $num, $Suffix
    $dest = Join-Path $OutDir ('{0}{1}{2}' -f $Prefix, $num, $Suffix)

    if (-not $DryRun -and -not $Force -and (Test-Pdf $dest)) {
        Write-Host ('{0}  已有,跳过' -f $num)
        $skipped++; $streak = 0; $highest = $n; $n++
        continue
    }

    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName())
    $status = $null; $ok = $false; $transportError = $null

    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing `
                              -UserAgent $UserAgent -TimeoutSec 120 -ErrorAction Stop
            $ok = $true; $transportError = $null
            break
        } catch {
            $status = Get-HttpStatus $_
            if ($null -ne $status) { $transportError = $null; break }   # 服务器答了 4xx/5xx,不必重试
            $transportError = $_.Exception.Message
            if ($attempt -lt 3) { Start-Sleep -Seconds ([Math]::Pow(2, $attempt)) }
        }
    }

    if ($transportError) {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
        Write-Error ('{0}  网络错误,重试 3 次仍失败:{1}' -f $num, $transportError)
        Write-Host  ('续抓:.\{0} -Start {1}' -f (Split-Path -Leaf $PSCommandPath), $n)
        exit 1
    }

    if (-not $ok) {
        $shown = if ($null -ne $status) { $status } else { '?' }
        Write-Host ('{0}  缺号 (HTTP {1})' -f $num, $shown)
        $misses++; $streak++
    }
    elseif (-not (Test-Pdf $tmp)) {
        $bytes = (Get-Item -LiteralPath $tmp).Length
        Write-Host ('{0}  非 PDF 内容,按缺号处理 ({1} 字节)' -f $num, $bytes)
        $misses++; $streak++
    }
    else {
        $bytes = (Get-Item -LiteralPath $tmp).Length
        if ($DryRun) {
            Write-Host ('{0}  存在 ({1} 字节) [干跑]' -f $num, $bytes)
        } else {
            Move-Item -LiteralPath $tmp -Destination $dest -Force
            $sha = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLower()
            Add-Content -LiteralPath $Manifest -Encoding UTF8 `
                -Value ('{0},{1},{2},{3},{4}' -f $num, (Split-Path -Leaf $dest), $bytes, $sha, $url)
            Write-Host ('{0}  已存 {1} ({2} 字节)' -f $num, $dest, $bytes)
        }
        $hits++; $streak = 0; $highest = $n
    }

    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue

    if ($End -le 0 -and $streak -ge $MissLimit) {
        Write-Host ('连续 {0} 期缺号,判定刊物到此为止。' -f $MissLimit)
        $stoppedEarly = $true
        break
    }

    $n++
    if ($n -le $Last -and $DelaySeconds -gt 0) { Start-Sleep -Seconds $DelaySeconds }
}

if ($End -le 0 -and -not $stoppedEarly -and $n -gt $Ceiling) {
    Write-Warning ('已到硬上限 {0} 仍在出刊,用 -Start {1} -Ceiling <更大值> 继续。' -f $Ceiling, $n)
}

$verb = if ($DryRun) { '探到' } else { '下载' }
Write-Host '———'
Write-Host ('{0} {1} 期,跳过 {2} 期,缺号 {3} 期,最大期号 {4}。' -f `
            $verb, $hits, $skipped, $misses, $highest.ToString('D' + $Pad))
if (-not $DryRun) { Write-Host ('清单:{0}' -f $Manifest) }
