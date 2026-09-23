# OCR a PNG and print every text line with its bounding box:
#   text<TAB>left<TAB>top<TAB>width<TAB>height
param([string]$ImagePath)

Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime] | Out-Null

try {
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
    $streamResult = $file.OpenAsync([Windows.Storage.FileAccessMode]::Read)
    $stream = Await $streamResult ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $softwareBitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $engine) {
        Write-Output "OCR_UNAVAILABLE"
        exit 1
    }

    $result = Await ($engine.RecognizeAsync($softwareBitmap)) ([Windows.Media.Ocr.OcrResult])
    foreach ($line in $result.Lines) {
        if (-not $line.Text -or -not $line.Text.Trim()) {
            continue
        }
        $left = 999999; $top = 999999; $right = -999999; $bottom = -999999
        foreach ($word in $line.Words) {
            $rect = $word.BoundingRect
            $rx = [double]$rect.X
            $ry = [double]$rect.Y
            $rw = [double]$rect.Width
            $rh = [double]$rect.Height
            if ($rx -lt $left) { $left = $rx }
            if ($ry -lt $top) { $top = $ry }
            $rx2 = $rx + $rw
            $ry2 = $ry + $rh
            if ($rx2 -gt $right) { $right = $rx2 }
            if ($ry2 -gt $bottom) { $bottom = $ry2 }
        }
        if ($right -lt $left) {
            $rect = $line.Words[0].BoundingRect
            $left = [double]$rect.X; $top = [double]$rect.Y
            $right = $left + [double]$rect.Width; $bottom = $top + [double]$rect.Height
        }
        $text = ($line.Words | ForEach-Object { $_.Text }) -join ' '
        $text = $text.Replace("`t", " ")
        "{0}`t{1}`t{2}`t{3}`t{4}" -f `
            $text,
            [int]($left + 0.5), [int]($top + 0.5),
            [int]($right - $left + 0.5), [int]($bottom - $top + 0.5)
    }
}
catch {
    Write-Output "OCR_ERROR $($_.Exception.Message)"
    exit 1
}