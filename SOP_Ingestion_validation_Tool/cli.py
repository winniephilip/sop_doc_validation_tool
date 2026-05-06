"""CLI for the SOP Validation Tool — parse or compare documents without the server."""
import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from parser import parse_file
from comparator import DiffEngine
from dataclasses import asdict


def cmd_parse(args):
    result = parse_file(args.file)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_compare(args):
    orig = parse_file(args.original)
    new  = parse_file(args.new_version)
    engine = DiffEngine()
    report = engine.compare(orig, new)
    report_dict = asdict(report)
    if args.output:
        Path(args.output).write_text(
            json.dumps(report_dict, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Report written to {args.output}")
    else:
        print(json.dumps(report_dict, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="SOP Ingestion Validation Tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="Parse a single PDF or DOCX file to JSON")
    p_parse.add_argument("file", help="Path to the document")
    p_parse.set_defaults(func=cmd_parse)

    p_compare = sub.add_parser("compare", help="Compare two documents")
    p_compare.add_argument("original", help="Path to the original document")
    p_compare.add_argument("new_version", help="Path to the new version document")
    p_compare.add_argument("-o", "--output", help="Save report to this JSON file")
    p_compare.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
