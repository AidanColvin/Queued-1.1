#!/usr/bin/env bash
set -Eeuo pipefail
mkdir -p ~/Library/LaunchAgents ~/nextwatch/logs

cat > ~/Library/LaunchAgents/com.aidancolvin.nextwatch.autolearn.plist <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.aidancolvin.nextwatch.autolearn</string>

    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>-lc</string>
      <string>cd ~/nextwatch && source .venv/bin/activate && python3 scripts/train_and_serve_movielens.py >> logs/launchd_train.log 2>&1 && pytest -q tests >> logs/launchd_test.log 2>&1</string>
    </array>

    <key>RunAtLoad</key>
    <true/>
    <key>StartInterval</key>
    <integer>21600</integer>

    <key>StandardOutPath</key>
    <string>/Users/aidancolvin/nextwatch/logs/launchd_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/aidancolvin/nextwatch/logs/launchd_stderr.log</string>
  </dict>
</plist>
PLIST

launchctl unload ~/Library/LaunchAgents/com.aidancolvin.nextwatch.autolearn.plist >/dev/null 2>&1 || true
launchctl load ~/Library/LaunchAgents/com.aidancolvin.nextwatch.autolearn.plist

echo "Installed launch agent: com.aidancolvin.nextwatch.autolearn"
echo "It will retrain and test every 6 hours."
