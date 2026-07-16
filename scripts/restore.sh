#!/usr/bin/env sh
set -eu
if [ "${CONFIRM_RESTORE:-}" != "YES" ]; then
  echo "Restore не запущен: требуется CONFIRM_RESTORE=YES и отдельное disposable окружение."
  exit 1
fi
echo "Основное окружение автоматически не перезаписывается. Используйте restore_check.py для проверки backup."
exit 1
