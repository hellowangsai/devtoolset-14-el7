#!/usr/bin/env python3
"""Discover the latest Rocky 8 source RPM URLs for gcc-toolset-14 components."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


DEFAULT_BASE_URL = "https://download.rockylinux.org/pub/rocky/8.10/Devel/source/tree/Packages"
RPM_SUFFIX = ".src.rpm"


def read_components(path):
    items = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        items.append(line)
    return items


def rpm_sort_key(value):
    parts = re.split(r"([0-9]+)", value)
    key = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part)
    return key


def fetch_index(url):
    try:
        with urlopen(url) as response:
            return response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError) as exc:
        try:
            output = subprocess.check_output(["curl", "-fsSL", url])
            return output.decode("utf-8", errors="replace")
        except Exception as curl_exc:
            raise RuntimeError(
                "failed to fetch {}: {} (curl fallback: {})".format(url, exc, curl_exc)
            )


def find_latest_filename(index_text, component):
    pattern = re.compile(
        re.escape(component) + r"-(?:[0-9][^\s\"'<>]*)" + re.escape(RPM_SUFFIX)
    )
    matches = sorted(set(pattern.findall(index_text)), key=rpm_sort_key)
    if not matches:
        raise RuntimeError("no source RPM found for component '{}'".format(component))
    return matches[-1]


def discover(base_url, components):
    cache = {}
    discovered = {}
    for component in components:
        initial = component[0].lower()
        index_url = "{}/{}/".format(base_url, initial)
        if index_url not in cache:
            cache[index_url] = fetch_index(index_url)
        filename = find_latest_filename(cache[index_url], component)
        discovered[component] = {
            "filename": filename,
            "url": "{}{}".format(index_url, filename),
        }
    return discovered


def print_lines(discovered):
    for component in sorted(discovered):
        entry = discovered[component]
        print("{}\t{}\t{}".format(component, entry["filename"], entry["url"]))


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--components-file",
        type=Path,
        default=Path("manifests/rocky8-core-components.txt"),
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--format", choices=("json", "lines"), default="json")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)

    components = read_components(args.components_file)
    discovered = discover(args.base_url, components)
    if args.format == "lines":
        print_lines(discovered)
    elif args.pretty:
        print(json.dumps(discovered, indent=2, sort_keys=True))
    else:
        print(json.dumps(discovered, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
