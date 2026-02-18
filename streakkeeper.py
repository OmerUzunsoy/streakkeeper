#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


APP_DIR = Path(".streakkeeper")
CONFIG_PATH = APP_DIR / "config.json"
STATE_PATH = APP_DIR / "state.json"

DEFAULT_CONFIG = {
    "busy_until": None,
    "busy_note": "Busy mode",
    "heartbeat_file": "streak-heartbeat.md",
    "maintenance_file": ".streakkeeper/project-maintenance.md",
    "remote": "origin",
    "branch": "",
    "commit_prefix": "chore(streak)",
    "maintenance_prefix": "chore(maintenance)",
}


def run_git(args: List[str], check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        text=True,
        capture_output=True,
    )
    if check and proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(message or f"git {' '.join(args)} failed")
    return (proc.stdout or "").strip()


def ensure_git_repo() -> None:
    try:
        inside = run_git(["rev-parse", "--is-inside-work-tree"])
    except RuntimeError as exc:
        raise RuntimeError("Bu klasor bir git reposu degil.") from exc
    if inside != "true":
        raise RuntimeError("Bu klasor bir git reposu degil.")


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


def parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(value)


def load_config() -> Dict:
    config = load_json(CONFIG_PATH, DEFAULT_CONFIG)
    for key, value in DEFAULT_CONFIG.items():
        config.setdefault(key, value)
    return config


def load_state() -> Dict:
    return load_json(STATE_PATH, {"last_commit_date": None})


def is_busy_active(config: Dict) -> Tuple[bool, Optional[date]]:
    until = parse_iso_date(config.get("busy_until"))
    if until is None:
        return False, None
    return date.today() <= until, until


def cmd_init(_: argparse.Namespace) -> int:
    ensure_git_repo()
    if CONFIG_PATH.exists():
        print(f"Config zaten var: {CONFIG_PATH}")
        return 0
    save_json(CONFIG_PATH, DEFAULT_CONFIG)
    save_json(STATE_PATH, {"last_commit_date": None})
    print(f"Olusturuldu: {CONFIG_PATH}")
    print(f"Olusturuldu: {STATE_PATH}")
    return 0


def cmd_busy(args: argparse.Namespace) -> int:
    ensure_git_repo()
    config = load_config()
    until = date.today() + timedelta(days=max(args.days, 1) - 1)
    config["busy_until"] = until.isoformat()
    if args.note:
        config["busy_note"] = args.note
    save_json(CONFIG_PATH, config)
    print(f"Busy mode aktif. Bitis: {until.isoformat()}")
    return 0


def cmd_off(_: argparse.Namespace) -> int:
    ensure_git_repo()
    config = load_config()
    config["busy_until"] = None
    save_json(CONFIG_PATH, config)
    print("Busy mode kapatildi.")
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    ensure_git_repo()
    config = load_config()
    state = load_state()
    active, until = is_busy_active(config)
    print(f"Busy mode: {'AKTIF' if active else 'PASIF'}")
    print(f"Busy until: {until.isoformat() if until else '-'}")
    print(f"Busy note: {config.get('busy_note', '-')}")
    print(f"Heartbeat file: {config.get('heartbeat_file')}")
    print(f"Last commit date: {state.get('last_commit_date') or '-'}")
    return 0


def current_branch() -> str:
    branch = run_git(["branch", "--show-current"], check=False)
    if branch:
        return branch
    fallback = run_git(["rev-parse", "--abbrev-ref", "HEAD"], check=False)
    if fallback and fallback != "HEAD":
        return fallback
    return ""


def has_commit_today() -> bool:
    today_start = f"{date.today().isoformat()} 00:00:00"
    out = run_git(["log", "--since", today_start, "--pretty=format:%H"], check=False)
    return bool(out.strip())


def changed_file_count() -> int:
    out = run_git(["status", "--porcelain"], check=False)
    lines = [line for line in out.splitlines() if line.strip()]
    return len(lines)


def tracked_file_count() -> int:
    out = run_git(["ls-files"], check=False)
    lines = [line for line in out.splitlines() if line.strip()]
    return len(lines)


def last_commit_subject() -> str:
    return run_git(["log", "-1", "--pretty=%s"], check=False) or "-"


def cmd_tick(args: argparse.Namespace) -> int:
    ensure_git_repo()
    config = load_config()
    state = load_state()
    today = date.today().isoformat()

    active, until = is_busy_active(config)
    if not active and not args.force:
        if until is None:
            print("Skip: Busy mode acik degil.")
        else:
            print(f"Skip: Busy mode suresi dolmus ({until.isoformat()}).")
        return 0

    if state.get("last_commit_date") == today and not args.force:
        print("Skip: Bugun zaten streak commit atilmis.")
        return 0

    heartbeat_file = Path(config["heartbeat_file"])
    heartbeat_file.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat(timespec="seconds")
    note = args.note or config.get("busy_note", "Busy mode")
    line = f"- {now} | {note}\n"

    if not args.dry_run:
        with heartbeat_file.open("a", encoding="utf-8") as f:
            f.write(line)

    state["last_commit_date"] = today
    if not args.dry_run:
        save_json(STATE_PATH, state)

    commit_message = (
        args.message or f"{config.get('commit_prefix', 'chore(streak)')}: keep streak {today}"
    )
    remote = config.get("remote", "origin")
    branch = config.get("branch") or current_branch()
    if not branch:
        if args.dry_run:
            branch = "<branch-belirsiz>"
        else:
            print(
                "Hata: branch tespit edilemedi. "
                "Config icinde 'branch' degeri gir veya once ilk commit'i olustur.",
                file=sys.stderr,
            )
            return 1

    if args.dry_run:
        print(f"Dry run: {heartbeat_file} guncellenecek.")
        print(f"Dry run: commit mesaji: {commit_message}")
        print(f"Dry run: push hedefi: {remote} {branch}")
        return 0

    try:
        run_git(["add", str(heartbeat_file), str(STATE_PATH)])
        run_git(["commit", "-m", commit_message])
        run_git(["push", remote, branch])
    except RuntimeError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1

    print(f"Commit ve push tamamlandi ({today}).")
    return 0


def cmd_maintain(args: argparse.Namespace) -> int:
    ensure_git_repo()
    config = load_config()
    today = date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    branch = config.get("branch") or current_branch() or "unknown"
    maintenance_file = Path(config.get("maintenance_file", ".streakkeeper/project-maintenance.md"))
    maintenance_file.parent.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "branch": branch,
        "tracked_files": tracked_file_count(),
        "changed_files_before": changed_file_count(),
        "had_commit_today_before": has_commit_today(),
        "last_commit_subject": last_commit_subject(),
    }

    note = args.note or "Daily maintenance snapshot"
    section = [
        f"## {now}",
        f"- note: {note}",
        f"- branch: {snapshot['branch']}",
        f"- tracked_files: {snapshot['tracked_files']}",
        f"- changed_files_before: {snapshot['changed_files_before']}",
        f"- had_commit_today_before: {snapshot['had_commit_today_before']}",
        f"- previous_last_commit: {snapshot['last_commit_subject']}",
        "",
    ]

    if not args.dry_run:
        with maintenance_file.open("a", encoding="utf-8") as f:
            f.write("\n".join(section))

    commit_message = (
        args.message
        or f"{config.get('maintenance_prefix', 'chore(maintenance)')}: repo snapshot {today}"
    )
    remote = config.get("remote", "origin")
    push_branch = config.get("branch") or current_branch()
    if not push_branch:
        if args.dry_run:
            push_branch = "<branch-belirsiz>"
        else:
            print(
                "Hata: branch tespit edilemedi. "
                "Config icinde 'branch' degeri gir veya once ilk commit'i olustur.",
                file=sys.stderr,
            )
            return 1

    if args.dry_run:
        print(f"Dry run: {maintenance_file} guncellenecek.")
        print(f"Dry run: commit mesaji: {commit_message}")
        print(f"Dry run: push hedefi: {remote} {push_branch}")
        return 0

    try:
        run_git(["add", str(maintenance_file)])
        run_git(["commit", "-m", commit_message])
        if not args.no_push:
            run_git(["push", remote, push_branch])
    except RuntimeError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1

    if args.no_push:
        print(f"Maintenance commit tamamlandi ({today}), push yapilmadi.")
    else:
        print(f"Maintenance commit ve push tamamlandi ({today}).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="streakkeeper",
        description="GitHub katki serisini korumaya yardimci mini arac.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Temel config dosyalarini olusturur.")
    p_init.set_defaults(func=cmd_init)

    p_busy = sub.add_parser("busy", help="Busy mode'u acik tutar.")
    p_busy.add_argument("--days", type=int, default=1, help="Kac gun aktif kalacagi.")
    p_busy.add_argument("--note", type=str, default="", help="Heartbeat satiri notu.")
    p_busy.set_defaults(func=cmd_busy)

    p_off = sub.add_parser("off", help="Busy mode'u kapatir.")
    p_off.set_defaults(func=cmd_off)

    p_status = sub.add_parser("status", help="Durumu gosterir.")
    p_status.set_defaults(func=cmd_status)

    p_tick = sub.add_parser("tick", help="Gerekirse streak commit'i atar.")
    p_tick.add_argument("--force", action="store_true", help="Busy mode kapali olsa da calisir.")
    p_tick.add_argument("--dry-run", action="store_true", help="Git islemi yapmadan plani gosterir.")
    p_tick.add_argument("--note", type=str, default="", help="Bu calisma icin heartbeat notu.")
    p_tick.add_argument("--message", type=str, default="", help="Commit mesaji.")
    p_tick.set_defaults(func=cmd_tick)

    p_maintain = sub.add_parser("maintain", help="Kucuk bakim kaydi commit'i atar.")
    p_maintain.add_argument("--dry-run", action="store_true", help="Git islemi yapmadan plani gosterir.")
    p_maintain.add_argument("--no-push", action="store_true", help="Sadece lokal commit atar.")
    p_maintain.add_argument("--note", type=str, default="", help="Bakim notu.")
    p_maintain.add_argument("--message", type=str, default="", help="Ozel commit mesaji.")
    p_maintain.set_defaults(func=cmd_maintain)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
