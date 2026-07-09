"""
Generator daftar universe.
--------------------------
Ambil daftar SEMUA saham US dari Nasdaq Trader (publik, gratis) lalu tulis
ke universe/us.txt.

Pakai:
  python build_universe.py us-all     # ambil semua saham US (ribuan)

Catatan: universe/idx.txt di-maintain manual (list likuid). Tambah ticker
IDX baru cukup edit file itu, 1 ticker per baris (mis. BBCA.JK).

PERINGATAN: universe US penuh = ribuan ticker. Scan-nya jauh lebih lama &
lebih gampang kena rate-limit Yahoo. Naikkan "jeda_antar_chunk_detik" di
config kalau sering gagal, dan pertimbangkan scan 1x sehari aja.
"""

import os
import sys

import requests

BASE = os.path.dirname(__file__)
UNIVERSE_DIR = os.path.join(BASE, "universe")

NASDAQ = "https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER = "https://ftp.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"


def _ambil(url, kolom_symbol, kolom_test, kolom_etf=None):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    baris = r.text.splitlines()
    header = baris[0].split("|")
    out = []
    for line in baris[1:]:
        if line.startswith("File Creation Time"):
            continue
        f = line.split("|")
        if len(f) <= max(kolom_symbol, kolom_test):
            continue
        sym = f[kolom_symbol].strip()
        if not sym:
            continue
        if f[kolom_test].strip() == "Y":  # skip test issue
            continue
        if kolom_etf is not None and len(f) > kolom_etf and f[kolom_etf].strip() == "Y":
            continue  # skip ETF, cuma mau saham
        # Yahoo pakai '-' untuk kelas saham (BRK.B -> BRK-B)
        sym = sym.replace(".", "-").replace("$", "-")
        if any(c in sym for c in [" "]):
            continue
        out.append(sym)
    return out


def us_all():
    print("Ambil daftar saham US dari Nasdaq Trader...")
    # nasdaqlisted: Symbol|Name|...|Test Issue|...|ETF|...
    nas = _ambil(NASDAQ, kolom_symbol=0, kolom_test=3, kolom_etf=6)
    # otherlisted: ACT Symbol|Name|Exchange|...|ETF|...|Test Issue(=last-? )
    oth = _ambil(OTHER, kolom_symbol=0, kolom_test=6, kolom_etf=4)
    semua = sorted(set(nas) | set(oth))
    path = os.path.join(UNIVERSE_DIR, "us.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Universe saham US LENGKAP (dari Nasdaq Trader). Auto-generated.\n")
        for s in semua:
            f.write(s + "\n")
    print(f"OK: {len(semua)} ticker ditulis ke {path}")
    print("PERINGATAN: scan sebanyak ini berat & bisa kena rate-limit. "
          "Pertimbangkan naikkan jeda & scan 1x/hari.")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "us-all":
        us_all()
    else:
        print(__doc__)
