#!/usr/bin/env python3
"""Render EL7-style SCL meta specs for devtoolset-14."""

import argparse
import sys
from pathlib import Path


TOOLSET = "devtoolset-14"
PREFIX = "/opt/rh/{}/root".format(TOOLSET)
SUBSTITUTIONS = {
    "@TOOLSET@": TOOLSET,
    "@PREFIX@": PREFIX,
    "@SCL_ROOT@": "/opt/rh/{}".format(TOOLSET),
}


def render(template):
    output = template
    for needle, replacement in SUBSTITUTIONS.items():
        output = output.replace(needle, replacement)
    return output


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--templates", type=Path, default=Path("specs"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    for template_path in sorted(args.templates.glob("*.spec.in")):
        rendered = render(template_path.read_text(encoding="utf-8"))
        output_name = template_path.name[:-3]
        (args.out / output_name).write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
