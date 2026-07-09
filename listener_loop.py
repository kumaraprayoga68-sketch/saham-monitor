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

import time

import requests

import listener  # pakai ulang proses_pesan(), load/save_offset(), TOKEN


def main():
    if not listener.TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN belum diisi.")
        return
    offset = listener.load_offset()
    print("Listener loop jalan (long polling, balas instan). Ctrl+C buat stop.")
    url = f"https://api.telegram.org/bot{listener.TOKEN}/getUpdates"
    while True:
        try:
            r = requests.get(
                url,
                params={"offset": offset, "timeout": 30},  # long polling 30 detik
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
        except requests.RequestException as e:
            print(f"[WARN] koneksi error, coba lagi 5 detik: {e}")
            time.sleep(5)
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
