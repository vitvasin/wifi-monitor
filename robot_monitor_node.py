#!/usr/bin/env python3
"""Robot usage monitor: tracks navigation goals, working status, and session times.

Subscribes to:
  /nav_p2p/named_target  — named navigation goal (std_msgs/String)
  /nav_p2p/setpoint      — coordinate goal (geometry_msgs/Vector3)
  /nav_p2p/go            — go command trigger (std_msgs/Int8)
  /robot_status/working  — working state changes (std_msgs/String)
"""

import atexit
import csv
import datetime
import configparser
import logging
import math
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
EVENTS_FILE = LOG_DIR / "robot_events.csv"
ROBOT_SYNC_STATE = BASE_DIR / ".robot_sync_state"
CONFIG_FILE = BASE_DIR / "config.ini"

EVENT_FIELDS = ["timestamp", "robot_name", "event_type", "detail"]


def load_config():
    cfg = configparser.ConfigParser()
    cfg.read([CONFIG_FILE, BASE_DIR / "config.local.ini"])
    return cfg


def write_event(robot_name, event_type, detail=""):
    LOG_DIR.mkdir(exist_ok=True)
    new_file = not EVENTS_FILE.exists()
    with open(EVENTS_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
        if new_file:
            w.writeheader()
        w.writerow({
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "robot_name": robot_name,
            "event_type": event_type,
            "detail": detail,
        })


def main():
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String, Int8
    from geometry_msgs.msg import Vector3

    cfg = load_config()
    robot_name = cfg.get("monitor", "robot_name", fallback="")
    sync_interval = cfg.getint("robot_monitor", "sync_interval", fallback=300)
    setpoint_threshold = cfg.getfloat("robot_monitor", "setpoint_change_threshold", fallback=0.05)

    level = getattr(logging, cfg.get("monitor", "log_level", fallback="INFO").upper(), logging.INFO)
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / "robot_monitor.log"),
        ],
    )
    logger = logging.getLogger(__name__)

    write_event(robot_name, "session_start", "robot_monitor_node started")
    logger.info("Robot monitor started")

    def on_shutdown():
        write_event(robot_name, "session_end", "robot_monitor_node stopped")
        logger.info("Robot monitor stopped")

    atexit.register(on_shutdown)

    rclpy.init()

    class RobotMonitorNode(Node):
        def __init__(self):
            super().__init__("robot_monitor_node")
            self._last_working = None
            self._last_go = None
            self._last_named = None
            self._last_setpoint = None  # (x, y, z)

            self.create_subscription(String, "/nav_p2p/named_target", self.on_named_target, 10)
            self.create_subscription(Vector3, "/nav_p2p/setpoint", self.on_setpoint, 10)
            self.create_subscription(Int8, "/nav_p2p/go", self.on_go, 10)
            self.create_subscription(String, "/robot_status/working", self.on_working_status, 10)
            self.create_timer(sync_interval, self.sync_sheets)

            logger.info("Subscribed to robot topics (sync_interval=%ds)", sync_interval)

        def on_named_target(self, msg):
            if msg.data == self._last_named:
                return
            self._last_named = msg.data
            write_event(robot_name, "nav_goal_named", msg.data)
            logger.info("Nav goal (named): %s", msg.data)

        def on_setpoint(self, msg):
            pos = (msg.x, msg.y, msg.z)
            if self._last_setpoint is not None:
                dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(pos, self._last_setpoint)))
                if dist < setpoint_threshold:
                    return
            self._last_setpoint = pos
            detail = f"x={msg.x:.3f},y={msg.y:.3f},z={msg.z:.3f}"
            write_event(robot_name, "nav_goal_setpoint", detail)
            logger.info("Nav goal (setpoint): %s", detail)

        def on_go(self, msg):
            if msg.data == self._last_go:
                return
            self._last_go = msg.data
            write_event(robot_name, "nav_go", str(msg.data))
            logger.info("Nav go: %s", msg.data)

        def on_working_status(self, msg):
            if msg.data == self._last_working:
                return
            prev = self._last_working
            self._last_working = msg.data
            detail = f"{prev}->{msg.data}" if prev is not None else msg.data
            write_event(robot_name, "working_state", detail)
            logger.info("Working state: %s", detail)

        def sync_sheets(self):
            if not cfg.getboolean("sheets", "enabled", fallback=False):
                return
            try:
                sys.path.insert(0, str(BASE_DIR))
                from sheets_sync import sync_robot_events
                sync_robot_events(cfg, EVENTS_FILE, ROBOT_SYNC_STATE, logger)
            except Exception as e:
                logger.error("Robot events sync failed: %s", e)

    node = RobotMonitorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
