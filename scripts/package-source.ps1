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

$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$archive.sha256" -Value "$hash  $archive" -Encoding ascii
Write-Output "Created $archive and $archive.sha256"
