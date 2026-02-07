print("EGX ALERTS - Safe Support/Resistance + RSI14 Sell + StopLoss Strategy + Updated Trends")

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
alerts = []
data_failures = []
last_candle_date = None

# =====================
# Helpers
# =====================
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def fetch_data(ticker):
    try:
        df = yf.download(
            ticker,
            period="6mo",
            interval="1d",
            auto_adjust=True,
            progress=False
        )
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except:
        return None

# =====================
# Trend determination
# =====================
def is_downtrend(last):
    # EMA 25,35,45,55
    ema25 = last["EMA25"]
    ema35 = last["EMA35"]
    ema45 = last["EMA45"]
    ema55 = last["EMA55"]
    price = last["Close"]

    if ema55 > ema45 > ema35 and price < ema25 and price < ema35:
        return True
    return False

def is_uptrend(last):
    ema25 = last["EMA25"]
    ema35 = last["EMA35"]
    price = last["Close"]
    prev_price = last["Close_prev"]

    if ema25 > ema35 and price > ema35 and prev_price > ema35:
        return True
    return False

# -------------------------------
# Uptrend signals
# -------------------------------
def uptrend_signals(last):
    price = last["Close"]
    ema4 = last["EMA4"]
    ema9 = last["EMA9"]
    ema3 = last["EMA3"]
    ema5 = last["EMA5"]
    ema25 = last["EMA25"]
    rsi14 = last["RSI14"]

    # شراء: EMA4 يساوي EMA9 أو يتقاطع لأعلى
    prev_ema4 = last["EMA4_prev"]
    prev_ema9 = last["EMA9_prev"]
    buy_signal = (ema4 >= ema9) or (prev_ema4 < prev_ema9 and ema4 > ema9)

    # بيع
    sell_signal = ema3 < ema5 or price < ema25 or rsi14 >= 85

    return buy_signal, sell_signal

# -------------------------------
# Sideways signals
# -------------------------------
TOLERANCE = 0.01  # 1%
STOP_LOSS = 0.02  # 2% كسر الدعم لوقف الخسارة
MIN_CANDLES_RESISTANCE = 4

def sideways_signals(df):
    last_30_close = df["Close"].tail(30)
    last_30_high = df["High"].tail(30)
    last_30_low = df["Low"].tail(30)
    current_price = last_30_close.iloc[-1]

    SUPPORT = last_30_low.min()
    RESISTANCE = last_30_high.max()

    buy_signal = current_price <= SUPPORT * (1 + TOLERANCE)
    sell_signal = current_price >= RESISTANCE * (1 - TOLERANCE) or current_price >= RESISTANCE * (1 - 0.02)

    stop_loss_signal = current_price < SUPPORT * (1 - STOP_LOSS)
    if stop_loss_signal:
        sell_signal = True

    return buy_signal, sell_signal, SUPPORT, RESISTANCE

# =====================
# Main loop
# =====================
N = 60  # last N days for support/resistance

for name, ticker in symbols.items():
    df = fetch_data(ticker)
    if df is None or len(df) < N:
        data_failures.append(name)
        continue

    last_candle_date = df.index[-1].date()

    # حفظ الشمعة السابقة
    df["Close_prev"] = df["Close"].shift(1)
    df["EMA4_prev"] = df["Close"].ewm(span=4, adjust=False).mean().shift(1)
    df["EMA9_prev"] = df["Close"].ewm(span=9, adjust=False).mean().shift(1)

    # EMA calculation
    df["EMA4"] = df["Close"].ewm(span=4, adjust=False).mean()
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA25"] = df["Close"].ewm(span=25, adjust=False).mean()
    df["EMA35"] = df["Close"].ewm(span=35, adjust=False).mean()
    df["EMA45"] = df["Close"].ewm(span=45, adjust=False).mean()
    df["EMA55"] = df["Close"].ewm(span=55, adjust=False).mean()

    # RSI14
    df["RSI14"] = rsi(df["Close"], 14)

    last = df.iloc[-1]

    # =====================
    # Determine trend & signals
    # =====================
    if is_downtrend(last):
        trend_type = "⚪ اتجاه هابط – تجاهل السهم"
        buy_signal = False
        sell_signal = False
        support = None
        resistance = None

    elif is_uptrend(last):
        trend_type = "🟢 ترند صاعد"
        buy_signal, sell_signal = uptrend_signals(last)
        support = None
        resistance = None

    else:
        trend_type = "🟡 اتجاه عرضي"
        buy_signal, sell_signal, support, resistance = sideways_signals(df)

    # =====================
    # Prepare alert
    # =====================
    prev_state = last_signals.get(name, {}).get("last_signal")

    if buy_signal and prev_state != "BUY":
        reason = ""
        if trend_type == "🟢 ترند صاعد":
            reason = f"EMA4 >= EMA9 touched/cross"
        else:
            reason = f"Near support ({support:.2f})"
        alerts.append(f"🟢 BUY | {name} | {last['Close']:.2f} | {last_candle_date} | Reason: {reason}")
        new_signals[name] = {
            "support": round(support, 2) if support else None,
            "resistance": round(resistance, 2) if resistance else None,
            "last_signal": "BUY"
        }

    elif sell_signal and prev_state != "SELL":
        if trend_type == "🟢 ترند صاعد":
            if last["Close"] < last["EMA25"]:
                reason = f"Price < EMA25"
            elif last["RSI14"] >= 85:
                reason = f"RSI14 >= 85"
            else:
                reason = "EMA3 < EMA5"
        else:
            if last["Close"] < support * (1 - STOP_LOSS):
                reason = f"Stop Loss - broke support ({support:.2f})"
            else:
                reason = f"Near resistance ({resistance:.2f})"

        alerts.append(f"🔴 SELL | {name} | {last['Close']:.2f} | {last_candle_date} | Reason: {reason}")
        new_signals[name] = {
            "support": round(support, 2) if support else None,
            "resistance": round(resistance, 2) if resistance else None,
            "last_signal": "SELL"
        }

# =====================
# Data failure alert
# =====================
if data_failures:
    alerts.append("⚠️ Failed to fetch data: " + ", ".join(data_failures))

# =====================
# Save signals
# =====================
with open(SIGNALS_FILE, "w") as f:
    json.dump(new_signals, f, indent=2)

# =====================
# Telegram output
# =====================
if alerts:
    send_telegram("🚦 EGX Alerts 2:\n\n" + "\n".join(alerts))
else:
    send_telegram(f"egx alerts 2 ℹ️ No new signals\nLast candle: {last_candle_date}")
