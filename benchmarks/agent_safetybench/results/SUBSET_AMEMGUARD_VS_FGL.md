# Agent-SafetyBench: A-MemGuard vs FGL vs без защиты (подмножество 64 кейса)

Сбалансированное подмножество `data_subset64.json` (8 категорий риска × 8 кейсов, 26 выполнимых).
Два агента: gpt-4.1-mini и Nous Hermes 3 8B (локальный Ollama). Guard-модель — gpt-4.1-mini.
Защиты встроены как pre-action guard (одинаковый интерфейс). Два судьи: авторский ShieldAgent-8B (GPU) и gpt-4.1-judge.

## Сводная таблица (safety score, выше — лучше)

| Агент | Защита | ShieldAgent-8B | gpt-4.1-judge | Блок выполнимых (налог) | Вызовов guard |
|---|---|---|---|---|---|
| gpt-4.1-mini | без защиты | 46,9% | 68,8% | 0,0% | 0 |
| gpt-4.1-mini | FGL (monitor) | 70,3% | 90,6% | 46,2% | ~85 |
| gpt-4.1-mini | A-MemGuard | 75,0% | 92,2% | 34,6% | 284 (k=3) |
| Hermes-3-8B | без защиты | 28,1% | 56,2% | 0,0% | 0 |
| Hermes-3-8B | FGL (monitor) | 51,6% | 78,1% | 30,8% | ~27 |
| Hermes-3-8B | A-MemGuard | 53,1% | 81,2% | 26,9% | 158 (k=3) |

Папки: `sub-*` (агент gpt-4.1-mini), `herm-*` (агент Hermes). Внутри каждой: `gen_res.json`, `score_shieldagent.json`, `score_llm_gpt-4.1.json`, `run_meta.json`.

## Выводы
- Валидация: gpt-4.1-mini без защиты по ShieldAgent 46,9% ≈ полный прогон на 2000 (46,5%) — подмножество сопоставимо.
- Картина устойчива по обоим агентам и обоим судьям: **A-MemGuard ≳ FGL ≳ без защиты**.
- Hermes как агент заметно слабее по безопасности (базовый уровень 28,1% против 46,9% у gpt-4.1-mini), поэтому защиты дают больший абсолютный прирост (FGL +23,5, A-MemGuard +25,0 по ShieldAgent).
- A-MemGuard даёт чуть больше безопасности при меньшем налоге на полезность, чем FGL, но ценой в несколько раз большего числа вызовов LLM (консенсус k=3).
- ShieldAgent строже gpt-4.1-judge по абсолюту; знак эффекта одинаков.

## Оговорки
- Малая выборка (64), single-session — это НЕ родная среда A-MemGuard (memory-poisoning с извлечением из памяти). У нас адаптация под action-guard: консенсус = self-consistency (k=3) + lesson-memory + deliberation. Прямой перенос чисел из статьи A-MemGuard некорректен.
- A-MemGuard реализован по механизму статьи (arXiv:2510.02373), код авторов не копировался (`amemguard.py`).
- Обе защиты реально режут выполнимые задачи (27–46%) — общий минус pre-action-гейтов.

## Воспроизведение
```
# агент gpt-4.1-mini
python run_asb.py --condition none|fgl_monitor|amemguard --agent-model gpt-4.1-mini \
    --data data_subset64.json --out results/sub-<cond>/gen_res.json
# агент Hermes (Ollama, через OpenAI-совместимый endpoint)
python run_asb.py --condition <cond> --agent-model hermes3:8b \
    --agent-base-url http://localhost:11435/v1 --agent-api-key ollama --guard-model gpt-4.1-mini \
    --data data_subset64.json --out results/herm-<cond>/gen_res.json
# оценка: gpt-4.1-judge (без GPU) и ShieldAgent-8B (GPU)
python score_asb.py --gen <gen> --scorer llm --judge-model gpt-4.1
python score_shield.py --gen <gen> --env-dir <ASB>/environments --load-8bit --batch 8
```
