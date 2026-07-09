"""
Daftarin command menu Telegram (tombol biru ☰ di sebelah kotak chat).
--------------------------------------------------------------------
Jalanin sekali aja (atau tiap kali mau ubah daftar command).
Setting-nya tersimpan permanen di sisi Telegram.

Pakai: python setup_telegram.py
Env wajib: TELEGRAM_BOT_TOKEN (dibaca dari .env)
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

COMMANDS = [
    {"command": "harga",   "description": "Harga saham terkini (mis: /harga BBCA.JK)"},
    {"command": "list",    "description": "Daftar saham di watchlist"},
    {"command": "scan",    "description": "Jalanin screener sekarang juga"},
    {"command": "tambah",  "description": "Tambah saham ke watchlist (mis: /tambah BBRI.JK 6000 4000)"},
    {"command": "hapus",   "description": "Hapus saham dari watchlist (mis: /hapus BBRI.JK)"},
    {"command": "scanadd", "description": "Tambah saham ke universe scan (mis: /scanadd ANTM.JK)"},
    {"command": "scandel", "description": "Hapus saham dari universe scan"},
    {"command": "set",     "description": "Ubah kriteria: naik/volume/gap/rsi_ob/rsi_os/sinyal"},
    {"command": "help",    "description": "Bantuan & daftar semua command"},
]


def main():
    if not TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN belum diisi di .env")
        return
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/setMyCommands",
        json={"commands": COMMANDS},
        timeout=15,
    )
    if r.ok and r.json().get("ok"):
        print(f"[OK] {len(COMMANDS)} command kedaftar. Tombol menu ☰ bakal muncul di chat.")
    else:
        print(f"[GAGAL] {r.text}")


if __name__ == "__main__":
    main()
