"""
Screener Saham -> scan banyak saham sekaligus, alert yang lolos kriteria.
----------------------------------------------------------------------------
Beda dari bot.py (watchlist): ini scan RATUSAN saham dari file universe,
lalu kirim RINGKASAN kandidat yang lolos kriteria (bukan 1 notif per saham).

Kriteria (diatur di config.json -> "screener"):
  - Top gainer / loser   : perubahan hari ini >= perubahan_persen_min
  - Lonjakan volume       : volume hari ini >= volume_vs_rata2_min x rata2 20 hari
  - RSI ekstrem           : RSI <= oversold  atau  RSI >= overbought
  - Golden / Death cross  : MA20 nyilang MA50

Data via yfinance batch download (efisien). Universe di folder universe/.

Jalanin: python screener.py
"""

import json
import os
import sys
import time

import pandas as pd
import yfinance as yf

import bot  # kirim_telegram(), format_harga(), hitung_rsi()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(__file__)
UNIVERSE_DIR = os.path.join(BASE, "universe")


def baca_universe(nama):
    """Baca file universe/<nama>.txt -> list ticker (skip komentar & kosong)."""
    path = os.path.join(UNIVERSE_DIR, f"{nama}.txt")
    if not os.path.exists(path):
        print(f"[WARN] Universe '{nama}' gak ada: {path}")
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            t = line.strip()
            if t and not t.startswith("#"):
                out.append(t)
    # buang duplikat, jaga urutan
    return list(dict.fromkeys(out))


def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def analisa_ticker(ticker, df):
    """Dari 1 DataFrame OHLCV -> metrik. Return dict atau None kalau data kurang."""
    try:
        closes = df["Close"].dropna()
        vols = df["Volume"].dropna()
        if len(closes) < 20:
            return None
        harga = float(closes.iloc[-1])
        prev = float(closes.iloc[-2])
        if prev <= 0:
            return None
        chg = (harga - prev) / prev * 100

        vol_now = float(vols.iloc[-1]) if len(vols) else 0.0
        vol_avg = float(vols.tail(20).mean()) if len(vols) >= 20 else 0.0
        vol_ratio = (vol_now / vol_avg) if vol_avg > 0 else 0.0

        rsi = bot.hitung_rsi(closes)

        ma20 = closes.rolling(20).mean()
        ma50 = closes.rolling(50).mean()
        cross = None
        if len(closes) >= 51:
            a, b = ma20.iloc[-1], ma50.iloc[-1]
            ap, bp = ma20.iloc[-2], ma50.iloc[-2]
            if pd.notna(a) and pd.notna(b) and pd.notna(ap) and pd.notna(bp):
                if ap <= bp and a > b:
                    cross = "golden"
                elif ap >= bp and a < b:
                    cross = "death"

        return {
            "ticker": ticker,
            "harga": harga,
            "chg": chg,
            "vol_ratio": vol_ratio,
            "rsi": rsi,
            "cross": cross,
        }
    except Exception:
        return None


def scan_universe(tickers, chunk_size, jeda):
    """Batch-download semua ticker, kembalikan list metrik per ticker."""
    hasil = []
    total = len(tickers)
    for idx, grup in enumerate(chunked(tickers, chunk_size), 1):
        print(f"  chunk {idx} ({len(grup)} ticker)...")
        try:
            data = yf.download(
                grup,
                period="3mo",
                interval="1d",
                group_by="ticker",
                threads=True,
                progress=False,
                auto_adjust=True,
            )
        except Exception as e:
            print(f"  [WARN] download chunk gagal: {e}")
            continue

        for t in grup:
            try:
                df = data[t] if len(grup) > 1 else data
            except (KeyError, TypeError):
                continue
            if df is None or df.empty:
                continue
            m = analisa_ticker(t, df)
            if m:
                hasil.append(m)
        time.sleep(jeda)
    print(f"  berhasil analisa {len(hasil)}/{total} ticker")
    return hasil


def bikin_laporan(hasil, kriteria, maxn):
    """Susun laporan Telegram dari hasil scan."""
    naik_min = kriteria.get("perubahan_persen_min", 5.0)
    vol_min = kriteria.get("volume_vs_rata2_min", 2.0)
    ob = kriteria.get("rsi_overbought", 70)
    os_ = kriteria.get("rsi_oversold", 30)

    gainers = sorted(
        [h for h in hasil if h["chg"] >= naik_min],
        key=lambda x: x["chg"], reverse=True,
    )[:maxn]
    losers = sorted(
        [h for h in hasil if h["chg"] <= -naik_min],
        key=lambda x: x["chg"],
    )[:maxn]
    vol_spike = sorted(
        [h for h in hasil if h["vol_ratio"] >= vol_min],
        key=lambda x: x["vol_ratio"], reverse=True,
    )[:maxn]
    overbought = sorted(
        [h for h in hasil if h["rsi"] is not None and h["rsi"] >= ob],
        key=lambda x: x["rsi"], reverse=True,
    )[:maxn]
    oversold = sorted(
        [h for h in hasil if h["rsi"] is not None and h["rsi"] <= os_],
        key=lambda x: x["rsi"],
    )[:maxn]
    golden = [h for h in hasil if h["cross"] == "golden"][:maxn]
    death = [h for h in hasil if h["cross"] == "death"][:maxn]

    def baris_chg(h):
        return f"  {h['ticker']}  {bot.format_harga(h['harga'])}  ({h['chg']:+.1f}%)"

    def baris_vol(h):
        return f"  {h['ticker']}  {h['vol_ratio']:.1f}x vol  ({h['chg']:+.1f}%)"

    def baris_rsi(h):
        return f"  {h['ticker']}  RSI {h['rsi']:.0f}  ({h['chg']:+.1f}%)"

    def baris_cross(h):
        return f"  {h['ticker']}  {bot.format_harga(h['harga'])}"

    seksi = []
    if gainers:
        seksi.append("📈 <b>Top Gainer</b>\n" + "\n".join(baris_chg(h) for h in gainers))
    if losers:
        seksi.append("📉 <b>Top Loser</b>\n" + "\n".join(baris_chg(h) for h in losers))
    if vol_spike:
        seksi.append("🔊 <b>Lonjakan Volume</b>\n" + "\n".join(baris_vol(h) for h in vol_spike))
    if oversold:
        seksi.append("💡 <b>RSI Oversold</b>\n" + "\n".join(baris_rsi(h) for h in oversold))
    if overbought:
        seksi.append("⚠️ <b>RSI Overbought</b>\n" + "\n".join(baris_rsi(h) for h in overbought))
    if golden:
        seksi.append("✨ <b>Golden Cross</b>\n" + "\n".join(baris_cross(h) for h in golden))
    if death:
        seksi.append("💀 <b>Death Cross</b>\n" + "\n".join(baris_cross(h) for h in death))

    return seksi


def kirim_laporan_panjang(judul, seksi):
    """Kirim ke Telegram, pecah kalau kepanjangan (limit 4096 char)."""
    if not seksi:
        bot.kirim_telegram(f"{judul}\n\nGak ada saham yang lolos kriteria saat ini.")
        return
    pesan = judul + "\n\n" + "\n\n".join(seksi)
    # Pecah per ~3500 char di batas seksi biar aman
    if len(pesan) <= 3500:
        bot.kirim_telegram(pesan)
        return
    buff = judul
    for s in seksi:
        if len(buff) + len(s) + 2 > 3500:
            bot.kirim_telegram(buff)
            buff = ""
        buff += ("\n\n" if buff else "") + s
    if buff:
        bot.kirim_telegram(buff)


def main():
    config = bot.load_config()
    scr = config.get("screener", {})
    if not scr.get("aktif", False):
        print("[INFO] Screener nonaktif di config.")
        return

    universe = scr.get("universe", ["idx"])
    kriteria = scr.get("kriteria", {})
    maxn = scr.get("max_hasil_per_kategori", 15)
    chunk_size = scr.get("chunk_size", 100)
    jeda = scr.get("jeda_antar_chunk_detik", 2)

    tickers = []
    for u in universe:
        t = baca_universe(u)
        print(f"Universe '{u}': {len(t)} ticker")
        tickers += t
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        print("[ERROR] Universe kosong.")
        return

    print(f"Mulai scan {len(tickers)} saham...")
    t0 = time.time()
    hasil = scan_universe(tickers, chunk_size, jeda)
    durasi = time.time() - t0

    from datetime import datetime
    judul = (
        f"🔎 <b>Hasil Screener</b> — {datetime.now():%d %b %Y %H:%M}\n"
        f"Scan {len(hasil)} saham ({durasi:.0f}s)"
    )
    seksi = bikin_laporan(hasil, kriteria, maxn)
    kirim_laporan_panjang(judul, seksi)
    print("[OK] Screener selesai, laporan terkirim.")


if __name__ == "__main__":
    main()
