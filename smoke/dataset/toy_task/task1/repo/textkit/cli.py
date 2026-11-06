"""Command line interface: textkit OP FILE"""

import argparse
import sys

from .core import OPERATIONS, run


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="textkit")
    parser.add_argument("op", choices=sorted(OPERATIONS))
    parser.add_argument("file")
    args = parser.parse_args(argv)
    with open(args.file) as fh:
        text = fh.read()
    result = run(args.op, text)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
