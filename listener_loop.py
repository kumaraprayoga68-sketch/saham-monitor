"""
Listener Telegram versi NYALA-TERUS (long polling).
----------------------------------------------------
Beda dari listener.py (cron, delay s/d 5 menit), ini jalan terus dan
balas command < 1 detik. Cocok buat host yang nyala-terus:
Railway / Render / Fly.io / VPS.

PENTING: JANGAN jalan barengan sama workflow listener.yml (GitHub Actions).
Dua-duanya manggil getUpdates -> bakal rebutan pesan. Pilih SALAH SATU:
kalau deploy di host instan ini, matiin workflow "Listener Telegram" di GitHub.

Jalanin: python listener_loop.py
Env yang wajib: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

import bot       # monitor: satu_putaran(), load/save_state(), load_config()
import listener  # pakai ulang proses_pesan(), load/save_offset(), TOKEN


def start_health_server():
    """HTTP server mini biar Render nganggep ini 'web service' (plan gratis).
    Balas 200 di semua path. Juga jadi target ping biar service gak ketiduran."""
    port = int(os.getenv("PORT", "10000"))

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"bot aktif")

        def log_message(self, *args):
            pass  # jangan spam log

    try:
        HTTPServer(("0.0.0.0", port), H).serve_forever()
    except Exception as e:
        print(f"[health] server error: {e}")


def jalankan_monitor():
    """Satu putaran monitor watchlist (alert + ringkasan). Aman kalau gagal."""
    try:
        bot.load_state()
        cfg = bot.load_config()
        bot.satu_putaran(cfg)
        bot.save_state()
        print("[monitor] putaran selesai.")
    except Exception as e:
        print(f"[monitor] gagal: {e}")


def main():
    if not listener.TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN belum diisi.")
        return
    # Nyalain health server di thread terpisah (buat Render web service gratis)
    threading.Thread(target=start_health_server, daemon=True).start()

    offset = listener.load_offset()
    interval_menit = bot.load_config().get("interval_minutes", 15)
    print(f"Worker jalan: balas command instan + monitor tiap {interval_menit} menit. Ctrl+C stop.")
    listener.kirim(listener.OWNER_CHAT_ID,
                   f"🤖 Bot AKTIF (mode nyala-terus).\nCommand instan + notif tiap {interval_menit} mnt.")

    url = f"https://api.telegram.org/bot{listener.TOKEN}/getUpdates"
    monitor_berikutnya = 0.0  # langsung jalanin monitor sekali di awal
    while True:
        try:
            # 1) Cek pesan masuk (long polling 30 detik)
            r = requests.get(
                url,
                params={"offset": offset, "timeout": 30},
                timeout=40,
            )
            updates = r.json().get("result", [])
            for up in updates:
                offset = max(offset, up["update_id"] + 1)
                msg = up.get("message") or up.get("edited_message")
                if msg:
                    listener.proses_pesan(msg)
            if updates:
                listener.save_offset(offset)

            # 2) Monitor berkala (pakai interval dari config, di-reload tiap kali)
            if time.time() >= monitor_berikutnya:
                jalankan_monitor()
                interval_menit = bot.load_config().get("interval_minutes", 15)
                monitor_berikutnya = time.time() + interval_menit * 60
        except requests.RequestException as e:
            print(f"[WARN] koneksi error, coba lagi 5 detik: {e}")
            time.sleep(5)
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
