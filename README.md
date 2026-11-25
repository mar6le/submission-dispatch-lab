# Передавання підтверджень для навчальних подань

Сервіс приймає POST /submissions з полями `group_code` та `submission_key`. Приклад коду — SE-31. SQLite утримує один запис на ключ. Новий POST дає 201, повтор того самого ключа для тієї самої групи — 200 з початковим номером. GET /submissions/<id> читає подання. Дані у всіх серіях синтетичні.

v1.2.0 повертає номер одразу після транзакції. v2.2.0 додає імітований стан доставки `queued` та посилання `reference`. Режим `closed` імітує недоступність підтвердження. Відповідь POST має код 503 і збережений номер, а окремий /health повертає 200.

## Перевірки випусків

Потрібні Python 3.12+, Docker, Docker Compose і curl. Випуски зібрано для Linux ARM64.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
python lab.py test --timeout 45
```

У CI крок **Verify submission behavior** запускає pytest через subprocess. Bash із pipefail повертає помилку тестів, навіть якщо вивід передали до tee. Коли тест /health навмисно очікує HTTP 418, крок **Package tested image** пропускається. Успішне пакування запускає окреме завдання, яке звіряє SHA-256 і прикріплює архіви до GitHub Releases.

- [Випуск v1.2.0](https://github.com/mar6le/submission-dispatch-lab/actions/runs/45614093605)
- [Випуск v2.2.0](https://github.com/mar6le/submission-dispatch-lab/actions/runs/45614141865)
- [Діагностика контрольного падіння](https://github.com/mar6le/submission-dispatch-lab/actions/runs/45614147386/job/139205080400)

## Завантаження та перевірка на staging

Команди завантаження потрібні для чистої копії. Якщо папки `local-artifacts/v1` і `local-artifacts/v2` вже містять образи, переходь до циклу. Скрипт доставки перевіряє SHA-256 архіву та ID образу.

```bash
gh release download v1.2.0 -D local-artifacts/v1
gh release download v2.2.0 -D local-artifacts/v2

for version in v1 v2; do
  bash scripts/deliver.sh "local-artifacts/$version" staging
  container=$(docker compose -p dispatch-stage ps -q stage)
  python -m pytest -q --hosts="docker://$container" infra
  key="smoke-$version-$(date +%s)"
  curl -fsSi --max-time 4 -H 'Content-Type: application/json' \
    -d "{\"group_code\":\"SE-31\",\"submission_key\":\"$key\"}" \
    http://127.0.0.1:8391/submissions
done
```

Staging працює зі своїм томом SQLite і режимом ready. Обидва POST мають повернути 201. У відповіді v2 також буде `delivery`. Робочі v1 та v2 мають спільний постійний том.

## Контроль частки запитів і відкат

Оператор оцінює серію з 200 новими ключами. Потрібні щонайменше 20 спроб на v2, частка помилок до 5% та p95 до 160 мс. Помилкою вважається відповідь 5xx або відсутня відповідь. p95 обчислюється серед завершених відповідей. SLI вимірює частку всіх спроб з 201 до 1 с, навчальний SLO становить 99%. Клієнт має тайм-аут 2 с та паузу 50 мс. У змішаній серії кожна десята спроба надходить до v2.

```bash
prefix="dispatch-$(date +%s)"
out="results/$prefix"
bash scripts/deliver.sh local-artifacts/v1 working
docker compose -p dispatch-work up -d prometheus
python scripts/traffic.py baseline --prefix "$prefix" --output "$out"
LAB_DISPATCH_MODE=closed bash scripts/deliver.sh local-artifacts/v2 working
python scripts/traffic.py canary --prefix "$prefix" --output "$out" &
traffic=$!
sleep 2
docker stats --no-stream $(docker compose -p dispatch-work ps -q v1 v2)
wait "$traffic"
sleep 2
python scripts/metrics.py --output "$out/canary-prometheus.json"
```

За перевищення ліміту оператор залишає запити на v1 і зупиняє v2. Далі виконується третя серія.

```bash
docker compose -p dispatch-work stop v2
python scripts/traffic.py rollback --prefix "$prefix" --output "$out"
docker compose -p dispatch-work logs --no-log-prefix v1 v2 | awk '/^[{]/' > "$out/submissions.jsonl"
python lab.py summarize "$out/submissions.jsonl"
python lab.py summarize "$out/absent.jsonl"
```

У canary.csv знайди рядок v2 зі статусом 503. За request_id знайди три події у журналі. Лічильник CLI враховує лише `submission_response`. Підстав номер та ключ з CSV у GET і POST на v1. Для збереженого експерименту це №290 та `dispatch-2511-canary-090`.

```bash
curl -fsSi --max-time 4 http://127.0.0.1:8381/submissions/290
curl -fsSi --max-time 4 -H 'Content-Type: application/json' \
  -d '{"group_code":"SE-31","submission_key":"dispatch-2511-canary-090"}' \
  http://127.0.0.1:8381/submissions
docker compose -p dispatch-work --profile working down
docker compose -p dispatch-stage --profile staging down
```

Замір з трьох серій та пов’язані журнали доступні у [evidence](evidence/). Під час вимкнення контейнерів томи залишаються на машині.

## Підготовка

ШІ допоміг з чернеткою реалізації, тестів і звіту. Остаточні показники та висновки отримано з реальних запусків pytest, Testinfra, GitHub Actions, Prometheus і HTTP-клієнта.
