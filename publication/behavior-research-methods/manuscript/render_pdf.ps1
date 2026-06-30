param(
    [string]$Main = "main.tex",
    [switch]$OpenPdf,
    [switch]$KeepAux,
    [switch]$UseLatexMk,
    [int]$MaxPdflatexReruns = 5
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TemplateDir = Resolve-Path (Join-Path $ScriptDir "..\springer-nature-latex-template\sn-article-template")
$BstDir = Resolve-Path (Join-Path $TemplateDir "bst")
$MainPath = Join-Path $ScriptDir $Main

if (-not (Test-Path -LiteralPath $MainPath -PathType Leaf)) {
    throw "Cannot find manuscript source: $MainPath"
}

if ($MaxPdflatexReruns -lt 2) {
    throw "MaxPdflatexReruns must be at least 2 so bibliography and cross-reference passes can settle."
}

function Add-TexPath {
    param(
        [string]$Name,
        [string]$Value
    )

    $current = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($current)) {
        [Environment]::SetEnvironmentVariable($Name, "$Value;", "Process")
    } else {
        [Environment]::SetEnvironmentVariable($Name, "$Value;$current", "Process")
    }
}

function Invoke-Step {
    param(
        [string]$Command,
        [string[]]$Arguments
    )

    Write-Host ">> $Command $($Arguments -join ' ')"
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE"
    }
}

function Remove-AuxFiles {
    param([string]$BaseName)

    $extensions = @(
        "acn", "acr", "alg", "aux", "bbl", "bcf", "blg", "fdb_latexmk",
        "fls", "glg", "glo", "gls", "idx", "ilg", "ind", "ist", "lof",
        "log", "lot", "out", "run.xml", "synctex.gz", "toc"
    )

    foreach ($extension in $extensions) {
        $path = Join-Path $ScriptDir "$BaseName.$extension"
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }
}

function Test-LogForPattern {
    param(
        [string]$Path,
        [string[]]$Patterns
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }

    $log = Get-Content -LiteralPath $Path -Raw
    foreach ($pattern in $Patterns) {
        if ($log -match $pattern) {
            return $true
        }
    }

    return $false
}

Push-Location $ScriptDir
try {
    Add-TexPath -Name "TEXINPUTS" -Value "$TemplateDir//"
    Add-TexPath -Name "BSTINPUTS" -Value "$BstDir//"

    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($Main)
    $pdfPath = Join-Path $ScriptDir "$baseName.pdf"
    $logPath = Join-Path $ScriptDir "$baseName.log"

    if ($UseLatexMk) {
        Invoke-Step "latexmk" @("-pdf", $Main)
    } else {
        $rerunPatterns = @(
            "Package natbib Warning: Citation\(s\) may have changed",
            "Label\(s\) may have changed",
            "Rerun to get cross-references right"
        )

        Invoke-Step "pdflatex" @("-interaction=nonstopmode", "-halt-on-error", $Main)
        Invoke-Step "bibtex" @($baseName)

        $pass = 0
        $needsRerun = $true
        while ($needsRerun -and $pass -lt $MaxPdflatexReruns) {
            $pass += 1
            Invoke-Step "pdflatex" @("-interaction=nonstopmode", "-halt-on-error", $Main)
            $needsRerun = Test-LogForPattern -Path $logPath -Patterns $rerunPatterns
            if ($needsRerun -and $pass -lt $MaxPdflatexReruns) {
                Write-Host ">> LaTeX requested another reference pass ($pass/$MaxPdflatexReruns)."
            }
        }
    }

    if (-not (Test-Path -LiteralPath $pdfPath -PathType Leaf)) {
        throw "Expected PDF was not created: $pdfPath"
    }

    if (Test-Path -LiteralPath $logPath -PathType Leaf) {
        $badPatterns = @(
            "LaTeX Warning: There were undefined references",
            "Package natbib Warning: There were undefined citations",
            "Package natbib Warning: Citation\(s\) may have changed",
            "Label\(s\) may have changed",
            "Rerun to get cross-references right"
        )
        foreach ($pattern in $badPatterns) {
            if (Test-LogForPattern -Path $logPath -Patterns @($pattern)) {
                throw "PDF was created, but the LaTeX log still requests attention: $pattern"
            }
        }
    }

    if (-not $KeepAux) {
        Remove-AuxFiles -BaseName $baseName
    }

    Write-Host "PDF written to: $pdfPath"

    if ($OpenPdf) {
        Start-Process -FilePath $pdfPath
    }
} finally {
    Pop-Location
}
