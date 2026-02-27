#!/usr/bin/env python3
import os
import json
from pathlib import Path
from obspy.clients.fdsn import Client

# Root directory where your plots live
ROOT = Path("/darrays/qc-working/images")

# Output JSON file
OUT = Path("stations.json")

# FDSN endpoint (direct node, not routing!)
FDSN_ENDPOINT = "https://eida.gein.noa.gr"

def build():
    client = Client(FDSN_ENDPOINT)
    data = {}

    # Loop over networks
    for net_dir in sorted([d for d in ROOT.iterdir() if d.is_dir()]):
        network = net_dir.name
        data[network] = {}

        # Loop over stations in each network
        for sta_dir in sorted([d for d in net_dir.iterdir() if d.is_dir()]):
            station = sta_dir.name
            site_name = ""

            try:
                inv = client.get_stations(network=network, station=station, level="station")
                site_name = inv[0][0].site.name or ""
            except Exception as e:
                print(f"Warning: could not fetch {network}.{station} ? {e}")

            data[network][station] = site_name

    # Save JSON
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} with {sum(len(stas) for stas in data.values())} stations")

if __name__ == "__main__":
    build()
