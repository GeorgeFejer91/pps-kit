param(
    [string]$Main = "main.tex",
    [switch]$OpenPdf,
    [switch]$KeepAux,
    [switch]$UseLatexMk,
    [int]$MaxPdflatexReruns = 5
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ManuscriptDir = Join-Path $RepoRoot "publication\behavior-research-methods\manuscript"
$RenderScript = Join-Path $ManuscriptDir "render_pdf.ps1"

if (-not (Test-Path -LiteralPath $RenderScript -PathType Leaf)) {
    throw "Cannot find manuscript render script: $RenderScript"
}

$renderArgs = @{
    Main = $Main
    MaxPdflatexReruns = $MaxPdflatexReruns
}
if ($OpenPdf) {
    $renderArgs.OpenPdf = $true
}
if ($KeepAux) {
    $renderArgs.KeepAux = $true
}
if ($UseLatexMk) {
    $renderArgs.UseLatexMk = $true
}

Write-Host "Permanent PC render entry: $PSCommandPath"
Write-Host "Delegating to manuscript renderer: $RenderScript"
& $RenderScript @renderArgs

$baseName = [System.IO.Path]::GetFileNameWithoutExtension($Main)
$pdfPath = Join-Path $ManuscriptDir "$baseName.pdf"
Write-Host "Rendered manuscript PDF: $pdfPath"
