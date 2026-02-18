# StreakKeeper (Taslak)

GitHub katki serisini (yesil kutular) bozmamak icin olusturulmus hafif bir CLI aracidir.

Mantik:
- `busy` modu acikken her gun tek bir "heartbeat" satiri ekler.
- `tick` komutu ayni gun ikinci kez commit atmaz.
- Sadece `streak-heartbeat.md` ve `.streakkeeper/state.json` dosyalarini stage eder.
- `maintain` komutu `.streakkeeper/project-maintenance.md` dosyasina repo snapshot ekler.

## Kurulum

Python 3.8+ yeterli.

```bash
chmod +x streakkeeper.py
```

## Hizli Baslangic

```bash
./streakkeeper.py init
./streakkeeper.py busy --days 3 --note "Toplantidayim"
./streakkeeper.py status
./streakkeeper.py tick
```

## Komutlar

- `init`: `.streakkeeper/config.json` ve `.streakkeeper/state.json` olusturur.
- `busy --days N --note "..."`: Busy modu N gun acik tutar.
- `off`: Busy modu kapatir.
- `status`: Mevcut durumu gosterir.
- `tick`: Gunun commit'ini gerekiyorsa atar.
  - `--dry-run`: Islem yapmadan ne olacagini gosterir.
  - `--force`: Busy kapali olsa bile calisir.
  - `--note`: Heartbeat satiri notu.
  - `--message`: Ozel commit mesaji.
- `maintain`: Kucuk bir repo bakim snapshot'i uretir, commit/push yapar.
  - `--dry-run`: Islem yapmadan plani gosterir.
  - `--no-push`: Sadece lokal commit atar.
  - `--note`: Snapshot notu.
  - `--message`: Ozel commit mesaji.

## Cron Ornegi (macOS/Linux)

Her gun saat 14:00'te kontrol etmek icin:

```cron
0 14 * * * cd /Users/omer/Documents/New\ project && /usr/bin/python3 ./streakkeeper.py tick >> /tmp/streakkeeper.log 2>&1
```

## Telegram Bot

`telegram_streak_bot.py` su isi yapar:
- Telegram'dan komut alir ve butonlu panel sunar (`/panel`).
- Aksam belirledigin saatte commit yoksa uyari mesaji yollar.

### 1) Bot token al

- Telegram'da `@BotFather` ile bot olustur.
- Token'i al.
- Kendi chat id degerini ogren (ornegin `@userinfobot` ile).

### 2) Bot config dosyasini duzenle

`/Users/omer/Documents/New project/.streakkeeper/telegram.json`:

```json
{
  "bot_token": "123456:ABCDEF...",
  "allowed_chat_id": "",
  "auto_bind_chat_on_start": true,
  "reminder_hour": 21,
  "reminder_minute": 30,
  "poll_timeout_seconds": 20,
  "reminder_enabled": true,
  "reminder_text": "Bugun bu repoda commit gorunmuyor. Streak riskte olabilir."
}
```

`allowed_chat_id` bos birakilirsa, botu ilk `/start` atan chat'e otomatik kilitler.

### 3) Botu calistir

```bash
chmod +x telegram_streak_bot.py
./telegram_streak_bot.py
```

Komutlar:
- `/yardim`
- `/panel` (tiklik menu)
- `/durum`
- `/mesgul 2 Toplantilar`
- `/kapat`
- `/tick Acil guncelleme`
- `/bakim Gun sonu snapshot`
- `/hatirlat 22:15`
- `/chatid`

Not:
- Bu bot sadece bu repository icinde islem yapar.
- Kurulumda ilk `/start` chat'i kaydeder ve diger chat'leri reddeder.
- Proje guncellemesi taklidi yerine gercek, izlenebilir bakim kaydi olusturur.
- `/panel` ve hizli klavye ile teknik bilgi olmadan da kullanilabilir.

### Yardim Menusu

Bot icinde `/yardim` yazinca detayli ve ornekli menu gelir. Ingilizce komutlar da calisir:
- `/help` = `/yardim`
- `/panel` = `/panel`
- `/status` = `/durum`
- `/busy` = `/mesgul`
- `/off` = `/kapat`
- `/maintain` = `/bakim`
- `/setreminder` = `/hatirlat`

## Surekli Calistirma (En Hizli ve Kesin)

En stabil yol: Oracle VM (Ubuntu) + `systemd`.

Neden:
- GitHub Pages statik hosting'dir, botu surekli calistiramaz.
- GitHub Actions surekli servis degil, periyodik calisir ve sure kisitlari vardir.
- VM uzerinde `systemd` ile bot 7/24 ayakta kalir, dusse otomatik yeniden baslar.

### Oracle VM Kurulum Ozeti

1. Kodu VM'e kopyala (git clone veya scp).
2. `telegram.json` icinde `bot_token` gir, `allowed_chat_id` bos kalabilir.
3. Servis dosyasini kopyala:

```bash
sudo cp /home/ubuntu/streakkeeper/deploy/telegram-streak-bot.service /etc/systemd/system/telegram-streak-bot.service
```

4. Gerekirse servis dosyasinda su alanlari duzelt:
- `User`
- `WorkingDirectory`
- `ExecStart`

5. Servisi aktif et:

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-streak-bot
sudo systemctl start telegram-streak-bot
```

6. Durumu kontrol et:

```bash
sudo systemctl status telegram-streak-bot
journalctl -u telegram-streak-bot -f
```

## Tek Komutla Guncelleme (PM2)

Bu projede `guncelle.sh` eklidir. Amaci:
- VM uzerinde tek komutla son kodu cekmek
- Botu PM2 ile yeniden baslatmak

Calistirma:

```bash
cd /home/ubuntu/streakkeeper
chmod +x guncelle.sh
./guncelle.sh
```

Opsiyonlar:

```bash
./guncelle.sh --branch main --app telegram-streak-bot --remote origin
```

Not:
- Script varsayilan olarak kirli git durumu varsa durur.
- Isteyerek gecmek icin: `./guncelle.sh --allow-dirty`

## Oracle VM Entegrasyonu (Adim Adim)

1. PM2 kur (VM icinde):

```bash
sudo apt update
sudo apt -y install nodejs npm
sudo npm install -g pm2
```

2. Ilk calistirma:

```bash
cd /home/ubuntu/streakkeeper
chmod +x guncelle.sh
./guncelle.sh
pm2 startup systemd -u ubuntu --hp /home/ubuntu
pm2 save
```

3. GitHub Actions secret'lari:
- `ORACLE_HOST`: `158.101.174.11`
- `ORACLE_USER`: `ubuntu`
- `ORACLE_SSH_KEY`: private key icerigi
- `ORACLE_PORT`: `22`
- `ORACLE_DEPLOY_PATH`: `/home/ubuntu/streakkeeper`
- `ORACLE_DEPLOY_REMOTE`: `origin`
- `ORACLE_DEPLOY_BRANCH`: `main`
- `ORACLE_PM2_APP_NAME`: `telegram-streak-bot`

4. Artik `main` branch'e her push'ta Action VM'ye baglanip `./guncelle.sh` calistirir.

## Notlar

- Bu taslak, aktif branch'e push eder (`config.json` icinde `branch` bos ise).
- Uzak depoya push icin git kimlik dogrulamasinin (SSH/token) zaten hazir olmasi gerekir.
- Gercek katki degerini arttirmak icin bu araci anlamsiz degil, kucuk ama anlamli bakim gorevleriyle birlikte kullanman daha saglikli olur.
