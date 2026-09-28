#!/bin/bash
# Ожидание завершения Kaggle-ядра, устойчивое к сбоям API.
#
# Наивный `until [ "$st" != "RUNNING" ]` выходит по ПУСТОМУ ответу: Kaggle
# периодически отдаёт 404 на GetKernelSessionStatus, и цикл решает, что прогон
# закончился. Поэтому выходим только по явному терминальному статусу.
SLUG="$1"; MAX="${2:-120}"
for i in $(seq 1 "$MAX"); do
  st=$(kaggle kernels status "$SLUG" 2>/dev/null | grep -oE "COMPLETE|ERROR|CANCEL|RUNNING|QUEUED")
  case "$st" in
    COMPLETE|ERROR|CANCEL) echo "$st"; exit 0 ;;
    RUNNING|QUEUED)        ;;                    # работает — ждём дальше
    *)  echo "…API не ответил (попытка $i), продолжаю ждать" >&2 ;;
  esac
  sleep 30
done
echo "TIMEOUT"; exit 1
