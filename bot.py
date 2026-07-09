"""
Bot Pemantau Saham -> Notifikasi Telegram
------------------------------------------
Sumber data : Yahoo Finance (yfinance) -> support IDX (.JK), saham US, crypto (-USD)
Notifikasi  : Telegram
Fitur alert : batas harga, perubahan %, update rutin, indikator teknikal (RSI + MA cross)

Jalanin: python bot.py
Konfigurasi ticker & aturan ada di config.json
Rahasia (token & chat_id) ada di .env
"""

import json
import os
import sys
import time
from datetime import datetime

# Windows console kadang cp1252 -> paksa UTF-8 biar emoji gak error saat print
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import requests
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

# Simpan status alert terakhir biar gak spam kirim pesan yang sama terus.
_alert_terakhir = {}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def kirim_telegram(pesan: str):
    """Kirim pesan ke Telegram. Return True kalau sukses."""
    if not TOKEN or not CHAT_ID:
        print("[ERROR] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diisi di .env")
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": pesan, "parse_mode": "HTML"},
            timeout=15,
        )
        return r.ok
    except requests.RequestException as e:
        print(f"[ERROR] Gagal kirim Telegram: {e}")
        return False


def hitung_rsi(closes, period: int = 14):
    """RSI sederhana. closes = pandas Series harga penutupan."""
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    if len(rsi.dropna()) == 0:
        return None
    return float(rsi.iloc[-1])


def ambil_data(ticker: str):
    """Ambil harga terkini + histori buat indikator. Return dict atau None."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="3mo", interval="1d")
        if hist.empty:
            print(f"[WARN] Data kosong untuk {ticker}")
            return None

        closes = hist["Close"].dropna()
        harga_now = float(closes.iloc[-1])
        harga_kemarin = float(closes.iloc[-2]) if len(closes) >= 2 else harga_now
        perubahan_persen = ((harga_now - harga_kemarin) / harga_kemarin) * 100

        ma20 = float(closes.rolling(20).mean().iloc[-1]) if len(closes) >= 20 else None
        ma50 = float(closes.rolling(50).mean().iloc[-1]) if len(closes) >= 50 else None
        # MA cross butuh nilai kemarin buat deteksi persilangan
        ma20_prev = float(closes.rolling(20).mean().iloc[-2]) if len(closes) >= 21 else None
        ma50_prev = float(closes.rolling(50).mean().iloc[-2]) if len(closes) >= 51 else None

        return {
            "harga": harga_now,
            "perubahan_persen": perubahan_persen,
            "rsi": hitung_rsi(closes),
            "ma20": ma20,
            "ma50": ma50,
            "ma20_prev": ma20_prev,
            "ma50_prev": ma50_prev,
        }
    except Exception as e:
        print(f"[ERROR] Gagal ambil data {ticker}: {e}")
        return None


def format_harga(x: float) -> str:
    if x >= 1000:
        return f"{x:,.0f}"
    return f"{x:,.2f}"


def cek_alert(item, data, fitur):
    """Kembalikan list pesan alert untuk satu saham."""
    pesan = []
    ticker = item["ticker"]
    nama = item.get("name", ticker)
    harga = data["harga"]
    key = ticker

    state = _alert_terakhir.setdefault(key, {})

    # 1) Batas harga
    batas_atas = item.get("batas_atas")
    batas_bawah = item.get("batas_bawah")
    if batas_atas is not None and harga >= batas_atas:
        if state.get("batas") != "atas":
            pesan.append(
                f"🔼 <b>{nama}</b> ({ticker}) tembus batas atas!\n"
                f"Harga: {format_harga(harga)} (batas: {format_harga(batas_atas)})"
            )
            state["batas"] = "atas"
    elif batas_bawah is not None and harga <= batas_bawah:
        if state.get("batas") != "bawah":
            pesan.append(
                f"🔽 <b>{nama}</b> ({ticker}) tembus batas bawah!\n"
                f"Harga: {format_harga(harga)} (batas: {format_harga(batas_bawah)})"
            )
            state["batas"] = "bawah"
    else:
        state["batas"] = None  # reset kalau balik ke rentang normal

    # 2) Perubahan persen
    ambang = item.get("alert_perubahan_persen")
    if ambang is not None and abs(data["perubahan_persen"]) >= ambang:
        arah = "naik" if data["perubahan_persen"] > 0 else "turun"
        emoji = "📈" if data["perubahan_persen"] > 0 else "📉"
        # kirim sekali per arah per hari biar gak spam
        tanda = f"{arah}-{datetime.now().date()}"
        if state.get("persen") != tanda:
            pesan.append(
                f"{emoji} <b>{nama}</b> ({ticker}) {arah} "
                f"{abs(data['perubahan_persen']):.2f}% hari ini.\n"
                f"Harga: {format_harga(harga)}"
            )
            state["persen"] = tanda

    # 3) Indikator teknikal
    if fitur.get("indikator_teknikal"):
        rsi = data.get("rsi")
        if rsi is not None:
            ob = fitur.get("rsi_overbought", 70)
            os_ = fitur.get("rsi_oversold", 30)
            if rsi >= ob and state.get("rsi") != "ob":
                pesan.append(
                    f"⚠️ <b>{nama}</b> ({ticker}) RSI {rsi:.0f} (overbought). "
                    f"Potensi jenuh beli."
                )
                state["rsi"] = "ob"
            elif rsi <= os_ and state.get("rsi") != "os":
                pesan.append(
                    f"💡 <b>{nama}</b> ({ticker}) RSI {rsi:.0f} (oversold). "
                    f"Potensi jenuh jual."
                )
                state["rsi"] = "os"
            elif os_ < rsi < ob:
                state["rsi"] = None

        # MA cross (golden/death cross)
        a, b = data.get("ma20"), data.get("ma50")
        ap, bp = data.get("ma20_prev"), data.get("ma50_prev")
        if None not in (a, b, ap, bp):
            if ap <= bp and a > b and state.get("cross") != "golden":
                pesan.append(
                    f"✨ <b>{nama}</b> ({ticker}) GOLDEN CROSS (MA20 > MA50). Sinyal bullish."
                )
                state["cross"] = "golden"
            elif ap >= bp and a < b and state.get("cross") != "death":
                pesan.append(
                    f"💀 <b>{nama}</b> ({ticker}) DEATH CROSS (MA20 < MA50). Sinyal bearish."
                )
                state["cross"] = "death"

    return pesan


def ringkasan_rutin(config, hasil):
    """Bikin satu pesan ringkasan semua saham."""
    baris = [f"📊 <b>Update Saham</b> — {datetime.now():%d %b %Y %H:%M}"]
    for item in config["watchlist"]:
        data = hasil.get(item["ticker"])
        if not data:
            baris.append(f"• {item.get('name', item['ticker'])}: (data gagal)")
            continue
        arah = "🟢" if data["perubahan_persen"] >= 0 else "🔴"
        baris.append(
            f"{arah} <b>{item.get('name', item['ticker'])}</b>: "
            f"{format_harga(data['harga'])} "
            f"({data['perubahan_persen']:+.2f}%)"
        )
    return "\n".join(baris)


def satu_putaran(config):
    fitur = config.get("fitur", {})
    hasil = {}
    for item in config["watchlist"]:
        data = ambil_data(item["ticker"])
        if data is None:
            continue
        hasil[item["ticker"]] = data
        for pesan in cek_alert(item, data, fitur):
            print(f"[ALERT] {pesan}")
            kirim_telegram(pesan)
        time.sleep(1)  # jeda kecil biar sopan ke Yahoo

    if fitur.get("update_rutin") and hasil:
        kirim_telegram(ringkasan_rutin(config, hasil))


def main():
    config = load_config()
    interval = config.get("interval_minutes", 15)
    print(f"Bot jalan. Cek tiap {interval} menit. Ctrl+C buat stop.")
    kirim_telegram(
        f"🤖 Bot pemantau saham AKTIF.\n"
        f"Memantau {len(config['watchlist'])} saham tiap {interval} menit."
    )
    while True:
        try:
            config = load_config()  # reload biar bisa edit config tanpa restart
            satu_putaran(config)
        except KeyboardInterrupt:
            print("\nBot dihentikan.")
            kirim_telegram("🛑 Bot pemantau saham dimatikan.")
            break
        except Exception as e:
            print(f"[ERROR] Putaran gagal: {e}")
        time.sleep(config.get("interval_minutes", 15) * 60)


if __name__ == "__main__":
    main()
