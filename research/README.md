# Исследовательская часть ML

Эксперименты, из которых выросли итоговые модели и логика «камеры → этап работ».

- Итоговые веса и их инференс: [`../ml/release/jepa-models-2026-09-28`](../ml/release/jepa-models-2026-09-28).
- Обоснование выбора моделей: [`../docs/Обоснование_моделей.pdf`](../docs/Обоснование_моделей.pdf).

Все команды ниже запускаются из каталога `research/`.

## Документы

| файл | о чём |
|---|---|
| `docs/ML_PLAN.md` | план ML-части: что измерено, данные, сравнение моделей, аугментации |
| `docs/ARCH.md` | свои архитектуры: P2-голова, P2slim, DGP-Net, иерархия классов, приор размера |
| `docs/ZEROSHOT_RESULTS.md` | zero-shot YOLO: 25 моделей × 3 сплита |
| `docs/STAGE_FUSION.md` | камеры → этап работ → сверка с планом |

## Код

| путь | что делает |
|---|---|
| `ml/kaggle/compare_yolo.*` | Kaggle-ноутбук: сравнение весов YOLO по mAP |
| `ml/kaggle/weights_fetch/` | Kaggle-ядро: офлайн-бандл весов (на Kaggle нет интернета) |
| `ml/kaggle/zeroshot/` | Kaggle-ядро: zero-shot таблица 25 × 3 |
| `ml/kaggle/finetune/finetune_cell.py` | одна ячейка дообучения, с неё начинался отбор 35 чекпойнтов из PDF |
| `ml/kaggle/klog.py`, `kwait.sh` | чтение логов и ожидание Kaggle-ядер |
| `ml/scripts/augment.py`, `aug_demo.py` | 6 групп доменных аугментаций и их витрина (`ml/runs/augs.jpg`) |
| `ml/scripts/preannotate.py` | предразметка кадров кейса через YOLOE + банк вырезок техники |
| `ml/scripts/copypaste.py`, `synth.py` | copy-paste: вставка вырезанной техники в реальные кадры |
| `ml/scripts/dgpnet.py`, `dgp_dataset.py`, `dgp_train.py` | DGP-Net: детектор + головы этапа и условий съёмки, trainer |
| `ml/scripts/bench_arch.py` | цена P2-головы и отказа от P5 |
| `ml/scripts/hierarchy.py`, `scale_prior.py` | иерархия классов, приор по физическим габаритам |
| `ml/scripts/probe.py`, `openvocab_probe.py` | первые пробы: предобученный YOLO, open-vocabulary |
| `ml/stage/` | камеры → этап; вход — `api.SiteAnalyzer`, мост классов итогового каскада — `api.JEPA_22` |
| `ml/configs/` | таксономия, маппинг классов датасетов, ранние правила «этап → техника», yaml моделей P2slim |
| `ml/runs/` | картинки и графики результатов |
| `data/stage_equipment.md` | матрица «этап XLSX → техника»: источник правды для `ml/stage` |

## Чего нет в репозитории

- **Кадры кейса.** В монорепо они лежат в `../data/ml` под DVC. Скриптам их можно передать через `--img-dir ../data/ml` или скопировать в `data/raw/screenshots`.
- **Датасет №8** — Kaggle `nickpudovkin/const-video-v2i-yolo26`, ожидается в `data/external/const_video`.
- **Веса `*.pt`.** ultralytics скачивает их сам.
- **Json-результаты из `ml/runs/`.** Они пересчитываются скриптами.

## Запуск

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# без датасетов — хватает data/stage_equipment.md
python ml/stage/experiments.py          # синтетические эксперименты «камеры → этап», ~70 с
python ml/stage/new_equipment_demo.py   # добавить технику в md без правки кода

# с датасетом №8
kaggle datasets download nickpudovkin/const-video-v2i-yolo26 -p data/external/const_video --unzip
python ml/stage/demo.py                 # 8 камер → этап → сверка с планом
python ml/stage/api.py                  # пример JSON-отчёта
python ml/stage/plots.py                # графики → ml/runs/stage/
```

Ноутбуки из `ml/kaggle/` запускаются на Kaggle. Датасеты подключаются как входы ядра, веса берутся из офлайн-бандла `weights_fetch`.
