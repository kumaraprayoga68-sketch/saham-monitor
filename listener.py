"""
Listener Telegram (mode cron / GitHub Actions)
----------------------------------------------
Ngecek pesan masuk lewat getUpdates, balas command, lalu keluar.
Karena jalan via cron (bukan nyala-terus), balasan bisa delay sampai
seinterval cron (default 5 menit di GitHub Actions).

Command yang didukung:
  /start, /help         -> bantuan
  /harga <TICKER>       -> harga terkini + perubahan (mis. /harga BBCA.JK)
  /list                 -> tampilkan watchlist dari config.json

Keamanan: cuma bales pesan dari TELEGRAM_CHAT_ID (pemilik). Pesan orang
lain diabaikan biar bot gak disalahgunakan.

Jalanin: python listener.py   (atau otomatis lewat .github/workflows/listener.yml)
"""

import json
import os
import sys

import requests
from dotenv import load_dotenv

import bot  # pakai ambil_data(), format_harga(), load_config()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OFFSET_PATH = os.path.join(os.path.dirname(__file__), "tg_offset.json")

BANTUAN = (
    "🤖 <b>Bot Pemantau Saham</b>\n\n"
    "Command yang bisa dipakai:\n"
    "• <code>/harga BBCA.JK</code> — harga terkini + perubahan\n"
    "• <code>/list</code> — daftar saham yang dipantau\n"
    "• <code>/help</code> — bantuan ini\n\n"
    "Kode ticker: IDX pakai <code>.JK</code> (BBCA.JK), US polos (AAPL), "
    "crypto <code>-USD</code> (BTC-USD)."
)


def kirim(chat_id, teks):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": chat_id, "text": teks, "parse_mode": "HTML"},
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"[ERROR] gagal kirim: {e}")


def load_offset():
    try:
        with open(OFFSET_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("offset", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0


def save_offset(offset):
    with open(OFFSET_PATH, "w", encoding="utf-8") as f:
        json.dump({"offset": offset}, f)


def handle_harga(chat_id, args):
    if not args:
        kirim(chat_id, "Formatnya: <code>/harga BBCA.JK</code>")
        return
    ticker = args[0].upper()
    kirim(chat_id, f"⏳ Ngambil harga {ticker}...")
    data = bot.ambil_data(ticker)
    if not data:
        kirim(chat_id, f"❌ Ticker <b>{ticker}</b> gak ketemu / data kosong. Cek lagi kodenya.")
        return
    arah = "🟢" if data["perubahan_persen"] >= 0 else "🔴"
    teks = (
        f"{arah} <b>{ticker}</b>\n"
        f"Harga: {bot.format_harga(data['harga'])}\n"
        f"Perubahan: {data['perubahan_persen']:+.2f}% (vs kemarin)"
    )
    if data.get("rsi") is not None:
        teks += f"\nRSI: {data['rsi']:.0f}"
    kirim(chat_id, teks)


def handle_list(chat_id):
    try:
        cfg = bot.load_config()
    except Exception:
        kirim(chat_id, "❌ Gagal baca config.")
        return
    baris = ["📋 <b>Watchlist:</b>"]
    for it in cfg.get("watchlist", []):
        baris.append(f"• {it.get('name', it['ticker'])} (<code>{it['ticker']}</code>)")
    kirim(chat_id, "\n".join(baris) if len(baris) > 1 else "Watchlist kosong.")


def proses_pesan(msg):
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    teks = (msg.get("text") or "").strip()

    # Keamanan: cuma layani pemilik
    if OWNER_CHAT_ID and str(chat_id) != str(OWNER_CHAT_ID):
        print(f"[SKIP] pesan dari chat {chat_id} (bukan owner)")
        return
    if not teks:
        return

    bagian = teks.split()
    cmd = bagian[0].lower().split("@")[0]  # buang @namabot kalau ada
    args = bagian[1:]

    if cmd in ("/start", "/help"):
        kirim(chat_id, BANTUAN)
    elif cmd == "/harga":
        handle_harga(chat_id, args)
    elif cmd == "/list":
        handle_list(chat_id)
    else:
        kirim(chat_id, "Command gak dikenal. Ketik /help buat lihat daftarnya.")


def main():
    if not TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN belum diisi.")
        return
    offset = load_offset()
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TOKEN}/getUpdates",
            params={"offset": offset, "timeout": 0},
            timeout=30,
        )
        updates = r.json().get("result", [])
    except Exception as e:
        print(f"[ERROR] getUpdates gagal: {e}")
        return

    if not updates:
        print("[OK] Gak ada pesan baru.")
        return

    for up in updates:
        offset = max(offset, up["update_id"] + 1)
        msg = up.get("message") or up.get("edited_message")
        if msg:
            proses_pesan(msg)

    save_offset(offset)
    print(f"[OK] Proses {len(updates)} update. Offset baru: {offset}")


if __name__ == "__main__":
    main()
