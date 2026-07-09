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
    "<b>Info:</b>\n"
    "• <code>/harga BBCA.JK</code> — harga terkini + perubahan\n"
    "• <code>/list</code> — daftar saham watchlist\n"
    "• <code>/scan</code> — jalanin screener sekarang\n\n"
    "<b>Kelola watchlist:</b>\n"
    "• <code>/tambah BBRI.JK 6000 4000</code> — pantau saham (batas atas, batas bawah opsional)\n"
    "• <code>/hapus BBRI.JK</code> — berhenti pantau\n\n"
    "<b>Kelola screener:</b>\n"
    "• <code>/scanadd ANTM.JK</code> — tambah ke daftar scan massal\n"
    "• <code>/scandel ANTM.JK</code> — hapus dari daftar scan\n"
    "• <code>/set gap 5</code> — ubah kriteria (naik/volume/gap/rsi_ob/rsi_os/sinyal)\n\n"
    "Ticker: IDX pakai <code>.JK</code>, US polos (AAPL), crypto <code>-USD</code>.\n"
    "<i>Perubahan disimpan ke GitHub, kepakai di scan berikutnya (±5 mnt).</i>"
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


def simpan_config(cfg):
    with open(bot.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _num(s):
    """Parse angka, dukung '6rb'/'6k' -> 6000. Return float atau None."""
    s = s.lower().replace(".", "").replace(",", ".")
    kali = 1
    if s.endswith(("rb", "k")):
        kali, s = 1000, s.rstrip("rbk")
    elif s.endswith("jt"):
        kali, s = 1_000_000, s[:-2]
    try:
        return float(s) * kali
    except ValueError:
        return None


def handle_tambah(chat_id, args):
    if not args:
        kirim(chat_id, "Format: <code>/tambah BBRI.JK 6000 4000</code> (batas atas & bawah opsional)")
        return
    ticker = args[0].upper()
    atas = _num(args[1]) if len(args) > 1 else None
    bawah = _num(args[2]) if len(args) > 2 else None
    cfg = bot.load_config()
    wl = cfg.setdefault("watchlist", [])
    entri = next((w for w in wl if w["ticker"].upper() == ticker), None)
    if entri is None:
        entri = {"ticker": ticker, "name": ticker}
        wl.append(entri)
        aksi = "ditambahkan"
    else:
        aksi = "diupdate"
    if atas is not None:
        entri["batas_atas"] = atas
    if bawah is not None:
        entri["batas_bawah"] = bawah
    simpan_config(cfg)
    kirim(chat_id, f"✅ <b>{ticker}</b> {aksi} ke watchlist.\n"
                   f"Batas atas: {entri.get('batas_atas','-')}, bawah: {entri.get('batas_bawah','-')}")


def handle_hapus(chat_id, args):
    if not args:
        kirim(chat_id, "Format: <code>/hapus BBRI.JK</code>")
        return
    ticker = args[0].upper()
    cfg = bot.load_config()
    wl = cfg.get("watchlist", [])
    baru = [w for w in wl if w["ticker"].upper() != ticker]
    if len(baru) == len(wl):
        kirim(chat_id, f"❓ <b>{ticker}</b> gak ada di watchlist.")
        return
    cfg["watchlist"] = baru
    simpan_config(cfg)
    kirim(chat_id, f"🗑️ <b>{ticker}</b> dihapus dari watchlist.")


def _universe_path(ticker):
    nama = "idx" if ticker.upper().endswith(".JK") else "us"
    return os.path.join(os.path.dirname(__file__), "universe", f"{nama}.txt"), nama


def handle_scanadd(chat_id, args):
    if not args:
        kirim(chat_id, "Format: <code>/scanadd ANTM.JK</code>")
        return
    ticker = args[0].upper()
    path, nama = _universe_path(ticker)
    isi = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            isi = [l.rstrip("\n") for l in f]
    ada = any(l.strip().upper() == ticker for l in isi if not l.strip().startswith("#"))
    if ada:
        kirim(chat_id, f"ℹ️ <b>{ticker}</b> udah ada di universe {nama}.")
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(ticker + "\n")
    kirim(chat_id, f"✅ <b>{ticker}</b> ditambah ke universe scan ({nama}).")


def handle_scandel(chat_id, args):
    if not args:
        kirim(chat_id, "Format: <code>/scandel ANTM.JK</code>")
        return
    ticker = args[0].upper()
    path, nama = _universe_path(ticker)
    if not os.path.exists(path):
        kirim(chat_id, f"❓ Universe {nama} gak ketemu.")
        return
    with open(path, "r", encoding="utf-8") as f:
        isi = f.readlines()
    baru = [l for l in isi if l.strip().upper() != ticker]
    if len(baru) == len(isi):
        kirim(chat_id, f"❓ <b>{ticker}</b> gak ada di universe {nama}.")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(baru)
    kirim(chat_id, f"🗑️ <b>{ticker}</b> dihapus dari universe scan ({nama}).")


SET_MAP = {
    "naik": "perubahan_persen_min",
    "volume": "volume_vs_rata2_min",
    "gap": "gap_persen_min",
    "rsi_ob": "rsi_overbought",
    "rsi_os": "rsi_oversold",
    "sinyal": "min_sinyal_gabungan",
}


def handle_set(chat_id, args):
    if len(args) < 2:
        kirim(chat_id, "Format: <code>/set gap 5</code>\n"
                       "Param: naik, volume, gap, rsi_ob, rsi_os, sinyal")
        return
    param = args[0].lower()
    if param not in SET_MAP:
        kirim(chat_id, f"❓ Param '{param}' gak dikenal. Pilih: {', '.join(SET_MAP)}")
        return
    val = _num(args[1])
    if val is None:
        kirim(chat_id, "Nilainya harus angka.")
        return
    cfg = bot.load_config()
    kriteria = cfg.setdefault("screener", {}).setdefault("kriteria", {})
    kriteria[SET_MAP[param]] = val
    simpan_config(cfg)
    kirim(chat_id, f"✅ Kriteria <b>{param}</b> = {val:g} disimpan.")


def handle_scan(chat_id):
    kirim(chat_id, "⏳ Screener lagi jalan, tunggu 1-3 menit ya...")
    try:
        import screener
        screener.main()
    except Exception as e:
        kirim(chat_id, f"❌ Scan gagal: {e}")


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
    elif cmd == "/tambah":
        handle_tambah(chat_id, args)
    elif cmd == "/hapus":
        handle_hapus(chat_id, args)
    elif cmd == "/scanadd":
        handle_scanadd(chat_id, args)
    elif cmd == "/scandel":
        handle_scandel(chat_id, args)
    elif cmd == "/set":
        handle_set(chat_id, args)
    elif cmd == "/scan":
        handle_scan(chat_id)
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
