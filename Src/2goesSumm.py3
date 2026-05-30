"""
2goesSumm.py  –  GOES XRA event summary
Reads a monthly XRA event file produced by 1goesevents.py and writes a CSV
summarising the daily count of each X-ray flare class (A, B, C, M, X, …).

Output format (one row per class):
    A-Class,  0,  0,  1, ...
    B-Class,  2,  0,  0, ...
    ...
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# User prompts
# ---------------------------------------------------------------------------

def _prompt_month_year() -> str:
    """Ask the user for a month/year string.  Kept as a separate callable so
    unit tests can inject a substitute without monkey-patching builtins."""
    return input(
        "\n Enter 3-character month and 2-digit year "
        "(any characters between them are ignored).\n"
        " Examples: Jun11  Jun 11  Jun...11\n > "
    )


def _prompt_base_dir(label: str) -> str:
    """Ask the user for the base directory path."""
    return input(f"Path to directory '{label}' [current directory]: ")


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def parse_month_year(raw: str) -> tuple[str, str]:
    """Return (MMM, YY) extracted from a raw month/year string.

    Accepts anything where the first three chars are letters and the last two
    are digits, with arbitrary filler between them, e.g. 'Jun11', 'JUN 11',
    'jun...11'.

    Raises SystemExit with a descriptive message on bad input.
    """
    if len(raw) < 5:
        sys.exit("Invalid entry: need at least 5 characters (e.g. 'Jun11').")

    mmm = raw[:3]
    if not mmm.isalpha():
        sys.exit(f"Invalid date: month field '{mmm}' must be letters only.")

    yy = raw[-2:]
    if not yy.isdigit():
        sys.exit(f"Invalid date: year field '{yy}' must be two digits.")

    return mmm.upper(), yy


def resolve_paths(
    input_func=_prompt_month_year,
    dir_func=_prompt_base_dir,
) -> tuple[Path, Path, str]:
    """Interactively resolve input/output paths.

    Returns:
        xra_path  – Path to the monthly XRA input file.
        out_path  – Path for the CSV summary output file.
        date_tag  – 'MMM_YY' label used in filenames (e.g. 'JUN_11').
    """
    mmm, yy = parse_month_year(input_func())
    date_tag = f"{mmm}_{yy}"

    raw_dir = dir_func(date_tag).strip()
    base_dir = Path(os.path.expanduser(raw_dir)) if raw_dir else Path.cwd()

    data_dir = base_dir / date_tag / "Data Received"
    xra_path = data_dir / f"{date_tag}XRA.txt"
    out_path = data_dir / f"{date_tag}XRASumm2.csv"

    return xra_path, out_path, date_tag


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

DAYS_IN_MONTH = 31
# Regex to capture the day field (columns 3-4, 0-indexed) and flare class
# (column 35) from each event line.
_LINE_RE = re.compile(r"^.{3}(\d{2}).{29}([A-Z])")


def read_xra_events(xra_path: Path) -> tuple[dict[str, list[int]], int]:
    """Parse the XRA event file and tally daily counts per flare class.

    Returns:
        counts   – {class_letter: [count_day1, count_day2, …, count_day31]}
        last_day – Highest day number seen (used to trim the output columns).
    """
    counts: dict[str, list[int]] = defaultdict(lambda: [0] * DAYS_IN_MONTH)
    last_day = 0

    with xra_path.open("r", encoding="ascii", errors="replace") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.rstrip("\n")
            if not line.strip():
                continue

            # Day field at columns 3-4 (1-indexed: positions 4-5 in the file)
            try:
                day = int(line[3:5])
            except ValueError:
                continue  # skip header/comment lines

            if day == 0:
                continue

            # Flare class is a single capital letter at column 35 (0-indexed)
            if len(line) <= 35:
                continue
            flare_class = line[35].upper()
            if not flare_class.isalpha():
                continue

            if day > DAYS_IN_MONTH:
                print(
                    f"  Warning: line {lineno} has day={day} > {DAYS_IN_MONTH}; skipped.",
                    file=sys.stderr,
                )
                continue

            counts[flare_class][day - 1] += 1
            last_day = max(last_day, day)

    return dict(counts), last_day


def write_summary(
    out_path: Path,
    counts: dict[str, list[int]],
    last_day: int,
) -> None:
    """Write a CSV summary with one row per flare class.

    Each row has the form:
        X-Class,  3,  0,  1, …  (values for days 1 through last_day)
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Sort classes; ensure the standard A-B-C-M-X set appears first
    standard = list("ABCMX")
    extra = sorted(k for k in counts if k not in standard)
    ordered_classes = [c for c in standard if c in counts] + extra

    with out_path.open("w", encoding="ascii") as fh:
        for cls in ordered_classes:
            daily = counts[cls][:last_day]
            values = ", ".join(f"{v:2d}" for v in daily)
            fh.write(f"{cls}-Class, {values}\n")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def event_summary(out_path: Path | str | None = None) -> None:
    """Main entry point.  If *out_path* is given it overrides the interactively
    derived output path (useful for scripted/batch use)."""
    xra_path, default_out, date_tag = resolve_paths()

    effective_out = Path(os.path.expanduser(out_path)) if out_path else default_out

    print(f"\nReading  : {xra_path}")
    print(f"Writing  : {effective_out}\n")

    if not xra_path.exists():
        sys.exit(f"Input file not found: {xra_path}")

    counts, last_day = read_xra_events(xra_path)

    if not counts:
        print("No valid events found in input file.", file=sys.stderr)
        return

    write_summary(effective_out, counts, last_day)
    print(f"Summary written for {date_tag}  ({last_day} days, "
          f"{len(counts)} flare class(es) found).")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarise GOES XRA flare events by class and day (CSV output).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "The input file is expected at:\n"
            "  <base_dir>/<MMM_YY>/Data Received/<MMM_YY>XRA.txt\n\n"
            "The default output file is written to the same directory:\n"
            "  <base_dir>/<MMM_YY>/Data Received/<MMM_YY>XRASumm2.csv"
        ),
    )
    parser.add_argument(
        "-o", "--outfile",
        metavar="PATH",
        help="Override the default output CSV path.",
    )
    return parser


if __name__ == "__main__":
    args = _build_parser().parse_args()
    event_summary(out_path=args.outfile)
