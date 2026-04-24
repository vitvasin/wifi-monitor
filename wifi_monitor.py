#!/usr/bin/env python3
"""WiFi connection monitor: tracks hardware, local, and internet status."""

import csv
import socket
import subprocess
import time
import datetime
import configparser
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
CSV_FILE = LOG_DIR / "wifi_log.csv"
CONFIG_FILE = BASE_DIR / "config.ini"
SYNC_STATE_FILE = BASE_DIR / ".sync_state"

CSV_FIELDS = [
    "timestamp", "robot_name", "interface", "hardware", "hardware_detail",
    "ssid", "rssi_dbm", "freq_mhz",
    "gateway", "local", "local_latency_ms",
    "internet", "internet_latency_ms",
]


def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE)
    return cfg


def get_wifi_interface():
    try:
        result = subprocess.run(
            ["ip", "link", "show"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            for prefix in ("wlan", "wlp", "wlx"):
                if prefix in line and ":" in line:
                    name = line.split(":")[1].strip().split("@")[0]
                    return name
    except Exception:
        pass
    return None


def get_wifi_info(interface):
    """Return (ssid, rssi_dbm, freq_mhz) via `iw dev <iface> link`."""
    if not interface:
        return None, None, None
    try:
        r = subprocess.run(
            ["iw", "dev", interface, "link"],
            capture_output=True, text=True, timeout=5,
        )
        if "Not connected" in r.stdout:
            return None, None, None
        ssid = rssi = freq = None
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("SSID:"):
                ssid = line.split(":", 1)[1].strip()
            elif line.startswith("signal:"):
                rssi = float(line.split(":")[1].split()[0])
            elif line.startswith("freq:"):
                freq = float(line.split(":")[1].strip())
        return ssid, rssi, freq
    except Exception:
        return None, None, None


def check_hardware(interface):
    if not interface:
        return False, "no_interface"
    operstate = Path(f"/sys/class/net/{interface}/operstate")
    if operstate.exists():
        state = operstate.read_text().strip()
        return state in ("up", "unknown"), state
    try:
        r = subprocess.run(
            ["ip", "link", "show", interface], capture_output=True, text=True, timeout=5
        )
        up = "UP" in r.stdout
        return up, "UP" if up else "DOWN"
    except Exception as e:
        return False, str(e)[:50]


def get_default_gateway():
    try:
        r = subprocess.run(
            ["ip", "route", "show", "default"], capture_output=True, text=True, timeout=5
        )
        for line in r.stdout.splitlines():
            if "default" in line and "via" in line:
                parts = line.split()
                return parts[parts.index("via") + 1]
    except Exception:
        pass
    return None


def check_local(gateway, timeout):
    if not gateway:
        return False, "no_gateway", None
    try:
        r = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), gateway],
            capture_output=True, text=True, timeout=timeout + 2,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if "time=" in line:
                    latency = float(line.split("time=")[1].split()[0])
                    return True, "ok", round(latency, 2)
            return True, "ok", None
        return False, "no_response", None
    except Exception as e:
        return False, str(e)[:50], None


def check_internet(host, port, timeout):
    try:
        start = time.monotonic()
        s = socket.create_connection((host, int(port)), timeout=float(timeout))
        latency = round((time.monotonic() - start) * 1000, 2)
        s.close()
        return True, "ok", latency
    except OSError as e:
        return False, str(e)[:50], None


def write_csv(row):
    LOG_DIR.mkdir(exist_ok=True)
    new_file = not CSV_FILE.exists()
    with open(CSV_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(row)


def maybe_sync_sheets(cfg, logger):
    if not cfg.getboolean("sheets", "enabled", fallback=False):
        return
    try:
        from sheets_sync import sync_to_sheets
        sync_to_sheets(cfg, CSV_FILE, SYNC_STATE_FILE, logger)
    except ImportError:
        logger.warning("sheets_sync module not found, skipping sync")
    except Exception as e:
        logger.error(f"Sheets sync failed: {e}")


def main():
    cfg = load_config()
    level = getattr(logging, cfg.get("monitor", "log_level", fallback="INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / "monitor.log" if LOG_DIR.exists() else Path("/tmp/wifi_monitor.log")),
        ],
    )
    LOG_DIR.mkdir(exist_ok=True)
    logging.getLogger().handlers[1] = logging.FileHandler(LOG_DIR / "monitor.log")
    logger = logging.getLogger(__name__)

    robot_name = cfg.get("monitor", "robot_name", fallback="")
    interval = cfg.getint("monitor", "interval", fallback=60)
    inet_host = cfg.get("monitor", "internet_host", fallback="8.8.8.8")
    inet_port = cfg.get("monitor", "internet_port", fallback="53")
    timeout = cfg.getint("monitor", "timeout", fallback=3)
    sync_interval = cfg.getint("sheets", "sync_interval", fallback=300)

    logger.info("WiFi monitor started (interval=%ds)", interval)
    last_sync = 0.0

    while True:
        now = time.monotonic()
        timestamp = datetime.datetime.now().isoformat(timespec="seconds")

        interface = get_wifi_interface()
        gateway = get_default_gateway()

        hw_ok, hw_detail = check_hardware(interface)
        ssid, rssi, freq = get_wifi_info(interface)
        local_ok, local_detail, local_lat = check_local(gateway, timeout)
        inet_ok, inet_detail, inet_lat = check_internet(inet_host, inet_port, timeout)

        row = {
            "timestamp": timestamp,
            "robot_name": robot_name,
            "interface": interface or "",
            "hardware": "ok" if hw_ok else "fail",
            "hardware_detail": hw_detail,
            "ssid": ssid or "",
            "rssi_dbm": rssi if rssi is not None else "",
            "freq_mhz": freq if freq is not None else "",
            "gateway": gateway or "",
            "local": "ok" if local_ok else "fail",
            "local_latency_ms": local_lat if local_lat is not None else "",
            "internet": "ok" if inet_ok else "fail",
            "internet_latency_ms": inet_lat if inet_lat is not None else "",
        }

        write_csv(row)
        logger.info(
            "%s | hw:%s ssid:%s rssi:%s freq:%s | local:%s(%s) inet:%s(%s) gw:%s",
            interface or "?", row["hardware"],
            ssid or "none", f"{rssi}dBm" if rssi else "-", f"{freq}MHz" if freq else "-",
            row["local"], f"{local_lat}ms" if local_lat else "-",
            row["internet"], f"{inet_lat}ms" if inet_lat else "-",
            gateway or "?",
        )

        if now - last_sync >= sync_interval:
            maybe_sync_sheets(cfg, logger)
            last_sync = now

        time.sleep(interval)


if __name__ == "__main__":
    main()
