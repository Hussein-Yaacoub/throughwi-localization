# ESP32 CSI capture

The firmware targets an ESP32 DevKit (ESP32-WROOM-32) with PlatformIO and Arduino. It associates with a 2.4 GHz access point, sends ICMP probes to the gateway at 10 per second during a capture, and streams CSI reports over USB serial at 115200 baud. Default capture length is 1,500 rows.

1. Copy `firmware/include/wifi_config.example.h` to `firmware/include/wifi_config.h` and set the network name and password there. Git ignores the local header.
2. Connect the board over USB and run `pio run -d firmware -t upload` from the repository root.
3. Install the logger dependency with `python -m pip install -r capture/requirements.txt`.
4. Run `python capture/csi_serial_capture.py --port /dev/ttyUSB0 --outdir captures` (use your board's serial port, such as `COM3` on Windows).
5. Set `scenario S01`, `position P01`, and optionally `desc <description>` or `rows 1500`. Type `start` to begin and `stop` to stop early. The logger writes a separate CSV for each session. Record the scenario, coordinates, and geometry for each filename.

Keep raw logs local until they have been reviewed. New logs contain access-point identifiers and need pseudonymization before they are added to a shared dataset.
