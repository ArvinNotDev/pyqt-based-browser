$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $torArchive = 'proxy/bundles/tor-expert-bundle-windows-x86_64-13.5.23.tar.gz'
    $requiredFiles = @(
        'main.py',
        'requirements.txt',
        'assets/icons/home.png',
        'ui/dashboard/dashboard.css',
        $torArchive
    )
    foreach ($file in $requiredFiles) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
            throw "Required packaging input is missing: $file"
        }
    }

    python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'Could not upgrade pip.' }
    python -m pip install -r requirements.txt 'pyinstaller==6.22.3'
    if ($LASTEXITCODE -ne 0) { throw 'Could not install runtime or PyInstaller dependencies.' }

    $pyinstallerArgs = @(
        '--noconfirm',
        '--clean',
        '--onefile',
        '--windowed',
        '--name', 'ARMA-Browser',
        '--collect-all', 'cv2',
        '--collect-all', 'pyzbar',
        '--collect-all', 'numpy',
        '--hidden-import', 'PySide6.QtWebEngineCore',
        '--hidden-import', 'PySide6.QtWebEngineWidgets',
        '--hidden-import', 'PySide6.QtWebChannel',
        '--add-data', 'assets;assets',
        '--add-data', 'ui/dashboard;ui/dashboard',
        '--add-data', "$torArchive;bundles",
        'main.py'
    )
    python -m PyInstaller @pyinstallerArgs
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed to build the one-file Windows executable.' }

    $exe = Join-Path $repoRoot 'dist/ARMA-Browser.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw 'The expected dist/ARMA-Browser.exe was not produced.'
    }
    $length = (Get-Item -LiteralPath $exe).Length
    if ($length -lt 20MB) {
        throw "The executable is unexpectedly small ($length bytes); refusing to publish an incomplete build."
    }

    $hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath "$exe.sha256" -Value "$hash  ARMA-Browser.exe" -Encoding ascii
    Write-Output "Built $exe ($length bytes)"
    Write-Output "SHA-256: $hash"
}
finally {
    Pop-Location
}
