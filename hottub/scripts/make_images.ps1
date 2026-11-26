# Makes the UI's pictures and icons from the duckling artwork in ui/art/.
#
#     powershell -File scripts/make_images.ps1
#
# ui/art/ holds the masters (1024 px JPEG, made with Gemini on a plain white
# background):
#
#   tub-hot.jpg      at temperature (also the app icon)
#   tub-heating.jpg  a duckling pouring a steaming kettle in
#   tub-off.jpg      frozen, icicles, hats and scarves
#   tub-waiting.jpg  asleep, alarm clock
#   wood.jpg         wood-stave texture for the header and the card rim
#
# This writes into ui/public/:
#
#   tub-*.webp            the tubs with the white background removed, all
#                         cropped to the same box so they line up (cut out
#                         here as PNG, then made WebP by ui/scripts/webp.mjs,
#                         which needs "npm install" in ui/ first)
#   wood.jpg              the texture, 900 px wide (shown at 450)
#   apple-touch-icon.png, icon-192.png, icon-512.png, favicon-32.png
#                         the app icon: tub-hot on the app's light blue
#
# Windows (System.Drawing, plus a little C# for the pixel work) and Node.
# A missing master is skipped.

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

public static class Cutout {
    // Makes the white background transparent.  A flood fill from the edges
    // runs through light, nearly grey pixels; within it, pure white becomes
    // clear and paler greys (steam, soft shadows) become see-through white,
    // so they still look right on a dark page.  Returns the bounding box of
    // what is left.
    const int Light = 175;     // flood through pixels at least this light...
    const int Grey = 20;       // ...and at most this colourful
    public static Rectangle RemoveWhite(Bitmap bmp) {
        int w = bmp.Width, h = bmp.Height;
        var rect = new Rectangle(0, 0, w, h);
        var data = bmp.LockBits(rect, ImageLockMode.ReadWrite, PixelFormat.Format32bppArgb);
        var px = new byte[w * h * 4];
        Marshal.Copy(data.Scan0, px, 0, px.Length);
        Func<int, bool> pale = i => {
            int b = px[i * 4], g = px[i * 4 + 1], r = px[i * 4 + 2];
            int lo = Math.Min(r, Math.Min(g, b)), hi = Math.Max(r, Math.Max(g, b));
            return lo >= Light && hi - lo <= Grey;
        };
        var bg = new bool[w * h];
        var queue = new Queue<int>();
        for (int x = 0; x < w; x++) { queue.Enqueue(x); queue.Enqueue((h - 1) * w + x); }
        for (int y = 0; y < h; y++) { queue.Enqueue(y * w); queue.Enqueue(y * w + w - 1); }
        while (queue.Count > 0) {
            int i = queue.Dequeue();
            if (bg[i] || !pale(i)) continue;
            bg[i] = true;
            int x = i % w, y = i / w;
            if (x > 0) queue.Enqueue(i - 1);
            if (x < w - 1) queue.Enqueue(i + 1);
            if (y > 0) queue.Enqueue(i - w);
            if (y < h - 1) queue.Enqueue(i + w);
        }
        int minX = w, minY = h, maxX = 0, maxY = 0;
        for (int y = 0; y < h; y++) {
            for (int x = 0; x < w; x++) {
                int i = y * w + x;
                if (bg[i]) {
                    // Pale greys become white that lets the page show through.
                    int lo = Math.Min(px[i * 4 + 2], Math.Min(px[i * 4 + 1], px[i * 4]));
                    double a = lo >= 246 ? 0 : Math.Min(1.0, (255.0 - lo) / (255.0 - Light) * 0.9);
                    if (a < 0.03) { px[i * 4 + 3] = 0; continue; }
                    px[i * 4] = px[i * 4 + 1] = px[i * 4 + 2] = 255;   // see-through white
                    px[i * 4 + 3] = (byte)(a * 255);
                    if (a < 0.15) continue;   // too faint to count for the crop
                }
                if (x < minX) minX = x; if (x > maxX) maxX = x;
                if (y < minY) minY = y; if (y > maxY) maxY = y;
            }
        }
        Marshal.Copy(px, 0, data.Scan0, px.Length);
        bmp.UnlockBits(data);
        return Rectangle.FromLTRB(minX, minY, maxX + 1, maxY + 1);
    }
}
"@

$root = Split-Path -Parent $PSScriptRoot
$art = Join-Path $root "ui\art"
$public = Join-Path $root "ui\public"
$jpeg = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq "image/jpeg" }

function New-Canvas($w, $h) {
    $bmp = New-Object System.Drawing.Bitmap $w, $h, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    return $bmp, $g
}

function Report($path) { "{0,-22} {1,8:N0} bytes" -f (Split-Path -Leaf $path), (Get-Item $path).Length }

# Cut out each tub, then crop them all to the union of their boxes so the
# tub sits in the same place whichever picture is showing.
$cut = @{}
$box = $null
foreach ($name in "tub-hot", "tub-heating", "tub-off", "tub-waiting") {
    if (-not (Test-Path "$art\$name.jpg")) { "skipping $name (no master)"; continue }
    $src = [System.Drawing.Image]::FromFile("$art\$name.jpg")
    $bmp, $g = New-Canvas 1024 1024
    $g.DrawImage($src, 0, 0, 1024, 1024); $g.Dispose(); $src.Dispose()
    $r = [Cutout]::RemoveWhite($bmp)
    $box = if ($box) { [System.Drawing.Rectangle]::Union($box, $r) } else { $r }
    $cut[$name] = $bmp
}
$pad = 12
$box = [System.Drawing.Rectangle]::FromLTRB([Math]::Max(0, $box.Left - $pad), [Math]::Max(0, $box.Top - $pad),
    [Math]::Min(1024, $box.Right + $pad), [Math]::Min(1024, $box.Bottom + $pad))
$outW = 500   # shown at up to 250 px, so sharp on high-density phones
$outH = [int]($outW * $box.Height / $box.Width)
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) "hottub-cutouts"
New-Item -ItemType Directory -Force $tmp | Out-Null
Remove-Item "$tmp\*.png" -ErrorAction SilentlyContinue
foreach ($name in $cut.Keys) {
    $out, $g = New-Canvas $outW $outH
    $g.DrawImage($cut[$name], (New-Object System.Drawing.Rectangle 0, 0, $outW, $outH), $box, [System.Drawing.GraphicsUnit]::Pixel)
    $g.Dispose()
    $out.Save("$tmp\$name.png", [System.Drawing.Imaging.ImageFormat]::Png); $out.Dispose()
}
node (Join-Path $root "ui\scripts\webp.mjs") $tmp $public
if ($LASTEXITCODE -ne 0) { throw "webp.mjs failed (run npm install in ui/ first?)" }
"tub pictures are $outW x $outH"

# The wood texture.
if (Test-Path "$art\wood.jpg") {
    $src = [System.Drawing.Image]::FromFile("$art\wood.jpg")
    $w = 900; $h = [int]($w * $src.Height / $src.Width)   # shown 450 px wide
    $out, $g = New-Canvas $w $h
    $g.DrawImage($src, 0, 0, $w, $h); $g.Dispose(); $src.Dispose()
    $params = New-Object System.Drawing.Imaging.EncoderParameters 1
    $params.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter ([System.Drawing.Imaging.Encoder]::Quality), ([long]78)
    $out.Save("$public\wood.jpg", $jpeg, $params); $out.Dispose()
    Report "$public\wood.jpg"
}

# The app icon: the at-temperature tub (or failing that the first one) on the
# app's light blue, as a square with the tub filling most of it.
$iconFrom = if ($cut["tub-hot"]) { $cut["tub-hot"] } else { $cut[@($cut.Keys)[0]] }
foreach ($icon in @(@("apple-touch-icon.png", 180, 0.06), @("icon-192.png", 192, 0.06), @("icon-512.png", 512, 0.06), @("favicon-32.png", 32, 0.0))) {
    $file, $size, $margin = $icon
    $out, $g = New-Canvas $size $size
    $g.Clear([System.Drawing.Color]::FromArgb(255, 227, 244, 252))   # --accent-soft
    $m = [int]($size * $margin)
    $g.DrawImage($iconFrom, (New-Object System.Drawing.Rectangle $m, $m, ($size - 2 * $m), ($size - 2 * $m)), $box, [System.Drawing.GraphicsUnit]::Pixel)
    $g.Dispose()
    $out.Save("$public\$file", [System.Drawing.Imaging.ImageFormat]::Png); $out.Dispose()
    Report "$public\$file"
}
foreach ($bmp in $cut.Values) { $bmp.Dispose() }
