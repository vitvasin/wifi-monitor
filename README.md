# wifi-monitor

Monitors WiFi connectivity and robot usage on ROS 2 robots, logging to CSV and syncing to Google Sheets.

## Features

- **WiFi monitor** — polls hardware, SSID, RSSI, gateway, and internet reachability every N seconds
- **Robot monitor** — ROS 2 node tracking navigation goals, working state changes, and session on/off times
- **Google Sheets sync** — appends new rows to separate worksheets on a configurable interval

## Requirements

- Python 3.12+
- ROS 2 Jazzy (for robot monitor)
- Google Cloud credentials (OAuth or service account)

## Setup

```bash
cp config.ini.example config.ini
# Edit config.ini — set robot_name, spreadsheet_id, etc.

bash setup.sh
```

`setup.sh` creates the venv, installs dependencies, and registers + starts the `wifi-monitor` systemd service.

### Robot monitor (separate service)

```bash
sudo cp robot-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable robot-monitor
sudo systemctl start robot-monitor
```

> Set `ROS_DOMAIN_ID` in `robot-monitor.service` to match your robot's ROS domain.

## Configuration

Copy `config.ini.example` to `config.ini` and set values. Robot-specific overrides go in `config.local.ini` (gitignored).

| Section | Key | Description |
|---|---|---|
| `monitor` | `robot_name` | Label shown in all log rows |
| `monitor` | `interval` | WiFi poll interval (seconds) |
| `robot_monitor` | `sync_interval` | Sheets sync interval (seconds) |
| `robot_monitor` | `setpoint_change_threshold` | Min movement (meters) to log a new setpoint |
| `sheets` | `auth_mode` | `oauth` or `service_account` |
| `sheets` | `spreadsheet_id` | Google Sheets document ID |
| `sheets` | `worksheet_name` | Worksheet name for WiFi log |
| `robot_monitor` | `worksheet_name` | Worksheet name for robot events |

## Google Sheets Auth

### OAuth (personal account)

```bash
python3 -c "
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
SCOPES = ['https://www.googleapis.com/auth/spreadsheets','https://www.googleapis.com/auth/drive.file']
flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
creds = flow.run_local_server(port=8080, open_browser=False)
Path('.oauth_token.json').write_text(creds.to_json())
"
```

Requires SSH port forward: `ssh -L 8080:localhost:8080 user@robot-ip`

### Service account

Set `auth_mode = service_account` and place the service account JSON as `credentials.json`.

## Log files

| File | Contents |
|---|---|
| `logs/wifi_log.csv` | WiFi connectivity rows |
| `logs/robot_events.csv` | Robot usage events |
| `logs/monitor.log` | WiFi monitor logs |
| `logs/robot_monitor.log` | Robot monitor logs |

## Robot events tracked

| `event_type` | Trigger | `detail` |
|---|---|---|
| `session_start` | Node starts (robot on) | — |
| `session_end` | Node stops (robot off) | — |
| `nav_goal_named` | New named navigation target | target name |
| `nav_goal_setpoint` | Coordinate goal (>threshold change) | `x=,y=,z=` |
| `nav_go` | Go command value changes | `0` or `1` |
| `working_state` | Working state transition | `prev->new` |

## Updating

```bash
bash update.sh
```

Pulls latest code, updates dependencies, and restarts the service.
