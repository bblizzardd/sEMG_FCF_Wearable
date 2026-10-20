$ErrorActionPreference='Stop'
$root='C:\Users\Admin\OneDrive\Documents\PlatformIO\Projects\sEMG\.report-work\latex-build'
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
$file=Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync("$root\bao_cao_tien_do.pdf")) ([Windows.Storage.StorageFile])
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
