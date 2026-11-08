#!/usr/bin/env python3
"""
csi_serial_capture.py — Captures ESP32 CSI serial output to clean CSV files.

Usage:
    python csi_serial_capture.py --port COM3          # Windows
    python csi_serial_capture.py --port /dev/ttyUSB0  # Linux

This script:
  1. Connects to the ESP32 serial port
  2. Forwards your typed commands to the ESP32
  3. Listens for ---CSV_START--- / ---CSV_END--- markers
  4. Saves each capture session to a properly named CSV file
  5. Strips comment/progress lines so the CSV is clean

Output files are saved to ./captures/ with names like:
    capture_20260321_143022.csv

Requirements:
    pip install pyserial
"""

import serial
import sys
import os
import re
import time
import argparse
import threading
import io
from datetime import datetime

# Force UTF-8 stdout on Windows to handle box-drawing and Unicode characters
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def make_filename(out_dir="captures"):
    """Generate a simple timestamped filename."""
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"capture_{ts}.csv"
    return os.path.join(out_dir, name)


def input_thread(ser):
    """Read user keyboard input and send to ESP32 (non-blocking on Windows)."""
    if sys.platform == "win32":
        import msvcrt
        buf = ""
        while True:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ('\r', '\n'):
                    print(flush=True)  # newline after typed text
                    ser.write((buf + "\n").encode())
                    buf = ""
                elif ch == '\x08':  # backspace
                    if buf:
                        buf = buf[:-1]
                        sys.stdout.write('\b \b')
                        sys.stdout.flush()
                else:
                    buf += ch
                    sys.stdout.write(ch)
                    sys.stdout.flush()
            else:
                time.sleep(0.02)
    else:
        # Unix: use standard input
        try:
            while True:
                cmd = input()
                ser.write((cmd + "\n").encode())
        except (EOFError, KeyboardInterrupt):
            pass


def main():
    parser = argparse.ArgumentParser(description="ESP32 CSI Serial Capture Tool")
    parser.add_argument("--port", required=True, help="Serial port (e.g. COM3, /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument("--outdir", default="captures", help="Output directory (default: captures)")
    args = parser.parse_args()

    print(f"[CAPTURE] Connecting to {args.port} at {args.baud} baud...", flush=True)

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"[ERROR] Cannot open {args.port}: {e}", flush=True)
        sys.exit(1)

    print(f"[CAPTURE] Connected. Type 'start' to begin capture.", flush=True)
    print(f"[CAPTURE] CSV files will be saved to ./{args.outdir}/", flush=True)
    print("-" * 60, flush=True)

    # Start keyboard input thread
    t = threading.Thread(target=input_thread, args=(ser,), daemon=True)
    t.start()

    # State
    capturing = False
    csv_file = None
    row_count = 0

    try:
        while True:
            line = ser.readline()
            if not line:
                continue

            try:
                text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            except Exception:
                continue

            # CSV capture start
            if text == "---CSV_START---":
                capturing = True
                row_count = 0
                fname = make_filename(args.outdir)
                csv_file = open(fname, "w", newline="")
                print(f"\n[CAPTURE] >>> Recording to: {fname}", flush=True)
                continue

            # CSV capture end
            if text == "---CSV_END---":
                capturing = False
                if csv_file:
                    csv_file.close()
                    print(f"\n[CAPTURE] >>> DONE! Saved {row_count} rows to file", flush=True)
                    csv_file = None
                continue

            # During capture
            if capturing:
                # Progress lines (start with #) — print live
                if text.startswith("#"):
                    print(f"\r{text}    ", end="", flush=True)
                    continue

                # Write CSV header or data row
                if text.startswith("ts_ms,") or (len(text) > 0 and (text[0].isdigit() or text[0] == '-')):
                    if csv_file:
                        csv_file.write(text + "\n")
                        if not text.startswith("ts_ms"):
                            row_count += 1
                            if row_count % 100 == 0:
                                csv_file.flush()
                    continue

            # Print everything to terminal (non-CSV lines, status, etc.)
            print(text, flush=True)

    except KeyboardInterrupt:
        print("\n[CAPTURE] Interrupted. Cleaning up...", flush=True)
        if csv_file:
            csv_file.close()
            print(f"[CAPTURE] Partial file saved ({row_count} rows)", flush=True)
        ser.close()
        print("[CAPTURE] Done.", flush=True)


if __name__ == "__main__":
    main()
