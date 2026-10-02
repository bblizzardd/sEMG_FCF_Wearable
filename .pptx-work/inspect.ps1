$ErrorActionPreference = 'Stop'
$root = 'C:\Users\Admin\OneDrive\Documents\PlatformIO\Projects\sEMG\.pptx-work'
New-Item -ItemType Directory -Force -Path "$root\source" | Out-Null
$app = New-Object -ComObject PowerPoint.Application
$deck = $app.Presentations.Open('C:\Users\Admin\Downloads\baocao_sEMG.pptx', -1, 0, 0)
try {
  $info = @()
  foreach ($slide in $deck.Slides) {
    $slide.Export("$root\source\slide-$($slide.SlideIndex.ToString('00')).png", 'PNG', 1200, 900)
    $shapes = @()
    foreach ($shape in $slide.Shapes) {
      if ($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
        $r = $shape.TextFrame.TextRange
        $shapes += [ordered]@{name=$shape.Name;text=$r.Text;left=$shape.Left;top=$shape.Top;width=$shape.Width;height=$shape.Height;font=$r.Font.Name;size=$r.Font.Size;color=$r.Font.Color.RGB;bold=$r.Font.Bold}
      }
    }
    $info += [ordered]@{number=$slide.SlideIndex;layout=$slide.CustomLayout.Name;shapes=$shapes}
  }
  [ordered]@{width=$deck.PageSetup.SlideWidth;height=$deck.PageSetup.SlideHeight;slides=$info} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "$root\source-info.json" -Encoding UTF8
  Write-Output "Rendered $($deck.Slides.Count) source slides"
} finally { $deck.Close(); $app.Quit() }
