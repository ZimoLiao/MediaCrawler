# MediaCrawler Hotboard User Services

These units run the hotboard HTTP API and scheduled captures as user-level
systemd services.

Install or refresh them on the server:

```bash
mkdir -p ~/.config/systemd/user
cp /repo/personal/MediaCrawler-hotboard/deploy/mediacrawler-hotboard.service ~/.config/systemd/user/
cp /repo/personal/MediaCrawler-hotboard/deploy/mediacrawler-hotboard-capture.service ~/.config/systemd/user/
cp /repo/personal/MediaCrawler-hotboard/deploy/mediacrawler-hotboard-capture.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now mediacrawler-hotboard.service
systemctl --user enable --now mediacrawler-hotboard-capture.timer
```

The API listens on `0.0.0.0:8765` and stores the SQLite database at
`/repo/personal/MediaCrawler-hotboard/data/hotboard/hotboard.db`.
