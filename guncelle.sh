#!/usr/bin/env bash
set -Eeuo pipefail

log() {
  printf "[guncelle] %s\n" "$1"
}

die() {
  printf "[guncelle][hata] %s\n" "$1" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "'$1' kurulu degil."
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_PATH="${DEPLOY_PATH:-$SCRIPT_DIR}"
DEPLOY_REMOTE="${DEPLOY_REMOTE:-origin}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
PM2_APP_NAME="${PM2_APP_NAME:-telegram-streak-bot}"
BOT_ENTRY="${BOT_ENTRY:-telegram_streak_bot.py}"
ALLOW_DIRTY="${ALLOW_DIRTY:-false}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --path)
      DEPLOY_PATH="$2"
      shift 2
      ;;
    --remote)
      DEPLOY_REMOTE="$2"
      shift 2
      ;;
    --branch)
      DEPLOY_BRANCH="$2"
      shift 2
      ;;
    --app)
      PM2_APP_NAME="$2"
      shift 2
      ;;
    --entry)
      BOT_ENTRY="$2"
      shift 2
      ;;
    --allow-dirty)
      ALLOW_DIRTY=true
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Kullanim:
  ./guncelle.sh [--path DIR] [--remote origin] [--branch main] [--app NAME] [--entry FILE] [--allow-dirty]

Ne yapar:
  1) Git fetch + fast-forward pull
  2) PM2 process restart (yoksa start)
  3) PM2 save
EOF
      exit 0
      ;;
    *)
      die "Bilinmeyen parametre: $1"
      ;;
  esac
done

require_cmd git
require_cmd pm2
require_cmd python3

cd "$DEPLOY_PATH" || die "Deploy path bulunamadi: $DEPLOY_PATH"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "Bu klasor bir git reposu degil: $DEPLOY_PATH"
[[ -f "$BOT_ENTRY" ]] || die "Bot giris dosyasi yok: $BOT_ENTRY"

if [[ "$ALLOW_DIRTY" != "true" ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    die "Calisma agacinda degisiklik var. Temizleyin veya --allow-dirty kullanin."
  fi
fi

log "Fetch: $DEPLOY_REMOTE/$DEPLOY_BRANCH"
git fetch "$DEPLOY_REMOTE" "$DEPLOY_BRANCH"

if git show-ref --verify --quiet "refs/heads/$DEPLOY_BRANCH"; then
  git checkout "$DEPLOY_BRANCH"
else
  git checkout -b "$DEPLOY_BRANCH" "$DEPLOY_REMOTE/$DEPLOY_BRANCH"
fi

CURRENT_SHA="$(git rev-parse --short HEAD 2>/dev/null || true)"
log "Pull (ff-only): $DEPLOY_REMOTE/$DEPLOY_BRANCH"
git pull --ff-only "$DEPLOY_REMOTE" "$DEPLOY_BRANCH"
NEW_SHA="$(git rev-parse --short HEAD 2>/dev/null || true)"

if pm2 describe "$PM2_APP_NAME" >/dev/null 2>&1; then
  log "PM2 restart: $PM2_APP_NAME"
  pm2 restart "$PM2_APP_NAME" --update-env
else
  log "PM2 start: $PM2_APP_NAME"
  pm2 start "$BOT_ENTRY" --name "$PM2_APP_NAME" --interpreter python3 --cwd "$DEPLOY_PATH"
fi

pm2 save >/dev/null

log "Tamamlandi. Commit: ${CURRENT_SHA:-none} -> ${NEW_SHA:-none}"
pm2 status "$PM2_APP_NAME"
