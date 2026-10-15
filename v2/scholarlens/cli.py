"""Data preparation and frozen-dataset validation; no model evaluation here."""

import argparse
import json

from .data import prepare
from .dataset import build_dataset, validate_dataset


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("prepare")
    command.add_argument("--config", required=True)
    command.add_argument("--sample-train", type=int)
    for name in ("freeze", "validate"):
        command = commands.add_parser(name)
        command.add_argument("--config", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.config, args.sample_train)
    elif args.command == "freeze":
        result = build_dataset(args.config)
    else:
        result = validate_dataset(args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
