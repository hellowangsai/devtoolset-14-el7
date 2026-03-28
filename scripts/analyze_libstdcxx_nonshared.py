#!/usr/bin/env python3
"""Analyze libstdc++_nonshared.a baselines across EL7 and Rocky 8."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SYMBOL_RE = re.compile(r"^\S+\s+[TDBVWR]\s+(\S+)$")
PATCH_SUBDIR_RE = re.compile(r"libstdc\+\+-v3/src/(nonshared\d+)/")
PATCH_VARIANT_RE = re.compile(r"libstdc\+\+_nonshared(\d+)|libnonshared\d+convenience(\d+)")
GLIBCXX_VERSION_RE = re.compile(r"^GLIBCXX_\d+(?:\.\d+)+$")
CXXABI_VERSION_RE = re.compile(r"^CXXABI_\d+(?:\.\d+)+$")


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


def run_text(args):
    return subprocess.check_output(args).decode("utf-8", errors="replace")


def read_archive_members(path):
    text = run_text(["ar", "t", str(path)])
    return [line.strip() for line in text.splitlines() if line.strip()]


def read_defined_symbols(path):
    text = subprocess.check_output(
        ["nm", "--defined-only", str(path)], stderr=subprocess.DEVNULL
    ).decode("utf-8", errors="replace")
    symbols = []
    for raw in text.splitlines():
        line = raw.strip()
        match = SYMBOL_RE.match(line)
        if match:
            symbols.append(match.group(1))
    return sorted(set(symbols))


def read_versioned_system_symbols(path):
    text = run_text(["strings", "-a", str(path)])
    glibcxx = sorted(
        {line for line in text.splitlines() if GLIBCXX_VERSION_RE.match(line)},
        key=rpm_sort_key,
    )
    cxxabi = sorted(
        {line for line in text.splitlines() if CXXABI_VERSION_RE.match(line)},
        key=rpm_sort_key,
    )
    return {
        "glibcxx_versions": glibcxx,
        "cxxabi_versions": cxxabi,
        "max_glibcxx": glibcxx[-1] if glibcxx else None,
        "max_cxxabi": cxxabi[-1] if cxxabi else None,
    }


def read_patch_summary(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    subdirs = sorted(set(PATCH_SUBDIR_RE.findall(text)))
    variants = sorted(
        {
            int(value)
            for pair in PATCH_VARIANT_RE.findall(text)
            for value in pair
            if value
        }
    )
    objects = sorted(
        {
            match.group(2)
            for match in re.finditer(
                r"^\+\+\+ libstdc\+\+-v3/src/(nonshared\d+)/(.*?)(?:\.jj)?\s",
                text,
                re.M,
            )
            if not match.group(2).startswith("Makefile.")
        }
    )
    return {
        "path": str(path),
        "nonshared_subdirs": subdirs,
        "baseline_variants": variants,
        "patched_objects": objects,
        "patched_object_count": len(objects),
    }


def summarize_named_set(left_name, left_items, right_name, right_items):
    left = set(left_items)
    right = set(right_items)
    return {
        "left": left_name,
        "right": right_name,
        "common_count": len(left & right),
        "left_only_count": len(left - right),
        "right_only_count": len(right - left),
        "left_only_examples": sorted(left - right)[:25],
        "right_only_examples": sorted(right - left)[:25],
    }


def archive_summary(label, path):
    members = read_archive_members(path)
    symbols = read_defined_symbols(path)
    return {
        "label": label,
        "path": str(path),
        "member_count": len(members),
        "members": members,
        "defined_symbol_count": len(symbols),
        "defined_symbol_examples_tail": symbols[-50:],
    }


def build_summary(args):
    dts8_patch = read_patch_summary(args.dts8_patch)
    rocky14_patch = read_patch_summary(args.rocky14_patch)
    dts8_archive = archive_summary("devtoolset-8", args.dts8_archive)
    dts11_archive = archive_summary("devtoolset-11", args.dts11_archive)
    rocky14_archive = archive_summary("gcc-toolset-14", args.rocky14_archive)
    system_versions = read_versioned_system_symbols(args.system_libstdcxx)

    summary = {
        "system_libstdcxx": {
            "path": str(args.system_libstdcxx),
            **system_versions,
        },
        "patches": {
            "devtoolset_8": dts8_patch,
            "gcc_toolset_14_rocky8": rocky14_patch,
        },
        "archives": {
            "devtoolset_8": dts8_archive,
            "devtoolset_11": dts11_archive,
            "gcc_toolset_14_rocky8": rocky14_archive,
        },
        "comparisons": {
            "dts8_vs_rocky14_members": summarize_named_set(
                "devtoolset-8",
                dts8_archive["members"],
                "gcc-toolset-14",
                rocky14_archive["members"],
            ),
            "dts11_vs_rocky14_members": summarize_named_set(
                "devtoolset-11",
                dts11_archive["members"],
                "gcc-toolset-14",
                rocky14_archive["members"],
            ),
            "dts8_vs_dts11_members": summarize_named_set(
                "devtoolset-8",
                dts8_archive["members"],
                "devtoolset-11",
                dts11_archive["members"],
            ),
        },
    }

    summary["verdict"] = {
        "can_directly_merge_two_increments": False,
        "required_nonshared_variant_for_el7": 48,
        "reason": (
            "devtoolset-8 ships a nonshared48 baseline for the CentOS 7 "
            "libstdc++.so.6 ABI, while Rocky 8 gcc-toolset-14 ships a "
            "nonshared80 baseline for the Rocky 8 / RHEL 8 ABI. The two "
            "archives overlap in some object families but also carry "
            "baseline-specific objects and different patch variants, so "
            "mechanically unioning them would not produce a valid EL7 "
            "libstdc++_nonshared.a."
        ),
        "evidence": {
            "centos7_patch_variants": dts8_patch["baseline_variants"],
            "rocky8_patch_variants": rocky14_patch["baseline_variants"],
            "dts8_only_member_examples": summary["comparisons"]["dts8_vs_rocky14_members"][
                "left_only_examples"
            ],
            "rocky14_only_member_examples": summary["comparisons"]["dts8_vs_rocky14_members"][
                "right_only_examples"
            ],
            "system_max_glibcxx": system_versions["max_glibcxx"],
            "system_max_cxxabi": system_versions["max_cxxabi"],
        },
    }
    return summary


def render_markdown(summary):
    verdict = summary["verdict"]
    dts8_vs_rocky14 = summary["comparisons"]["dts8_vs_rocky14_members"]
    dts8_patch = summary["patches"]["devtoolset_8"]
    rocky_patch = summary["patches"]["gcc_toolset_14_rocky8"]
    lines = [
        "# libstdc++_nonshared analysis",
        "",
        "## Baseline",
        "",
        "- CentOS 7 system libstdc++.so.6 max `GLIBCXX`: `{}`".format(
            summary["system_libstdcxx"]["max_glibcxx"]
        ),
        "- CentOS 7 system libstdc++.so.6 max `CXXABI`: `{}`".format(
            summary["system_libstdcxx"]["max_cxxabi"]
        ),
        "- devtoolset-8 compat patch variants: `{}`".format(
            ", ".join(str(v) for v in dts8_patch["baseline_variants"])
        ),
        "- Rocky 8 gcc-toolset-14 compat patch variants: `{}`".format(
            ", ".join(str(v) for v in rocky_patch["baseline_variants"])
        ),
        "",
        "## Archive diff",
        "",
        "- Common object members: `{}`".format(dts8_vs_rocky14["common_count"]),
        "- devtoolset-8 only members: `{}`".format(dts8_vs_rocky14["left_only_count"]),
        "- Rocky 8 gcc-toolset-14 only members: `{}`".format(
            dts8_vs_rocky14["right_only_count"]
        ),
        "- Sample devtoolset-8 only members: `{}`".format(
            ", ".join(dts8_vs_rocky14["left_only_examples"][:12])
        ),
        "- Sample Rocky 8 only members: `{}`".format(
            ", ".join(dts8_vs_rocky14["right_only_examples"][:12])
        ),
        "",
        "## Verdict",
        "",
        "- Directly merging the two increments is not valid.",
        "- Required EL7 target remains `nonshared48`.",
        "- Reason: {}".format(verdict["reason"]),
    ]
    return "\n".join(lines) + "\n"


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dts8-patch",
        type=Path,
        default=ROOT
        / "vendor/extracted-centos7/devtoolset-8-gcc-8.3.1-3.2.el7/gcc8-libstdc++-compat.patch",
    )
    parser.add_argument(
        "--rocky14-patch",
        type=Path,
        default=ROOT
        / "vendor/extracted-core/gcc-toolset-14-gcc-14.2.1-11.el8_10/gcc14-libstdc++-compat.patch",
    )
    parser.add_argument(
        "--dts8-archive",
        type=Path,
        default=ROOT
        / "vendor/extracted-centos7-rpms/devtoolset-8-libstdcxx-devel/opt/rh/devtoolset-8/root/usr/lib/gcc/x86_64-redhat-linux/8/libstdc++_nonshared.a",
    )
    parser.add_argument(
        "--rocky14-archive",
        type=Path,
        default=ROOT
        / "vendor/extracted-rocky8-rpms/gcc-toolset-14-libstdcxx-devel/opt/rh/gcc-toolset-14/root/usr/lib/gcc/x86_64-redhat-linux/14/libstdc++_nonshared.a",
    )
    parser.add_argument(
        "--dts11-archive",
        type=Path,
        default=Path(
            "/opt/rh/devtoolset-11/root/usr/lib/gcc/x86_64-redhat-linux/11/libstdc++_nonshared.a"
        ),
    )
    parser.add_argument(
        "--system-libstdcxx",
        type=Path,
        default=Path("/usr/lib64/libstdc++.so.6"),
    )
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args(argv)

    for path in [
        args.dts8_patch,
        args.rocky14_patch,
        args.dts8_archive,
        args.rocky14_archive,
        args.dts11_archive,
        args.system_libstdcxx,
    ]:
        if not path.exists():
            raise SystemExit("missing required input: {}".format(path))

    summary = build_summary(args)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )
    markdown = render_markdown(summary)
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
