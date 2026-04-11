# Доменная модель (UML, черновик под MVP)

Цель: **события**, **участники**, **«ищу компанию»** отдельно, **города** с первой строкой «Москва», модерация на уровне статусов. Чат внутри события в MVP не моделируем — только связи пользователей.

## PlantUML ([PlantText](https://www.planttext.com) и аналоги)

В PlantText нужен синтаксис **PlantUML**, а не Mermaid. Строки вроде `classDiagram` / `direction TB` относятся к Mermaid и дают ошибку парсера.

Готовый файл для вставки в редактор: **`domain-model.puml`** (рядом с этим файлом). Скопируй содержимое `.puml` в [planttext.com](https://www.planttext.com) — диаграмма должна отрисоваться.

## Диаграмма классов (Mermaid)

```mermaid
classDiagram
    direction TB

    class City {
        +int id
        +string name
        +string slug
        +string timezone
    }

    class User {
        +int id
        +bigint telegram_id
        +datetime created_at
    }

    class Event {
        +int id
        +int city_id
        +int organizer_id
        +string title
        +text description
        +datetime starts_at
        +string place_text
        +string status
        +datetime created_at
    }

    class EventParticipant {
        +int id
        +int event_id
        +int user_id
        +string status
        +datetime created_at
    }

    class CompanySeeking {
        +int id
        +int city_id
        +int author_id
        +string title
        +text body
        +datetime expires_at
        +string status
        +datetime created_at
    }

    class CompanySeekingResponse {
        +int id
        +int seeking_id
        +int user_id
        +datetime created_at
    }

    City "1" --> "*" Event : city
    City "1" --> "*" CompanySeeking : city
    User "1" --> "*" Event : organizes
    User "1" --> "*" EventParticipant : member
    User "1" --> "*" CompanySeeking : author
    User "1" --> "*" CompanySeekingResponse : responder
    Event "1" --> "*" EventParticipant : participants
    CompanySeeking "1" --> "*" CompanySeekingResponse : responses
```

## Статусы (смысл, не обязательно финальные имена в БД)

| Сущность | Статусы (пример) |
|----------|------------------|
| **Event** | `draft` → `pending_review` → `published` / `rejected` / `cancelled` |
| **EventParticipant** | `joined` / `left` (при необходимости позже `pending` от организатора) |
| **CompanySeeking** | как у событий: черновик / на проверке / опубликовано / снято |
| **CompanySeekingResponse** | факт отклика («хочу в компанию») |

## Примечания

- **MVP по городу**: в коде фильтр по `city_id` Москвы; таблица `cities` с одной строкой — задел на выбор городов.
- **Канал → бот**: вне БД в ссылке `?start=event_<id>` или `seek_<id>`; при первом `/start` создаётся/обновляется `User`.
- После согласования полей — отражать изменения в **Alembic** и в **`STRUCTURE.md`**.
