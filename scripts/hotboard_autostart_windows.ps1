param(
    [string]$Distro = "Ubuntu-24.04",
    [string]$WslRepo = "/home/lzmo/repos/external/MediaCrawler",
    [int]$ServicePort = 8767,
    [int]$RelayPort = 8768,
    [string]$LogDir = "$env:LOCALAPPDATA\MediaCrawler\Hotboard"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "autostart.log"

function Write-HotboardLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "$timestamp $Message"
}

function Test-ListeningPort {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $connections
}

function Start-WslHotboard {
    $bash = @"
set -e
cd '$WslRepo'
mkdir -p data/hotboard
if pgrep -f 'python -m hotboard.*--port $ServicePort' >/dev/null 2>&1; then
  exit 0
fi
setsid .venv/bin/python -m hotboard --port $ServicePort --db data/hotboard/hotboard.db > data/hotboard/service.log 2>&1 < /dev/null &
"@
    & wsl.exe -d $Distro -- bash -lc $bash
}

function Start-WindowsRelay {
    if (Test-ListeningPort -Port $RelayPort) {
        Write-HotboardLog "Relay port $RelayPort already listening"
        return
    }

    $relayPath = Join-Path $LogDir "mediacrawler_hotboard_relay_$RelayPort.py"
    $relayCode = @"
import asyncio
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = $RelayPort
TARGET_HOST = "127.0.0.1"
TARGET_PORT = $ServicePort

async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()

async def handle(client_reader, client_writer):
    target_reader, target_writer = await asyncio.open_connection(TARGET_HOST, TARGET_PORT)
    await asyncio.gather(pipe(client_reader, target_writer), pipe(target_reader, client_writer))

async def main():
    server = await asyncio.start_server(handle, LISTEN_HOST, LISTEN_PORT)
    async with server:
        await server.serve_forever()

asyncio.run(main())
"@
    Set-Content -Path $relayPath -Value $relayCode -Encoding UTF8
    Start-Process -FilePath python -ArgumentList $relayPath -WindowStyle Hidden
    Write-HotboardLog "Started relay $RelayPort -> 127.0.0.1:$ServicePort"
}

try {
    Write-HotboardLog "Starting MediaCrawler hotboard autostart"
    Start-WslHotboard
    Start-Sleep -Seconds 3

    try {
        $status = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "http://127.0.0.1:$ServicePort/api/status"
        Write-HotboardLog "WSL hotboard status returned HTTP $($status.StatusCode)"
    } catch {
        Write-HotboardLog "WSL hotboard status check failed: $($_.Exception.Message)"
    }

    Start-WindowsRelay
    Start-Sleep -Seconds 1

    try {
        $relayStatus = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "http://127.0.0.1:$RelayPort/api/status"
        Write-HotboardLog "Relay status returned HTTP $($relayStatus.StatusCode)"
    } catch {
        Write-HotboardLog "Relay status check failed: $($_.Exception.Message)"
    }
} catch {
    Write-HotboardLog "Autostart failed: $($_.Exception.Message)"
    throw
}
