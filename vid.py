# wifi_metrics_streamlit.py
import streamlit as st
import subprocess
import re
import pandas as pd
import time
from io import BytesIO
import tempfile
import os
import xml.sax.saxutils as sax

st.set_page_config(page_title="Wi-Fi Metrics Scanner", layout="wide")

st.title("Wi‑Fi Metrics Scanner (Windows)")

st.markdown("""
This app scans visible Wi‑Fi networks, extracts SSID/BSSID/Signal% and computes RSSI & estimated SNR.
For the currently connected network (or networks you allow the app to connect to with provided passwords),
it can also run `ping` and `iperf3` tests to collect latency, jitter, packet loss and throughput.
""")

# -----------------------
# Helper functions
# -----------------------
def run_cmd(cmd, timeout=20):
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False)
        return res.stdout, res.stderr, res.returncode
    except Exception as e:
        return "", str(e), -1

def parse_netsh_networks(output):
    networks = []
    current = {}
    bssid = None
    for line in output.splitlines():
        line = line.strip()
        m = re.match(r"^SSID\s+\d+\s+:\s*(.*)$", line)
        if m:
            if current:
                networks.append(current)
            current = {"SSID": m.group(1), "BSSIDs": []}
            bssid = None
            continue
        m2 = re.match(r"^BSSID\s+\d+\s+:\s*(.*)$", line)
        if m2:
            bssid = m2.group(1)
            current["BSSIDs"].append({"BSSID": bssid})
            continue
        m3 = re.match(r"^Signal\s*:\s*(\d+)%", line)
        if m3 and bssid is not None:
            sig = int(m3.group(1))
            rssi = (sig / 2.0) - 100.0
            snr = rssi - (-95.0)
            current["BSSIDs"][-1].update({
                "Signal%": sig,
                "RSSI(dBm)": round(rssi,1),
                "Estimated_SNR(dB)": round(snr,1)
            })
            continue
    if current:
        networks.append(current)
    return networks

def get_visible_networks():
    out, err, code = run_cmd(["netsh", "wlan", "show", "networks", "mode=bssid"])
    if code != 0:
        st.error(f"Failed to run netsh wlan show networks: {err}")
        return []
    return parse_netsh_networks(out)

def get_connected_interface_info():
    out, err, code = run_cmd(["netsh", "wlan", "show", "interfaces"])
    if code != 0:
        return None
    ssid = None
    signal = None
    bssid = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("SSID") and "BSSID" not in line and ":" in line:
            try:
                k, v = line.split(":", 1)
                if k.strip() == "SSID":
                    ssid = v.strip()
            except:
                pass
        if line.startswith("Signal") and ":" in line:
            try:
                signal = int(line.split(":",1)[1].strip().replace("%",""))
            except:
                pass
        if line.startswith("BSSID") and ":" in line:
            try:
                bssid = line.split(":",1)[1].strip()
            except:
                pass
    if ssid:
        rssi = (signal/2.0) - 100.0 if signal is not None else None
        snr = rssi - (-95.0) if rssi is not None else None
        return {"SSID": ssid, "Signal%": signal, "RSSI(dBm)": round(rssi,1) if rssi is not None else None, "Estimated_SNR(dB)": round(snr,1) if snr is not None else None, "BSSID": bssid}
    return None

def run_ping_metrics(server, count=5):
    try:
        out, err, code = run_cmd(["ping", server, "-n", str(count)], timeout=20)
        if not out:
            return None

        # Packet loss
        loss_pct = None
        m = re.search(r"Lost\s*=\s*\d+\s*\((\d+)%\s*loss\)", out, re.IGNORECASE)
        if m:
            loss_pct = int(m.group(1))
        else:
            # fallback for different languages
            m2 = re.search(r"(\d+)%\s*loss", out, re.IGNORECASE)
            if m2:
                loss_pct = int(m2.group(1))

        # RTT metrics
        rtts = re.findall(r"time[=<]\s*(\d+)ms", out)
        if rtts:
            rtts = list(map(int, rtts))
            mini = min(rtts)
            maxi = max(rtts)
            avg = round(sum(rtts)/len(rtts))
            jitter = maxi-mini
            return {"packet_loss_%": loss_pct, "rtt_min_ms": mini, "rtt_max_ms": maxi, "rtt_avg_ms": avg, "jitter_ms": jitter}
        else:
            # fallback for Windows summary line
            m2 = re.search(r"Minimum\s*=\s*(\d+)ms,\s*Maximum\s*=\s*(\d+)ms,\s*Average\s*=\s*(\d+)ms", out)
            if m2:
                mini = int(m2.group(1))
                maxi = int(m2.group(2))
                avg = int(m2.group(3))
                jitter = maxi - mini
                return {"packet_loss_%": loss_pct, "rtt_min_ms": mini, "rtt_max_ms": maxi, "rtt_avg_ms": avg, "jitter_ms": jitter}

        return {"packet_loss_%": loss_pct, "rtt_min_ms": None, "rtt_max_ms": None, "rtt_avg_ms": None, "jitter_ms": None}
    except Exception as e:
        return {"packet_loss_%": None, "rtt_min_ms": None, "rtt_max_ms": None, "rtt_avg_ms": None, "jitter_ms": None}

def run_iperf3(iperf_cmd, server, time_s=5):
    try:
        cmd = [iperf_cmd, "-c", server, "-t", str(time_s), "-f", "m"]
        out, err, code = run_cmd(cmd, timeout=time_s+10)
        if not out:
            return {"throughput_Mbps": None}

        matches = re.findall(r"([\d\.]+)\s+Mbits/sec", out)
        if matches:
            val = float(matches[-1])
            return {"throughput_Mbps": round(val,2)}
        else:
            # fallback: check stderr if iperf printed there
            matches2 = re.findall(r"([\d\.]+)\s+Mbits/sec", err)
            if matches2:
                val = float(matches2[-1])
                return {"throughput_Mbps": round(val,2)}
        return {"throughput_Mbps": None}
    except Exception:
        return {"throughput_Mbps": None}

def create_wlan_profile_and_add(ssid, password):
    safe_ssid = sax.escape(ssid)
    safe_key = sax.escape(password)
    profile_xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{safe_ssid}</name>
    <SSIDConfig>
        <SSID>
            <name>{safe_ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{safe_key}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>"""
    fd, path = tempfile.mkstemp(suffix=".xml")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(profile_xml)
    out, err, code = run_cmd(["netsh", "wlan", "add", "profile", f"filename={path}", "user=all"])
    if code != 0:
        os.remove(path)
        return None
    return path

def connect_to_network(ssid):
    out, err, code = run_cmd(["netsh", "wlan", "connect", f"name={ssid}", f"ssid={ssid}"])
    time.sleep(4)
    return code == 0

# -----------------------
# Streamlit UI
# -----------------------

col1, col2 = st.columns([2,1])

with col1:
    st.subheader("Scan & Test Options")
    server_ip = st.text_input("iperf3 server IP (optional — for throughput testing)", placeholder="e.g. 192.168.1.100")
    iperf_exe = st.text_input("iperf3 executable name or full path (optional, default 'iperf3')", value="iperf3")
    attempt_connect = st.checkbox("Attempt to auto-connect to networks listed in uploaded CSV (SSID,password) to run tests", value=False)
    ssid_pw_file = None
    if attempt_connect:
        ssid_pw_file = st.file_uploader("Upload CSV with columns: SSID,password (no header required or header accepted)", type=["csv"])
    run_button = st.button("Run Scan & Tests")

with col2:
    st.subheader("Notes / Limitations")
    st.info("""
- The app uses Windows `netsh` and `ping`. It must run on the Windows machine whose Wi‑Fi you want to scan.
- Throughput requires an iperf3 server reachable from that machine.
- Connecting programmatically will add temporary Wi‑Fi profiles; use carefully.
- If you don't provide passwords, the app will only show passive metrics (Signal%, RSSI, SNR).
    """)
    st.write("Last run status:")
    status_area = st.empty()

if run_button:
    status_area.info("Scanning visible Wi‑Fi networks...")
    networks = get_visible_networks()
    status_area.info(f"Found {sum(len(n['BSSIDs']) for n in networks)} BSSID entries across {len(networks)} SSIDs.")

    connected_info = get_connected_interface_info()
    if connected_info:
        status_area.success(f"Currently connected to: {connected_info['SSID']}")
    else:
        status_area.warning("Not currently connected to any Wi‑Fi (or unable to parse connection).")

    creds = {}
    if ssid_pw_file and attempt_connect:
        try:
            df_creds = pd.read_csv(ssid_pw_file, header=0) if st.checkbox("CSV has header", value=False) else pd.read_csv(ssid_pw_file, header=None, names=["SSID","password"])
            for _, r in df_creds.iterrows():
                creds[str(r["SSID"])] = str(r["password"])
            status_area.info(f"Loaded {len(creds)} credentials from CSV.")
        except Exception as e:
            status_area.error(f"Failed to parse credentials CSV: {e}")

    rows = []
    for net in networks:
        ssid = net.get("SSID")
        for b in net.get("BSSIDs", []):
            row = {
                "SSID": ssid,
                "BSSID": b.get("BSSID"),
                "Signal%": b.get("Signal%"),
                "RSSI(dBm)": b.get("RSSI(dBm)"),
                "Estimated_SNR(dB)": b.get("Estimated_SNR(dB)"),
                "Connected": False,
                "Ping_avg_ms": None,
                "Ping_min_ms": None,
                "Ping_max_ms": None,
                "Jitter_ms": None,
                "Packet_loss_%": None,
                "Throughput_Mbps": None,
                "Notes": ""
            }
            if connected_info and connected_info.get("SSID") == ssid:
                row["Connected"] = True
                if connected_info.get("Signal%") is not None:
                    row["Signal%"] = connected_info.get("Signal%")
                    row["RSSI(dBm)"] = connected_info.get("RSSI(dBm)")
                    row["Estimated_SNR(dB)"] = connected_info.get("Estimated_SNR(dB)")

                if server_ip:
                    status_area.info(f"Pinging {server_ip} via connected network {ssid} ...")
                    ping_res = run_ping_metrics(server_ip, count=5)
                    if ping_res:
                        row["Ping_avg_ms"] = ping_res.get("rtt_avg_ms")
                        row["Ping_min_ms"] = ping_res.get("rtt_min_ms")
                        row["Ping_max_ms"] = ping_res.get("rtt_max_ms")
                        row["Jitter_ms"] = ping_res.get("jitter_ms")
                        row["Packet_loss_%"] = ping_res.get("packet_loss_%")

                if server_ip and iperf_exe:
                    status_area.info(f"Running iperf3 to {server_ip} for network {ssid} ... (this may take a few seconds)")
                    thr = run_iperf3(iperf_exe, server_ip, time_s=5)
                    if thr:
                        row["Throughput_Mbps"] = thr.get("throughput_Mbps")

            rows.append(row)

    if attempt_connect and creds:
        status_area.info("Attempting to connect to networks from provided credentials...")
        for ssid, pwd in creds.items():
            status_area.info(f"Preparing profile for {ssid} ...")
            xml_path = create_wlan_profile_and_add(ssid, pwd)
            if not xml_path:
                status_area.error(f"Failed to add profile for {ssid}. Skipping.")
                continue
            ok = connect_to_network(ssid)
            if not ok:
                status_area.warning(f"Could not connect to {ssid} after adding profile. You may need to connect manually.")
                try: os.remove(xml_path)
                except: pass
                continue
            ci = get_connected_interface_info()
            ping_res = None
            thr = None
            if server_ip:
                status_area.info(f"Running ping to {server_ip} on {ssid} ...")
                ping_res = run_ping_metrics(server_ip, count=5)
                status_area.info(f"Running iperf3 to {server_ip} on {ssid} ...")
                thr = run_iperf3(iperf_exe, server_ip, time_s=5)
            rows.append({
                "SSID": ssid,
                "BSSID": ci.get("BSSID") if ci else None,
                "Signal%": ci.get("Signal%") if ci else None,
                "RSSI(dBm)": ci.get("RSSI(dBm)") if ci else None,
                "Estimated_SNR(dB)": ci.get("Estimated_SNR(dB)") if ci else None,
                "Connected": True,
                "Ping_avg_ms": ping_res.get("rtt_avg_ms") if ping_res else None,
                "Ping_min_ms": ping_res.get("rtt_min_ms") if ping_res else None,
                "Ping_max_ms": ping_res.get("rtt_max_ms") if ping_res else None,
                "Jitter_ms": ping_res.get("jitter_ms") if ping_res else None,
                "Packet_loss_%": ping_res.get("packet_loss_%") if ping_res else None,
                "Throughput_Mbps": thr.get("throughput_Mbps") if thr else None,
                "Notes": "Auto-connected via provided credential"
            })
            try: os.remove(xml_path)
            except: pass

    if rows:
        df = pd.DataFrame(rows)
        st.subheader("Results table")
        st.dataframe(df, use_container_width=True)
        towrite = BytesIO()
        with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="wifi_metrics")
        towrite.seek(0)
        st.download_button(label="Download Excel (.xlsx)", data=towrite.getvalue(), file_name="wifi_metrics.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        status_area.success("Scan & tests completed.")
    else:
        st.warning("No networks found or no rows generated.")
