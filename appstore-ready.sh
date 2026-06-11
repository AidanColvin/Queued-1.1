#!/usr/bin/env bash
set -e

echo "== Queued App Store prep =="

echo
echo "1) Repo summary"
find . -maxdepth 2 \( -name frontend -o -name backend -o -name docs -o -name ios -o -name render.yaml -o -name README.md \) -print

echo
echo "2) Check for likely required files"
for f in docs/APP_STORE.md docs/PRIVACY_POLICY.md render.yaml README.md; do
  if [ -e "$f" ]; then
    echo "[FOUND] $f"
  else
    echo "[MISSING] $f"
  fi
done

echo
echo "3) iOS/Capacitor hints"
find ./frontend -maxdepth 3 \( -name "capacitor.config.*" -o -name "*.xcodeproj" -o -name "*.xcworkspace" -o -name "Info.plist" \) -print 2>/dev/null || true

echo
echo "4) Env files"
find . -maxdepth 3 \( -name ".env" -o -name ".env.*" \) -print

echo
echo "5) Next actions"
cat <<'NEXT'
- Publish docs/PRIVACY_POLICY.md to a public URL.
- Open the iOS project in Xcode.
- Set bundle ID, signing team, version, and app icons.
- Archive the app and upload to TestFlight.
- Complete App Privacy in App Store Connect.
- Add Sign in with Apple if required by your auth options.
- Verify dataset licensing before public distribution.
NEXT
