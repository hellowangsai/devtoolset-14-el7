#!/usr/bin/env python3
"""Discover the latest package URLs from a YUM/DNF repository."""

import argparse
import gzip
import io
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


COMMON_NS = "{http://linux.duke.edu/metadata/common}"
REPO_NS = {"repo": "http://linux.duke.edu/metadata/repo"}


def read_package_names(path):
    packages = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        packages.append(line)
    return packages


def rpm_sort_key(value):
    parts = []
    token = []
    digit_mode = None
    for char in value:
        is_digit = char.isdigit()
        if digit_mode is None:
            digit_mode = is_digit
            token.append(char)
            continue
        if is_digit == digit_mode:
            token.append(char)
            continue
        text = "".join(token)
        parts.append(int(text) if digit_mode else text)
        token = [char]
        digit_mode = is_digit
    if token:
        text = "".join(token)
        parts.append(int(text) if digit_mode else text)
    return parts


def fetch_bytes(url):
    try:
        with urlopen(url) as response:
            return response.read()
    except (HTTPError, URLError) as exc:
        try:
            return subprocess.check_output(["curl", "-fsSL", url])
        except Exception as curl_exc:
            raise RuntimeError(
                "failed to fetch {}: {} (curl fallback: {})".format(url, exc, curl_exc)
            )


def fetch_primary_xml(repo_base_url):
    base = repo_base_url.rstrip("/")
    repomd_url = "{}/repodata/repomd.xml".format(base)
    repomd_root = ET.fromstring(fetch_bytes(repomd_url))
    primary = repomd_root.find("repo:data[@type='primary']/repo:location", REPO_NS)
    if primary is None:
        raise RuntimeError("primary metadata not found in {}".format(repomd_url))
    primary_href = primary.attrib["href"]
    primary_url = "{}/{}".format(base, primary_href)
    payload = fetch_bytes(primary_url)
    if primary_href.endswith(".gz"):
        return gzip.decompress(payload)
    return payload


def iter_matching_packages(primary_xml, wanted_names, arches=None):
    wanted = set(wanted_names)
    arch_filter = set(arches or [])
    stream = io.BytesIO(primary_xml)
    for _, elem in ET.iterparse(stream, events=("end",)):
        if elem.tag != COMMON_NS + "package":
            continue
        name = elem.findtext(COMMON_NS + "name")
        arch = elem.findtext(COMMON_NS + "arch")
        if name not in wanted or (arch_filter and arch not in arch_filter):
            elem.clear()
            continue
        version = elem.find(COMMON_NS + "version")
        location = elem.find(COMMON_NS + "location")
        if version is None or location is None:
            elem.clear()
            continue
        href = location.attrib["href"]
        yield {
            "name": name,
            "arch": arch,
            "epoch": version.attrib.get("epoch", "0"),
            "version": version.attrib["ver"],
            "release": version.attrib["rel"],
            "href": href,
            "filename": Path(href).name,
        }
        elem.clear()


def select_latest(entries):
    by_name = {}
    for entry in entries:
        current = by_name.get(entry["name"])
        if current is None:
            by_name[entry["name"]] = entry
            continue
        current_key = rpm_sort_key(
            "{}:{}-{}".format(current["epoch"], current["version"], current["release"])
        )
        candidate_key = rpm_sort_key(
            "{}:{}-{}".format(entry["epoch"], entry["version"], entry["release"])
        )
        if candidate_key > current_key:
            by_name[entry["name"]] = entry
    return by_name


def discover(repo_base_url, packages, arches=None):
    primary_xml = fetch_primary_xml(repo_base_url)
    discovered = select_latest(iter_matching_packages(primary_xml, packages, arches))
    missing = [package for package in packages if package not in discovered]
    if missing:
        raise RuntimeError("missing packages in {}: {}".format(repo_base_url, ", ".join(missing)))
    base = repo_base_url.rstrip("/")
    for entry in discovered.values():
        entry["url"] = "{}/{}".format(base, entry["href"])
    return discovered


def print_lines(discovered):
    for package in sorted(discovered):
        entry = discovered[package]
        print(
            "{}\t{}\t{}\t{}".format(
                package, entry["arch"], entry["filename"], entry["url"]
            )
        )


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-base-url", required=True)
    parser.add_argument("--packages-file", type=Path, required=True)
    parser.add_argument("--arch", action="append", dest="arches")
    parser.add_argument("--format", choices=("json", "lines"), default="json")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)

    packages = read_package_names(args.packages_file)
    discovered = discover(args.repo_base_url, packages, arches=args.arches)
    if args.format == "lines":
        print_lines(discovered)
    elif args.pretty:
        print(json.dumps(discovered, indent=2, sort_keys=True))
    else:
        print(json.dumps(discovered, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
