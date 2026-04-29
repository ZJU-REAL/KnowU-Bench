#!/usr/bin/env python3
"""
Smart HTTP/CONNECT proxy with WebSocket support + header fixing.
Local hosts (10.0.2.2) -> connect directly to 127.0.0.1
All other traffic -> forward to upstream proxy
Fixes Proxy-Connection -> Connection for WebSocket upgrades.
"""
import socket
import select
import threading
import sys
import re
import time
import os
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_UPSTREAM_PROXY = ("10.130.138.46", 7897)
DEFAULT_DIRECT_HOSTS = {"10.0.2.2", "127.0.0.1", "localhost"}
DEFAULT_DIRECT_ADDR = "127.0.0.1"
DEFAULT_LISTEN_HOST = "0.0.0.0"
DEFAULT_LISTEN_PORT = 8118

LOG_LOCK = threading.Lock()


def log(msg):
    with LOG_LOCK:
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)


def _strip_quotes(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_env_defaults(path):
    if not path.exists():
        return
    try:
        lines = path.read_text().splitlines()
    except OSError as e:
        log(f"Could not read env file {path}: {e}")
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if key in os.environ or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            continue
        value = value.strip()
        quote_chars = ("'", '"')
        if not (value.startswith(quote_chars) and value.endswith(quote_chars)):
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        os.environ[key] = _strip_quotes(value)


def _load_proxy_dotenv():
    candidates = []
    if env_file := os.getenv("SMART_PROXY_ENV_FILE"):
        candidates.append(Path(env_file))
    candidates.extend([Path("/app/service/.env"), Path.cwd() / ".env"])

    seen = set()
    for path in candidates:
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        _load_env_defaults(resolved)


def _parse_proxy_endpoint(raw):
    value = raw.strip()
    if not value:
        raise ValueError("empty proxy endpoint")

    if "://" in value:
        parsed = urlsplit(value)
        if not parsed.hostname or parsed.port is None:
            raise ValueError(f"proxy endpoint must include host and port: {raw}")
        return parsed.hostname, parsed.port

    host, sep, port = value.rpartition(":")
    if not sep or not host or not port:
        raise ValueError(f"proxy endpoint must be host:port: {raw}")
    return host, int(port)


def _env_int(*names, default):
    for name in names:
        value = os.getenv(name)
        if value:
            return int(value)
    return default


def _upstream_proxy_from_env():
    for name in ("SMART_PROXY_UPSTREAM", "UPSTREAM_PROXY"):
        if value := os.getenv(name):
            return _parse_proxy_endpoint(value)

    host = (
        os.getenv("SMART_PROXY_UPSTREAM_HOST")
        or os.getenv("UPSTREAM_PROXY_HOST")
        or DEFAULT_UPSTREAM_PROXY[0]
    )
    port = _env_int(
        "SMART_PROXY_UPSTREAM_PORT",
        "UPSTREAM_PROXY_PORT",
        default=DEFAULT_UPSTREAM_PROXY[1],
    )
    return host, port


def _direct_hosts_from_env():
    raw = os.getenv("SMART_PROXY_DIRECT_HOSTS")
    if not raw:
        return set(DEFAULT_DIRECT_HOSTS)
    return {host.strip() for host in raw.split(",") if host.strip()}


_load_proxy_dotenv()
UPSTREAM_PROXY = _upstream_proxy_from_env()
DIRECT_HOSTS = _direct_hosts_from_env()
DIRECT_ADDR = os.getenv("SMART_PROXY_DIRECT_ADDR", DEFAULT_DIRECT_ADDR)
LISTEN_HOST = os.getenv("SMART_PROXY_LISTEN_HOST", DEFAULT_LISTEN_HOST)
LISTEN_PORT = _env_int("SMART_PROXY_PORT", default=DEFAULT_LISTEN_PORT)


def tunnel(s1, s2, label=""):
    pair = [s1, s2]
    bytes_total = 0
    try:
        while True:
            r, _, x = select.select(pair, [], pair, 120)
            if x or not r:
                if not r:
                    log(f"  {label} tunnel timeout (120s idle)")
                break
            for s in r:
                data = s.recv(65536)
                if not data:
                    return
                bytes_total += len(data)
                target = s2 if s is s1 else s1
                target.sendall(data)
    except Exception as e:
        log(f"  {label} tunnel error: {e}")
    finally:
        log(f"  {label} tunnel closed ({bytes_total} bytes)")
        for s in (s1, s2):
            try:
                s.close()
            except Exception:
                pass


def recv_hdrs(sock):
    data = b""
    while b"\r\n\r\n" not in data:
        c = sock.recv(4096)
        if not c:
            return None, None
        data += c
    i = data.index(b"\r\n\r\n") + 4
    return data[:i], data[i:]


def fix_headers_for_direct(header_bytes, is_websocket):
    """Fix headers when forwarding to a direct (non-proxy) server.
    - Rewrite first line from absolute URL to relative path
    - Convert Proxy-Connection to Connection
    - Remove Proxy-Authorization
    - For WebSocket: ensure Connection: Upgrade is present
    """
    lines = header_bytes.split(b"\r\n")
    first_line = lines[0]
    parts = first_line.decode("latin-1").split(" ", 2)
    if len(parts) < 3:
        return None, None, None, None

    method, url, ver = parts
    m = re.match(r"http://([^/:]+)(?::(\d+))?(/.*)$", url)
    if not m:
        return None, None, None, None

    host = m.group(1)
    port = int(m.group(2)) if m.group(2) else 80
    path = m.group(3)

    # Rebuild headers
    new_lines = [f"{method} {path} {ver}".encode("latin-1")]
    has_connection = False
    for line in lines[1:]:
        if not line:  # empty line (end of headers)
            continue
        line_lower = line.lower()
        # Convert Proxy-Connection to Connection
        if line_lower.startswith(b"proxy-connection:"):
            value = line.split(b":", 1)[1].strip()
            new_lines.append(b"Connection: " + value)
            has_connection = True
        # Skip Proxy-Authorization
        elif line_lower.startswith(b"proxy-authorization:"):
            continue
        # Skip Origin header for WebSocket (Mattermost rejects mismatched Origin)
        elif line_lower.startswith(b"origin:") and is_websocket:
            continue
        # Track if Connection header exists
        elif line_lower.startswith(b"connection:"):
            new_lines.append(line)
            has_connection = True
        else:
            new_lines.append(line)

    # For WebSocket, ensure Connection: Upgrade is present
    if is_websocket and not has_connection:
        new_lines.append(b"Connection: Upgrade")

    new_lines.append(b"")
    new_lines.append(b"")
    rebuilt = b"\r\n".join(new_lines)
    return host, port, path, rebuilt


def do_connect(client, host, port):
    if host in DIRECT_HOSTS:
        log(f"CONNECT {host}:{port} -> DIRECT 127.0.0.1:{port}")
        try:
            remote = socket.create_connection((DIRECT_ADDR, port), timeout=10)
            client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            log(f"  tunnel established")
            tunnel(client, remote, f"CONNECT-D:{port}")
        except Exception as e:
            log(f"  CONNECT DIRECT FAILED: {e}")
            try:
                client.sendall(f"HTTP/1.1 502 Bad Gateway\r\n\r\n{e}".encode())
                client.close()
            except Exception:
                pass
    else:
        log(f"CONNECT {host}:{port} -> UPSTREAM")
        try:
            px = socket.create_connection(UPSTREAM_PROXY, timeout=10)
            px.sendall(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
            resp, extra = recv_hdrs(px)
            if resp and b"200" in resp.split(b"\r\n")[0]:
                client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                if extra:
                    client.sendall(extra)
                log(f"  upstream tunnel ok")
                tunnel(client, px, f"CONNECT-U:{host}")
            else:
                log(f"  upstream CONNECT rejected")
                client.sendall(resp or b"HTTP/1.1 502\r\n\r\n")
                client.close()
                px.close()
        except Exception as e:
            log(f"  CONNECT UPSTREAM FAILED: {e}")
            try:
                client.sendall(f"HTTP/1.1 502 Bad Gateway\r\n\r\n{e}".encode())
                client.close()
            except Exception:
                pass


def do_http(client, hdrs, extra):
    first = hdrs.split(b"\r\n")[0]
    hdr_str = hdrs.decode("latin-1", errors="replace").lower()
    is_ws = "upgrade" in hdr_str and "websocket" in hdr_str

    parts = first.decode("latin-1").split(" ", 2)
    if len(parts) < 3:
        client.close()
        return
    method, url, ver = parts
    m = re.match(r"http://([^/:]+)(?::(\d+))?(/.*)$", url)
    if not m:
        log(f"BAD URL: {url[:80]}")
        client.sendall(b"HTTP/1.1 400\r\n\r\n")
        client.close()
        return

    host = m.group(1)
    port = int(m.group(2)) if m.group(2) else 80
    path = m.group(3)

    if host in DIRECT_HOSTS:
        tag = "WS-DIRECT" if is_ws else "HTTP-DIRECT"
        log(f"{tag} {method} {host}:{port}{path}")
        try:
            # Fix headers for direct server
            _, _, _, rebuilt = fix_headers_for_direct(hdrs, is_ws)
            if rebuilt is None:
                client.sendall(b"HTTP/1.1 400\r\n\r\n")
                client.close()
                return

            if is_ws:
                # Log the rebuilt headers for debugging
                hdr_lines = rebuilt.decode("latin-1", errors="replace").split("\r\n")[:8]
                for hl in hdr_lines:
                    if hl.strip():
                        log(f"  >> {hl}")

            remote = socket.create_connection((DIRECT_ADDR, port), timeout=10)
            remote.sendall(rebuilt)
            if extra:
                remote.sendall(extra)

            if is_ws:
                # For WebSocket, peek at the server response
                resp_data = b""
                remote.settimeout(5)
                try:
                    while b"\r\n\r\n" not in resp_data:
                        chunk = remote.recv(4096)
                        if not chunk:
                            break
                        resp_data += chunk
                except socket.timeout:
                    log(f"  WS response timeout!")
                remote.settimeout(120)

                if resp_data:
                    resp_first = resp_data.split(b"\r\n")[0].decode("latin-1", errors="replace")
                    log(f"  << {resp_first}")
                    # Forward the response to client
                    client.sendall(resp_data)
                    if b"101" in resp_data.split(b"\r\n")[0]:
                        log(f"  WebSocket upgraded OK, starting tunnel")
                        tunnel(client, remote, f"WS:{port}")
                    else:
                        log(f"  WebSocket upgrade FAILED, server said: {resp_first}")
                        tunnel(client, remote, f"WS-FAIL:{port}")
                else:
                    log(f"  No response from server for WebSocket!")
                    client.close()
                    remote.close()
            else:
                tunnel(client, remote, f"HTTP-D:{port}")
        except Exception as e:
            log(f"  {tag} FAILED: {e}")
            try:
                client.sendall(f"HTTP/1.1 502\r\n\r\n{e}".encode())
                client.close()
            except Exception:
                pass
    else:
        tag = "WS-UPSTREAM" if is_ws else "HTTP-UPSTREAM"
        log(f"{tag} {method} {host}:{port}{path}")
        try:
            px = socket.create_connection(UPSTREAM_PROXY, timeout=10)
            px.sendall(hdrs)
            if extra:
                px.sendall(extra)
            tunnel(client, px, f"HTTP-U:{host}")
        except Exception as e:
            log(f"  {tag} FAILED: {e}")
            try:
                client.sendall(f"HTTP/1.1 502\r\n\r\n{e}".encode())
                client.close()
            except Exception:
                pass


def handle(client):
    try:
        hdrs, extra = recv_hdrs(client)
        if not hdrs:
            client.close()
            return
        first = hdrs.split(b"\r\n")[0]
        parts = first.split(b" ", 2)
        if len(parts) < 2:
            client.close()
            return
        method = parts[0].decode("latin-1").upper()
        if method == "CONNECT":
            hp = parts[1].decode("latin-1").split(":")
            do_connect(client, hp[0], int(hp[1]) if len(hp) > 1 else 443)
        else:
            do_http(client, hdrs, extra)
    except Exception as e:
        log(f"HANDLE ERROR: {e}")
        try:
            client.close()
        except Exception:
            pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else LISTEN_PORT
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, port))
    srv.listen(200)
    log(f"Smart proxy on {LISTEN_HOST}:{port}")
    log(f"Direct: {DIRECT_HOSTS} -> {DIRECT_ADDR}")
    log(f"Upstream: {UPSTREAM_PROXY[0]}:{UPSTREAM_PROXY[1]}")
    while True:
        c, _ = srv.accept()
        c.settimeout(120)
        threading.Thread(target=handle, args=(c,), daemon=True).start()


if __name__ == "__main__":
    main()
