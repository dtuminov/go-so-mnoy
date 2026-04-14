"""Add Moscow suburbs and other missing cities

Revision ID: 011_more_cities
Revises: 010_user_city_and_seed_cities
Create Date: 2026-04-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_more_cities"
down_revision: Union[str, None] = "010_user_city_and_seed_cities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (name, slug, timezone)
CITIES: list[tuple[str, str, str]] = [
    # Подмосковье
    ("Химки", "khimki", "Europe/Moscow"),
    ("Одинцово", "odintsovo", "Europe/Moscow"),
    ("Красногорск", "krasnogorsk", "Europe/Moscow"),
    ("Домодедово", "domodedovo", "Europe/Moscow"),
    ("Щёлково", "shchyolkovo", "Europe/Moscow"),
    ("Долгопрудный", "dolgoprudny", "Europe/Moscow"),
    ("Реутов", "reutov", "Europe/Moscow"),
    ("Жуковский", "zhukovsky", "Europe/Moscow"),
    ("Пушкино", "pushkino", "Europe/Moscow"),
    ("Раменское", "ramenskoye", "Europe/Moscow"),
    ("Сергиев Посад", "sergiev-posad", "Europe/Moscow"),
    ("Ногинск", "noginsk", "Europe/Moscow"),
    ("Коломна", "kolomna", "Europe/Moscow"),
    ("Электросталь", "elektrostal", "Europe/Moscow"),
    ("Серпухов", "serpukhov", "Europe/Moscow"),
    ("Обнинск", "obninsk", "Europe/Moscow"),
    ("Видное", "vidnoye", "Europe/Moscow"),
    ("Лобня", "lobnya", "Europe/Moscow"),
    ("Ивантеевка", "ivanteevka", "Europe/Moscow"),
    ("Фрязино", "fryazino", "Europe/Moscow"),
    ("Дубна", "dubna", "Europe/Moscow"),
    ("Клин", "klin", "Europe/Moscow"),
    ("Чехов", "chekhov", "Europe/Moscow"),
    ("Наро-Фоминск", "naro-fominsk", "Europe/Moscow"),
    ("Егорьевск", "yegoryevsk", "Europe/Moscow"),
    ("Дмитров", "dmitrov", "Europe/Moscow"),
    ("Котельники", "kotelniki", "Europe/Moscow"),
    ("Дзержинский", "dzerzhinskiy-mo", "Europe/Moscow"),
    # Пригороды Питера
    ("Колпино", "kolpino", "Europe/Moscow"),
    ("Пушкин", "pushkin-spb", "Europe/Moscow"),
    ("Петергоф", "peterhof", "Europe/Moscow"),
    ("Гатчина", "gatchina", "Europe/Moscow"),
    ("Выборг", "vyborg", "Europe/Moscow"),
    ("Всеволожск", "vsevolozhsk", "Europe/Moscow"),
    # Другие крупные пригороды
    ("Березники", "berezniki", "Asia/Yekaterinburg"),
    ("Каменск-Уральский", "kamensk-uralsky", "Asia/Yekaterinburg"),
    ("Первоуральск", "pervouralsk", "Asia/Yekaterinburg"),
    ("Миасс", "miass", "Asia/Yekaterinburg"),
    ("Копейск", "kopeysk", "Asia/Yekaterinburg"),
    ("Бердск", "berdsk", "Asia/Novosibirsk"),
    ("Батайск", "bataysk", "Europe/Moscow"),
    ("Новочеркасск", "novocherkassk", "Europe/Moscow"),
]


def upgrade() -> None:
    cities_table = sa.table(
        "cities",
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("timezone", sa.String),
    )
    op.bulk_insert(cities_table, [
        {"name": name, "slug": slug, "timezone": tz}
        for name, slug, tz in CITIES
    ])


def downgrade() -> None:
    slugs = [slug for _, slug, _ in CITIES]
    quoted = ", ".join(f"'{s}'" for s in slugs)
    op.execute(f"DELETE FROM cities WHERE slug IN ({quoted})")
