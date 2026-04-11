"""Константы домена (MVP: один город — Москва)."""

# После миграции 002 первая строка в cities — Москва.
MOSCOW_CITY_ID: int = 1

# События
EVENT_DRAFT = "draft"
EVENT_PENDING_REVIEW = "pending_review"
EVENT_PUBLISHED = "published"
EVENT_REJECTED = "rejected"
EVENT_CANCELLED = "cancelled"

# Участие
PARTICIPANT_JOINED = "joined"
PARTICIPANT_LEFT = "left"

# «Ищу компанию»
SEEKING_DRAFT = "draft"
SEEKING_PENDING_REVIEW = "pending_review"
SEEKING_PUBLISHED = "published"
SEEKING_CLOSED = "closed"
