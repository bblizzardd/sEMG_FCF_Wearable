$ErrorActionPreference='Stop'
$root='C:\Users\Admin\OneDrive\Documents\PlatformIO\Projects\sEMG\.report-work'
$word=New-Object -ComObject Word.Application
$word.Visible=$false
$word.DisplayAlerts=0
$doc=$word.Documents.Open("$root\candidate.docx",$false,$false)
try {
  $doc.Fields.Update() | Out-Null
  foreach($toc in $doc.TablesOfContents) { $toc.Update() }
  $doc.Repaginate()
  $doc.Fields.Update() | Out-Null
  foreach($toc in $doc.TablesOfContents) { $toc.UpdatePageNumbers() }
  $doc.Save()
  $doc.ExportAsFixedFormat("$root\candidate.pdf",17)
  Write-Output "Native Word pages: $($doc.ComputeStatistics(2))"
  $pageText=@()
  for($n=1; $n -le $doc.ComputeStatistics(2); $n++) {
    $r=$doc.GoTo(1,1,$n)
    $begin=$r.Start
    if($n -lt $doc.ComputeStatistics(2)) { $end=$doc.GoTo(1,1,($n+1)).Start }
    else { $end=$doc.Content.End }
    $pageText += [ordered]@{page=$n;text=$doc.Range($begin,$end).Text}
  }
  $pageText | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$root\page-text.json" -Encoding UTF8
} finally { $doc.Close(0); $word.Quit() }

Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Pdf.PdfDocument,Windows.Data.Pdf,ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Pdf.PdfPageRenderOptions,Windows.Data.Pdf,ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.Streams.InMemoryRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.Streams.DataReader,Windows.Storage.Streams,ContentType=WindowsRuntime] | Out-Null
$genericTask=[System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
$actionTask=[System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and -not $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' } | Select-Object -First 1
function Await-Result($operation,[type]$resultType) {
  $task=$genericTask.MakeGenericMethod($resultType).Invoke($null,@($operation))
  $task.Wait()
  return $task.Result
}
$file=Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync("$root\candidate.pdf")) ([Windows.Storage.StorageFile])
$pdf=Await-Result ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])
New-Item -ItemType Directory -Force -Path "$root\pages" | Out-Null
for($n=0; $n -lt $pdf.PageCount; $n++) {
  $page=$pdf.GetPage($n)
  $stream=New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
  $options=New-Object Windows.Data.Pdf.PdfPageRenderOptions
  $options.DestinationWidth=1240
  $operation=$page.RenderToStreamAsync($stream,$options)
  $task=$actionTask.Invoke($null,@($operation)); $task.Wait()
  $reader=New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
  $loaded=Await-Result ($reader.LoadAsync([uint32]$stream.Size)) ([uint32])
  $bytes=New-Object byte[] ([int]$stream.Size)
  $reader.ReadBytes($bytes)
  [System.IO.File]::WriteAllBytes("$root\pages\page-$((($n+1).ToString('00'))).png",$bytes)
  $reader.Dispose(); $stream.Dispose(); $page.Dispose()
}
Write-Output "Rendered $($pdf.PageCount) PDF pages to PNG."
