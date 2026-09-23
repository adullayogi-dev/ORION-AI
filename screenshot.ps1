# Capture every monitor into a single PNG.
param([string]$Path)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$minX = [System.Int32]::MaxValue
$minY = [System.Int32]::MaxValue
$maxX = [System.Int32]::MinValue
$maxY = [System.Int32]::MinValue

foreach ($s in [System.Windows.Forms.Screen]::AllScreens) {
    $b = $s.Bounds
    if ($b.X -lt $minX) { $minX = $b.X }
    if ($b.Y -lt $minY) { $minY = $b.Y }
    if (($b.X + $b.Width) -gt $maxX) { $maxX = $b.X + $b.Width }
    if (($b.Y + $b.Height) -gt $maxY) { $maxY = $b.Y + $b.Height }
}

$width = $maxX - $minX
$height = $maxY - $minY

if ($width -le 0 -or $height -le 0) {
    Write-Output "SCREEN_CAPTURE_ERROR"
    exit 1
}

$bitmap = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($minX, $minY, 0, 0, (New-Object System.Drawing.Size $width, $height))
$bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()

Write-Output $Path