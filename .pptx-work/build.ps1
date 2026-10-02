$ErrorActionPreference = 'Stop'
$root = 'C:\Users\Admin\OneDrive\Documents\PlatformIO\Projects\sEMG'
$work = "$root\.pptx-work"
$output = "$root\docs\presentation"
New-Item -ItemType Directory -Force -Path $output, "$work\final" | Out-Null
$content = Get-Content -LiteralPath "$work\content.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$app = New-Object -ComObject PowerPoint.Application
$deck = $app.Presentations.Open('C:\Users\Admin\Downloads\baocao_sEMG.pptx', 0, 0, 0)
$fits = @()

function Add-Text($slide, $x, $y, $w, $h, $text, $size, $bold=0) {
  $shape = $slide.Shapes.AddTextbox(1, $x, $y, $w, $h)
  $shape.TextFrame.MarginLeft=0; $shape.TextFrame.MarginRight=0
  $shape.TextFrame.MarginTop=0; $shape.TextFrame.MarginBottom=0
  $shape.TextFrame.WordWrap=-1; $shape.TextFrame.AutoSize=0
  $r = $shape.TextFrame.TextRange
  $r.Text=$text; $r.Font.Name='Lato'; $r.Font.Size=[single]$size
  $r.Font.Bold=[int]$bold; $r.Font.Color.RGB=2500134
  $r.ParagraphFormat.Bullet.Visible=0
  $r.ParagraphFormat.SpaceAfter=0
  $shape.TextFrame2.AutoSize=0
  $shape.Height=[single]$h
  return $shape
}
function Add-Table($slide, $block) {
  $rows = @($block.rows)
  $shape = $slide.Shapes.AddTable($rows.Count, @($rows[0]).Count, $block.x, $block.y, $block.w, $block.h)
  $table = $shape.Table
  for ($c=1; $c -le $table.Columns.Count; $c++) { $table.Columns.Item($c).Width = [single]$block.widths[$c-1] }
  $headerH = 35
  if ($rows.Count -eq 1) { $headerH=$block.h }
  for ($r=1; $r -le $rows.Count; $r++) {
    if ($r -eq 1) { $table.Rows.Item($r).Height=[single]$headerH }
    else { $table.Rows.Item($r).Height=[single](($block.h-$headerH)/($rows.Count-1)) }
    for ($c=1; $c -le $table.Columns.Count; $c++) {
      $cell=$table.Cell($r,$c)
      $s=$cell.Shape
      $s.Fill.ForeColor.RGB=16777215
      $s.TextFrame.MarginLeft=5; $s.TextFrame.MarginRight=5
      $s.TextFrame.MarginTop=3; $s.TextFrame.MarginBottom=3
      $s.TextFrame.VerticalAnchor=3
      $tr=$s.TextFrame.TextRange
      $tr.Text=$rows[$r-1][$c-1]; $tr.Font.Name='Lato'; $tr.Font.Size=[single]$block.size
      $tr.Font.Color.RGB=2500134; $tr.Font.Bold=0
      $tr.ParagraphFormat.Bullet.Visible=0; $tr.ParagraphFormat.SpaceAfter=0
      if ($r -eq 1) { $s.Fill.ForeColor.RGB=2500134; $tr.Font.Color.RGB=16777215; $tr.Font.Bold=-1 }
      foreach ($edge in 1..4) { $cell.Borders.Item($edge).ForeColor.RGB=13816530; $cell.Borders.Item($edge).Weight=0.6 }
    }
  }
}
function Add-Flow($slide, $block) {
  $labels=@($block.labels); $gap=14
  $width=($block.w-$gap*($labels.Count-1))/$labels.Count
  for ($i=0; $i -lt $labels.Count; $i++) {
    $left=$block.x+$i*($width+$gap)
    $s=$slide.Shapes.AddShape(1,$left,$block.y,$width,$block.h)
    $s.Fill.ForeColor.RGB=16777215; $s.Line.ForeColor.RGB=3416256; $s.Line.Weight=1.2
    $s.TextFrame.MarginLeft=5; $s.TextFrame.MarginRight=5; $s.TextFrame.MarginTop=4; $s.TextFrame.MarginBottom=4
    $s.TextFrame.VerticalAnchor=3; $s.TextFrame.AutoSize=0
    $r=$s.TextFrame.TextRange; $r.Text=$labels[$i].Replace("\n", "`r")
    $r.Font.Name='Lato'; $r.Font.Size=14; $r.Font.Color.RGB=2500134
    $r.ParagraphFormat.Alignment=2; $r.ParagraphFormat.SpaceAfter=0; $r.ParagraphFormat.Bullet.Visible=0
    if ($i -lt $labels.Count-1) {
      $a=$slide.Shapes.AddShape(33,$left+$width+2,$block.y+$block.h/2-5,$gap-4,10)
      $a.Fill.ForeColor.RGB=12632256; $a.Line.Visible=0
    }
  }
}
try {
  $template=$deck.Slides.Item(13)
  for ($i=0; $i -lt $content.Count; $i++) {
    Write-Output "Authoring slide $(52+$i)"
    $spec=$content[$i]
    $slide=$template.Duplicate().Item(1)
    $slide.MoveTo(52+$i)
    for ($j=$slide.Shapes.Count; $j -ge 1; $j--) {
      $shape=$slide.Shapes.Item($j)
      if ($shape.Name -notin @('Title 3','TextBox 4','Slide Number Placeholder 5')) { $shape.Delete() }
    }
    $slide.Shapes.Item('Title 3').TextFrame.TextRange.Text='GIAI DOAN PHAN CUNG'
    # Read the Vietnamese section title from the original slide.
    $slide.Shapes.Item('Title 3').TextFrame.TextRange.Text=$deck.Slides.Item(51).Shapes.Item('Title 3').TextFrame.TextRange.Text
    $subtitle=$slide.Shapes.Item('TextBox 4')
    $subtitle.TextFrame.TextRange.Text=$spec.subtitle
    $subtitle.TextFrame.TextRange.Font.Size=17
    $subtitle.Width=676.8
    foreach ($b in $spec.blocks) {
      switch ($b.type) {
        'table' { Add-Table $slide $b }
        'flow' { Add-Flow $slide $b }
        'text' { $s=Add-Text $slide $b.x $b.y $b.w $b.h $b.text $b.size }
        'heading' { $s=Add-Text $slide $b.x $b.y $b.w $b.h $b.text $b.size -1 }
        'bullets' {
          $s=Add-Text $slide $b.x $b.y $b.w $b.h ([string]::Join("`r", @($b.items))) $b.size
          $r=$s.TextFrame.TextRange
          $r.ParagraphFormat.Bullet.Visible=-1
          $r.ParagraphFormat.Bullet.Character=8226
          $r.ParagraphFormat.SpaceAfter=10
          $s.TextFrame.Ruler.Levels.Item(1).FirstMargin=0
          $s.TextFrame.Ruler.Levels.Item(1).LeftMargin=12
          $s.Height=[single]$b.h
        }
        'mpuPlot' {
          $pic=$slide.Shapes.AddPicture("$work\mpu-axes.png",0,-1,$b.x,$b.y,$b.w,-1)
          $crop=$pic.PictureFormat.Crop
          $pictureH=$pic.Height
          $crop.ShapeWidth=[single]$b.w; $crop.ShapeHeight=[single]$b.h
          $crop.PictureWidth=[single]$b.w; $crop.PictureHeight=[single]$pictureH
          $crop.PictureOffsetX=0; $crop.PictureOffsetY=($pictureH-$b.h)/2
          $pic.Left=[single]$b.x; $pic.Top=[single]$b.y
        }
      }
    }
    $slide.NotesPage.Shapes.Placeholders.Item(2).TextFrame.TextRange.Text=$spec.notes
  }
  foreach ($slide in $deck.Slides) {
    foreach ($shape in $slide.Shapes) {
      if ($shape.Name -like 'Slide Number Placeholder*') { $shape.TextFrame.TextRange.Text=[string]$slide.SlideIndex }
    }
  }
  $draft="$work\candidate.pptx"
  $deck.SaveAs($draft,24)
  foreach ($slide in $deck.Slides) {
    $slide.Export("$work\final\slide-$($slide.SlideIndex.ToString('00')).png",'PNG',1200,900)
    if ($slide.SlideIndex -ge 52 -and $slide.SlideIndex -le 63) {
      foreach ($shape in $slide.Shapes) {
        if ($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
          $t=$shape.TextFrame.TextRange
          $fits += [ordered]@{slide=$slide.SlideIndex;name=$shape.Name;text=$t.Text;height=$shape.Height;boundHeight=$t.BoundHeight;width=$shape.Width;boundWidth=$t.BoundWidth}
        }
        if ($shape.HasTable -eq -1) {
          for ($r=1; $r -le $shape.Table.Rows.Count; $r++) {
            for ($c=1; $c -le $shape.Table.Columns.Count; $c++) {
              $cell=$shape.Table.Cell($r,$c).Shape; $t=$cell.TextFrame.TextRange
              $fits += [ordered]@{slide=$slide.SlideIndex;name="table-$r-$c";text=$t.Text;height=$cell.Height-6;boundHeight=$t.BoundHeight;width=$cell.Width-10;boundWidth=$t.BoundWidth}
            }
          }
        }
      }
    }
  }
  $fits | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "$work\fit-report.json" -Encoding UTF8
  Write-Output "Created candidate with $($deck.Slides.Count) slides"
} finally { $deck.Close(); $app.Quit() }
