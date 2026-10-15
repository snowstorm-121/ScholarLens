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
    command = commands.add_parser("index")
    command.add_argument("--config", required=True)
    command.add_argument("--limit", type=int)
    command = commands.add_parser("retrieve")
    command.add_argument("--config", required=True)
    command.add_argument("--paper-id", required=True)
    command.add_argument("--query", required=True)
    command.add_argument("--method", choices=["bm25", "dense", "hybrid"], default="hybrid")
    command.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.config, args.sample_train)
    elif args.command == "freeze":
        result = build_dataset(args.config)
    elif args.command == "index":
        from .build_index import build_index
        result = build_index(args.config, args.limit)
    elif args.command == "retrieve":
        from .retrieval import retrieve
        result = retrieve(args.query, args.paper_id, args.method, args.k, args.config)
    else:
        result = validate_dataset(args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
