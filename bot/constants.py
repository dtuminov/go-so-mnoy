"""Константы домена (MVP: один город — Москва)."""

# После миграции 002 первая строка в cities — Москва.
MOSCOW_CITY_ID: int = 1

# Activity.kind
ACTIVITY_EVENT = "event"
ACTIVITY_SEEKING = "seeking"

# Activity.status (lifecycle модерации)
ACTIVITY_DRAFT = "draft"
ACTIVITY_PENDING_REVIEW = "pending_review"
ACTIVITY_PUBLISHED = "published"
ACTIVITY_REJECTED = "rejected"
ACTIVITY_CANCELLED = "cancelled"
ACTIVITY_CLOSED = "closed"  # для seeking — автор сам закрыл

# Activity.visibility
VISIBILITY_OPEN = "open"
VISIBILITY_PRIVATE = "private"

# ActivityMember.status
MEMBER_PENDING = "pending"
MEMBER_JOINED = "joined"
