# KnowU-Bench Proxy Guide

This project uses a two-layer proxy setup for benchmark containers and Android
emulators.

## Proxy Chain

The normal network path is:

```text
Container process
  -> http://127.0.0.1:8118
  -> smart_proxy.py inside the knowu-bench container
  -> SMART_PROXY_UPSTREAM, for example 10.130.138.46:7897
  -> external network
```

For Android emulator apps, the path is:

```text
Android emulator app
  -> http://10.0.2.2:8118
  -> smart_proxy.py inside the knowu-bench container
  -> SMART_PROXY_UPSTREAM
  -> external network
```

`10.0.2.2` is the Android emulator's special address for reaching the host side
of the emulator. In this container setup, it reaches the container-side smart
proxy.

## Main Configuration

The upstream proxy is configured in the repository root `.env` file:

```env
SMART_PROXY_UPSTREAM=10.130.138.46:7897
```

Common values:

```env
SMART_PROXY_UPSTREAM=10.130.138.46:7897
SMART_PROXY_UPSTREAM=10.130.138.47:7897
```

The container starts a local smart proxy on port `8118` by default:

```env
SMART_PROXY_PORT=8118
```

If `SMART_PROXY_UPSTREAM` is not set, `src/knowu_bench/smart_proxy.py` currently
defaults to:

```text
10.130.138.46:7897
```

## How It Is Loaded

When a knowu-bench container starts, `docker/entrypoint.sh` sources:

```bash
/app/docker/start_proxy.sh
```

That script:

1. Loads proxy-related variables from `/app/service/.env`.
2. Starts `smart_proxy.py` on `SMART_PROXY_PORT`, default `8118`.
3. Exports container Linux process proxy variables:

```bash
http_proxy=http://127.0.0.1:8118
https_proxy=http://127.0.0.1:8118
HTTP_PROXY=http://127.0.0.1:8118
HTTPS_PROXY=http://127.0.0.1:8118
NO_PROXY=127.0.0.1,localhost,10.0.2.2
```

This affects Linux processes inside the container, such as `uv`, Python, curl,
and the benchmark server.

Android emulator apps are separate. They need Android's global HTTP proxy set to:

```text
10.0.2.2:8118
```

## Change Proxy for New Containers

Edit `.env`:

```env
SMART_PROXY_UPSTREAM=10.130.138.46:7897
```

Then create a new container:

```bash
mw env run --count 1 --dev --image knowu-bench:latest --launch-interval 20 --name-prefix experiment
```

For 8 evaluation containers:

```bash
mw env run --count 8 --image knowu-bench:latest --launch-interval 20
```

Newly created containers will read the current `.env`.

## Important: Docker Restart Does Not Change Env

`docker restart` does not reload repository `.env` and does not change the
container's creation-time environment variables.

This means:

```bash
docker restart experiment_0_dev
```

may keep using the old upstream proxy if the container was created with an old
environment.

For a permanent clean change, remove and recreate the container:

```bash
docker rm -f experiment_0_dev
mw env run --count 1 --dev --image knowu-bench:latest --launch-interval 20 --name-prefix experiment
```

## Change Proxy in a Running Container

To switch a running container without recreating it, restart only the smart proxy
process and pass the new upstream explicitly:

```bash
docker exec experiment_0_dev bash -lc '
pids=$(ps -eo pid,args | awk "/[s]mart_proxy.py 8118/ {print \$1}")
if [ -n "$pids" ]; then kill $pids; fi
cd /app/service
SMART_PROXY_UPSTREAM=10.130.138.46:7897 nohup python /app/service/src/knowu_bench/smart_proxy.py 8118 >> /var/log/smart_proxy.log 2>&1 &
'
```

Confirm the new upstream:

```bash
docker exec experiment_0_dev bash -lc 'grep "Upstream:" /var/log/smart_proxy.log | tail -n 5'
```

Expected output:

```text
Upstream: 10.130.138.46:7897
```

This is only a runtime change. If the container is restarted later, it may return
to the environment captured when the container was created.

## Set Android Emulator Proxy

Set Android global HTTP proxy:

```bash
docker exec experiment_0_dev adb shell settings put global http_proxy 10.0.2.2:8118
```

Check it:

```bash
docker exec experiment_0_dev adb shell settings get global http_proxy
```

Expected:

```text
10.0.2.2:8118
```

Clear Android proxy:

```bash
docker exec experiment_0_dev adb shell settings put global http_proxy :0
```

## Android Route Fix

Sometimes the Android emulator has the correct Wi-Fi proxy but still shows no
network. Check route state:

```bash
docker exec experiment_0_dev adb shell ip route
```

A healthy route table should include:

```text
default via 10.0.2.2 dev eth0
```

If missing, Android may not be able to reach `10.0.2.2:8118` even if the proxy
setting is correct. Add it:

```bash
docker exec experiment_0_dev adb shell ip route add default via 10.0.2.2 dev eth0
```

Then re-apply the Android proxy:

```bash
docker exec experiment_0_dev adb shell settings put global http_proxy 10.0.2.2:8118
```

If the VNC UI still shows no network, toggle Wi-Fi:

```bash
docker exec experiment_0_dev adb shell svc wifi disable
sleep 2
docker exec experiment_0_dev adb shell svc wifi enable
docker exec experiment_0_dev adb shell settings put global http_proxy 10.0.2.2:8118
docker exec experiment_0_dev adb shell ip route add default via 10.0.2.2 dev eth0 2>/dev/null || true
```

## Verify Proxy

### Test Upstream Proxy From Host

```bash
curl -I --max-time 30 -x http://10.130.138.46:7897 https://pypi.org/simple/hatchling/
```

Expected:

```text
HTTP/1.1 200 Connection established
HTTP/2 200
```

Docker Hub may be slower:

```bash
curl -I --max-time 30 -x http://10.130.138.46:7897 https://registry-1.docker.io/v2/
```

Expected when reachable:

```text
HTTP/1.1 200 Connection established
HTTP/2 401
```

`401 Unauthorized` is normal for Docker Hub registry root. It means the registry
is reachable.

### Test Smart Proxy Inside Container

```bash
docker exec experiment_0_dev curl -I --max-time 15 -x http://127.0.0.1:8118 https://pypi.org/simple/hatchling/
```

Expected:

```text
HTTP/1.1 200 Connection established
HTTP/2 200
```

### Watch Smart Proxy Logs

```bash
docker exec experiment_0_dev tail -f /var/log/smart_proxy.log
```

Successful requests look like:

```text
CONNECT www.google.com:443 -> UPSTREAM
upstream tunnel ok
HTTP-UPSTREAM GET connectivitycheck.gstatic.com:80/generate_204
```

Failed upstream proxy usually looks like:

```text
CONNECT UPSTREAM FAILED: [Errno 111] Connection refused
HTTP-UPSTREAM FAILED: [Errno 111] Connection refused
```

This means the configured upstream proxy, such as `10.130.138.46:7897`, is not
accepting connections from the container at that time.

## Common Problems

### Container Is Healthy But Android Has No Network

Check Android proxy:

```bash
docker exec experiment_0_dev adb shell settings get global http_proxy
```

Check Android route:

```bash
docker exec experiment_0_dev adb shell ip route
```

Fix:

```bash
docker exec experiment_0_dev adb shell settings put global http_proxy 10.0.2.2:8118
docker exec experiment_0_dev adb shell ip route add default via 10.0.2.2 dev eth0 2>/dev/null || true
```

### `ping` Fails In Android

This does not necessarily mean HTTP proxy is broken. `ping` does not use an HTTP
proxy. Use smart proxy logs and browser/WebView requests to verify actual app
network traffic.

### `uv` Or Server Startup Fails Downloading Packages

Check `/var/log/server.log`:

```bash
docker exec experiment_0_dev tail -n 120 /var/log/server.log
```

If errors mention `hatchling`, `dill`, PyPI, or timeout, test:

```bash
docker exec experiment_0_dev curl -I --max-time 15 -x http://127.0.0.1:8118 https://pypi.org/simple/hatchling/
```

If this fails, check `SMART_PROXY_UPSTREAM` and the upstream proxy service.

### Docker Build Cannot Pull Base Image

The benchmark container proxy does not automatically affect Docker daemon or
BuildKit. If `docker buildx build` fails while fetching Docker Hub metadata, you
need Docker daemon or BuildKit proxy configuration separately.

Test from host:

```bash
curl -I --max-time 30 -x http://10.130.138.46:7897 https://registry-1.docker.io/v2/
```

If this works but Docker build still fails, configure proxy for Docker daemon or
the buildx builder.

