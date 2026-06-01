"""
Скрипт для исправления установки, скачанной как zip-архив.

Если при /update бот пишет "Это не Git репозиторий!" — значит ты установил
бота через скачивание zip. Этот скрипт превратит твою папку в git-репозиторий
и подключит её к GitHub, чтобы автообновления заработали.

Использование:
    python fix_git_repo.py

Скрипт сохранит твои настройки (configs/, storage/, plugins/, logs/, docs/),
а остальные файлы возьмёт с GitHub.
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

REPO_URL = "https://github.com/etheriumflipper/StarvellCardinal.git"
BRANCH = "main"

# Папки, которые нужно сохранить (твои личные данные)
PROTECTED_DIRS = ["configs", "storage", "plugins", "logs", "docs"]


def run(cmd, cwd=None, check=True):
    """Запустить shell-команду."""
    print(f"$ {cmd}")
    result = subprocess.run(
        cmd, shell=True, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="ignore"
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0 and check:
        if result.stderr.strip():
            print(f"ОШИБКА: {result.stderr.strip()}")
        sys.exit(1)
    return result


def main():
    here = Path.cwd()
    print("=" * 60)
    print(" Starvell Cardinal — починка git-репозитория")
    print("=" * 60)
    print(f"Текущая папка: {here}")
    print()

    # Проверяем, что мы в правильной папке
    if not (here / "main.py").exists():
        print("ОШИБКА: Не найден main.py. Запусти скрипт из папки Starvell Cardinal.")
        sys.exit(1)

    # Проверяем, есть ли уже .git
    if (here / ".git").exists():
        print("✓ Папка .git уже существует. Репозиторий настроен.")
        ans = input("Проверить remote и подтянуть обновления? (y/n): ").strip().lower()
        if ans == "y":
            run("git remote -v")
            run(f"git fetch origin {BRANCH}")
            run(f"git reset --hard origin/{BRANCH}")
            print("✓ Готово! Автообновление должно работать.")
        return

    print("⚠️  Папка .git не найдена. Скорее всего, ты установил бота через zip.")
    print("Сейчас я превращу эту папку в git-репозиторий.")
    print()
    ans = input("Продолжить? (y/n): ").strip().lower()
    if ans != "y":
        print("Отменено.")
        return

    # Сохраняем защищённые папки во временную папку
    backup_dir = here.parent / "starvell_backup_temp"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    backup_dir.mkdir()

    print()
    print("💾 Сохраняю личные данные...")
    for d in PROTECTED_DIRS:
        src = here / d
        if src.exists():
            dst = backup_dir / d
            shutil.move(str(src), str(dst))
            print(f"  ✓ {d}/ сохранён")

    # Инициализируем git
    print()
    print("🔧 Инициализирую git-репозиторий...")
    run("git init")
    run(f"git remote add origin {REPO_URL}")
    run(f"git fetch origin {BRANCH}")
    run(f"git checkout -b {BRANCH} origin/{BRANCH} --force")

    # Восстанавливаем папки
    print()
    print("📦 Восстанавливаю личные данные...")
    for d in PROTECTED_DIRS:
        src = backup_dir / d
        dst = here / d
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.move(str(src), str(dst))
            print(f"  ✓ {d}/ восстановлен")

    # Удаляем временную папку
    try:
        shutil.rmtree(backup_dir)
    except Exception:
        pass

    print()
    print("=" * 60)
    print("✅ Готово! Теперь автообновления будут работать.")
    print("Проверь: /update в чате с ботом")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        sys.exit(1)
