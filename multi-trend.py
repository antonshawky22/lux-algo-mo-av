print("EGX ALERTS - Phase 6: Compact Directional Alerts")

import yfinance as yf
import requests
import os
import json
import pandas as pd

# =====================
# Telegram settings
# =====================
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        print("Telegram credentials not set")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        print("Telegram send failed:", e)

# =====================
# EGX symbols
# =====================
symbols = {
    "OFH": "OFH.CA","OLFI": "OLFI.CA","EMFD": "EMFD.CA","ETEL": "ETEL.CA",
    "EAST": "EAST.CA","EFIH": "EFIH.CA","ABUK": "ABUK.CA","OIH": "OIH.CA",
    "SWDY": "SWDY.CA","ISPH": "ISPH.CA","ATQA": "ATQA.CA","MTIE": "MTIE.CA",
    "ELEC": "ELEC.CA","HRHO": "HRHO.CA","ORWE": "ORWE.CA","JUFO": "JUFO.CA",
    "DSCW": "DSCW.CA","SUGR": "SUGR.CA","ELSH": "ELSH.CA","RMDA": "RMDA.CA",
    "RAYA": "RAYA.CA","EEII": "EEII.CA","MPCO": "MPCO.CA","GBCO": "GBCO.CA",
    "TMGH": "TMGH.CA","ORHD": "ORHD.CA","AMOC": "AMOC.CA","FWRY": "FWRY.CA",
    "COMI": "COMI.CA","ADIB": "ADIB.CA","PHDC": "PHDC.CA",
    "EGTS": "EGTS.CA","MCQE": "MCQE.CA","SKPC": "SKPC.CA",
    "EGAL": "EGAL.CA"
}

# =====================
# Load last signals
# =====================
SIGNALS_FILE = "last_signals.json"
try:
    with open(SIGNALS_FILE, "r") as f:
        last_signals = json.load(f)
except:
    last_signals = {}

new_signals = last_signals.copy()
data_failures = []
last_candle_date = None

# =====================
# Helpers
# =====================
def fetch_data(ticker):
    try:
        df = yf.download(ticker, period="6mo", interval="1d", auto_adjust=True, progress=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except:
        return None

# =====================
# Parameters
# =====================
EMA_PERIOD = 60
LOOKBACK = 20
THRESHOLD = 0.60
EMA_FORCED_SELL = 25

# =====================
# Containers
# =====================
section_up = []            # صاعد ↗️
section_side = []          # عرضي 🔛
section_side_peaks = []    # قرب القمم
section_side_valleys = []  # قرب القيعان
section_down = []          # هابط 🔻

# =====================
# Main Logic
# =====================
for name, ticker in symbols.items():
    df = fetch_data(ticker)
    if df is None or len(df) < LOOKBACK:
        data_failures.append(name)
        continue

    last_candle_date = df.index[-1].date()

    df["EMA60"] = df["Close"].ewm(span=EMA_PERIOD, adjust=False).mean()
    df["EMA4"] = df["Close"].ewm(span=4, adjust=False).mean()
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA25"] = df["Close"].ewm(span=EMA_FORCED_SELL, adjust=False).mean()

    recent_closes = df["Close"].iloc[-LOOKBACK:]
    recent_ema = df["EMA60"].iloc[-LOOKBACK:]

    bullish_ratio = (recent_closes > recent_ema).sum() / LOOKBACK
    bearish_ratio = (recent_closes < recent_ema).sum() / LOOKBACK

    last_close = df["Close"].iloc[-1]
    prev_close = df["Close"].iloc[-2]
    last_ema4 = df["EMA4"].iloc[-1]
    last_ema9 = df["EMA9"].iloc[-1]
    prev_ema4 = df["EMA4"].iloc[-2]
    prev_ema9 = df["EMA9"].iloc[-2]

    buy_signal = sell_signal = False
    changed_mark = ""

    # =====================
    # Trend classification
    # =====================
    if bullish_ratio >= THRESHOLD:
        trend = "↗️"
        # EMA4/EMA9 simple strategy
        if prev_ema4 <= prev_ema9 and last_ema4 > last_ema9:
            buy_signal = True
        elif prev_ema4 >= prev_ema9 and last_ema4 < last_ema9:
            sell_signal = True

    elif bearish_ratio >= THRESHOLD:
        trend = "🔻"
        # no buy/sell for downtrend

    else:
        trend = "🔛"
        # Peaks and valleys 5%
        high_lookback = df["Close"].iloc[-EMA_PERIOD:]
        low_lookback = df["Close"].iloc[-EMA_PERIOD:]
        high_threshold = high_lookback.max() * 0.95
        low_threshold = low_lookback.min() * 1.05
        near_peak = last_close >= high_threshold
        near_valley = last_close <= low_threshold

        if near_peak:
            sell_signal = True
            section_side_peaks.append(f"{name} | {last_close:.2f} | {((last_close/high_lookback.max())*100):.2f}%")
        elif near_valley:
            buy_signal = True
            section_side_valleys.append(f"{name} | {last_close:.2f} | {((last_close/low_lookback.min())*100):.2f}%")

    # =====================
    # Track direction change
    # =====================
    prev_data = last_signals.get(name, {})
    prev_trend = prev_data.get("trend", "")
    if trend != prev_trend:
        changed_mark = "🚧"

    # =====================
    # Append to sections
    # =====================
    if trend == "↗️" and (buy_signal or sell_signal):
        signal_text = f"{changed_mark}{name} | {last_close:.2f}"
        signal_text += "|🟢BUY" if buy_signal else "|🔴SELL"
        section_up.append(signal_text)
    elif trend == "🔛":
        if sell_signal and near_peak:
            section_side.append(f"🔴{name} | {last_close:.2f} | {((last_close/high_lookback.max())*100):.2f}%")
        elif buy_signal and near_valley:
            section_side.append(f"🟢{name} | {last_close:.2f} | {((last_close/low_lookback.min())*100):.2f}%")
    elif trend == "🔻":
        section_down.append(f"{name} | {last_close:.2f}")

    # =====================
    # Update last signals
    # =====================
    new_signals[name] = {
        "last_signal": "BUY" if buy_signal else "SELL" if sell_signal else prev_data.get("last_signal",""),
        "trend": trend
    }

# =====================
# Compile compact message
# =====================
alerts = ["🚦 EGX Alerts (Compact):\n"]

if section_up:
    alerts.append("↗️ صاعد (شراء/بيع):")
    alerts.extend(["- " + s for s in section_up])
if section_side:
    alerts.append("\n🔛 عرضي (قمم/قيعان):")
    alerts.extend(["- " + s for s in section_side])
if section_down:
    alerts.append("\n🔻 هابط:")
    alerts.extend(["- " + s for s in section_down])

if data_failures:
    alerts.append("\n⚠️ Failed to fetch data:\n- " + "\n- ".join(data_failures))

# =====================
# Save & Notify
# =====================
with open(SIGNALS_FILE, "w") as f:
    json.dump(new_signals, f, indent=2, ensure_ascii=False)

if alerts:
    send_telegram("\n".join(alerts))
else:
    send_telegram(f"ℹ️ No new signals\nLast candle: {last_candle_date}")
