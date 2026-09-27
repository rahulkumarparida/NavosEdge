#!/usr/bin/env python3
"""
NavosEdge — UNO Q Local TUI
Local terminal user interface for displaying real-time Edge Intelligence.
Works entirely offline by querying the local FastAPI server.

Usage:
    python3 scripts/unoq_tui.py [--node NODE_ID]
"""

import argparse
import curses
import json
import logging
import time
import urllib.request
from urllib.error import URLError

API_BASE = "http://127.0.0.1:8420"
logger = logging.getLogger(__name__)


def fetch_latest(node_id=None):
    try:
        if not node_id:
            # Auto-discover node
            req = urllib.request.Request(f"{API_BASE}/api/v1/nodes")
            with urllib.request.urlopen(req, timeout=2) as response:
                nodes_data = json.loads(response.read())
            if not nodes_data.get("nodes"):
                return None, "No nodes connected."
            node_id = nodes_data["nodes"][0]["node_id"]

        req = urllib.request.Request(f"{API_BASE}/api/v1/nodes/{node_id}/latest")
        with urllib.request.urlopen(req, timeout=2) as response:
            return json.loads(response.read()), None
    except URLError as e:
        return None, f"Connection failed: {e.reason}"
    except Exception as e:
        return None, f"Error: {str(e)}"


def draw_tui(stdscr, node_id):
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)   # GOOD
    curses.init_pair(2, curses.COLOR_YELLOW, -1)  # MODERATE / WARNING
    curses.init_pair(3, curses.COLOR_RED, -1)     # UNHEALTHY / DANGER
    curses.init_pair(4, curses.COLOR_CYAN, -1)    # INFO
    curses.init_pair(5, curses.COLOR_MAGENTA, -1) # SEVERE
    
    # Hide cursor
    curses.curs_set(0)
    stdscr.nodelay(1)  # Non-blocking input

    while True:
        # Handle resize / clear
        stdscr.erase()
        max_y, max_x = stdscr.getmaxyx()
        
        # Header
        title = f" NavosEdge UNO Q — Edge Intelligence "
        stdscr.attron(curses.A_REVERSE | curses.A_BOLD)
        stdscr.addstr(0, 0, title + " " * (max_x - len(title)))
        stdscr.attroff(curses.A_REVERSE | curses.A_BOLD)
        
        data, err = fetch_latest(node_id)
        
        if err:
            stdscr.addstr(2, 2, f"Waiting for local server... ({err})", curses.color_pair(2))
        elif data:
            try:
                # --- Parsed Data ---
                node = data.get("node_id", "UNKNOWN")
                ts = data.get("timestamp", "")
                
                aqi_res = data.get("aqi_result", {})
                aqi = aqi_res.get("aqi", 0)
                aqi_cat = aqi_res.get("category", "Unknown")
                
                sensors = data.get("raw_payload", {})
                env = sensors.get("environment", {})
                temp = env.get("temperature_C", 0.0)
                hum = env.get("humidity_pct", 0.0)
                
                pm = sensors.get("particulate_matter", {})
                pm1 = pm.get("PM1_0", 0.0)
                pm25 = pm.get("PM2_5", 0.0)
                pm10 = pm.get("PM10", 0.0)
                
                gas = sensors.get("gas_sensors", {})
                mq2 = gas.get("MQ2", {}).get("voltage_V", 0.0)
                mq9 = gas.get("MQ9", {}).get("voltage_V", 0.0)
                mq135 = gas.get("MQ135", {}).get("voltage_V", 0.0)
                
                inf = data.get("inference", {})
                gas_class = inf.get("gas_class", "None")
                safety = inf.get("safety_status", "safe")
                
                src = data.get("source", {})
                top_source = src.get("top_source", "UNKNOWN")
                
                advisory = data.get("advisory", {})
                adv_level = advisory.get("level", "INFO")
                adv_msg = advisory.get("message", "")
                adv_actions = advisory.get("recommended_actions", [])
                
                fc = data.get("forecast", {})
                forecast_msg = "Stable"
                if fc and fc.get("status") == "ok":
                    ch_fc = fc.get("channels", [])
                    if ch_fc:
                        forecast_msg = f"{ch_fc[0].get('trend', 'STABLE')} (reliability: {fc.get('reliability', 'N/A')})"
                
                # --- Colors ---
                if aqi <= 50: aqi_color = 1
                elif aqi <= 100: aqi_color = 2
                elif aqi <= 150: aqi_color = 3
                else: aqi_color = 5
                
                if safety == "unsafe": safety_color = 3
                else: safety_color = 1
                
                if adv_level in ("DANGER", "CRITICAL"): adv_color = 3
                elif adv_level == "WARNING": adv_color = 2
                else: adv_color = 1

                # --- Draw Layout ---
                # Left Column: AQI & Environment
                stdscr.addstr(2, 2, "┌─ Air Quality Index ───────────┐", curses.A_BOLD)
                stdscr.addstr(3, 2, f"│ AQI:      ")
                stdscr.addstr(3, 14, f"{aqi:<19}", curses.color_pair(aqi_color) | curses.A_BOLD)
                stdscr.addstr(3, 33, "│")
                stdscr.addstr(4, 2, f"│ Category: {aqi_cat:<19} │")
                stdscr.addstr(5, 2, f"│ Status:   {adv_level:<19} │", curses.color_pair(adv_color))
                stdscr.addstr(6, 2, "└───────────────────────────────┘", curses.A_BOLD)
                
                stdscr.addstr(8, 2, "┌─ Particulate Matter (µg/m³) ──┐", curses.A_BOLD)
                stdscr.addstr(9, 2, f"│ PM1.0: {pm1:>6.1f}                 │")
                stdscr.addstr(10, 2, f"│ PM2.5: {pm25:>6.1f}                 │")
                stdscr.addstr(11, 2, f"│ PM10:  {pm10:>6.1f}                 │")
                stdscr.addstr(12, 2, "└───────────────────────────────┘", curses.A_BOLD)

                stdscr.addstr(14, 2, "┌─ Environment ─────────────────┐", curses.A_BOLD)
                stdscr.addstr(15, 2, f"│ Temp:  {temp:>5.1f} °C               │")
                stdscr.addstr(16, 2, f"│ Hum:   {hum:>5.1f} %                │")
                stdscr.addstr(17, 2, "└───────────────────────────────┘", curses.A_BOLD)

                # Right Column: Gases & Intelligence
                col2 = 36
                stdscr.addstr(2, col2, "┌─ Gas Sensors (Voltage) ───────┐", curses.A_BOLD)
                stdscr.addstr(3, col2, f"│ MQ2:   {mq2:>4.2f} V  (Smoke/Gas)   │")
                stdscr.addstr(4, col2, f"│ MQ9:   {mq9:>4.2f} V  (CO/Gas)      │")
                stdscr.addstr(5, col2, f"│ MQ135: {mq135:>4.2f} V  (Air Quality) │")
                stdscr.addstr(6, col2, "└───────────────────────────────┘", curses.A_BOLD)

                stdscr.addstr(8, col2, "┌─ Edge Intelligence ───────────┐", curses.A_BOLD)
                stdscr.addstr(9, col2, f"│ Primary Gas: {gas_class:<16} │")
                stdscr.addstr(10, col2, f"│ Safety:      ")
                stdscr.addstr(10, col2+15, f"{safety:<16}", curses.color_pair(safety_color) | curses.A_BOLD)
                stdscr.addstr(10, col2+31, "│")
                stdscr.addstr(11, col2, f"│ Source:      {top_source:<16} │")
                stdscr.addstr(12, col2, f"│ Forecast:    {forecast_msg:<16} │")
                stdscr.addstr(13, col2, "└───────────────────────────────┘", curses.A_BOLD)

                # Bottom row: Advisory
                stdscr.addstr(19, 2, "┌─ Active Advisory ───────────────────────────────────────────┐", curses.A_BOLD)
                stdscr.addstr(20, 2, f"│ {adv_msg[:59]:<59} │", curses.color_pair(adv_color))
                stdscr.addstr(21, 2, "│ Actions:                                                    │")
                row = 22
                for i, act in enumerate(adv_actions[:3]):
                    stdscr.addstr(row+i, 2, f"│ - {act[:57]:<57} │")
                
                # Fill remaining lines if fewer than 3 actions
                for j in range(len(adv_actions), 3):
                    stdscr.addstr(row+j, 2, "│                                                             │")
                stdscr.addstr(25, 2, "└─────────────────────────────────────────────────────────────┘", curses.A_BOLD)

                # Footer
                stdscr.addstr(max_y-1, 0, f" Node: {node} | Time: {ts} | Press 'q' to quit ", curses.A_REVERSE)

            except Exception as e:
                stdscr.addstr(2, 2, f"Parsing error: {e}")
        
        stdscr.refresh()
        
        # Handle input with sleep loop
        t_end = time.time() + 2.0
        while time.time() < t_end:
            c = stdscr.getch()
            if c == ord('q') or c == ord('Q'):
                return
            time.sleep(0.1)

def main():
    parser = argparse.ArgumentParser(description="NavosEdge UNO Q TUI")
    parser.add_argument("--node", help="Node ID to monitor", default=None)
    args = parser.parse_args()
    
    try:
        curses.wrapper(draw_tui, args.node)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
