# Smoke test a built Intel AI Studio executable: start it with a throwaway data
# directory, wait for the HTTP API and the bundled static UI to answer, then stop it.
param(
    [string]$Exe = "dist/Intel-AI-Studio/Intel-AI-Studio.exe",
    [int]$Port = 8810,
    [int]$TimeoutSec = 60
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Exe)) {
    throw "Executable not found: $Exe (run the build first)"
}
$Exe = (Resolve-Path -LiteralPath $Exe).Path

$data = Join-Path $env:TEMP ("ai-studio-smoke-" + [guid]::NewGuid().ToString("N"))
$env:AI_STUDIO_DATA = $data

Write-Host "Starting $Exe ..."
$proc = Start-Process -FilePath $Exe -PassThru
$ok = $false
try {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 750
        if ($proc.HasExited) {
            throw "The executable exited early (code $($proc.ExitCode))"
        }

        $up = $false
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/config" -UseBasicParsing -TimeoutSec 2
            $up = ($r.StatusCode -eq 200)
        } catch {
            # not up yet
        }
        if (-not $up) { continue }

        # The bundled static UI must be present and served.
        $index = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 5
        if ($index.StatusCode -ne 200 -or $index.Content -notmatch "Intel AI Studio") {
            throw "Static UI check failed (status $($index.StatusCode))"
        }
        $js = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/i18n.js" -UseBasicParsing -TimeoutSec 5
        if ($js.StatusCode -ne 200 -or $js.Content -notmatch '"chat.new_title":') {
            throw "Bundled i18n.js check failed (status $($js.StatusCode))"
        }
        $ok = $true
        break
    }
} finally {
    if (-not $ok) {
        $appLog = Join-Path $data "app.log"
        if (Test-Path $appLog) {
            Write-Host "--- app.log (tail) ---"
            Get-Content $appLog -Tail 40 | Write-Host
        } else {
            Write-Host "--- no app.log found at $appLog ---"
        }
        Write-Host "--- process alive: $(-not $proc.HasExited) ---"
    }
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
    Remove-Item -LiteralPath $data -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not $ok) {
    throw "Smoke test failed: no HTTP response on 127.0.0.1:$Port within $TimeoutSec seconds"
}
Write-Host "Smoke test OK: $Exe"
