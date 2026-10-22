#!/usr/bin/env bash
# Independent stock-OS probe: no private app, account, backend, or cloud access.
set -euo pipefail
out="$PWD/results/android-health"
mkdir -p "$out"
exec > >(tee "$out/probe.log") 2>&1
sdk="${ANDROID_HOME:?ANDROID_HOME is required}"
manager="$sdk/cmdline-tools/latest/bin/sdkmanager"
avdmanager="$sdk/cmdline-tools/latest/bin/avdmanager"
image='system-images;android-35;google_apis;x86_64'
"$manager" "$image" platform-tools
# Match the observed failing OS image and emulator; never silently change versions.
grep -Eq '^Pkg.Revision *= *9$' "$sdk/system-images/android-35/google_apis/x86_64/source.properties"
curl -fsSL https://dl.google.com/android/repository/emulator-linux_x64-15917651.zip -o "$RUNNER_TEMP/emulator.zip"
echo "1b1f78891abf8ec268264356e1365c25519e8379  $RUNNER_TEMP/emulator.zip" | sha1sum -c -
unzip -q "$RUNNER_TEMP/emulator.zip" -d "$RUNNER_TEMP/android-health-tools"
emulator="$RUNNER_TEMP/android-health-tools/emulator/emulator"
adb="$sdk/platform-tools/adb"
"$emulator" -version
sudo chmod a+rw /dev/kvm
printf 'no\n' | "$avdmanager" create avd -n stock-health -k "$image" -d pixel_3a
"$emulator" -avd stock-health -no-window -no-audio -no-boot-anim -no-metrics -no-snapshot -no-snapshot-save -accel on -gpu software -port 5554 > "$out/emulator.log" 2>&1 &
pid=$!
cleanup() {
  "$adb" -s emulator-5554 emu kill >/dev/null 2>&1 || true
  kill "$pid" >/dev/null 2>&1 || true
}
trap cleanup EXIT
limit=$((SECONDS + 900))
until [[ "$("$adb" -s emulator-5554 shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == 1 ]]; do
  if (( SECONDS >= limit )); then echo 'Stock OS boot deadline exceeded'; exit 1; fi
  sleep 5
done
"$adb" -s emulator-5554 shell pm list packages | sort > "$out/packages.txt"
"$adb" -s emulator-5554 shell dumpsys package com.google.android.apps.wellbeing > "$out/wellbeing-package.txt"
"$adb" -s emulator-5554 shell am start -W -a android.settings.SETTINGS
"$adb" -s emulator-5554 shell am start -W -n com.android.chrome/com.google.android.apps.chrome.Main
# Observe once for three minutes; do not dismiss errors, relaunch apps, or retry tests.
limit=$((SECONDS + 180))
while (( SECONDS < limit )); do
  printf '%s ' "$(date -u +%FT%TZ)" >> "$out/host-load.txt"
  cat /proc/loadavg >> "$out/host-load.txt"
  sleep 10
done
"$adb" -s emulator-5554 logcat -b events -d -v threadtime > "$out/events.log"
"$adb" -s emulator-5554 shell dumpsys activity lastanr > "$out/last-anr.txt"
"$adb" -s emulator-5554 exec-out screencap -p > "$out/screen.png"
if grep -Eq 'am_anr|am_crash' "$out/events.log"; then
  echo 'Stock OS crash/ANR observed; inspect evidence'
  exit 1
fi
echo 'No stock OS ANR observed in this bounded sample; this is not application E2E acceptance.'
