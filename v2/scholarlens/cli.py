"""T2 data-preparation entry point. Later commands belong to later tasks."""

import argparse
import json

from .data import prepare


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("prepare")
    command.add_argument("--config", required=True)
    command.add_argument("--sample-train", type=int)
    args = parser.parse_args()
    print(json.dumps(prepare(args.config, args.sample_train), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
