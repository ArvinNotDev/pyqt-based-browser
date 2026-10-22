param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^v\d+\.\d+\.\d+([.-][0-9A-Za-z.-]+)?$')]
    [string]$Tag
)

$ErrorActionPreference = 'Stop'

git cat-file -e "$Tag^{commit}"
if ($LASTEXITCODE -ne 0) {
    throw "Tag '$Tag' does not resolve to a commit."
}

$archive = "pyqt-based-browser-$Tag-source.zip"
$prefix = "pyqt-based-browser-$Tag/"
git archive --format=zip "--prefix=$prefix" --output=$archive $Tag
if ($LASTEXITCODE -ne 0) {
    throw "Could not create source archive for '$Tag'."
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $archive).Path)
try {
    $entries = @($zip.Entries | ForEach-Object { $_.FullName })
    $requiredEntries = @(
        "${prefix}README.md",
        "${prefix}LICENSE",
        "${prefix}requirements.txt",
        "${prefix}requirements-dev.txt",
        "${prefix}pyproject.toml",
        "${prefix}docs/PACKAGING.md",
        "${prefix}docs/RELEASE_CHECKLIST.md",
        "${prefix}assets/icons/home.png",
        "${prefix}proxy/bundles/tor-expert-bundle-windows-x86_64-13.5.23.tar.gz",
        "${prefix}proxy/bundles/tor-expert-bundle-linux-x86_64-15.0.tar.gz"
    )
    foreach ($entry in $requiredEntries) {
        if ($entry -notin $entries) {
            throw "Source archive is missing required file '$entry'."
        }
    }

    $privateDataPattern = '(^|/)(settings\.json|config\.json|blocked_hosts\.json|exclude_hosts\.json|history\.json|temp_torrc\.txt|tor_log\.txt)$|(^|/)profile_data(/|$)'
    $privateEntries = @($entries | Where-Object { $_ -match $privateDataPattern })
    if ($privateEntries.Count -gt 0) {
        throw "Source archive contains runtime or profile data: $($privateEntries -join ', ')"
    }
}
finally {
    $zip.Dispose()
}

$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$archive.sha256" -Value "$hash  $archive" -Encoding ascii
Write-Output "Created and validated $archive and $archive.sha256"
