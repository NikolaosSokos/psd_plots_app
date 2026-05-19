from flask import Flask, render_template, send_from_directory, url_for, request, redirect
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
import subprocess
import time
from pathlib import Path
from functools import lru_cache
import config

app = Flask(__name__)
auth = HTTPBasicAuth()

PLOTS_DIR = config.PLOTS_DIR

SITE_JSON = Path("stations.json")
SITE_NAMES = {}
if SITE_JSON.exists():
    with SITE_JSON.open() as f:
        SITE_NAMES = json.load(f)

META_JSON = Path("stations_meta.json")
STATIONS_META = {}
if META_JSON.exists():
    with META_JSON.open() as f:
        STATIONS_META = json.load(f)

PLOT_ORDER = ["week", "two_weeks", "month", "year", "full"]

# --- Dashboard Auth -------------------------------------------
DASHBOARD_USERS = {
    "admin": generate_password_hash("noa2026!")
}

@auth.verify_password
def verify_password(username, password):
    if username in DASHBOARD_USERS and \
       check_password_hash(DASHBOARD_USERS[username], password):
        return username

# --- Helpers --------------------------------------------------
def get_site_name(network, station):
    return SITE_NAMES.get(network, {}).get(station, station)


@lru_cache(maxsize=1024)
def find_thumbnail(path):
    priority = {1: None, 2: None, 3: None, 4: None, 99: None}
    other_imgs = ("week.jpg", "two_weeks.jpg", "month.jpg", "year.jpg",
                  "week.png", "two_weeks.png", "month.png", "year.png")
    for root, _, files in os.walk(path):
        parts = root.split(os.sep)
        channel = parts[-1] if len(parts) > 1 else ""
        for file in files:
            fpath = os.path.join(root, file)
            rel = os.path.relpath(fpath, PLOTS_DIR)
            if channel.endswith("HHZ") and file == "full.jpg":
                return url_for("serve_plot", filename=rel)
            elif channel.endswith("Z") and file == "full.jpg":
                priority[2] = priority[2] or rel
            elif channel.endswith("HHZ") and file in other_imgs:
                priority[3] = priority[3] or rel
            elif channel.endswith("Z") and file in other_imgs:
                priority[4] = priority[4] or rel
            elif file.lower().endswith((".jpg", ".png")):
                priority[99] = priority[99] or rel
    for key in (1, 2, 3, 4, 99):
        if priority[key] is not None:
            return url_for("serve_plot", filename=priority[key])
    return None


CUSTOM_ORDER = ["HL", "HT", "HP", "HA", "HC", "CQ", "ME", "1Y", "HI", "EG", "5B", "KF"]

def sort_networks(networks):
    return sorted(
        networks,
        key=lambda net: (
            CUSTOM_ORDER.index(net) if net in CUSTOM_ORDER else 9999,
            net
        )
    )


# --- Routes ---------------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("map_page"))


@app.route("/networks")
def networks_page():
    networks = [
        d for d in os.listdir(PLOTS_DIR)
        if os.path.isdir(os.path.join(PLOTS_DIR, d))
    ]
    networks = sort_networks(networks)
    network_cards = []
    for net in networks:
        net_path = os.path.join(PLOTS_DIR, net)
        thumb = find_thumbnail(net_path)
        if thumb:
            network_cards.append((net, thumb))
    return render_template("index.html", networks=network_cards)


@app.route("/search")
def search():
    query = request.args.get("q", "").strip().upper()
    if not query:
        return redirect(url_for("index"))
    parts = query.split(".")
    if len(parts) == 3:
        net, sta, chan = parts
        return redirect(url_for("channel_page", network=net, station=sta, channel=chan))
    results = []
    for key, meta in STATIONS_META.items():
        net = meta.get("network", "").upper()
        sta = meta.get("station", "").upper()
        site = meta.get("site_name", "").upper()
        full_key = key.upper()
        if (query in net or query in sta or query in site or query in full_key):
            net_code = meta.get("network")
            sta_code = meta.get("station")
            thumb = find_thumbnail(os.path.join(PLOTS_DIR, net_code, sta_code))
            results.append({
                "network": net_code,
                "station": sta_code,
                "site_name": meta.get("site_name", f"{net_code}.{sta_code}"),
                "thumb": thumb
            })
    results.sort(key=lambda x: (x["network"], x["station"]))
    return render_template("search_results.html", query=query, results=results)


@app.route("/psds/<network>")
def network_page(network):
    net_path = os.path.join(PLOTS_DIR, network)
    if not os.path.exists(net_path):
        return f"Network {network} not found", 404
    stations = sorted(
        [d for d in os.listdir(net_path) if os.path.isdir(os.path.join(net_path, d))]
    )
    groups = {"HH": [], "EH": [], "HN": []}
    for sta in stations:
        sta_path = os.path.join(net_path, sta)
        available_channels = [
            c for c in os.listdir(sta_path)
            if os.path.isdir(os.path.join(sta_path, c))
        ]
        for prefix in ("HH", "EH", "HN"):
            if any(ch.startswith(prefix) for ch in available_channels):
                thumb = find_thumbnail(os.path.join(net_path, sta))
                site_name = get_site_name(network, sta)
                groups[prefix].append((sta, thumb, site_name))
                break
    return render_template("network.html", network=network, groups=groups)


@app.route("/psds/<network>/<station>")
def station_page(network, station):
    sta_path = os.path.join(PLOTS_DIR, network, station)
    if not os.path.exists(sta_path):
        return f"Station {station} not found in {network}", 404
    channels = sorted(
        [d for d in os.listdir(sta_path) if os.path.isdir(os.path.join(sta_path, d))]
    )
    station_data = {}
    for chan in channels:
        chan_path = os.path.join(sta_path, chan)
        plots = {}
        for file in os.listdir(chan_path):
            if file.lower().endswith((".jpg", ".png")):
                plot_name = os.path.splitext(file)[0]
                plots[plot_name] = url_for(
                    "serve_plot",
                    filename=f"{network}/{station}/{chan}/{file}",
                )
        if plots:
            station_data[chan] = plots
    groups = {"HH": [], "EH": [], "HN": [], "OTHER": []}
    for chan in station_data.keys():
        if chan.startswith("HH"):
            groups["HH"].append(chan)
        elif chan.startswith("EH"):
            groups["EH"].append(chan)
        elif chan.startswith("HN"):
            groups["HN"].append(chan)
        else:
            groups["OTHER"].append(chan)
    site_name = get_site_name(network, station)
    return render_template(
        "station.html",
        network=network,
        station=station,
        site_name=site_name,
        groups=groups,
        station_data=station_data,
        no_plots=(len(station_data) == 0),
    )


@app.route("/psds/<network>/<station>/<channel>")
def channel_page(network, station, channel):
    chan_path = os.path.join(PLOTS_DIR, network, station, channel)
    if not os.path.exists(chan_path):
        return f"Channel {channel} not found in {network}.{station}", 404
    plots = {}
    for file in os.listdir(chan_path):
        if file.lower().endswith((".jpg", ".png")):
            plot_name = os.path.splitext(file)[0]
            plots[plot_name] = url_for(
                "serve_plot", filename=f"{network}/{station}/{channel}/{file}"
            )
    ordered = {k: plots[k] for k in PLOT_ORDER if k in plots}
    for k in sorted(plots):
        if k not in ordered:
            ordered[k] = plots[k]
    site_name = get_site_name(network, station)
    meta_key = f"{network}.{station}"
    meta = STATIONS_META.get(meta_key, {})
    return render_template(
        "channel.html",
        network=network,
        station=station,
        channel=channel,
        plots=ordered,
        site_name=site_name,
        no_plots=(len(ordered) == 0),
        meta=meta,
    )


@app.route("/plots/<path:filename>")
def serve_plot(filename):
    return send_from_directory(PLOTS_DIR, filename)


@app.route("/map")
def map_page():
    stations = []
    for key, meta in STATIONS_META.items():
        stations.append({
            "network":   meta.get("network"),
            "station":   meta.get("station"),
            "latitude":  meta.get("latitude"),
            "longitude": meta.get("longitude"),
            "site_name": meta.get("site_name", f"{meta.get('network')}.{meta.get('station')}"),
            "elevation": meta.get("elevation"),
            "channels":  meta.get("channels", [])
        })
    return render_template("map.html", stations=stations)


@app.route("/dashboard")
@auth.login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/dashboard/refresh")
@auth.login_required
def dashboard_refresh():
    subprocess.Popen(
        ["/home/qc/.local/bin/uv", "run",
         "/darrays/qc-working/scripts/generate_dashboard.py"],
        cwd="/darrays/qc-working/scripts"
    )
    time.sleep(4)
    return redirect(url_for("dashboard"))


# --- Main -----------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, host=config.HOST, port=config.PORT)
