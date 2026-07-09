# 🤖 Bot Pemantau Saham → Telegram

Bot Python yang mantau harga saham/crypto dan ngirim alert ke Telegram.

- **Sumber data:** Yahoo Finance (gratis) — support IDX (`.JK`), saham US, dan crypto (`-USD`)
- **Notif:** Telegram
- **Alert:** batas harga, perubahan %, update rutin, indikator teknikal (RSI + MA cross)

## Cara Pakai

### 1. Install (sekali aja)
```bash
pip install -r requirements.txt
```

### 2. Setup rahasia (`.env`)
Udah keisi kalau lu ngikutin setup awal. Kalau bikin ulang:
```
TELEGRAM_BOT_TOKEN=token_dari_@BotFather
TELEGRAM_CHAT_ID=chat_id_lu
```
> Dapetin chat_id: chat bot lu dulu, lalu buka `https://api.telegram.org/bot<TOKEN>/getUpdates`

### 3. Atur saham yang dipantau (`config.json`)
```json
{
  "ticker": "BBCA.JK",        // .JK = IDX, tanpa akhiran = US, -USD = crypto
  "name": "Bank Central Asia",
  "batas_atas": 11000,        // alert kalau harga >= ini
  "batas_bawah": 9000,        // alert kalau harga <= ini
  "alert_perubahan_persen": 3 // alert kalau naik/turun >= 3% dalam sehari
}
```
Tambah/hapus saham sesuka lu di array `watchlist`. Bot reload config tiap putaran, jadi **gak perlu restart** kalau edit config.

Contoh ticker:
- IDX: `BBCA.JK`, `TLKM.JK`, `GOTO.JK`, `BBRI.JK`
- US: `AAPL`, `TSLA`, `NVDA`, `MSFT`
- Crypto: `BTC-USD`, `ETH-USD`, `SOL-USD`

### 4. Jalankan
```bash
python bot.py
```
Bot bakal cek tiap `interval_minutes` (default 15 menit) dan kirim alert otomatis. Stop dengan `Ctrl+C`.

## Catatan
- Data Yahoo Finance interval harian bisa delay ~15 menit dan gak real-time tick. Cukup buat swing/monitoring, bukan scalping.
- Anti-spam: tiap jenis alert cuma dikirim sekali sampai kondisinya reset (biar gak nge-flood).
- Kalau mau bot jalan terus walau laptop nyala: biarin terminal kebuka, atau pakai Task Scheduler Windows.

## Kustomisasi cepat
| Mau apa | Edit di `config.json` |
|---|---|
| Ganti interval cek | `interval_minutes` |
| Matiin update rutin | `fitur.update_rutin: false` |
| Matiin indikator teknikal | `fitur.indikator_teknikal: false` |
| Ubah ambang RSI | `rsi_oversold` / `rsi_overbought` |
