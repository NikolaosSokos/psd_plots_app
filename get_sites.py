#!/usr/bin/env python3
import json
import sys
import threading
import itertools
import time
from datetime import datetime
from pathlib import Path
from obspy.clients.fdsn import Client

ROOT      = Path("/darrays/qc-working/images")
SDS_ROOT  = Path("/home/qc/iso_sds")
OUT_SITES = Path("stations.json")
OUT_META  = Path("stations_meta.json")
FDSN_ENDPOINT = "https://eida.gein.noa.gr"
NETWORKS  = ["HL","HT","HP","HA","HC","CQ","ME","1Y","HI","EG","5B","KF"]

NOW = datetime.utcnow()


class Spinner:
    def __init__(self, message=""):
        self.message = message
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._spin)

    def _spin(self):
        for frame in itertools.cycle(["?","?","?","?","?","?","?","?","?","?"]):
            if self._stop_event.is_set():
                break
            sys.stdout.write(f"\r  {frame}  {self.message}")
            sys.stdout.flush()
            time.sleep(0.1)

    def start(self):
        self._thread.start()
        return self

    def stop(self, msg=""):
        self._stop_event.set()
        self._thread.join()
        sys.stdout.write(f"\r  ?  {msg or self.message}\n")
        sys.stdout.flush()

    def fail(self, msg=""):
        self._stop_event.set()
        self._thread.join()
        sys.stdout.write(f"\r  ?  {msg}\n")
        sys.stdout.flush()


def fetch_network(client, network):
    """Fetch station+channel inventory for a single network (all epochs,
    including closed stations so we can record their end_date)."""
    try:
        inv = client.get_stations(network=network, level="channel")
        result = {}
        for net in inv:
            for sta in net:
                # Station end_date: closed if end_date exists and is in the past
                sta_end = None
                if sta.end_date:
                    sta_end = sta.end_date.strftime("%Y-%m-%dT%H:%M:%S")

                is_active = (sta.end_date is None) or (sta.end_date.datetime > NOW)

                channels = []
                for cha in sta:
                    channels.append({
                        "location":   cha.location_code,
                        "code":       cha.code,
                        "start_date": cha.start_date.strftime("%Y-%m-%dT%H:%M:%S") if cha.start_date else None,
                        "end_date":   cha.end_date.strftime("%Y-%m-%dT%H:%M:%S")   if cha.end_date   else None,
                    })
                result[sta.code] = {
                    "site_name": sta.site.name or "",
                    "latitude":  sta.latitude,
                    "longitude": sta.longitude,
                    "elevation": sta.elevation,
                    "end_date":  sta_end,      # None means still active
                    "is_active": is_active,    # False means decommissioned
                    "channels":  channels,
                }
        return result
    except Exception as e:
        return {"_error": str(e)}


def build():
    client = Client(FDSN_ENDPOINT)
    lookup = {}  # {(network, station): {...}}

    # Fetch per network
    print("Fetching inventory per network...\n")
    for net in NETWORKS:
        spinner = Spinner(f"Fetching {net}...").start()
        result = fetch_network(client, net)

        if "_error" in result:
            spinner.fail(f"{net} ? {result['_error']}")
            continue

        for sta_code, info in result.items():
            lookup[(net, sta_code)] = info

        active   = sum(1 for v in result.values() if v["is_active"])
        inactive = len(result) - active
        status   = f"{net} ? {active} active"
        if inactive:
            status += f", {inactive} closed"
        spinner.stop(status)

    # Walk images dir AND SDS archive to discover all stations
    # (a station might have SDS data but no image dir if plotting never ran for it)
    print()
    spinner = Spinner("Matching stations to image dirs and SDS archive...").start()
    sites = {}
    meta  = {}
    found = 0
    missing = 0
    missing_list = []
    closed_count = 0

    # Step 1: Discover all (network, station) pairs from BOTH image dir and SDS
    discovered = {}  # {(net, sta): {"has_image_dir": bool, "image_dir": Path|None}}

    # 1a: From image directory
    if ROOT.exists():
        for net_dir in sorted(d for d in ROOT.iterdir() if d.is_dir()):
            network = net_dir.name
            if network not in NETWORKS:
                continue
            for sta_dir in sorted(d for d in net_dir.iterdir() if d.is_dir()):
                station = sta_dir.name
                discovered[(network, station)] = {
                    "has_image_dir": True,
                    "image_dir": sta_dir,
                }

    # 1b: From SDS archive ? pick up stations with data but no image dir
    # SDS layout: /home/qc/iso_sds/<YEAR>/<NET>/<STA>/<CHAN.D>/files
    if SDS_ROOT.exists():
        try:
            for year_dir in SDS_ROOT.iterdir():
                if not year_dir.name.isdigit():
                    continue
                # Only scan recent years to keep this fast (current and previous)
                if int(year_dir.name) < NOW.year - 1:
                    continue
                if not (year_dir.is_dir() or year_dir.is_symlink()):
                    continue
                try:
                    for net_dir in year_dir.iterdir():
                        network = net_dir.name
                        if network not in NETWORKS:
                            continue
                        if not net_dir.is_dir():
                            continue
                        try:
                            for sta_dir in net_dir.iterdir():
                                station = sta_dir.name
                                if (network, station) not in discovered:
                                    discovered[(network, station)] = {
                                        "has_image_dir": False,
                                        "image_dir": None,
                                    }
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception as e:
            print(f"\n  WARN: SDS scan failed: {e}")

    # Step 2: Match discovered stations against FDSN inventory
    for (network, station), disco in sorted(discovered.items()):
        sites.setdefault(network, {})
        info = lookup.get((network, station))
        sta_dir = disco["image_dir"]

        if info:
            sites[network][station] = info["site_name"]
            meta[f"{network}.{station}"] = {
                "network":   network,
                "station":   station,
                "site_name": info["site_name"],
                "latitude":  info["latitude"],
                "longitude": info["longitude"],
                "elevation": info["elevation"],
                "end_date":  info["end_date"],   # None = still active
                "is_active": info["is_active"],  # False = decommissioned
                "not_in_fdsn": False,
                "has_image_dir": disco["has_image_dir"],
                "channels":  info["channels"],
            }
            found += 1
            if not info["is_active"]:
                closed_count += 1
        else:
            # Station NOT registered in FDSN.
            # Could have: image dir, SDS data, or both.
            plot_count = len(list(sta_dir.rglob("*.jpg"))) if sta_dir else 0
            sites[network][station] = ""
            meta[f"{network}.{station}"] = {
                "network":      network,
                "station":      station,
                "site_name":    "",
                "latitude":     None,
                "longitude":    None,
                "elevation":    None,
                "end_date":     None,
                "is_active":    True,
                "not_in_fdsn":  True,
                "has_image_dir": disco["has_image_dir"],
                "plot_count":   plot_count,
                "channels":     [],
            }
            missing_list.append({
                "key":           f"{network}.{station}",
                "plot_count":    plot_count,
                "has_image_dir": disco["has_image_dir"],
            })
            missing += 1

    spinner.stop(f"Matched {found} stations ({closed_count} closed) ? {missing} not in FDSN inventory")

    # Write files
    spinner = Spinner("Writing JSON files...").start()
    OUT_SITES.write_text(json.dumps(sites, indent=2), encoding="utf-8")
    OUT_META.write_text(json.dumps(meta,  indent=2), encoding="utf-8")
    spinner.stop(f"Wrote {OUT_SITES} and {OUT_META}")

    # Summary
    total = found + missing
    active_count = found - closed_count
    with_plots    = sum(1 for m in missing_list if m["plot_count"] > 0)
    no_plots      = sum(1 for m in missing_list if m["plot_count"] == 0 and m["has_image_dir"])
    sds_only      = sum(1 for m in missing_list if not m["has_image_dir"])

    print(f"\n{'-'*60}")
    print(f"  Total      : {total}")
    print(f"  Active     : {active_count}")
    print(f"  Closed     : {closed_count}")
    print(f"  Not in FDSN: {missing}")
    if missing_list:
        print(f"\n  ? Not in FDSN inventory (data and/or image dirs but no FDSN registration):")
        print()
        for m in sorted(missing_list, key=lambda x: x["key"]):
            if not m["has_image_dir"]:
                flag = "(SDS data only ? no plots yet)"
            elif m["plot_count"] > 0:
                flag = f"({m['plot_count']} plots)"
            else:
                flag = "(no plots ? safe to delete dir)"
            print(f"    · {m['key']:<20} {flag}")
        print()
        print(f"    Summary: {with_plots} have plots, {no_plots} are empty image dirs, {sds_only} have SDS data but no image dir")
    print(f"{'-'*60}")


if __name__ == "__main__":
    build()
