# Hotboard Monitor

Hotboard Monitor is a standalone read-only service for periodic hotboard capture and dashboard viewing. It does not use browser login, CDP, or MediaCrawler's keyword crawler flow.

## What It Captures

Every scheduled run stores the full available list from each source:

- Weibo hot search
- Douyin hot search
- Bilibili ranking
- Baidu Tieba hot topics
- Zhihu hot list from a public aggregation page
- Kuaishou hot search from a public aggregation page
- Xiaohongshu hot list from TopHub

Raw snapshots are retained in SQLite. Weekly summaries use only each platform's rank 1-20 rows per snapshot so all platforms share the same comparison depth.

## Start The Dashboard

```bash
uv run python -m hotboard
```

Defaults:

- Database: `data/hotboard/hotboard.db`
- Bind address: `0.0.0.0`
- Port: `8765`
- Capture interval: 6 hours
- Initial capture: enabled

Open from the same machine:

```text
http://127.0.0.1:8765
```

Open through Tailscale from another device:

```text
http://<tailscale-ip-or-hostname>:8765
```

The dashboard is read-only. Tailscale is the intended access boundary; the service does not add its own authentication layer.

## WSL + Windows Tailscale

When the service runs inside WSL, Windows can usually access it through `127.0.0.1:<port>`, but other Tailscale devices may not be able to reach the WSL listener directly through the Windows Tailscale IP. Start a small Windows-side relay if direct Tailscale access fails.

Example relay from Windows `0.0.0.0:8768` to WSL-forwarded `127.0.0.1:8767`:

```powershell
$relay = "$env:TEMP\mediacrawler_hotboard_relay_8768.py"
$code = @'
import asyncio
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8768
TARGET_HOST = "127.0.0.1"
TARGET_PORT = 8767

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
'@
Set-Content -Path $relay -Value $code -Encoding UTF8
Start-Process -FilePath python -ArgumentList $relay -WindowStyle Hidden
```

Then open:

```text
http://<windows-tailscale-ip>:8768
```

## Useful Commands

Run one capture and exit:

```bash
uv run python -m hotboard --once
```

Use a custom database:

```bash
uv run python -m hotboard --db /tmp/hotboard.db
```

Use a different port:

```bash
uv run python -m hotboard --port 8899
```

Serve existing data first and wait for the next scheduled capture:

```bash
uv run python -m hotboard --no-initial-capture
```

Use a shorter interval for testing:

```bash
uv run python -m hotboard --interval-hours 0.1
```

## Read-Only API

```text
GET /api/status
GET /api/latest
GET /api/weekly?window_days=7&top_n=20
GET /api/snapshots?limit=50
```

## Long-Running Background Example

For an interactive shell:

```bash
nohup uv run python -m hotboard > data/hotboard/service.log 2>&1 &
```

In agent or non-interactive WSL sessions, use `setsid` so the process is not tied to the launching shell:

```bash
setsid .venv/bin/python -m hotboard --port 8767 --db data/hotboard/hotboard.db \
  > data/hotboard/service.log 2>&1 < /dev/null &
```

Check it:

```bash
curl http://127.0.0.1:8767/api/status
```

Stop it:

```bash
pkill -f "python -m hotboard"
```

Stop the Windows relay:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match "mediacrawler_hotboard_relay_8768.py" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```
