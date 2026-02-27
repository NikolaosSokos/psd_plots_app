from flask import Flask, render_template, send_from_directory, url_for, request,redirect
import os
import json
from pathlib import Path
from functools import lru_cache
import config

app = Flask(__name__)

# Paths
PLOTS_DIR = config.PLOTS_DIR

# Load station names (pretty names)
SITE_JSON = Path("stations.json")
SITE_NAMES = {}
if SITE_JSON.exists():
    with SITE_JSON.open() as f:
        SITE_NAMES = json.load(f)

# Load station metadata (coords + channels)
META_JSON = Path("stations_meta.json")
STATIONS_META = {}
if META_JSON.exists():
    with META_JSON.open() as f:
        STATIONS_META = json.load(f)

# Plot order
PLOT_ORDER = ["week", "two_weeks", "month", "year", "full"]


# --- Helpers ------------------------------------------------
def get_site_name(network, station):
    return SITE_NAMES.get(network, {}).get(station, station)


@lru_cache(maxsize=1024)
def find_thumbnail(path):
    """
    Find the best thumbnail for a network.

    Priority:
      1. HHZ/full.jpg
      2. */*Z/full.jpg
      3. HHZ/{week, two_weeks, month, year}.jpg
      4. */*Z/{week, two_weeks, month, year}.jpg
      5. fallback: first JPG/PNG found
    """

    # Priority buckets
    priority = {
        1: None,  # HHZ full.jpg
        2: None,  # any Z full.jpg
        3: None,  # HHZ other plots
        4: None,  # any Z other plots
        99: None, # fallback
    }

    # Valid plot names for non-full thumbnails
    other_imgs = ("week.jpg", "two_weeks.jpg", "month.jpg", "year.jpg",
                  "week.png", "two_weeks.png", "month.png", "year.png")

    for root, _, files in os.walk(path):
        # Extract channel code from folder structure
        parts = root.split(os.sep)
        channel = parts[-1] if len(parts) > 1 else ""

        for file in files:
            fpath = os.path.join(root, file)
            rel = os.path.relpath(fpath, PLOTS_DIR)

            # 1. HHZ full.jpg
            if channel.endswith("HHZ") and file == "full.jpg":
                # Best priority found, return immediately!
                return url_for("serve_plot", filename=rel)

            # 2. Any Z full.jpg
            elif channel.endswith("Z") and file == "full.jpg":
                priority[2] = priority[2] or rel

            # 3. HHZ other images
            elif channel.endswith("HHZ") and file in other_imgs:
                priority[3] = priority[3] or rel

            # 4. Any Z other images
            elif channel.endswith("Z") and file in other_imgs:
                priority[4] = priority[4] or rel

            # 5. fallback
            elif file.lower().endswith((".jpg", ".png")):
                priority[99] = priority[99] or rel

    # Return first available priority
    for key in (1, 2, 3, 4, 99):
        if priority[key] is not None:
            return url_for("serve_plot", filename=priority[key])

    return None

# --- Routes ------------------------------------------------
# Custom sort order
CUSTOM_ORDER = ["HL", "HT", "HP", "HA", "HC", "CQ", "ME", "1Y", "HI", "EG", "5B", "KF"]

def sort_networks(networks):
    return sorted(
        networks,
        key=lambda net: (
            CUSTOM_ORDER.index(net) if net in CUSTOM_ORDER else 9999,
            net  # secondary alphabetical sort
        )
    )


@app.route("/")
def index():
    """Main page: list networks with thumbnails"""

    # original network list
    networks = [
        d for d in os.listdir(PLOTS_DIR)
        if os.path.isdir(os.path.join(PLOTS_DIR, d))
    ]

    # APPLY CUSTOM SORT ORDER
    networks = sort_networks(networks)

    network_cards = []
    for net in networks:
        net_path = os.path.join(PLOTS_DIR, net)
        thumb = find_thumbnail(net_path)
        if thumb:  # only show networks with plots
            network_cards.append((net, thumb))

    return render_template("index.html", networks=network_cards)
@app.route("/search")
def search():
    query = request.args.get("q", "").strip().upper()
    
    if not query:
        return redirect(url_for('index'))

    # Check for deep search: "NET.STA.CHAN" (e.g., HL.ATH.HHE)
    parts = query.split('.')
    
    # CASE 1: Full Channel Jump (HL.ATH.HHE)
    if len(parts) == 3:
        net, sta, chan = parts
        # Redirect directly to the channel page if it exists
        return redirect(url_for('channel_page', network=net, station=sta, channel=chan))

    # CASE 2: Regular Search (Network, Station, or Site Name)
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

    results.sort(key=lambda x: (x['network'], x['station']))
    return render_template("search_results.html", query=query, results=results)
@app.route("/psds/<network>")
def network_page(network):
    """Network page: group stations by available channel types (HH*, EH*, HN*)"""
    net_path = os.path.join(PLOTS_DIR, network)
    if not os.path.exists(net_path):
        return f"Network {network} not found", 404

    stations = sorted(
        [d for d in os.listdir(net_path) if os.path.isdir(os.path.join(net_path, d))]
    )

    groups = {"HH": [], "EH": [], "HN": []}
    
    for sta in stations:
        sta_path = os.path.join(net_path, sta)

        # Determine which group this station belongs to (first match wins)
        available_channels = [
            c for c in os.listdir(sta_path)
            if os.path.isdir(os.path.join(sta_path, c))
        ]

        # Preferred category order: HH ? EH ? HN
        assigned = False
        for prefix in ("HH", "EH", "HN"):
            if any(ch.startswith(prefix) for ch in available_channels):
                thumb = find_thumbnail(os.path.join(net_path, sta))
                site_name = get_site_name(network, sta)
                groups[prefix].append((sta, thumb, site_name))
                assigned = True
                break

        # If station does not match any category ? ignore for now
        # You can add a fallback group if needed.

    return render_template(
        "network.html",
        network=network,
        groups=groups
    )

@app.route("/psds/<network>/<station>")
def station_page(network, station):
    """
    Station page: group channels into HH*, EH*, HN* sections.
    """
    sta_path = os.path.join(PLOTS_DIR, network, station)
    if not os.path.exists(sta_path):
        return f"Station {station} not found in {network}", 404

    # All channel directories under the station
    channels = sorted(
        [d for d in os.listdir(sta_path) if os.path.isdir(os.path.join(sta_path, d))]
    )

    # ---------------------------------------------------------
    # Build {channel: {plot_type: plot_url}} structure
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Group channels by prefix
    # ---------------------------------------------------------

    groups = {
        "HH": [],   # High broadband
        "EH": [],   # Short period
        "HN": [],   # Strong motion
        "OTHER": [] # Everything else
    }

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
        groups=groups,          # new grouped channel dictionary
        station_data=station_data,
        no_plots=(len(station_data) == 0),
    )


@app.route("/psds/<network>/<station>/<channel>")
def channel_page(network, station, channel):
    """Channel page: show all plots for a single channel"""
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

    # Merge metadata if available
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
    """Serve static images"""
    return send_from_directory(PLOTS_DIR, filename)


@app.route("/map")
def map_page():
    """Map page: show all stations with coordinates"""
    stations = []

    for key, meta in STATIONS_META.items():
        stations.append({
            "network": meta.get("network"),
            "station": meta.get("station"),
            "latitude": meta.get("latitude"),
            "longitude": meta.get("longitude"),
            "site_name": meta.get("site_name", f"{meta.get('network')}.{meta.get('station')}"),
            "elevation": meta.get("elevation"),
            "channels": meta.get("channels", [])
        })

    return render_template("map.html", stations=stations)


# --- Main ---------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, host=config.HOST, port=config.PORT)
