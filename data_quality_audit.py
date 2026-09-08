import json
import os
import math
from datetime import datetime

# ============================================================
# EGX DATA QUALITY AUDIT
# Full-history audit for Yahoo Finance + TradingView database
#
# INPUT:
#   egx_history_database_v2.json
#
# OUTPUT:
#   egx_history_database_clean.json
#   corporate_actions_audit.json
#
# IMPORTANT:
# This version DOES NOT modify prices automatically.
# It only detects and reports suspicious events.
# ============================================================

INPUT_FILE = "egx_history_database_v2.json"

CLEAN_FILE = "egx_history_database_clean.json"
AUDIT_FILE = "corporate_actions_audit.json"

# ------------------------------------------------------------
# Detection thresholds
# ------------------------------------------------------------

# Very large daily movement
LARGE_MOVE_PERCENT = 20.0

# Possible corporate-action ratios
# Examples:
# 0.50  -> 2:1 split / bonus-like adjustment
# 0.333 -> 3:1
# 0.25  -> 4:1
# 2.00  -> reverse split / adjustment
# 3.00  -> reverse split
# 4.00  -> reverse split
CORPORATE_RATIOS = [
    0.25,
    0.333,
    0.50,
    0.667,
    1.50,
    2.00,
    3.00,
    4.00,
]

RATIO_TOLERANCE = 0.035

# Volume jump detection
VOLUME_JUMP_MULTIPLIER = 5.0

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def safe_float(value):
    try:
        value = float(value)

        if math.isnan(value) or math.isinf(value):
            return None

        return value

    except (TypeError, ValueError):
        return None


def percent_change(old, new):
    if old is None or old == 0 or new is None:
        return None

    return ((new - old) / old) * 100.0


def closest_corporate_ratio(ratio):

    if ratio is None or ratio <= 0:
        return None

    best_ratio = None
    best_distance = float("inf")

    for target in CORPORATE_RATIOS:

        distance = abs(ratio - target)

        if distance < best_distance:
            best_distance = distance
            best_ratio = target

    if best_distance <= RATIO_TOLERANCE:
        return {
            "target_ratio": best_ratio,
            "distance": best_distance,
        }

    return None


def classify_ratio(ratio):

    if ratio is None:
        return "UNKNOWN"

    if abs(ratio - 0.50) <= RATIO_TOLERANCE:
        return "POSSIBLE_2_FOR_1_SPLIT_BONUS"

    if abs(ratio - 0.333) <= RATIO_TOLERANCE:
        return "POSSIBLE_3_FOR_1_SPLIT_BONUS"

    if abs(ratio - 0.25) <= RATIO_TOLERANCE:
        return "POSSIBLE_4_FOR_1_SPLIT_BONUS"

    if abs(ratio - 0.667) <= RATIO_TOLERANCE:
        return "POSSIBLE_3_FOR_2_SPLIT_BONUS"

    if abs(ratio - 2.0) <= RATIO_TOLERANCE:
        return "POSSIBLE_REVERSE_SPLIT_2_FOR_1"

    if abs(ratio - 3.0) <= RATIO_TOLERANCE:
        return "POSSIBLE_REVERSE_SPLIT_3_FOR_1"

    if abs(ratio - 4.0) <= RATIO_TOLERANCE:
        return "POSSIBLE_REVERSE_SPLIT_4_FOR_1"

    return "LARGE_PRICE_MOVE"


# ------------------------------------------------------------
# Load database
# ------------------------------------------------------------

print("=" * 80)
print("EGX DATA QUALITY AUDIT")
print("=" * 80)

if not os.path.exists(INPUT_FILE):
    raise FileNotFoundError(
        f"Input database not found: {INPUT_FILE}"
    )

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    database = json.load(f)

print(f"Input file: {INPUT_FILE}")
print(f"Symbols found: {len(database)}")
print()


# ------------------------------------------------------------
# Audit
# ------------------------------------------------------------

audit = {
    "audit_info": {
        "created_at": datetime.utcnow().isoformat() + "Z",
        "input_file": INPUT_FILE,
        "large_move_threshold_percent": LARGE_MOVE_PERCENT,
        "ratio_tolerance": RATIO_TOLERANCE,
        "corporate_ratios_checked": CORPORATE_RATIOS,
        "prices_modified": False,
    },
    "summary": {
        "total_symbols": len(database),
        "symbols_with_events": 0,
        "total_events": 0,
        "possible_corporate_actions": 0,
        "large_price_moves": 0,
        "ohlc_errors": 0,
        "volume_anomalies": 0,
    },
    "symbols": {},
}


for symbol, stock in database.items():

    data = stock.get("data", {})

    if not isinstance(data, dict):
        continue

    # --------------------------------------------------------
    # Sort from oldest to newest
    # --------------------------------------------------------

    dates = sorted(data.keys())

    symbol_events = []

    previous_date = None
    previous_row = None

    for date in dates:

        row = data.get(date, {})

        if not isinstance(row, dict):
            continue

        open_price = safe_float(row.get("Open"))
        high_price = safe_float(row.get("High"))
        low_price = safe_float(row.get("Low"))
        close_price = safe_float(row.get("Close"))
        volume = safe_float(row.get("Volume"))

        # ----------------------------------------------------
        # OHLC integrity
        # ----------------------------------------------------

        if (
            open_price is not None
            and high_price is not None
            and low_price is not None
            and close_price is not None
        ):

            ohlc_error = False

            if high_price < low_price:
                ohlc_error = True

            if high_price < open_price:
                ohlc_error = True

            if high_price < close_price:
                ohlc_error = True

            if low_price > open_price:
                ohlc_error = True

            if low_price > close_price:
                ohlc_error = True

            if ohlc_error:

                event = {
                    "date": date,
                    "type": "OHLC_INTEGRITY_ERROR",
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                }

                symbol_events.append(event)

                audit["summary"]["ohlc_errors"] += 1

        # ----------------------------------------------------
        # Compare with previous day
        # ----------------------------------------------------

        if (
            previous_row is not None
            and previous_date is not None
        ):

            previous_close = safe_float(
                previous_row.get("Close")
            )

            if (
                previous_close is not None
                and close_price is not None
                and previous_close > 0
            ):

                ratio = close_price / previous_close

                move_percent = (
                    (ratio - 1.0) * 100.0
                )

                # ------------------------------------------------
                # Large movement
                # ------------------------------------------------

                if abs(move_percent) >= LARGE_MOVE_PERCENT:

                    ratio_match = closest_corporate_ratio(
                        ratio
                    )

                    if ratio_match:

                        event_type = classify_ratio(
                            ratio
                        )

                        confidence = "HIGH"

                        audit["summary"][
                            "possible_corporate_actions"
                        ] += 1

                    else:

                        event_type = "LARGE_PRICE_MOVE"

                        confidence = "LOW"

                        audit["summary"][
                            "large_price_moves"
                        ] += 1

                    event = {
                        "date": date,
                        "previous_date": previous_date,
                        "type": event_type,
                        "confidence": confidence,

                        "previous_close": previous_close,
                        "current_close": close_price,

                        "ratio": round(ratio, 6),
                        "move_percent": round(
                            move_percent,
                            2
                        ),

                        "open": open_price,
                        "high": high_price,
                        "low": low_price,
                        "close": close_price,
                        "volume": volume,
                    }

                    if ratio_match:

                        event[
                            "matched_ratio"
                        ] = ratio_match[
                            "target_ratio"
                        ]

                        event[
                            "ratio_distance"
                        ] = round(
                            ratio_match[
                                "distance"
                            ],
                            6
                        )

                    symbol_events.append(event)

                # ------------------------------------------------
                # Volume anomaly
                # ------------------------------------------------

                previous_volume = safe_float(
                    previous_row.get("Volume")
                )

                if (
                    previous_volume is not None
                    and previous_volume > 0
                    and volume is not None
                ):

                    volume_ratio = (
                        volume /
                        previous_volume
                    )

                    if (
                        volume_ratio >=
                        VOLUME_JUMP_MULTIPLIER
                    ):

                        event = {
                            "date": date,
                            "previous_date": previous_date,
                            "type": "VOLUME_SPIKE",

                            "previous_volume":
                                previous_volume,

                            "current_volume":
                                volume,

                            "volume_ratio":
                                round(
                                    volume_ratio,
                                    2
                                ),

                            "previous_close":
                                previous_close,

                            "current_close":
                                close_price,
                        }

                        symbol_events.append(event)

                        audit["summary"][
                            "volume_anomalies"
                        ] += 1

        previous_date = date
        previous_row = row

    # --------------------------------------------------------
    # Save symbol audit
    # --------------------------------------------------------

    if symbol_events:

        audit["summary"][
            "symbols_with_events"
        ] += 1

        audit["summary"][
            "total_events"
        ] += len(symbol_events)

        audit["symbols"][symbol] = {
            "first_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None,
            "total_days": len(dates),
            "events_count": len(symbol_events),
            "events": symbol_events,
        }


# ------------------------------------------------------------
# Save audit report
# ------------------------------------------------------------

with open(
    AUDIT_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        audit,
        f,
        ensure_ascii=False,
        indent=2
    )


# ------------------------------------------------------------
# Create CLEAN COPY
#
# IMPORTANT:
# No prices are changed in this first version.
# ------------------------------------------------------------

with open(
    CLEAN_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        database,
        f,
        ensure_ascii=False,
        indent=2
    )


# ------------------------------------------------------------
# Console summary
# ------------------------------------------------------------

print("=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)

print(
    f"Total symbols              : "
    f"{audit['summary']['total_symbols']}"
)

print(
    f"Symbols with events        : "
    f"{audit['summary']['symbols_with_events']}"
)

print(
    f"Total events               : "
    f"{audit['summary']['total_events']}"
)

print(
    f"Possible corporate actions : "
    f"{audit['summary']['possible_corporate_actions']}"
)

print(
    f"Large price moves          : "
    f"{audit['summary']['large_price_moves']}"
)

print(
    f"OHLC errors                : "
    f"{audit['summary']['ohlc_errors']}"
)

print(
    f"Volume anomalies           : "
    f"{audit['summary']['volume_anomalies']}"
)

print()

print("Files created:")

print(f"  - {CLEAN_FILE}")
print(f"  - {AUDIT_FILE}")

print()

print(
    "IMPORTANT: "
    "No prices were modified."
)

print(
    "The CLEAN file is currently an identical copy "
    "of the original database."
)

print("=" * 80)


# ------------------------------------------------------------
# Print suspicious symbols
# ------------------------------------------------------------

if audit["symbols"]:

    print()
    print("SYMBOLS REQUIRING REVIEW")
    print("-" * 80)

    for symbol, info in audit["symbols"].items():

        print(
            f"{symbol:8} | "
            f"{info['events_count']:3} events | "
            f"{info['first_date']} -> "
            f"{info['last_date']}"
        )

else:

    print()
    print("No suspicious events detected.")
