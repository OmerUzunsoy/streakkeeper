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
from typing import Dict, List, Tuple


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
    "default_busy_days": 1,
    "default_busy_note": "Yogun mod",
    "default_maintenance_note": "Gun sonu bakim",
}

DEFAULT_BOT_STATE = {
    "last_update_id": 0,
    "last_reminder_date": None,
}


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[streak-bot] {ts} | {msg}", flush=True)


HELP_TEXT = (
    "Streak Bot - Kolay Kullanim\n\n"
    "Hizli Baslangic:\n"
    "1) /start\n"
    "2) /panel (butonlu menu)\n"
    "3) /durum\n\n"
    "Temel Komutlar:\n"
    "- /panel: Butonlu hizli menu acar.\n"
    "- /durum: Anlik repo durumunu gosterir.\n"
    "- /mesgul <gun> [not]: Mesgul modunu acar.\n"
    "- /kapat: Mesgul modunu kapatir.\n"
    "- /tick [not]: Bugunluk streak commit aksiyonu.\n"
    "- /bakim [not]: Bakim snapshot commit/push aksiyonu.\n"
    "- /streak: Uygun ise tek hamlede streak korur.\n"
    "- /hatirlat HH:MM: Gunluk uyari saatini ayarlar.\n"
    "- /hatirlat-ac / /hatirlat-kapat: Uyarii ac/kapat.\n"
    "- /chatid: Bu sohbetin kimligini gosterir.\n\n"
    "Not:\n"
    "- Bot sadece yetkili sohbetten komut kabul eder.\n"
    "- Ilk /start mesajini atan sohbet otomatik yetkilenir."
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
    "/panel": "/panel",
    "panel": "/panel",
    "/hatirlat-ac": "/reminder_on",
    "hatirlat-ac": "/reminder_on",
    "/hatirlat-kapat": "/reminder_off",
    "hatirlat-kapat": "/reminder_off",
    "/streak": "/streak",
    "streak": "/streak",
}

CALLBACK_PREFIX = "act:"
CB_STATUS = f"{CALLBACK_PREFIX}status"
CB_TICK = f"{CALLBACK_PREFIX}tick"
CB_MAINTAIN = f"{CALLBACK_PREFIX}maintain"
CB_BUSY_1 = f"{CALLBACK_PREFIX}busy1"
CB_BUSY_3 = f"{CALLBACK_PREFIX}busy3"
CB_OFF = f"{CALLBACK_PREFIX}off"
CB_REMINDER_ON = f"{CALLBACK_PREFIX}reminder_on"
CB_REMINDER_OFF = f"{CALLBACK_PREFIX}reminder_off"
CB_REMINDER_2130 = f"{CALLBACK_PREFIX}reminder_2130"
CB_PANEL = f"{CALLBACK_PREFIX}panel"
CB_STREAK = f"{CALLBACK_PREFIX}streak"


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

    def send_message(self, chat_id: str, text: str, reply_markup: Dict = None) -> None:
        params: Dict[str, str] = {"chat_id": chat_id, "text": text}
        if reply_markup:
            params["reply_markup"] = json.dumps(reply_markup, separators=(",", ":"))
        self.call("sendMessage", params)

    def answer_callback(self, callback_query_id: str, text: str = "") -> None:
        params = {"callback_query_id": callback_query_id}
        if text:
            params["text"] = text
        self.call("answerCallbackQuery", params)

    def get_updates(self, offset: int, timeout: int) -> List[Dict]:
        payload = self.call(
            "getUpdates",
            {"offset": offset, "timeout": timeout, "allowed_updates": '["message","callback_query"]'},
        )
        return payload.get("result", [])


def main_keyboard() -> Dict:
    return {
        "keyboard": [
            ["/panel", "/durum"],
            ["/mesgul 1", "/kapat"],
            ["/streak", "/tick", "/bakim"],
            ["/hatirlat 21:30", "/yardim"],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }


def panel_keyboard(cfg: Dict) -> Dict:
    reminder_enabled = bool(cfg.get("reminder_enabled", True))
    reminder_toggle_button = (
        {"text": "Hatirlatma Kapat", "callback_data": CB_REMINDER_OFF}
        if reminder_enabled
        else {"text": "Hatirlatma Ac", "callback_data": CB_REMINDER_ON}
    )
    return {
        "inline_keyboard": [
            [
                {"text": "Streak Koru", "callback_data": CB_STREAK},
                {"text": "Durum", "callback_data": CB_STATUS},
                {"text": "Tick", "callback_data": CB_TICK},
                {"text": "Bakim", "callback_data": CB_MAINTAIN},
            ],
            [
                {"text": "Mesgul 1 Gun", "callback_data": CB_BUSY_1},
                {"text": "Mesgul 3 Gun", "callback_data": CB_BUSY_3},
                {"text": "Mesgul Kapat", "callback_data": CB_OFF},
            ],
            [
                {"text": "Hatirlat 21:30", "callback_data": CB_REMINDER_2130},
                reminder_toggle_button,
            ],
            [
                {"text": "Paneli Yenile", "callback_data": CB_PANEL},
            ],
        ]
    }


def panel_text(cfg: Dict) -> str:
    return (
        "Streak Bot Kontrol Paneli\n"
        "Asagidaki butonlardan tek tik ile islem yapabilirsin.\n"
        f"- Hatirlatma: {'Acik' if cfg.get('reminder_enabled', True) else 'Kapali'}\n"
        f"- Saat: {int(cfg.get('reminder_hour', 21)):02d}:{int(cfg.get('reminder_minute', 30)):02d}"
    )


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


def run_action(action: str, cfg: Dict) -> str:
    if action == "status":
        return format_status_text()

    if action == "busy1":
        note = cfg.get("default_busy_note", "Yogun mod")
        code, out = run_streakkeeper(["busy", "--days", "1", "--note", str(note)])
        return out or ("Mesgul modu 1 gun acildi." if code == 0 else "Mesgul modu acilamadi.")

    if action == "busy3":
        note = cfg.get("default_busy_note", "Yogun mod")
        code, out = run_streakkeeper(["busy", "--days", "3", "--note", str(note)])
        return out or ("Mesgul modu 3 gun acildi." if code == 0 else "Mesgul modu acilamadi.")

    if action == "off":
        code, out = run_streakkeeper(["off"])
        return out or ("Mesgul modu kapatildi." if code == 0 else "Mesgul modu kapatilamadi.")

    if action == "tick":
        code, out = run_streakkeeper(["tick"])
        return out or ("Tick calisti." if code == 0 else "Tick hatali.")

    if action == "maintain":
        note = cfg.get("default_maintenance_note", "Gun sonu bakim")
        code, out = run_streakkeeper(["maintain", "--note", str(note)])
        return out or ("Bakim calisti." if code == 0 else "Bakim hatali.")

    if action == "streak":
        if has_commit_today():
            return "Bugun zaten commit var. Ek islem yapilmadi."
        streak_status = load_streak_status()
        if streak_status.get("busy_until"):
            code, out = run_streakkeeper(["tick"])
            if code == 0 and "Skip:" not in out:
                return out or "Streak koruma: tick uygulandi."
        note = cfg.get("default_maintenance_note", "Gun sonu bakim")
        code, out = run_streakkeeper(["maintain", "--note", str(note)])
        return out or ("Streak koruma: bakim commit'i uygulandi." if code == 0 else "Streak koruma hatali.")

    if action == "reminder_on":
        cfg["reminder_enabled"] = True
        save_json(BOT_CONFIG_PATH, cfg)
        return "Hatirlatma acildi."

    if action == "reminder_off":
        cfg["reminder_enabled"] = False
        save_json(BOT_CONFIG_PATH, cfg)
        return "Hatirlatma kapatildi."

    if action == "reminder_2130":
        cfg["reminder_hour"] = 21
        cfg["reminder_minute"] = 30
        cfg["reminder_enabled"] = True
        save_json(BOT_CONFIG_PATH, cfg)
        return "Hatirlatma saati 21:30 olarak ayarlandi."

    if action == "panel":
        return panel_text(cfg)

    return "Bilinmeyen islem."


def run_command(cmd: str, args: List[str], cfg: Dict, chat_id: str) -> str:
    if cmd == "/start":
        return (
            "Bot aktif. Hos geldin.\n"
            "Hizli kullanim icin /panel yaz ve butonlardan sec.\n\n"
            + HELP_TEXT
        )

    if cmd in ("/help",):
        return HELP_TEXT

    if cmd == "/panel":
        return panel_text(cfg)

    if cmd == "/status":
        return run_action("status", cfg)

    if cmd == "/streak":
        return run_action("streak", cfg)

    if cmd == "/busy":
        if not args:
            days = str(max(int(cfg.get("default_busy_days", 1)), 1))
            note = str(cfg.get("default_busy_note", "Yogun mod"))
            code, out = run_streakkeeper(["busy", "--days", days, "--note", note])
            return out or (f"Mesgul modu {days} gun acildi." if code == 0 else "Mesgul modu acilamadi.")
        days = args[0]
        note = " ".join(args[1:]).strip()
        cmd_args = ["busy", "--days", days]
        if note:
            cmd_args.extend(["--note", note])
        code, out = run_streakkeeper(cmd_args)
        return out or ("Mesgul ayarlandi." if code == 0 else "Mesgul ayarlanamadi.")

    if cmd == "/off":
        return run_action("off", cfg)

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
        else:
            cmd_args.extend(["--note", str(cfg.get("default_maintenance_note", "Gun sonu bakim"))])
        code, out = run_streakkeeper(cmd_args)
        return out or ("Bakim calisti." if code == 0 else "Bakim hatali.")

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
        cfg["reminder_enabled"] = True
        save_json(BOT_CONFIG_PATH, cfg)
        return f"Hatirlatma saati {h:02d}:{m:02d} olarak guncellendi."

    if cmd == "/reminder_on":
        return run_action("reminder_on", cfg)

    if cmd == "/reminder_off":
        return run_action("reminder_off", cfg)

    if cmd == "/chatid":
        return f"Bu sohbetin chat_id degeri: {chat_id}"

    return "Bilinmeyen komut. /panel veya /yardim yaz."


def callback_to_action(data: str) -> str:
    mapping = {
        CB_STREAK: "streak",
        CB_STATUS: "status",
        CB_TICK: "tick",
        CB_MAINTAIN: "maintain",
        CB_BUSY_1: "busy1",
        CB_BUSY_3: "busy3",
        CB_OFF: "off",
        CB_REMINDER_ON: "reminder_on",
        CB_REMINDER_OFF: "reminder_off",
        CB_REMINDER_2130: "reminder_2130",
        CB_PANEL: "panel",
    }
    return mapping.get(data, "")


def authorize_chat(chat_id: str, cmd: str, cfg: Dict) -> Tuple[bool, bool]:
    allowed = str(cfg.get("allowed_chat_id", "")).strip()
    bind_on_start = bool(cfg.get("auto_bind_chat_on_start", True))
    bound_now = False
    if not allowed:
        if bind_on_start and cmd == "/start":
            cfg["allowed_chat_id"] = chat_id
            save_json(BOT_CONFIG_PATH, cfg)
            bound_now = True
            return True, bound_now
        return False, bound_now
    if allowed != chat_id:
        return False, bound_now
    return True, bound_now


def handle_message_update(client: TelegramClient, update: Dict, cfg: Dict) -> None:
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    if not chat_id:
        return

    text = msg.get("text", "")
    cmd, args = parse_command(text)
    if not cmd:
        return

    authorized, bound_now = authorize_chat(chat_id, cmd, cfg)
    if not authorized:
        if str(cfg.get("allowed_chat_id", "")).strip():
            client.send_message(chat_id, "Yetkisiz chat.")
        else:
            client.send_message(chat_id, "Ilk kurulum icin /start komutunu gonder.")
        return

    response = run_command(cmd, args, cfg, chat_id)
    if bound_now:
        log(f"Allowed chat auto-bound: {chat_id}")
        response = f"Bu chat bot yonetimi icin kaydedildi (chat_id={chat_id}).\n\n{response}"
    inline = panel_keyboard(cfg) if cmd in ("/start", "/help", "/panel") else None
    client.send_message(chat_id, response, reply_markup=inline)
    if cmd in ("/start", "/help", "/panel"):
        client.send_message(chat_id, "Hizli komut klavyesi aktif.", reply_markup=main_keyboard())
    log(f"Command handled: cmd={cmd} chat_id={chat_id}")


def handle_callback_update(client: TelegramClient, update: Dict, cfg: Dict) -> None:
    cb = update.get("callback_query") or {}
    callback_id = str(cb.get("id", ""))
    data = str(cb.get("data", ""))
    msg = cb.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    if not callback_id or not chat_id:
        return

    authorized, _ = authorize_chat(chat_id, "/panel", cfg)
    if not authorized:
        client.answer_callback(callback_id, "Yetkisiz istek.")
        return

    action = callback_to_action(data)
    if not action:
        client.answer_callback(callback_id, "Bilinmeyen buton.")
        return

    client.answer_callback(callback_id, "Islem alindi.")
    response = run_action(action, cfg)
    inline = panel_keyboard(cfg)
    client.send_message(chat_id, response, reply_markup=inline)
    log(f"Callback handled: action={action} chat_id={chat_id}")


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
                if upd.get("message"):
                    handle_message_update(client, upd, cfg)
                elif upd.get("callback_query"):
                    handle_callback_update(client, upd, cfg)

            if is_reminder_due(cfg, state):
                chat_id = str(cfg.get("allowed_chat_id", "")).strip()
                if chat_id:
                    text = cfg.get("reminder_text", DEFAULT_BOT_CONFIG["reminder_text"])
                    extra = "\nHizli erisim: /panel /durum /tick /bakim"
                    client.send_message(chat_id, f"{text}{extra}", reply_markup=panel_keyboard(cfg))
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
