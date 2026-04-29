#!/bin/bash

trim_env_value() {
  local value="$*"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

load_proxy_env_defaults() {
  local env_file="${SMART_PROXY_ENV_FILE:-/app/service/.env}"
  local raw_line line key value

  if [ ! -f "$env_file" ]; then
    return 0
  fi

  echo "[proxy-init] loading proxy env defaults from ${env_file}"
  while IFS= read -r raw_line || [ -n "$raw_line" ]; do
    line="${raw_line%$'\r'}"
    line="$(trim_env_value "$line")"
    case "$line" in
      ""|\#*) continue ;;
    esac

    line="${line#export }"
    if [[ "$line" != *=* ]]; then
      continue
    fi

    key="$(trim_env_value "${line%%=*}")"
    value="$(trim_env_value "${line#*=}")"
    if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      continue
    fi

    case "$key" in
      SMART_PROXY_*|UPSTREAM_PROXY|UPSTREAM_PROXY_HOST|UPSTREAM_PROXY_PORT|ANDROID_SMART_PROXY_HOST|ANDROID_UPSTREAM_PROXY|CONTAINER_PROXY_HOST) ;;
      *) continue ;;
    esac

    if [ -n "${!key+x}" ]; then
      continue
    fi

    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    else
      value="${value%%[[:space:]]#*}"
      value="$(trim_env_value "$value")"
    fi

    export "$key=$value"
  done < "$env_file"
}

load_proxy_env_defaults

SMART_PROXY_PORT="${SMART_PROXY_PORT:-8118}"
SMART_PROXY_SCRIPT="${SMART_PROXY_SCRIPT:-/app/service/src/knowu_bench/smart_proxy.py}"
CONTAINER_PROXY_HOST="${CONTAINER_PROXY_HOST:-127.0.0.1}"
SMART_PROXY_LOG="${SMART_PROXY_LOG:-/var/log/smart_proxy.log}"

PROXY_URL="http://${CONTAINER_PROXY_HOST}:${SMART_PROXY_PORT}"

echo "[proxy-init] exporting proxy env: ${PROXY_URL}"
export http_proxy="${http_proxy:-$PROXY_URL}"
export https_proxy="${https_proxy:-$PROXY_URL}"
export HTTP_PROXY="${HTTP_PROXY:-$http_proxy}"
export HTTPS_PROXY="${HTTPS_PROXY:-$https_proxy}"
DEFAULT_NO_PROXY="127.0.0.1,localhost,10.0.2.2"
export no_proxy="${no_proxy:-$DEFAULT_NO_PROXY}"
export NO_PROXY="${NO_PROXY:-$no_proxy}"

is_proxy_ready() {
  python - "$SMART_PROXY_PORT" <<'PY'
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket()
sock.settimeout(0.5)
try:
    sock.connect(("127.0.0.1", port))
    print("ready")
except OSError:
    print("not-ready")
finally:
    sock.close()
PY
}

if [ ! -f "$SMART_PROXY_SCRIPT" ]; then
  echo "[proxy-init] smart proxy script not found: $SMART_PROXY_SCRIPT"
  return 0
fi

if [ "$(is_proxy_ready)" = "ready" ]; then
  echo "[proxy-init] smart proxy already running on port ${SMART_PROXY_PORT}"
  return 0
fi

echo "[proxy-init] starting smart proxy: $SMART_PROXY_SCRIPT"
nohup python "$SMART_PROXY_SCRIPT" "$SMART_PROXY_PORT" >> "$SMART_PROXY_LOG" 2>&1 &

for _ in {1..20}; do
  if [ "$(is_proxy_ready)" = "ready" ]; then
    echo "[proxy-init] smart proxy started on ${SMART_PROXY_PORT}"
    return 0
  fi
  sleep 0.2
done

echo "[proxy-init] warning: smart proxy failed to become ready"
return 0
