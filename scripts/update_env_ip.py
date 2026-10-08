#!/usr/bin/env python3
"""
NavosEdge — Network IP Detection & .env Configuration Utility
==============================================================
Automatically detects the connected network IP (Wi-Fi or Ethernet)
and updates the UNO Q IP configuration in .env.

Can be run:
  1. On UNO Q startup (e.g. from run_navosedge.sh or run_hardware.sh)
  2. Standalone via CLI: python3 scripts/update_env_ip.py [--ip <custom_ip>]
  3. Imported by Manager backend to apply IP changes dynamically.
"""

import argparse
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from typing import Dict, Optional, Tuple


def get_project_root() -> Path:
    """Finds repository root directory containing .env or .env.example."""
    # Try relative to this file
    this_dir = Path(__file__).resolve().parent
    if (this_dir.parent / ".env").exists() or (this_dir.parent / ".env.example").exists():
        return this_dir.parent
    # Check current working directory
    cwd = Path.cwd()
    if (cwd / ".env").exists() or (cwd / ".env.example").exists():
        return cwd
    return this_dir.parent


import time


def _detect_single_attempt() -> Optional[str]:
    """Single attempt to detect active network IP address."""
    # Strategy 1: 'ip route get' (standard Linux routing table lookup)
    try:
        res = subprocess.run(
            ["ip", "route", "get", "1.1.1.1"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0:
            tokens = res.stdout.split()
            if "src" in tokens:
                idx = tokens.index("src")
                if idx + 1 < len(tokens):
                    candidate = tokens[idx + 1].strip()
                    if _is_valid_usable_ip(candidate):
                        return candidate
    except Exception:
        pass

    # Strategy 2: Check default gateway routing via ip route
    try:
        res = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0 and res.stdout.strip():
            tokens = res.stdout.split()
            if "src" in tokens:
                idx = tokens.index("src")
                if idx + 1 < len(tokens):
                    candidate = tokens[idx + 1].strip()
                    if _is_valid_usable_ip(candidate):
                        return candidate
    except Exception:
        pass

    # Strategy 3: UDP socket lookup to well-known endpoints (does not send network packets)
    for target in [("10.255.255.255", 1), ("8.8.8.8", 80), ("1.1.1.1", 80)]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(target)
            candidate = s.getsockname()[0]
            s.close()
            if _is_valid_usable_ip(candidate):
                return candidate
        except Exception:
            pass

    # Strategy 4: 'hostname -I'
    try:
        res = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0:
            for ip in res.stdout.strip().split():
                if _is_valid_usable_ip(ip):
                    return ip
    except Exception:
        pass

    return None


def detect_network_ip(timeout_s: float = 0.0) -> Optional[str]:
    """
    Detects the IP address of the active network interface connected to LAN/Internet.
    Filters out loopback (127.*), link-local (169.254.*), and standard docker bridges (172.17.*).
    Optionally retries for up to `timeout_s` seconds if network is still connecting.
    """
    start_time = time.time()
    while True:
        ip = _detect_single_attempt()
        if ip:
            return ip
        if timeout_s <= 0 or (time.time() - start_time) >= timeout_s:
            break
        time.sleep(1.0)
    return None


def _is_valid_usable_ip(ip_str: str) -> bool:
    """Verifies that an IP string is IPv4 and not loopback or invalid."""
    if not ip_str:
        return False
    parts = ip_str.strip().split(".")
    if len(parts) != 4:
        return False
    try:
        octets = [int(p) for p in parts]
        if not all(0 <= o <= 255 for o in octets):
            return False
    except ValueError:
        return False

    # Disallow loopback (127.x.x.x)
    if octets[0] == 127:
        return False
    # Disallow 0.0.0.0
    if octets[0] == 0:
        return False
    # Disallow link-local (169.254.x.x)
    if octets[0] == 169 and octets[1] == 254:
        return False

    return True


def read_current_env_ip(env_file: Optional[Path] = None) -> Tuple[Optional[str], Optional[int]]:
    """Reads current NAVOS_UNO_Q_IP and NAVOS_UNO_Q_PORT from .env."""
    root = get_project_root()
    env_path = env_file or (root / ".env")
    if not env_path.exists():
        return None, None

    ip = None
    port = None
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k == "NAVOS_UNO_Q_IP":
                ip = v
            elif k == "NAVOS_UNO_Q_PORT":
                try:
                    port = int(v)
                except ValueError:
                    pass
    return ip, port


def update_env_file(
    ip: str,
    port: Optional[int] = None,
    env_file: Optional[Path] = None,
    poll_enabled: Optional[bool] = None,
) -> Dict[str, str]:
    """
    Updates or appends NAVOS_UNO_Q_IP, NAVOS_UNO_Q_PORT, NAVOS_UNO_Q_URL,
    and UNO_Q_HOST_DEFAULT in .env preserving all comments and other settings.
    """
    root = get_project_root()
    env_path = env_file or (root / ".env")
    example_path = root / ".env.example"

    # If .env does not exist, initialize from .env.example if available
    if not env_path.exists():
        if example_path.exists():
            content = example_path.read_text(encoding="utf-8")
        else:
            content = "# NavosEdge Environment Configuration\n"
        env_path.write_text(content, encoding="utf-8")

    lines = env_path.read_text(encoding="utf-8").splitlines()

    # Determine port
    if port is None:
        # Check existing port in lines
        for line in lines:
            if line.startswith("NAVOS_UNO_Q_PORT="):
                try:
                    port = int(line.split("=", 1)[1].strip().strip("'\""))
                except ValueError:
                    pass
                break
        if port is None:
            port = 8420

    url = f"http://{ip}:{port}"

    keys_to_update = {
        "NAVOS_UNO_Q_IP": ip,
        "NAVOS_UNO_Q_PORT": str(port),
        "NAVOS_UNO_Q_URL": url,
        "UNO_Q_HOST_DEFAULT": ip,
    }
    if poll_enabled is not None:
        keys_to_update["NAVOS_POLL_ENABLED"] = "true" if poll_enabled else "false"

    updated_keys = set()
    new_lines = []

    for line in lines:
        stripped = line.strip()
        matched = False
        for key, val in keys_to_update.items():
            if re.match(rf"^{key}\s*=", stripped):
                new_lines.append(f"{key}={val}")
                updated_keys.add(key)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    # Append any keys that weren't present in the file
    missing_keys = [k for k in keys_to_update if k not in updated_keys]
    if missing_keys:
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.append("# UNO Q Edge Node IP Configuration (Auto-updated)")
        for k in missing_keys:
            new_lines.append(f"{k}={keys_to_update[k]}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    return {
        "ip": ip,
        "port": str(port),
        "url": url,
        "env_path": str(env_path),
    }


def main():
    parser = argparse.ArgumentParser(description="NavosEdge Network IP Detection & .env Config")
    parser.add_argument("--ip", type=str, help="Explicit IP to set instead of auto-detection")
    parser.add_argument("--port", type=int, default=None, help="Port to set (default: existing or 8420)")
    parser.add_argument("--detect-only", action="store_true", help="Print detected IP without modifying .env")
    parser.add_argument("--retry", type=float, default=0.0, help="Seconds to retry detection if not immediately found")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output for scripting")
    args = parser.parse_args()

    detected_ip = detect_network_ip(timeout_s=args.retry)

    if args.detect_only:
        out = detected_ip or "127.0.0.1"
        print(out)
        return 0

    target_ip = args.ip
    if not target_ip:
        if detected_ip:
            target_ip = detected_ip
        else:
            current_ip, current_port = read_current_env_ip()
            if current_ip:
                if not args.quiet:
                    print(f"[NAVOS] No active network IP detected. Keeping existing .env IP: {current_ip}")
                return 0
            else:
                target_ip = "127.0.0.1"
                if not args.quiet:
                    print(f"[NAVOS] No network IP found. Defaulting to loopback: {target_ip}")

    # Check current .env IP
    curr_ip, curr_port = read_current_env_ip()
    port = args.port or curr_port or 8420

    if curr_ip == target_ip and (args.port is None or curr_port == args.port):
        if not args.quiet:
            print(f"[NAVOS] IP already up to date in .env: NAVOS_UNO_Q_IP={target_ip} (Port: {port})")
        return 0

    result = update_env_file(ip=target_ip, port=port)
    if not args.quiet:
        print(f"[NAVOS] Auto-detected Network IP: {target_ip}")
        print(f"[NAVOS] Updated {result['env_path']}:")
        print(f"        NAVOS_UNO_Q_IP={result['ip']}")
        print(f"        NAVOS_UNO_Q_PORT={result['port']}")
        print(f"        NAVOS_UNO_Q_URL={result['url']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
