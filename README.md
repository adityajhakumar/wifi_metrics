
# Wi‑Fi Metrics Scanner (Windows) – Detailed Documentation

A **Streamlit app** to scan Wi‑Fi networks on Windows, collect metrics such as signal strength, RSSI, estimated SNR, ping statistics, and iperf3 throughput. The app can also **auto-connect** to Wi-Fi networks using provided credentials for testing.

---

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Requirements](#requirements)
4. [How the Code Works](#how-the-code-works)

   * [Scanning Wi-Fi Networks](#scanning-wi-fi-networks)
   * [Getting Connected Network Info](#getting-connected-network-info)
   * [Ping Metrics](#ping-metrics)
   * [iperf3 Throughput Metrics](#iperf3-throughput-metrics)
   * [Auto-Connect to Networks](#auto-connect-to-networks)
   * [Data Aggregation and Export](#data-aggregation-and-export)
5. [Running the App](#running-the-app)
6. [CSV File Format](#csv-file-format)
7. [Notes and Limitations](#notes-and-limitations)
8. [Troubleshooting](#troubleshooting)

---

## Overview

This app runs on **Windows** and uses **built-in commands (`netsh`, `ping`)** plus optional **iperf3** to measure Wi-Fi network metrics. It provides:

* Passive scanning for all visible Wi-Fi networks.
* Metrics for the currently connected network.
* Optional auto-connection to networks from a CSV file.
* Export results in Excel format.

The app is fully interactive via Streamlit and requires no GUI beyond the browser interface.
<img width="1886" height="1078" alt="image" src="https://github.com/user-attachments/assets/28070fa9-7241-4238-a1ec-3aaaccb5ab95" />


---

## Features

* Scan visible Wi-Fi networks: SSID, BSSID, Signal%, RSSI, Estimated SNR.
* Detect currently connected Wi-Fi and collect detailed metrics.
* Run **ping** tests to measure latency, jitter, and packet loss.
* Run **iperf3** tests to measure throughput.
* Auto-connect to networks using a CSV of credentials to collect metrics.
* Export all collected data to **Excel** for offline analysis.

---

## Requirements

### Python Packages

```bash
pip install --upgrade pip streamlit pandas openpyxl
```

### System Requirements

* Windows 10 or 11.
* `iperf3` installed and reachable via PATH (for throughput testing).
* Admin privileges not strictly required, but some networks may require elevated permissions to connect programmatically.

---

## How the Code Works

The code is structured into **helper functions** and **Streamlit UI components**. Here’s a detailed walkthrough:

---

### 1️⃣ Scanning Wi-Fi Networks

* Uses the command:

```bash
netsh wlan show networks mode=bssid
```

* Parses output with regex to extract:

  * SSID (network name)
  * BSSID (access point MAC)
  * Signal %
  * RSSI (calculated as `(Signal% / 2) - 100`)
  * Estimated SNR (calculated as `RSSI - (-95)` as reference noise floor)

* Multiple BSSIDs under the same SSID are handled correctly.

**Output Example:**

| SSID     | BSSID          | Signal% | RSSI(dBm) | Estimated_SNR(dB) |
| -------- | -------------- | ------- | --------- | ----------------- |
| HomeWiFi | 12:34:56:78:9A | 80      | -60       | 35                |

---

### 2️⃣ Getting Connected Network Info

* Uses:

```bash
netsh wlan show interfaces
```

* Extracts:

  * Connected SSID
  * Signal %
  * BSSID
  * RSSI and SNR (same calculation as above)

* This ensures **metrics for the currently connected network are accurate** even if the signal has changed since scanning.

---

### 3️⃣ Ping Metrics

* The app can run ping tests to a user-specified server.

* Metrics collected:

  * Packet loss %
  * RTT min / max / avg
  * Jitter (max - min)

* Handles **different Windows languages** and formats by using regex fallback patterns.

**Example ping output processed:**

| Packet_loss_% | RTT_min_ms | RTT_max_ms | RTT_avg_ms | Jitter_ms |
| ------------- | ---------- | ---------- | ---------- | --------- |
| 0             | 5          | 7          | 6          | 2         |

---

### 4️⃣ iperf3 Throughput Metrics

* Runs iperf3 to a server specified by the user.

```bash
iperf3 -c <server_ip> -t 5 -f m
```

* Extracts throughput in Mbps using regex.
* Handles Kbits/sec and Mbits/sec outputs.
* Fallback to stderr parsing if needed.

**Example Output:**

| Throughput_Mbps |
| --------------- |
| 85.34           |

* Important: throughput is only measured for networks the machine is **connected to**.

---

### 5️⃣ Auto-Connect to Networks

* Users can upload a CSV with SSID and password.
* The app creates a **temporary WLAN profile** in XML format and adds it via:

```bash
netsh wlan add profile filename=<tempfile.xml> user=all
```

* Then it attempts to connect programmatically:

```bash
netsh wlan connect name=<SSID> ssid=<SSID>
```

* After connection, ping and iperf3 metrics are collected.
* Temporary XML profiles are removed after the test.

---

### 6️⃣ Data Aggregation and Export

* Each network (SSID/BSSID) gets a **row** with metrics:

| SSID | BSSID | Signal% | RSSI | SNR | Connected | Ping_avg | Ping_min | Ping_max | Jitter | Packet_loss | Throughput | Notes |

* Both passive scan metrics and active connection metrics (ping/iperf3) are included.
* Results are displayed in a Streamlit **DataFrame** and can be **downloaded as Excel** using `openpyxl`.

---

## Running the App

1. Install dependencies:

```bash
pip install --upgrade pip streamlit pandas openpyxl
```

2. Run the app:

```bash
streamlit run wifi_metrics_streamlit.py
```

3. Fill in:

* Optional **iperf3 server IP**
* Optional **iperf3 executable path**
* Upload **CSV file** for auto-connect if needed

4. Click **Run Scan & Tests**. Results appear in the table and can be exported as Excel.

---

## CSV File Format for Auto-Connect

* Either with or without header.
* Columns: SSID,password

Example (no header):

```
HomeWiFi,MyPassword123
GuestWiFi,guestpass
```

---

## Notes and Limitations

* Only works on **Windows**.
* Throughput requires an **iperf3 server** reachable from the machine.
* Auto-connect may add temporary Wi-Fi profiles; use carefully.
* Ping may show 0% packet loss on stable local networks.
* Throughput may show `None` if iperf3 cannot reach the server or executable path is incorrect.

---

## Troubleshooting

* **iperf3 throughput not appearing:**

  * Ensure server is reachable.
  * Provide full path to iperf3 executable.
  * Increase test duration if needed.

* **Packet loss always 0%:**

  * Normal if server is local or network is stable.
  * Test against external server like `8.8.8.8` for measurable packet loss/jitter.

* **CSV upload errors:**

  * Check CSV formatting and encoding.

---

