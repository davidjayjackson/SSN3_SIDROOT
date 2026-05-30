"""
goes_events.py
--------------
Reads GOES satellite daily event listing files and extracts solar flare (FLA)
and/or X-ray (XRA) events into sorted, formatted output files suitable for
downstream analysis (e.g. 2goesSumm.py or import into R).

Directory layout expected on disk
──────────────────────────────────
<base_dir>/
└── <MMM_YY>/                      e.g.  JUN_11/
    ├── eventlistings/
    │   ├── yyyymmddevents.txt     e.g.  20110601events.txt
    │   └── ...
    └── Data Received/             created automatically if absent
        ├── JUN_11XRA.txt          output
        └── JUN_11FLA.txt          output

Input file column layout (fixed-width, 0-based indexing)
─────────────────────────────────────────────────────────
cols 11-16  start time
cols 17-23  peak time
cols 27-33  end time
cols 43-47  event qualifier / type  (e.g. XRA, FLA)
cols 58-64  event strength / class

Output line format
──────────────────
  MM DD     HHMMSS HHMMSS HHMMSS TYPE   CLASS
  └─ date ─┘└start┘└peak ┘└end  ┘└type┘└class┘

Events are sorted chronologically and grouped by day (blank line between days).

Usage
─────
  python goes_events.py                         # interactive prompts
  python goes_events.py -o /path/to/output/MMM_YY   # explicit output base path
"""

import argparse
import glob
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def process_goes_events(output_base: Path | None = None) -> None:
    """Top-level entry point called from __main__ or from other scripts."""
    event_glob, output_base_resolved = get_file_paths()
    qual_codes = get_event_qualifiers()

    if output_base is not None:
        output_base_resolved = output_base

    process_files(event_glob, output_base_resolved, qual_codes)


# ---------------------------------------------------------------------------
# Path / directory helpers
# ---------------------------------------------------------------------------

def _prompt_month_year() -> str:
    """
    Ask the user for a month and year.
    Separated into its own function so unit tests can substitute a mock.
    """
    return input(
        "\n Enter 3-character month and 2-digit year "
        "(any separator is fine):\n"
        " Examples:  Jun11   Jun 11   Jun...11\n > "
    )


def _prompt_base_dir(label: str) -> str:
    """Ask the user for the base directory that contains <label>."""
    return input(
        f"\n Path to the directory containing '{label}'"
        f" [press Enter for current directory]: "
    )


def _parse_month_year(raw: str) -> tuple[str, str]:
    """
    Parse a loose 'MMMnn' string into (MMM, YY).

    Accepts any characters between the three-letter month and two-digit year,
    e.g. 'Jun11', 'Jun 11', 'jun_11', 'JUN...11'.

    Returns
    -------
    (mmm, yy) both as uppercase/normalised strings, e.g. ('JUN', '11').

    Raises
    ------
    ValueError on any parse failure.
    """
    raw = raw.strip()
    if len(raw) < 5:
        raise ValueError(f"Entry too short: '{raw}'")

    mmm = raw[:3]
    if not mmm.isalpha():
        raise ValueError(f"Month portion '{mmm}' must be letters only.")

    yy = raw[-2:]
    if not yy.isdigit():
        raise ValueError(f"Year portion '{yy}' must be two digits.")

    return mmm.upper(), yy


def get_file_paths(
    month_year_func=_prompt_month_year,
    base_dir_func=_prompt_base_dir,
) -> tuple[str, Path]:
    """
    Interactively collect the month/year and base directory from the user.

    Returns
    -------
    event_glob : str
        A glob pattern that matches all daily event listing files.
    output_base : Path
        Stem for output files; caller appends e.g. 'XRA.txt'.
    """
    raw = month_year_func()
    try:
        mmm, yy = _parse_month_year(raw)
    except ValueError as exc:
        sys.exit(f"\n Invalid date entry: {exc}\n")

    period_label = f"{mmm}_{yy}"          # e.g. JUN_11

    raw_dir = base_dir_func(period_label).strip()
    base_dir = Path(raw_dir).expanduser() if raw_dir else Path.cwd()

    period_dir   = base_dir / period_label
    listings_dir = period_dir / "eventlistings"
    output_dir   = period_dir / "Data Received"

    # Validate that the source directory exists and is readable.
    if not listings_dir.is_dir():
        sys.exit(
            f"\n Event listings directory not found:\n  {listings_dir}\n"
            "  Check that the path and period label are correct.\n"
        )

    # Create the output directory if it doesn't already exist.
    output_dir.mkdir(parents=True, exist_ok=True)

    event_glob  = str(listings_dir / "*events.txt")
    output_base = output_dir / period_label

    return event_glob, output_base


# ---------------------------------------------------------------------------
# Qualifier selection
# ---------------------------------------------------------------------------

_VALID_CODES = {"FLA", "XRA"}


def _prompt_qualifiers() -> str:
    return input(
        "\n\n  Available event types: FLA  XRA\n"
        "  Enter one or both, comma-separated (e.g.  XRA,FLA): "
    )


def get_event_qualifiers(input_func=_prompt_qualifiers) -> list[str]:
    """
    Ask the user which event types to extract.

    Returns a list containing any combination of 'FLA' and 'XRA',
    in that canonical order.  Unrecognised tokens are silently ignored.
    Exits if neither valid code is found in the input.
    """
    raw   = input_func().upper()
    tokens = {t.strip() for t in raw.split(",")}
    codes  = [c for c in ("FLA", "XRA") if c in tokens]

    if not codes:
        sys.exit(
            "\n No valid event qualifiers found. "
            "Please enter FLA, XRA, or both.\n"
        )

    return codes


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def process_files(
    event_glob: str,
    output_base: Path,
    qual_codes: list[str],
) -> None:
    """
    For each requested event type, scan all matching daily files,
    collect valid events, sort them, and write the output file.
    """
    daily_files = sorted(glob.glob(event_glob))

    if not daily_files:
        print(f"\n Warning: no event files matched pattern:\n  {event_glob}\n")
        return

    for code in qual_codes:
        events: list[str] = []
        for filepath in daily_files:
            events.extend(_extract_events(filepath, code))

        output_path = Path(str(output_base) + code + ".txt")
        _write_output(output_path, events, code)
        print(f"  Wrote {len(events):4d} {code} events → {output_path}")


def _extract_events(filepath: str, code: str) -> list[str]:
    """
    Read one daily event file and return formatted lines for *code* events.

    Output line columns (space-separated, fixed width)
    ───────────────────────────────────────────────────
    cols  0- 4  month day  (from filename, e.g. '06 01')
    cols  5-10  padding
    cols 11-16  start time   (from input cols 11-16)
    cols 17-23  peak time    (from input cols 17-23)
    cols 24-30  end time     (from input cols 27-33)
    cols 31-35  event type   (from input cols 43-47)
    cols 36-42  strength     (from input cols 58-64)
    """
    results: list[str] = []
    path    = Path(filepath)
    stem    = path.stem                       # e.g. '20110601events'

    # Derive MM DD from filename positions 4-5 (month) and 6-7 (day).
    try:
        month_day = f"{stem[4:6]} {stem[6:8]}"
    except IndexError:
        print(f"  Warning: unexpected filename format '{path.name}', skipping.")
        return results

    try:
        with open(filepath, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                # Lines shorter than 65 chars cannot contain all needed fields.
                if len(line) < 65:
                    continue
                if line[43:46] == code:
                    formatted = (
                        f"{month_day}     "
                        f"{line[11:17]}"
                        f"{line[17:24]}"
                        f"{line[27:34]}"
                        f"{line[43:48]}"
                        f"{line[58:65]}"
                    )
                    results.append(formatted.rstrip())
    except OSError as exc:
        print(f"  Warning: could not read '{filepath}': {exc}")

    return results


def _write_output(output_path: Path, events: list[str], code: str) -> None:
    """
    Write sorted events to *output_path*.

    Events are sorted by the time portion of the line (cols 3-13) so that
    events from different days appear in chronological order.  A blank line
    is inserted between each change of day (cols 3-4 = month day).
    """
    with open(output_path, "w", encoding="utf-8") as fh:
        if not events:
            fh.write(f"No valid {code} events found\n")
            return

        events.sort(key=lambda s: s[3:14])

        current_day = None
        for entry in events:
            day = entry[3:5]
            if current_day is not None and day != current_day:
                fh.write("\n")
            current_day = day
            fh.write(f"{entry}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract FLA/XRA events from GOES daily event listing files "
            "and write sorted, formatted output files for downstream analysis."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-o", "--outfile",
        metavar="BASE_PATH",
        help=(
            "Base path for output files.  The qualifier code and '.txt' are "
            "appended automatically, e.g. /data/JUN_11  →  /data/JUN_11XRA.txt"
        ),
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()

    out = Path(args.outfile).expanduser() if args.outfile else None
    process_goes_events(out)
