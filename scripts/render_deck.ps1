<#
把 pptx 导出成 PNG，供 Claude 用 Read 工具"看图"检查排版。

依赖：本机装有 WPS Office（注册了 KWPP.Application 这个 COM ProgID）。
      没有 WPS 的话，装 LibreOffice 后可用：
      soffice --headless --convert-to png --outdir <dir> <pptx>

用法：
    powershell -File render_deck.ps1 examples\v4-index-schedules.pptx
    powershell -File render_deck.ps1 examples\v4-index-schedules.pptx out_dir 1600 1200
#>
param(
    [Parameter(Mandatory = $true)][string]$Pptx,
    [string]$OutDir = "",
    [int]$Width = 1400,
    [int]$Height = 1050
)

$pptxPath = (Resolve-Path $Pptx).Path
if (-not $OutDir) {
    $OutDir = Join-Path (Split-Path $pptxPath -Parent) "_render"
}
New-Item -ItemType Directory -Force $OutDir | Out-Null
Get-ChildItem $OutDir -File -ErrorAction SilentlyContinue | Remove-Item -Force

try {
    $app = New-Object -ComObject KWPP.Application
} catch {
    Write-Output "FAILED: 没有可用的 KWPP.Application（WPS 未安装？）→ 试试 LibreOffice headless"
    exit 1
}

try {
    $pres = $app.Presentations.Open($pptxPath, $true, $false, $false)   # ReadOnly, WithWindow=false
    $count = $pres.Slides.Count
    $pres.Export($OutDir, "PNG", $Width, $Height)
    $pres.Close()
    $app.Quit()
    $files = Get-ChildItem $OutDir -File | Sort-Object Name
    Write-Output "OK: $count 页 → $OutDir"
    foreach ($f in $files) { Write-Output ("  " + $f.Name) }
} catch {
    Write-Output "FAILED: $($_.Exception.Message)"
    try { $app.Quit() } catch {}
    exit 1
}
