# Развёртывание

## Требования

* Docker Engine 24+ с Compose v2.
* CPU: от 8 ядер (модель на CPU), RAM: от 16 ГБ (qwen3:4b ≈ 3 ГБ, qwen3:8b ≈ 6 ГБ), диск: 20 ГБ.
* Исходящий доступ в интернет: поисковики (через SearXNG), сайты источников, адреса санкционных
  списков (`methodology/sanctions-sources.yaml`), реестр моделей Ollama.

## Установка

```bash
git clone … ipdl && cd ipdl
cp .env.example .env
# POSTGRES_PASSWORD=$(openssl rand -hex 24)   SEARXNG_SECRET=$(openssl rand -hex 32)
# IPDL_LLM__MODEL=qwen3:4b (CPU) или qwen3:8b (GPU)
docker compose up -d --build
docker compose logs -f migrate worker        # миграции, загрузка санкционных списков
docker compose exec api ipdl users create admin --role admin
```

Интерфейс слушает `127.0.0.1:${IPDL_WEB_PORT:-3000}`. Публиковать его — только через
обратный прокси с HTTPS (cookie сессии имеют флаг `Secure`).

### Caddy

```caddyfile
ipdl.example.org {
	encode zstd gzip
	header {
		Strict-Transport-Security "max-age=31536000"
		-Server
	}
	reverse_proxy 127.0.0.1:3000
}
```

Доступ стоит дополнительно ограничить (VPN, белый список IP или Cloudflare Access) — система
предназначена для служебного пользования.

## Первичная настройка

```bash
docker compose exec api ipdl partners add --country UZ --name "…"   # зарубежные ПФР
docker compose exec api ipdl users create ivanova --role analyst --display-name "Иванова А."
docker compose exec api ipdl sanctions update                        # принудительно обновить
docker compose exec api ipdl methodology                             # проверить справочники
```

Пользователей-партнёров удобнее создавать в интерфейсе («Администрирование»), указав ПФР.

Служебные учётные записи (например, для чата Consultant) создаются из скриптов: пароль — из
stdin, повторный запуск приводит роль и пароль к заданным, не создавая дубликат:

```bash
printf '%s\n' "$SERVICE_PASSWORD" |
  docker compose exec -T api ipdl users create consultant-svc --role analyst --password-stdin --exist-ok
```

## Обновление

```bash
git pull && docker compose up -d --build     # migrate применит новые миграции
```

## Сопровождение

| Что | Когда | Как |
|---|---|---|
| Санкционные списки | ежедневно, 03:15 UTC (автоматически) | `ipdl sanctions update`; состояние — страница «Санкции» |
| Перечни FATF | после пленарных заседаний (февраль, июнь, октябрь) | обновить `methodology/jurisdictions.yaml`, пересобрать образ |
| Перечень льготного налогообложения | при изменении приказа МФ РК | там же |
| Методика | по решению ответственного за методику | `methodology/risk-model.yaml`, новая версия `id` |
| Резервные копии | ежедневно | `docker compose exec postgres pg_dump -U ipdl ipdl \| gzip > ipdl-$(date +%F).sql.gz` |

## Мониторинг

`GET /readyz` (база, очередь), `GET /metrics` (Prometheus: длительность HTTP, портреты по
статусам и длительности, обновления списков, попытки входа). Логи — JSON в stdout.

## GPU

Для NVIDIA добавьте ollama `deploy.resources.reservations.devices` (driver: nvidia) и
используйте `IPDL_LLM__MODEL=qwen3:8b` или крупнее; `IPDL_LLM__MAX_SOURCES` можно увеличить.
