#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parent
APP_DIR = ROOT_DIR / ".streakkeeper"
BOT_CONFIG_PATH = APP_DIR / "telegram.json"
BOT_STATE_PATH = APP_DIR / "bot_state.json"
STREAK_CONFIG_PATH = APP_DIR / "config.json"
STREAK_STATE_PATH = APP_DIR / "state.json"

DEFAULT_BOT_CONFIG = {
    "bot_token": "",
    "allowed_chat_id": "",
    "auto_bind_chat_on_start": True,
    "reminder_hour": 21,
    "reminder_minute": 30,
    "poll_timeout_seconds": 20,
    "reminder_enabled": True,
    "reminder_text": "Bugun bu repoda commit gorunmuyor. Streak riskte olabilir.",
}

DEFAULT_BOT_STATE = {
    "last_update_id": 0,
    "last_reminder_date": None,
}


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[streak-bot] {ts} | {msg}", flush=True)


HELP_TEXT = (
    "Streak Bot Yardim Menusu\n\n"
    "Amac:\n"
    "- Gun sonuna dogru commit yoksa seni uyarmak\n"
    "- Telegram uzerinden bakim komutu calistirmak\n\n"
    "Temel Komutlar:\n"
    "/yardim veya /help\n"
    "  Tanim: Bu menuyu gosterir.\n\n"
    "/durum veya /status\n"
    "  Tanim: Bugunku commit var mi, repo durumu ne gosterir.\n\n"
    "/mesgul <gun> [not] veya /busy <days> [note]\n"
    "  Tanim: N gun boyunca streak koruma modunu ac.\n"
    "  Ornek: /mesgul 2 Toplantilar yogun\n\n"
    "/kapat veya /off\n"
    "  Tanim: Mesgul modunu kapat.\n\n"
    "/tick [not]\n"
    "  Tanim: Gerekiyorsa bugunluk streak commit isini calistir.\n"
    "  Ornek: /tick Gun sonu kontrol\n\n"
    "/bakim [not] veya /maintain [note]\n"
    "  Tanim: Kucuk bir bakim snapshot'i commit/push yapar.\n"
    "  Ornek: /bakim Gun sonu repo snapshot\n\n"
    "/hatirlat HH:MM veya /setreminder HH:MM\n"
    "  Tanim: Gunluk uyari saatini ayarla (24 saat formati).\n"
    "  Ornek: /hatirlat 22:15\n\n"
    "/chatid\n"
    "  Tanim: Aktif chat kimligini gosterir.\n\n"
    "Not:\n"
    "- Bot sadece kayitli chat'ten komut kabul eder.\n"
    "- Ilk kurulumda /start gonderen chat otomatik kayit edilir."
)

COMMAND_ALIASES = {
    "/help": "/help",
    "/yardim": "/help",
    "/komutlar": "/help",
    "help": "/help",
    "yardim": "/help",
    "komutlar": "/help",
    "/start": "/start",
    "/status": "/status",
    "/durum": "/status",
    "status": "/status",
    "durum": "/status",
    "/busy": "/busy",
    "/mesgul": "/busy",
    "busy": "/busy",
    "mesgul": "/busy",
    "/off": "/off",
    "/kapat": "/off",
    "off": "/off",
    "kapat": "/off",
    "/tick": "/tick",
    "tick": "/tick",
    "/maintain": "/maintain",
    "/bakim": "/maintain",
    "maintain": "/maintain",
    "bakim": "/maintain",
    "/setreminder": "/setreminder",
    "/hatirlat": "/setreminder",
    "setreminder": "/setreminder",
    "hatirlat": "/setreminder",
    "/chatid": "/chatid",
    "chatid": "/chatid",
}


def load_json(path: Path, default: Dict) -> Dict:
    if not path.exists():
        return dict(default)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def ensure_bot_config() -> Dict:
    config = load_json(BOT_CONFIG_PATH, DEFAULT_BOT_CONFIG)
    for key, value in DEFAULT_BOT_CONFIG.items():
        config.setdefault(key, value)
    env_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if env_token:
        config["bot_token"] = env_token
    env_chat = os.environ.get("TELEGRAM_ALLOWED_CHAT_ID", "").strip()
    if env_chat:
        config["allowed_chat_id"] = env_chat
    if not BOT_CONFIG_PATH.exists():
        save_json(BOT_CONFIG_PATH, config)
    return config


def git_output(args: List[str], check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(msg or f"git {' '.join(args)} failed")
    return (proc.stdout or "").strip()


def has_commit_today() -> bool:
    today_start = f"{date.today().isoformat()} 00:00:00"
    out = git_output(["log", "--since", today_start, "--pretty=format:%H"], check=False)
    return bool(out.strip())


def changed_file_count() -> int:
    out = git_output(["status", "--porcelain"], check=False)
    return len([line for line in out.splitlines() if line.strip()])


def run_streakkeeper(args: List[str]) -> Tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT_DIR / "streakkeeper.py"), *args],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    combined = output if not err else f"{output}\n{err}".strip()
    return proc.returncode, combined


class TelegramClient:
    def __init__(self, token: str):
        self.base_url = f"https://api.telegram.org/bot{token}"

    def call(self, method: str, params: Dict) -> Dict:
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/{method}", data=data)
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API error: {payload}")
        return payload

    def send_message(self, chat_id: str, text: str) -> None:
        self.call("sendMessage", {"chat_id": chat_id, "text": text})

    def get_updates(self, offset: int, timeout: int) -> List[Dict]:
        payload = self.call(
            "getUpdates",
            {"offset": offset, "timeout": timeout, "allowed_updates": '["message"]'},
        )
        return payload.get("result", [])


def load_streak_status() -> Dict:
    config = load_json(STREAK_CONFIG_PATH, {})
    state = load_json(STREAK_STATE_PATH, {})
    return {
        "busy_until": config.get("busy_until"),
        "busy_note": config.get("busy_note"),
        "last_commit_date": state.get("last_commit_date"),
    }


def is_reminder_due(bot_cfg: Dict, bot_state: Dict) -> bool:
    if not bot_cfg.get("reminder_enabled", True):
        return False
    now = datetime.now()
    h = int(bot_cfg.get("reminder_hour", 21))
    m = int(bot_cfg.get("reminder_minute", 30))
    if (now.hour, now.minute) < (h, m):
        return False
    if bot_state.get("last_reminder_date") == date.today().isoformat():
        return False
    return not has_commit_today()


def format_status_text() -> str:
    branch = git_output(["branch", "--show-current"], check=False) or "unknown"
    today_commit = has_commit_today()
    changes = changed_file_count()
    streak = load_streak_status()
    return (
        "Streak Bot Durumu\n"
        f"- Branch: {branch}\n"
        f"- Bugun commit var mi: {'Evet' if today_commit else 'Hayir'}\n"
        f"- Degisen dosya sayisi: {changes}\n"
        f"- Mesgul modu bitis: {streak.get('busy_until') or '-'}\n"
        f"- Mesgul notu: {streak.get('busy_note') or '-'}\n"
        f"- Son tick commit tarihi: {streak.get('last_commit_date') or '-'}"
    )


def parse_command(text: str) -> Tuple[str, List[str]]:
    raw = (text or "").strip()
    if not raw:
        return "", []
    parts = raw.split()
    cmd = parts[0].split("@")[0].lower()
    cmd = COMMAND_ALIASES.get(cmd, cmd)
    return cmd, parts[1:]


def run_command(cmd: str, args: List[str], cfg: Dict, chat_id: str) -> str:
    if cmd in ("/start", "/help"):
        return HELP_TEXT

    if cmd == "/status":
        return format_status_text()

    if cmd == "/busy":
        if not args:
            return "Kullanim: /busy <days> [note]"
        days = args[0]
        note = " ".join(args[1:]).strip()
        cmd_args = ["busy", "--days", days]
        if note:
            cmd_args.extend(["--note", note])
        code, out = run_streakkeeper(cmd_args)
        return out or ("Busy ayarlandi." if code == 0 else "Busy ayarlanamadi.")

    if cmd == "/off":
        code, out = run_streakkeeper(["off"])
        return out or ("Busy kapatildi." if code == 0 else "Busy kapatilamadi.")

    if cmd == "/tick":
        note = " ".join(args).strip()
        cmd_args = ["tick"]
        if note:
            cmd_args.extend(["--note", note])
        code, out = run_streakkeeper(cmd_args)
        return out or ("Tick calisti." if code == 0 else "Tick hatali.")

    if cmd == "/maintain":
        note = " ".join(args).strip()
        cmd_args = ["maintain"]
        if note:
            cmd_args.extend(["--note", note])
        code, out = run_streakkeeper(cmd_args)
        return out or ("Maintenance calisti." if code == 0 else "Maintenance hatali.")

    if cmd == "/setreminder":
        if len(args) != 1 or ":" not in args[0]:
            return "Kullanim: /hatirlat HH:MM (ornek: /hatirlat 22:15)"
        hm = args[0].split(":")
        if len(hm) != 2:
            return "Kullanim: /hatirlat HH:MM (ornek: /hatirlat 22:15)"
        hour, minute = hm
        if not (hour.isdigit() and minute.isdigit()):
            return "Saat formati hatali."
        h = int(hour)
        m = int(minute)
        if h < 0 or h > 23 or m < 0 or m > 59:
            return "Saat formati hatali."
        cfg["reminder_hour"] = h
        cfg["reminder_minute"] = m
        save_json(BOT_CONFIG_PATH, cfg)
        return f"Hatirlatma saati {h:02d}:{m:02d} olarak guncellendi."

    if cmd == "/chatid":
        return f"Bu sohbetin chat_id degeri: {chat_id}"

    return "Bilinmeyen komut. /yardim yazarak tum komutlari gorebilirsin."


def handle_update(client: TelegramClient, update: Dict, cfg: Dict) -> None:
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    if not chat_id:
        return

    text = msg.get("text", "")
    cmd, args = parse_command(text)
    if not cmd:
        return

    allowed = str(cfg.get("allowed_chat_id", "")).strip()
    bind_on_start = bool(cfg.get("auto_bind_chat_on_start", True))
    bound_now = False

    if not allowed:
        if bind_on_start and cmd == "/start":
            cfg["allowed_chat_id"] = chat_id
            save_json(BOT_CONFIG_PATH, cfg)
            allowed = chat_id
            bound_now = True
            log(f"Allowed chat auto-bound: {chat_id}")
        else:
            client.send_message(chat_id, "Ilk kurulum icin /start komutunu gonder.")
            return

    if allowed and chat_id != allowed:
        client.send_message(chat_id, "Yetkisiz chat.")
        return

    response = run_command(cmd, args, cfg, chat_id)
    if bound_now:
        response = f"Bu chat bot yonetimi icin kaydedildi (chat_id={chat_id}).\n\n{response}"
    client.send_message(chat_id, response)
    log(f"Command handled: cmd={cmd} chat_id={chat_id}")


def run_loop() -> int:
    cfg = ensure_bot_config()
    state = load_json(BOT_STATE_PATH, DEFAULT_BOT_STATE)
    for key, value in DEFAULT_BOT_STATE.items():
        state.setdefault(key, value)

    token = cfg.get("bot_token", "").strip()
    if not token:
        print(f"Bot token gerekli. Dosyayi duzenle: {BOT_CONFIG_PATH}", file=sys.stderr)
        return 1

    client = TelegramClient(token)
    timeout = int(cfg.get("poll_timeout_seconds", 20))
    offset = int(state.get("last_update_id", 0)) + 1
    masked_token = f"{token[:6]}...{token[-4:]}" if len(token) > 12 else "***"
    log("Bot baslatiliyor.")
    log(f"Config: timeout={timeout}s reminder={cfg.get('reminder_hour', 21):02d}:{cfg.get('reminder_minute', 30):02d}")
    log(f"Config: allowed_chat_id={cfg.get('allowed_chat_id') or '-'} token={masked_token}")
    log(f"Polling basladi. offset={offset}")

    while True:
        try:
            updates = client.get_updates(offset=offset, timeout=timeout)
            for upd in updates:
                upd_id = int(upd.get("update_id", 0))
                if upd_id >= offset:
                    offset = upd_id + 1
                state["last_update_id"] = upd_id
                handle_update(client, upd, cfg)

            if is_reminder_due(cfg, state):
                chat_id = str(cfg.get("allowed_chat_id", "")).strip()
                if chat_id:
                    text = cfg.get("reminder_text", DEFAULT_BOT_CONFIG["reminder_text"])
                    extra = "\nKomutlar: /status /tick /maintain"
                    client.send_message(chat_id, f"{text}{extra}")
                    state["last_reminder_date"] = date.today().isoformat()
                    log(f"Reminder sent to chat_id={chat_id}")

            save_json(BOT_STATE_PATH, state)
        except KeyboardInterrupt:
            log("Bot durduruldu.")
            return 0
        except Exception as exc:
            print(f"Hata: {exc}", file=sys.stderr)
            log("Gecici hata alindi, 5 sn sonra tekrar denenecek.")
            time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(run_loop())
