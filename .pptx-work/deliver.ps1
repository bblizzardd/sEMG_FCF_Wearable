$ErrorActionPreference='Stop'
$root='C:\Users\Admin\OneDrive\Documents\PlatformIO\Projects\sEMG'
$work="$root\.pptx-work"
$final="$root\docs\presentation\baocao_sEMG_MPU_ADS_cap_nhat.pptx"
if (Test-Path -LiteralPath $final) { throw 'Output exists' }
Copy-Item -LiteralPath "$work\candidate.pptx" -Destination $final
$app=New-Object -ComObject PowerPoint.Application
$deck=$app.Presentations.Open($final,-1,0,0)
try {
  if ($deck.Slides.Count -ne 68) { throw 'Wrong slide count' }
  New-Item -ItemType Directory -Force -Path "$work\delivered" | Out-Null
  foreach ($slide in $deck.Slides) {
    $slide.Export("$work\delivered\slide-$($slide.SlideIndex.ToString('00')).png",'PNG',1200,900)
  }
  Write-Output "PowerPoint reopened final file: $($deck.Slides.Count) slides."
} finally { $deck.Close(); $app.Quit() }
$receipt=Get-Content -LiteralPath "$work\content-validation.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$receipt | Add-Member -NotePropertyName finalPath -NotePropertyValue $final
$receipt | Add-Member -NotePropertyName finalSha256 -NotePropertyValue ((Get-FileHash -LiteralPath $final -Algorithm SHA256).Hash.ToLowerInvariant())
$receipt | Add-Member -NotePropertyName nativePowerPointReopenAndRender -NotePropertyValue 'pass: all 68 slides'
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "$work\delivery-validation.json" -Encoding UTF8
Get-Item -LiteralPath $final | Select-Object FullName,Length
