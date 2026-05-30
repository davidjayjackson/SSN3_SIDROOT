"""
SID Reporter - Sudden Ionospheric Disturbance Analysis
Processes observer SID reports and generates correlation analysis output files.

Data structures
---------------
Control (dict):
    enableXRA, enableFLA  : bool   - Include XRA/FLA correlation. Default False.
    enableINIUpdate       : bool   - Update Observers INI after analysis. Default False.
    path                  : str    - Working directory for input/output.
    month                 : str    - Three-letter month (e.g. 'JUN').
    year                  : str    - Two-digit year (e.g. '11').
    HiQualLimit           : int    - Min quality ratio to include uncorrelated events.
    nObservers            : int    - Number of observers read for analysis.
    nEvents               : int    - Total submitted events.
    nCorr                 : int    - Number of correlated events.
    nImp                  : list   - Count per importance level in correlations.
    response              : list   - Report selections from user.

OBSERVER (class):
    ID         : int   - Numeric observer ID.
    id         : str   - String ID beginning with 'A'.
    name       : str   - Full name.
    ngdcName   : str   - First initial + last name.
    location   : str   - City, State / City, Country.
    quality    : int   - Running quality rating.
    qualCount  : int   - Reports used to compute quality rating.
    nReports   : int   - Reports submitted for this analysis run.
    reports    : list  - List of report dicts (see below).

report (dict):
    path          : str   - Full path to data file.
    filen         : str   - File name.
    station       : str   - Station code and frequency string.
    nEvents       : int   - Events in report.
    unusedEvents  : int   - Uncorrelated events.
    qualRatio     : int   - (correlated / total) * 10.
    Events        : list  - List of event dicts (see below).

event (dict):
    strEvent    : str   - Raw event line from file.
    importance  : int   - Numeric importance (0-6).
    day         : int   - Day of event.
    peakTime    : int   - Peak time in UT minutes (0-1440).
    duration    : int   - Stop time minus start time (minutes).
    crFlag      : int   - 0 = uncorrelated; positive value = correlation type.

XRA / FLA (dict):
    day         : int   - Day of event.
    peak        : int   - Peak time in UT minutes.
    duration    : int   - Stop minus start time (minutes).
    strength    : str   - X-ray strength string  (XRA only).
    strengthN   : float - Numeric strength        (XRA only).
"""

import os
import sys
import configparser
import argparse
from functools import cmp_to_key

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FALSE = 0
TRUE = 1

# Correlation-flag values
USER_CORRELATED   = 1
XRA_CORRELATED    = 2
FLA_CORRELATED    = 3
HIQUAL_CORRELATED = 4

# Database output modes
DB_FULL    = 0
DB_PARTIAL = 1

OBSERVERS_INI = "SIDAnalObservers.ini"
STATION_INI   = "SIDAnalStations.ini"

IMPORTANCE_MAP = {"1-": 0, "1": 1, "1+": 2, "2": 3, "2+": 4, "3": 5, "3+": 6}
IMP_TO_STR     = {v: k for k, v in IMPORTANCE_MAP.items()}

MONTH_NAMES = {
    "jan": "January",  "feb": "February", "mar": "March",
    "apr": "April",    "may": "May",       "jun": "June",
    "jul": "July",     "aug": "August",    "sep": "September",
    "oct": "October",  "nov": "November",  "dec": "December",
}

MONTH_NUMS = ["jan", "feb", "mar", "apr", "may", "jun",
              "jul", "aug", "sep", "oct", "nov", "dec"]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def time_ascii_to_int(s: str) -> int:
    """Convert a four-character HHMM string to minutes since midnight (0-1440)."""
    if not s.isdigit():
        return 0
    return int(s[:2]) * 60 + int(s[2:])


def time_int_to_ascii(minutes: int) -> str:
    """Convert minutes since midnight to a four-character HHMM string."""
    return f"{minutes // 60:02d}{minutes % 60:02d}"


def month_str(month: str) -> str:
    """Return the full month name for a three-letter abbreviation."""
    return MONTH_NAMES[month.lower()]


def importance_to_str(n: int) -> str:
    """Convert a numeric importance level (0-6) to its string representation."""
    return IMP_TO_STR.get(n, "?")


def set_date_for_db_file(year: str, month: str, day) -> str:
    """Return a YYYYMMDD date string for use in database output files."""
    mm = f"{MONTH_NUMS.index(month.lower()) + 1:02d}"
    return f"20{year}{mm}{int(day):02d}"


# ---------------------------------------------------------------------------
# User-input helpers (factored out for unit-testing)
# ---------------------------------------------------------------------------

def prompt_month_year() -> str:
    return input(
        "\n Enter 3-character month and 2-digit year "
        "(any characters between them):\n"
        " Examples: Jun11, Jun 11, Jun...11: "
    )


def prompt_base_directory(mmm_yy: str) -> str:
    return input(
        f"What is the path to the directory {mmm_yy} [current directory]? "
    )


# ---------------------------------------------------------------------------
# Set-up
# ---------------------------------------------------------------------------

def setup_default_directory(control: dict, input_func=prompt_month_year) -> None:
    """Parse month/year from the user, resolve the working path, and update *control*."""
    mmmyy = input_func()

    if len(mmmyy) < 5:
        sys.exit("\n Invalid entry\n")

    mmm = mmmyy[:3]
    if not mmm.isalpha():
        sys.exit("\n Invalid date: month field not all characters\n")
    mmm = mmm.upper()

    yy = mmmyy[-2:]
    if not yy.isdigit():
        sys.exit("\n Invalid date: year field is not an integer\n")

    date = f"{mmm}_{yy}"
    raw_path = prompt_base_directory(date)
    base = os.path.expanduser(raw_path) if raw_path else os.getcwd()

    path = os.path.join(base, date, "Data Received")
    os.makedirs(path, exist_ok=True)

    control.update(month=mmm, year=yy, path=path)


# ---------------------------------------------------------------------------
# File chooser
# ---------------------------------------------------------------------------

def get_files() -> tuple:
    """Open a Tk file-chooser dialog and return a tuple of selected .dat paths."""
    import tkinter as tk
    import tkinter.filedialog as fd

    root = tk.Tk()
    root.withdraw()
    files = fd.askopenfilenames(
        parent=root,
        title="Choose Observer files",
        filetypes=[("Observer files", "*.dat")],
    )
    files = root.tk.splitlist(files)
    root.destroy()
    return files


# ---------------------------------------------------------------------------
# OBSERVER class
# ---------------------------------------------------------------------------

class Observer:
    """Holds observer metadata and the reports (with events) submitted for analysis."""

    def __init__(self, numeric_id: int, str_id: str, station_code: str):
        self.ID       = numeric_id   # integer part of observer id
        self.id       = str_id       # e.g. 'A050'
        self.strSTA   = station_code
        self.nReports = 0
        self.reports: list = []
        # Populated by get_observer_info()
        self.name      = ""
        self.ngdcName  = ""
        self.location  = ""
        self.quality   = 0
        self.qualCount = 0

    # ------------------------------------------------------------------
    def get_observer_info(
        self,
        observers_ini: str,
        get_name=None,
        get_location=None,
    ) -> None:
        """Load (or create) observer metadata from *observers_ini*."""

        if get_name is None:
            get_name = lambda: input("Enter full name: ")
        if get_location is None:
            get_location = lambda: input(
                "Enter observer's location; format: City, State: "
            )

        config = configparser.RawConfigParser()
        config.optionxform = str
        config.read(observers_ini)

        if not config.has_option("NGDC NAME", self.id):
            print(f"No data in {observers_ini} for {self.id}")
            name     = get_name()
            parts    = name.split()
            ngdc     = f"{parts[0][0]} {parts[-1]}" if len(parts) >= 2 else name
            location = get_location()

            for section, key, value in [
                ("NAME",           self.id, name),
                ("NGDC NAME",      self.id, ngdc),
                ("LOCATION",       self.id, location),
                ("QUALITY RATING", self.id, "0"),
                ("QUALITY COUNT",  self.id, "0"),
            ]:
                if not config.has_section(section):
                    config.add_section(section)
                config.set(section, key, value)

            with open(observers_ini, "w") as fh:
                config.write(fh)

        self.name      = config.get("NAME",           self.id)
        self.ngdcName  = config.get("NGDC NAME",      self.id)
        self.location  = config.get("LOCATION",       self.id)
        self.quality   = int(config.get("QUALITY RATING", self.id))
        self.qualCount = int(config.get("QUALITY COUNT",  self.id))

    # ------------------------------------------------------------------
    def init_report(self, station_code: str, filepath: str, stations_ini: str = STATION_INI) -> None:
        """Append a new report dict for *filepath* and resolve station info."""
        report = {
            "path":         filepath,
            "filen":        os.path.basename(filepath),
            "station":      self._get_station_info(station_code, stations_ini),
            "nEvents":      0,
            "unusedEvents": 0,
            "qualRatio":    0,
            "Events":       [],
        }
        self.reports.append(report)

    def _get_station_info(self, station_code: str, stations_ini: str) -> str:
        """Return the frequency string for *station_code*, prompting if unknown."""
        config = configparser.RawConfigParser()
        config.optionxform = str
        config.read(stations_ini)

        if not config.has_option("FREQUENCY", station_code):
            while True:
                freq = input(
                    f"No frequency for {station_code} in {stations_ini}. "
                    "Enter VLF frequency (kHz): "
                )
                if not freq.isalpha():
                    break
                print("Input should be numeric. Try again.")

            if not config.has_section("FREQUENCY"):
                config.add_section("FREQUENCY")
            config.set("FREQUENCY", station_code, f"{freq}kHz ({station_code})")
            with open(stations_ini, "w") as fh:
                config.write(fh)

        return config.get("FREQUENCY", station_code)

    # ------------------------------------------------------------------
    def get_events(self, report_index: int) -> None:
        """Parse SID event lines from the report file and populate report['Events']."""
        report = self.reports[report_index]
        events = []
        problem_entry = 0

        with open(report["path"], "r") as fh:
            for line in fh:
                fields = line.split()
                if not fields or fields[0] != "40":
                    continue

                problem_entry += 1

                # Handle timestamps that may have a trailing D/E/U character
                if len(fields) != 8:
                    for ch in ("D", "E", "U"):
                        line = line.replace(ch, " ")
                    fields = line.split()

                try:
                    event = {
                        "day":       int(fields[1][-2:]),
                        "peakTime":  time_ascii_to_int(fields[4][:4]),
                        "importance": IMPORTANCE_MAP[fields[5][:2]],
                        "duration":  (
                            time_ascii_to_int(fields[3][:4])
                            - time_ascii_to_int(fields[2][:4])
                        ),
                        "crFlag":    FALSE,
                        "strEvent":  line.rstrip(),
                    }
                    events.append(event)
                except (KeyError, ValueError, IndexError):
                    print(
                        f"{os.path.basename(report['path'])} has an unexpected "
                        f"event string, entry {problem_entry}"
                    )

        report["nEvents"] += len(events)
        report["Events"]   = events
        self.nReports     += 1

    # ------------------------------------------------------------------
    def __eq__(self, other) -> bool:
        if not isinstance(other, Observer):
            return False
        return self.__dict__ == other.__dict__

    def __str__(self) -> str:
        return ", ".join(f"{k}:{v}" for k, v in sorted(self.__dict__.items()))


# ---------------------------------------------------------------------------
# Reading observer reports
# ---------------------------------------------------------------------------

def read_reports(files: tuple, control: dict, observers_ini: str) -> list:
    """
    For each selected file, create or locate the matching Observer, initialise a
    report, and parse its events.  Returns a sorted list of Observer objects.
    """
    observers: list  = []
    obs_id_list: list = []

    for filepath in files:
        basename = os.path.splitext(os.path.basename(filepath))[0]
        int_id   = basename[1:-3]   # numeric portion
        str_id   = basename[:-3]    # full string ID  (e.g. 'A050')
        sta_code = basename[-3:]    # three-letter station code

        if not int_id.isdigit():
            print(f"Unexpected observer ID format: {int_id!r} in {basename}")
        else:
            int_id = int(int_id)

        if not sta_code.isalpha():
            print(f"Unexpected station code: {sta_code!r} in {basename}")

        if int_id not in obs_id_list:
            obs = Observer(int_id, str_id, sta_code)
            obs.get_observer_info(observers_ini)
            observers.append(obs)
            obs_id_list.append(int_id)
            control["nObservers"] += 1

        idx = obs_id_list.index(int_id)
        report_index = observers[idx].nReports
        observers[idx].init_report(sta_code, filepath)
        observers[idx].get_events(report_index)

    observers.sort(key=lambda o: o.id)
    return observers


# ---------------------------------------------------------------------------
# Correlation helpers
# ---------------------------------------------------------------------------

def match_event(timerange: int, day: int, pk_time: float, event_list: list) -> int:
    """Return the index of the first uncorrelated event within *timerange* of *pk_time*,
    or -1 if none is found."""
    for i, event in enumerate(event_list):
        if not event["crFlag"] and event["day"] == day:
            if abs(event["peakTime"] - pk_time) <= timerange:
                return i
    return -1


def correlate_observers(timerange: int, control: dict, observers: list) -> list:
    """
    Correlate events across observers within *timerange* minutes of each other.
    Updates event crFlag values in-place and returns the list of correlated events.
    """
    corr_events: list = []
    c_idx = control["nCorr"]

    for o_idx, obs in enumerate(observers):
        for report in obs.reports:
            for event in report["Events"]:
                if event["crFlag"] != FALSE:
                    continue

                corr_found = False
                ave_peak   = event["peakTime"]
                ave_count  = 1

                # First pass: gather matches to compute an average peak time
                s_ind = 1 + obs.reports.index(report)
                for obs2 in observers[o_idx:]:
                    for report2 in obs2.reports[s_ind:]:
                        m = match_event(timerange, event["day"], event["peakTime"], report2["Events"])
                        if m != -1:
                            corr_found  = True
                            ave_peak   += report2["Events"][m]["peakTime"]
                            ave_count  += 1
                            break
                    s_ind = 0

                if not corr_found:
                    continue

                ave_peak /= ave_count

                # Second pass: correlate using the averaged peak time
                for obs2 in observers:
                    for report2 in obs2.reports:
                        m = match_event(timerange, event["day"], ave_peak, report2["Events"])
                        if m == -1:
                            continue

                        if not event["crFlag"]:
                            corr_events.append({
                                "importance": event["importance"],
                                "day":        event["day"],
                                "peak":       event["peakTime"],
                                "crFlag":     USER_CORRELATED,
                                "count":      1,
                            })
                            event["crFlag"] += 1

                        corr_events[c_idx]["importance"] += report2["Events"][m]["importance"]
                        corr_events[c_idx]["peak"]       += report2["Events"][m]["peakTime"]
                        corr_events[c_idx]["count"]      += 1
                        report2["Events"][m]["crFlag"]   += 1

                corr_events[c_idx]["importance"] /= corr_events[c_idx]["count"]
                corr_events[c_idx]["peak"]       /= corr_events[c_idx]["count"]
                c_idx += 1

    control["nCorr"] = c_idx
    return corr_events


def compare_observers_to_corr_list(
    timerange: int, control: dict, observers: list, corr_events: list
) -> list:
    """Match any still-uncorrelated events against the existing correlated list."""
    for o_idx, obs in enumerate(observers):
        for report in obs.reports:
            for event in report["Events"]:
                if event["crFlag"]:
                    continue
                for corr in corr_events[o_idx + 1:]:
                    if corr["day"] == event["day"] and abs(corr["peak"] - event["peakTime"]) <= timerange:
                        n = corr["count"]
                        corr["peak"]       = (corr["peak"] * n + event["peakTime"]) / (n + 1)
                        corr["importance"] = (corr["importance"] * n + event["importance"]) / (n + 1)
                        corr["count"]     += 1
                        event["crFlag"]   += 1
                        break
    return corr_events


def match_xra_fla_event(timerange: int, day: int, pk_time: int, xrafla_data: list) -> bool:
    """Return True if any entry in *xrafla_data* matches day and peak time."""
    for entry in xrafla_data:
        if entry["day"] == -1 or entry["day"] > day:
            break
        if entry["day"] == day and abs(entry["peak"] - pk_time) <= timerange:
            return True
    return False


def compare_to_xra_fla(
    timerange: int,
    control: dict,
    observers: list,
    corr: list,
    xrafla_data: list,
    status: int,
) -> int:
    """Correlate remaining uncorrelated observer events against XRA or FLA data."""
    c_idx = control["nCorr"]

    for obs in observers:
        for report in obs.reports:
            for event in report["Events"]:
                if not event["crFlag"]:
                    if match_xra_fla_event(timerange, event["day"], event["peakTime"], xrafla_data):
                        corr.append({
                            "importance": event["importance"],
                            "day":        event["day"],
                            "peak":       event["peakTime"],
                            "count":      1,
                            "userID":     obs.ID,
                            "crFlag":     status,
                        })
                        event["crFlag"] = status
                        c_idx += 1

    return c_idx - control["nCorr"]


def detect_hi_qual_non_correlated(control: dict, observers: list, corr: list) -> int:
    """Include uncorrelated events from high-quality observers in the correlation list."""
    c_idx = control["nCorr"]

    for obs in observers:
        if obs.quality < control["HiQualLimit"] and control["HiQualLimit"] != 0:
            continue
        for report in obs.reports:
            if report["qualRatio"] < 5 and control["HiQualLimit"] != 0:
                continue
            for event in report["Events"]:
                if not event["crFlag"]:
                    corr.append({
                        "importance": event["importance"],
                        "day":        event["day"],
                        "peak":       event["peakTime"],
                        "count":      1,
                        "userID":     obs.ID,
                        "crFlag":     HIQUAL_CORRELATED,
                    })
                    event["crFlag"] = HIQUAL_CORRELATED
                    c_idx += 1

    return c_idx - control["nCorr"]


def compute_unused_observer_events(
    control: dict, observers: list, update_quality: bool
) -> None:
    """Compute qualRatio for every report and optionally update the observers INI."""
    for obs in observers:
        for report in obs.reports:
            unused = sum(1 for e in report["Events"] if not e["crFlag"])
            report["unusedEvents"] = unused
            n = report["nEvents"]
            report["qualRatio"] = int((n - unused) / float(n) * 10) if n else 0

            if update_quality and report["qualRatio"] > 2:
                obs.quality = (
                    (obs.quality * obs.qualCount + report["qualRatio"])
                    / (obs.qualCount + 1)
                )
                obs.qualCount += 1

                config = configparser.RawConfigParser()
                config.optionxform = str
                config.read(OBSERVERS_INI)
                config.set("QUALITY RATING", obs.id, str(obs.quality))
                config.set("QUALITY COUNT",  obs.id, str(obs.qualCount))
                with open(OBSERVERS_INI, "w") as fh:
                    config.write(fh)


# ---------------------------------------------------------------------------
# Reading GOES data
# ---------------------------------------------------------------------------

def read_xra(control: dict) -> list:
    """Load XRA (X-ray) event data from the month's processed file."""
    class_strength = {"A": 1, "B": 10, "C": 100, "M": 1000, "X": 10000}
    filename = os.path.join(
        control["path"], f"{control['month']}_{control['year']}XRA.txt"
    )
    xra = []
    with open(filename, "r") as fh:
        for line in fh:
            if line[0].isdigit():
                xra.append({
                    "day":       int(line[3:5]),
                    "peak":      time_ascii_to_int(line[17:21]),
                    "duration":  time_ascii_to_int(line[24:28]) - time_ascii_to_int(line[10:14]),
                    "strength":  line[35:40],
                    "strengthN": class_strength[line[35]] * float(line[36:39]),
                })
    xra.append({"day": -1})   # sentinel
    return xra


def read_fla(control: dict) -> list:
    """Load FLA (optical flare) event data from the month's processed file."""
    filename = os.path.join(
        control["path"], f"{control['month']}_{control['year']}FLA.txt"
    )
    fla = []
    with open(filename, "r") as fh:
        for line in fh:
            if line[0].isdigit():
                fla.append({
                    "day":      int(line[3:5]),
                    "peak":     time_ascii_to_int(line[17:21]),
                    "duration": time_ascii_to_int(line[24:28]) - time_ascii_to_int(line[10:14]),
                })
    fla.append({"day": -1})   # sentinel
    return fla


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

def sort_correlation_list(item1: dict, item2: dict) -> int:
    """Comparator for sorting correlated events by day then peak time."""
    if item1["day"] != item2["day"]:
        return -1 if item1["day"] < item2["day"] else 1
    if item1["peak"] != item2["peak"]:
        return -1 if item1["peak"] < item2["peak"] else 1
    return 0


# ---------------------------------------------------------------------------
# Importance summary
# ---------------------------------------------------------------------------

def sum_importance_levels(control: dict, corr_events: list, mode: int) -> int:
    """Tally events per importance level, store in control['nImp'], return total."""
    control["nImp"] = []
    total = 0

    for i in range(7):
        count = 0
        for corr in corr_events:
            if corr["importance"] != i:
                continue
            if mode == DB_FULL:
                count += 1
            elif mode == DB_PARTIAL:
                flag = corr["crFlag"]
                if flag in (USER_CORRELATED, HIQUAL_CORRELATED):
                    count += 1
                elif flag in (XRA_CORRELATED, FLA_CORRELATED) and corr["peak"] <= 600:
                    count += 1
        control["nImp"].append(count)
        total += count

    return total


# ---------------------------------------------------------------------------
# Output generators
# ---------------------------------------------------------------------------

def generate_ngdc_file(control: dict, observers: list) -> None:
    """Write the NGDC-format SID report text file."""
    mo_year = f"{month_str(control['month'])}, 20{control['year']}"
    filename = os.path.join(
        control["path"],
        f"SIDngdc_{control['month']}{control['year']}.txt",
    )

    with open(filename, "w") as fh:
        fh.write("                         Sudden Ionospheric Disturbance Report\n")
        fh.write(f"                                    -- {mo_year} --\n\n")

        for obs in observers:
            obs_line = f"{obs.id} {obs.ngdcName}, {obs.location} - "
            for report in obs.reports:
                obs_line += f" {report['station']}"
            fh.write(obs_line.rstrip() + "\n\n")

        # Gather and sort correlated event strings
        event_lines = [
            e["strEvent"]
            for obs in observers
            for report in obs.reports
            for e in report["Events"]
            if e["crFlag"]
        ]
        event_lines.sort(key=lambda s: s[5:18] + s[69:74])

        for line in event_lines:
            fh.write("\n" + line)

        fh.write("\n\n-- End Report --")


def generate_database_file(
    control: dict, observers: list, corr_events: list, mode: int
) -> None:
    """Write the SID database text file (partial or full) and a CSV importance summary."""
    cr_type = {0: "", 1: "XRA", 2: "FLA", 3: "QUAL"}
    month = control["month"].capitalize()
    mm    = f"{MONTH_NUMS.index(control['month'].lower()) + 1:02d}"
    year  = f"20{control['year']}"
    mo_year = f"{month} {year}"

    db_filename = os.path.join(
        control["path"],
        f"SIDDatabase_{month}{control['year']}.txt"
        if mode == DB_PARTIAL
        else f"SIDDatabaseFull_{month}{control['year']}.txt",
    )
    csv_filename = os.path.join(control["path"], f"{year}{mm}DatabaseFullSumm.csv")

    with open(db_filename, "w") as fh:
        fh.write("AAVSO Sudden Ionospheric Disturbance Report")
        fh.write(f"\n{month} {year}\n\nObservers:\n")

        # Observer ID block (two rows)
        k      = control["nObservers"] // 2
        line1  = 1 if k == 0 else k + control["nObservers"] % k
        line2  = 0 if k == 0 else k
        ids    = [o.id for o in observers]
        fh.write("\t".join(ids[:line1]) + "\n")
        if line2:
            fh.write("\t".join(ids[line1: line1 + line2]) + "\n")

        fh.write("\n\nYYMMDD          Event Peak              Importance")

        for corr in corr_events:
            flag   = corr["crFlag"]
            early  = corr["peak"] <= 600
            include = (
                mode == DB_FULL
                or flag in (USER_CORRELATED, HIQUAL_CORRELATED)
                or (flag in (XRA_CORRELATED, FLA_CORRELATED) and early)
            )
            if not include:
                continue

            date_str = set_date_for_db_file(control["year"], control["month"], corr["day"])
            fh.write(
                f"\n{date_str}\t\t{time_int_to_ascii(int(corr['peak']))}"
                f"\t\t\t{importance_to_str(int(corr['importance']))}"
            )
            if mode == DB_FULL and corr["count"] == 1:
                fh.write(f"\t{corr.get('userID', '')} - {cr_type.get(flag - 1, '')}")

        total = sum_importance_levels(control, corr_events, mode)

        fh.write("\n\n\n\n" + "*" * 50)
        fh.write(f"\nImportance Summary - {mo_year}")
        for i in range(7):
            fh.write(f"\n\t{importance_to_str(i):2s} events: {control['nImp'][i]:2d}")
        fh.write(f"\n ------------------\n   Total events: {total:02d}")

    with open(csv_filename, "w") as fh:
        for i in range(7):
            fh.write(f"\n\t{importance_to_str(i)},{control['nImp'][i]:2d}")

    response = control.get("response", [])
    if ("3" in response and mode == DB_FULL) or ("4" in response and mode == DB_PARTIAL) or "*" in response:
        generate_analysis_summary_file(control, observers, corr_events, mode, mo_year)


def generate_analysis_summary_file(
    control: dict,
    observers: list,
    corr_events: list,
    mode: int,
    mo_year: str,
) -> None:
    """Write a human-readable analysis summary file."""
    mode_str = "FULL" if mode == DB_FULL else "PARTIAL"
    filename = os.path.join(
        control["path"],
        "SID_DatabaseFull_Sum.txt" if mode == DB_FULL else "SID_Database_Sum.txt",
    )

    with open(filename, "w") as fh:
        fh.write(
            f"Data Analysis Summary file   -  "
            f"{month_str(control['month'])}, 20{control['year']}\n"
        )

        if control["enableXRA"] or control["enableFLA"]:
            fh.write("\n\nSecondary correlation with GOES XRA, FLA Data was performed")
            if mode == DB_PARTIAL:
                fh.write(
                    "\n  XRA, FLA correlated events included only if event time < 1000 UT"
                )
            else:
                fh.write("\n  All XRA, FLA correlated events included in this listing")

        fh.write(
            f"\n\nUncorrelated events included for observers with "
            f"quality rating >= {control['HiQualLimit']:d}"
        )

        fh.write(f"\n\nImportance Summary - {mo_year}  {mode_str}")
        fh.write("\n\nImportance\tCount")
        for i in range(7):
            fh.write(f"\n{importance_to_str(i):2s} \t\t{control['nImp'][i]:2d}")

        fh.write("\n\n\n\nContributing Observers\n")
        for obs in observers:
            stations = " ".join(
                r["station"].split()[1][1:-1] for r in obs.reports
            )
            fh.write(f"\n{obs.ngdcName}{10 * ' '}\t{obs.id}\t{stations}")


def generate_file_of_unused_observer_events(control: dict, observers: list) -> None:
    """Write a per-observer summary of uncorrelated events."""
    compute_unused_observer_events(control, observers, False)

    filename = os.path.join(control["path"], "Observers Summary.txt")
    with open(filename, "w") as fh:
        fh.write(
            f"SID OBSERVER Unused Event Summary  -  "
            f"{month_str(control['month'])}, 20{control['year']}\n"
        )
        fh.write(f"\n\nMinimum observer quality rating used in analysis - [{control['HiQualLimit']}]")
        fh.write(
            "\n\nObserver quality rating based on correlated events only,\n"
            "not events included due to previous high quality rating."
        )

        for obs in observers:
            fh.write(
                f"\n\nObserver: {obs.id:4}   -   {obs.name}"
                f"\t\t\tQuality Rating: {obs.quality} for {obs.qualCount} reports"
            )
            for report in obs.reports:
                fh.write(f"\n    Station: {report['station']}")
                fh.write(f"\n      Quality Rating:  [{report['qualRatio']:2d}]")
                fh.write(f"\n        Total events:  {report['nEvents']:2d}")
                fh.write(f"\n       Unused events:  {report['unusedEvents']:2d}")
                for event in report["Events"]:
                    if not event["crFlag"]:
                        fh.write(f"\n        {event['strEvent']}")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def sid_reporter(
    observers_ini: str = OBSERVERS_INI,
    stations_ini: str = STATION_INI,
) -> None:
    """Entry point after command-line parsing.  Drives the full analysis pipeline."""

    control: dict = {
        "enableXRA":      False,
        "enableFLA":      False,
        "HiQualLimit":    10,
        "enableINIUpdate": False,
        "nObservers":     0,
        "nEvents":        0,
        "nCorr":          0,
        "nImp":           [],
        "path":           "",
    }

    setup_default_directory(control)

    # GOES correlation
    if input("Use GOES Data Correlation? y/[n]: ").lower() == "y":
        control["enableXRA"] = control["enableFLA"] = True
        print("Using GOES data correlation\n")

    # High-quality limit
    raw = input(
        "Set Observer Minimum Quality Rating to include uncorrelated events\n"
        "reported by a single observer [10]: "
    )
    hi_qual = int(raw) if raw.isdigit() else 10
    if hi_qual == 0:
        if input("Type 'Y' to confirm Minimum Quality Rating of 0: ") != "Y":
            hi_qual = 10
    control["HiQualLimit"] = hi_qual
    print(f"Minimum Quality Rating: {hi_qual}\n")

    # Observer INI update
    if input(f"Update {observers_ini} file based on this analysis? y/[n]: ").lower() == "y":
        control["enableINIUpdate"] = True
        print(f"{observers_ini} will be updated.")

    # Report selection
    month_tag = control["month"].upper() + control["year"]
    print(
        f"\nThe program will generate DatabaseFullSumm.csv and SIDDatabase_{month_tag}.\n"
        "Use the numbers below to select additional reports (comma-separated list).\n"
        f"  1-SIDngdc_{month_tag}  2-SIDDatabaseFull_{month_tag}  "
        "3-SID_DatabaseFull_Sum  4-SID_Database_Sum  5-Observers Summary  *-All\n"
    )
    response = input("Enter your choices [none]: ").split(",")
    control["response"] = [r.strip() for r in response]

    # Select files
    files = get_files()
    if not files:
        print("No files selected. Exiting.")
        return

    observers = read_reports(files, control, observers_ini)

    xra = read_xra(control) if control["enableXRA"] else []
    fla = read_fla(control) if control["enableFLA"] else []

    # Correlation pipeline
    corr = correlate_observers(5, control, observers)
    corr = compare_observers_to_corr_list(15, control, observers, corr)

    if control["enableXRA"]:
        control["nCorr"] += compare_to_xra_fla(15, control, observers, corr, xra, XRA_CORRELATED)
    if control["enableFLA"]:
        control["nCorr"] += compare_to_xra_fla(15, control, observers, corr, fla, FLA_CORRELATED)

    compute_unused_observer_events(control, observers, control["enableINIUpdate"])

    if control["HiQualLimit"] < 10:
        control["nCorr"] += detect_hi_qual_non_correlated(control, observers, corr)

    corr = sorted(corr, key=cmp_to_key(sort_correlation_list))

    # Output
    generate_database_file(control, observers, corr, DB_PARTIAL)

    if "1" in response or "*" in response:
        generate_ngdc_file(control, observers)
    if "2" in response or "*" in response:
        generate_database_file(control, observers, corr, DB_FULL)
    if "5" in response or "*" in response:
        generate_file_of_unused_observer_events(control, observers)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process SID reports and generate correlation analysis output files."
    )
    parser.add_argument(
        "-d", "--directory",
        help="Path to root directory for analysis (default: current directory)",
    )
    parser.add_argument(
        "-o", "--observer",
        help=f"Path to Observer information file (default: {OBSERVERS_INI})",
    )
    parser.add_argument(
        "-s", "--station",
        help=f"Path to Station information file (default: {STATION_INI})",
    )
    args = parser.parse_args()

    path = os.path.expanduser(args.directory) if args.directory else os.getcwd()

    if os.path.isdir(path):
        if not (os.access(path, os.R_OK) and os.access(path, os.W_OK)):
            sys.exit(f"Check read/write access for {path}")
    else:
        print(f"Creating path {path}")
        os.makedirs(path, exist_ok=True)

    # Pass path into Control via a temporary global-ish approach (kept simple)
    _CONTROL_PATH = path

    obs_ini = os.path.expanduser(args.observer) if args.observer else OBSERVERS_INI
    sta_ini = os.path.expanduser(args.station)  if args.station  else STATION_INI

    # Patch the module-level default so setup_default_directory picks it up
    import types
    _mod = sys.modules[__name__]
    _orig_setup = setup_default_directory

    def _patched_setup(control, input_func=prompt_month_year):
        control["path"] = _CONTROL_PATH
        _orig_setup(control, input_func)

    _mod.setup_default_directory = _patched_setup

    sid_reporter(obs_ini, sta_ini)
