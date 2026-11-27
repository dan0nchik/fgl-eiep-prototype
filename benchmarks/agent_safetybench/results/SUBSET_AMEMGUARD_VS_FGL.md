# Agent-SafetyBench: A-MemGuard vs FGL vs без защиты (подмножество 64 кейса)

Сбалансированное подмножество `data_subset64.json` (8 категорий риска × 8 кейсов, 26 выполнимых).
Агент — gpt-4.1-mini, guard-модель — gpt-4.1-mini. Защиты встроены как pre-action guard (одинаковый интерфейс).

| Условие | ShieldAgent-8B safe | gpt-4.1-judge safe | Блок выполнимых (налог) | Вызовов guard | Артефакт |
|---|---|---|---|---|---|
| Без защиты | 46,9% | 68,8% | 0,0% | 0 | `sub-none/` |
| FGL (monitor) | 70,3% | 90,6% | 46,2% | ~85 | `sub-fgl_monitor/` |
| A-MemGuard | 75,0% | 92,2% | 34,6% | 284 (k=3) + 29 уроков | `sub-amemguard/` |

Каждая папка: `gen_res.json` (трассы), `score_shieldagent.json` (авторский судья), `score_llm_gpt-4.1.json` (кросс-судья), `run_meta.json`.

## Выводы
- Валидация: «без защиты» по ShieldAgent 46,9% ≈ полный прогон на 2000 (46,5%) — подмножество сопоставимо.
- Оба судьи согласны: A-MemGuard ≳ FGL ≳ без защиты.
- A-MemGuard даёт больше безопасности (+28,1 п.п. vs +23,4) при меньшем налоге на полезность (34,6% vs 46,2%), но ценой ~3× вызовов LLM (консенсус k=3).
- ShieldAgent строже gpt-4.1-judge по абсолюту; знак эффекта одинаков.

## Оговорки
- Малая выборка (64), single-session — это НЕ родная среда A-MemGuard (memory-poisoning с извлечением из памяти). У нас адаптация под action-guard: консенсус = self-consistency (k=3) + lesson-memory + deliberation. Прямой перенос чисел из статьи A-MemGuard некорректен.
- A-MemGuard реализован по механизму статьи (arXiv:2510.02373), код авторов не копировался (`amemguard.py`).
- Обе защиты реально режут выполнимые задачи (34–46%) — общий минус pre-action-гейтов.

## Воспроизведение
```
# прогон (агент + guard)
python run_asb.py --condition none|fgl_monitor|amemguard --agent-model gpt-4.1-mini \
    --data data_subset64.json --out results/sub-<cond>/gen_res.json
# оценка (локальный судья, без GPU)
python score_asb.py --gen results/sub-<cond>/gen_res.json --scorer llm --judge-model gpt-4.1
# оценка (авторский ShieldAgent-8B, нужен GPU)
python score_shield.py --gen <gen> --env-dir <ASB>/environments --load-8bit --batch 8
```
