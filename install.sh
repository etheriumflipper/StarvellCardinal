#!/usr/bin/env bash
set -euo pipefail

APP_NAME="Starvell Cardinal"
SERVICE_NAME="starvell-cardinal"
APP_USER="starvell"
APP_GROUP="starvell"
INSTALL_DIR="/opt/starvell-cardinal"
ENV_FILE="/etc/starvell-cardinal.env"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
REPOSITORY_URL="https://github.com/etheriumflipper/StarvellCardinal.git"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_SOURCE_DIR="$SOURCE_DIR"
SELF_ARGS=("$@")

log() {
    printf '[INFO] %s\n' "$1"
}

warn() {
    printf '[WARN] %s\n' "$1"
}

fail() {
    printf '[ERROR] %s\n' "$1" >&2
    exit 1
}

require_linux() {
    if [[ "$(uname -s)" != "Linux" ]]; then
        fail "install.sh предназначен только для Linux."
    fi
}

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        exec sudo bash "$0" "${SELF_ARGS[@]}"
    fi
}

prepare_source_dir() {
    if [[ -f "$SOURCE_DIR/main.py" && -f "$SOURCE_DIR/requirements.txt" ]]; then
        WORK_SOURCE_DIR="$SOURCE_DIR"
        return
    fi

    local temp_dir
    temp_dir="$(mktemp -d)"
    log "Локальный код проекта не найден, клонирую $REPOSITORY_URL ..."
    git clone --branch main --single-branch "$REPOSITORY_URL" "$temp_dir/repo"
    WORK_SOURCE_DIR="$temp_dir/repo"
}

install_packages() {
    export DEBIAN_FRONTEND=noninteractive
    log "Устанавливаю системные пакеты..."
    apt-get update
    apt-get install -y python3 python3-venv python3-pip git rsync
}

ensure_user() {
    if ! getent group "$APP_GROUP" >/dev/null 2>&1; then
        groupadd --system "$APP_GROUP"
    fi

    if ! id -u "$APP_USER" >/dev/null 2>&1; then
        useradd \
            --system \
            --gid "$APP_GROUP" \
            --create-home \
            --home-dir "/var/lib/${SERVICE_NAME}" \
            --shell /usr/sbin/nologin \
            "$APP_USER"
    fi
}

sync_project() {
    log "Копирую проект в $INSTALL_DIR ..."
    mkdir -p "$INSTALL_DIR"

    if [[ "$WORK_SOURCE_DIR" != "$INSTALL_DIR" ]]; then
        rsync -a --delete \
            --exclude 'venv/' \
            --exclude '__pycache__/' \
            --exclude '*.pyc' \
            --exclude 'configs/_main.cfg' \
            --exclude 'logs/*.log' \
            --exclude 'logs/*.txt' \
            --exclude 'storage/*.json' \
            --exclude 'storage/*/*.json' \
            --exclude 'storage/*/*/*.json' \
            "$WORK_SOURCE_DIR/" "$INSTALL_DIR/"
    else
        warn "install.sh запущен из каталога установки, копирование файлов пропущено."
    fi

    mkdir -p \
        "$INSTALL_DIR/configs" \
        "$INSTALL_DIR/logs" \
        "$INSTALL_DIR/storage/cache" \
        "$INSTALL_DIR/storage/products" \
        "$INSTALL_DIR/storage/settings" \
        "$INSTALL_DIR/storage/stats"
}

reset_runtime_state_if_needed() {
    if [[ -f "$INSTALL_DIR/configs/_main.cfg" ]]; then
        return
    fi

    log "Свежая установка без конфига: очищаю старый runtime state..."
    find "$INSTALL_DIR/logs" -maxdepth 1 -type f \( -name '*.log' -o -name '*.txt' \) -delete 2>/dev/null || true
    find "$INSTALL_DIR/storage" -type f \( -name '*.json' -o -name '*.txt' \) -delete 2>/dev/null || true
    find "$INSTALL_DIR/cache" -type f \( -name '*.json' -o -name '*.txt' \) -delete 2>/dev/null || true
}

setup_python() {
    if [[ ! -x "$INSTALL_DIR/venv/bin/python" ]]; then
        log "Создаю виртуальное окружение..."
        python3 -m venv "$INSTALL_DIR/venv"
    fi

    log "Устанавливаю Python-зависимости..."
    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
    "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
}

write_env_file() {
    if [[ ! -f "$ENV_FILE" ]]; then
        log "Создаю $ENV_FILE ..."
        cat > "$ENV_FILE" <<'EOF'
# Optional update source for Starvell Cardinal.
# Example:
# STARVELL_VERSION_URL=https://example.com/version.py
STARVELL_VERSION_URL=https://raw.githubusercontent.com/etheriumflipper/StarvellCardinal/main/version.py
EOF
    fi

    chown root:"$APP_GROUP" "$ENV_FILE"
    chmod 640 "$ENV_FILE"
}

run_first_setup() {
    if [[ -s "$INSTALL_DIR/configs/_main.cfg" ]]; then
        log "Конфиг уже существует, первичную настройку пропускаю."
        return
    fi

    log "Запускаю первичную настройку от пользователя $APP_USER ..."
    runuser -u "$APP_USER" -- bash -lc "cd '$INSTALL_DIR' && '$INSTALL_DIR/venv/bin/python' first_setup.py"

    if [[ ! -s "$INSTALL_DIR/configs/_main.cfg" ]]; then
        fail "Первичная настройка не создала configs/_main.cfg."
    fi
}

write_service() {
    log "Создаю systemd unit..."
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Starvell Cardinal Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-$ENV_FILE
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/main.py
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
}

enable_service() {
    log "Активирую systemd service..."
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl restart "$SERVICE_NAME"
}

fix_permissions() {
    chown -R "$APP_USER:$APP_GROUP" "$INSTALL_DIR"
}

print_summary() {
    cat <<EOF

================================
$APP_NAME установлен
================================

Каталог: $INSTALL_DIR
Сервис:  $SERVICE_NAME

Команды управления:
  sudo systemctl status $SERVICE_NAME
  sudo systemctl restart $SERVICE_NAME
  sudo systemctl stop $SERVICE_NAME
  sudo journalctl -u $SERVICE_NAME -f

Ручной запуск:
  cd $INSTALL_DIR
  ./start.sh
EOF
}

main() {
    require_linux
    require_root
    install_packages
    prepare_source_dir
    ensure_user
    sync_project
    reset_runtime_state_if_needed
    setup_python
    fix_permissions
    write_env_file
    run_first_setup
    write_service
    enable_service
    print_summary
}

main
