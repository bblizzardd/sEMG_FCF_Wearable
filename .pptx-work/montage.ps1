param([string]$InputDir, [string]$OutputPath)
Add-Type -AssemblyName System.Drawing
$files = @(Get-ChildItem -LiteralPath $InputDir -Filter '*.png' | Sort-Object Name)
$rows = [int][Math]::Ceiling($files.Count / 4.0)
$bitmap = New-Object System.Drawing.Bitmap(1600, ($rows * 320))
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.Clear([System.Drawing.Color]::LightGray)
$font = New-Object System.Drawing.Font('Arial', 12)
for ($i = 0; $i -lt $files.Count; $i++) {
  $img = [System.Drawing.Image]::FromFile($files[$i].FullName)
  $graphics.DrawImage($img, (($i % 4) * 400), ([int][Math]::Floor($i / 4) * 320), 390, 292)
  $graphics.DrawString($files[$i].BaseName, $font, [System.Drawing.Brushes]::Black, (($i % 4) * 400 + 5), ([int][Math]::Floor($i / 4) * 320 + 295))
  $img.Dispose()
}
$bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Jpeg)
$graphics.Dispose(); $bitmap.Dispose(); $font.Dispose()
