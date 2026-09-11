# 装.ps1 —— 把插件装进 Obsidian 库。**不用 Node,不用 npm。**
#
#   cd D:\Coding\CN_Map\tools\obsidian-plugin
#   .\装.ps1
#
# 库不在 D:\Archive 的话:.\装.ps1 -Vault "E:\别处"
#
# 装的是三个文件,main.js 是已经打包好、跟着仓库一起来的 ——
# 所以这台机器上有没有 Node 都不相干。改过插件源码要重新打包才用得着 Node。

param([string]$Vault = "D:\Archive")

$src  = $PSScriptRoot
$dest = Join-Path $Vault ".obsidian\plugins\dianzi-gongye-ditu"

if (-not (Test-Path (Join-Path $Vault ".obsidian"))) {
    Write-Host "这里头没有 .obsidian —— $Vault 不像是个 Obsidian 库。" -ForegroundColor Red
    Write-Host "库是你在 Obsidian 里打开的那个文件夹,不是仓库。"
    exit 1
}

New-Item -ItemType Directory -Force -Path $dest | Out-Null

foreach ($f in @("main.js", "manifest.json", "styles.css")) {
    $p = Join-Path $src $f
    if (-not (Test-Path $p)) {
        Write-Host "少了 $f —— 仓库拉全了吗?" -ForegroundColor Red
        exit 1
    }
    Copy-Item $p $dest -Force
    Write-Host ("  -> " + (Join-Path $dest $f))
}

Write-Host ""
Write-Host "装好了。" -ForegroundColor Green
Write-Host "头一回装,还要去 Obsidian 的 设置 -> 第三方插件,把「电子工业地图流程」打开。"
Write-Host "装过一回、这次是更新的话:在插件列表里把它关一下再开,新的才生效。"
