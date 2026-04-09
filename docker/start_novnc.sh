#!/usr/bin/env bash
set -euo pipefail
NOVNC_DIR=/usr/share/novnc
WEBSOCKIFY=/usr/share/novnc/utils/novnc_proxy

export DISPLAY=:0
# 1) Virtual display
Xvfb :0 -screen 0 1920x1080x24 &

# Wait for the X socket to exist and respond
echo "Waiting for Xvfb..."
for i in {1..30}; do
  if [ -S /tmp/.X11-unix/X0 ] && xset -display :0 q >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

# 2) Window manager (with dbus to avoid session quirks)
if command -v dbus-launch >/dev/null 2>&1; then
  dbus-launch openbox &
else
  openbox &
fi

# Wait until a WM registers on the root window
echo "Waiting for window manager..."
for i in {1..30}; do
  if xprop -root _NET_SUPPORTING_WM_CHECK >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

x11vnc -display :0 -forever -shared -rfbport 5900 -nopw -quiet &


$WEBSOCKIFY --vnc localhost:5900 --listen 0.0.0.0:5800 --web $NOVNC_DIR &
echo "noVNC running at http://0.0.0.0:5800/vnc.html"


