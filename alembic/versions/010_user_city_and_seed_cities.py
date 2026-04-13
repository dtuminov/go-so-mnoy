"""Add city_id to users, seed ~100 Russian cities

Revision ID: 010_user_city_and_seed_cities
Revises: 009_moderation_notified
Create Date: 2026-04-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_user_city_and_seed_cities"
down_revision: Union[str, None] = "009_moderation_notified"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (name, slug, timezone)
CITIES: list[tuple[str, str, str]] = [
    # Москва уже засижена в 002, id=1 — пропускаем
    ("Санкт-Петербург", "spb", "Europe/Moscow"),
    ("Новосибирск", "novosibirsk", "Asia/Novosibirsk"),
    ("Екатеринбург", "yekaterinburg", "Asia/Yekaterinburg"),
    ("Казань", "kazan", "Europe/Moscow"),
    ("Нижний Новгород", "nizhny-novgorod", "Europe/Moscow"),
    ("Челябинск", "chelyabinsk", "Asia/Yekaterinburg"),
    ("Самара", "samara", "Europe/Samara"),
    ("Омск", "omsk", "Asia/Omsk"),
    ("Ростов-на-Дону", "rostov-on-don", "Europe/Moscow"),
    ("Уфа", "ufa", "Asia/Yekaterinburg"),
    ("Красноярск", "krasnoyarsk", "Asia/Krasnoyarsk"),
    ("Воронеж", "voronezh", "Europe/Moscow"),
    ("Пермь", "perm", "Asia/Yekaterinburg"),
    ("Волгоград", "volgograd", "Europe/Volgograd"),
    ("Краснодар", "krasnodar", "Europe/Moscow"),
    ("Тюмень", "tyumen", "Asia/Yekaterinburg"),
    ("Саратов", "saratov", "Europe/Saratov"),
    ("Тольятти", "tolyatti", "Europe/Samara"),
    ("Ижевск", "izhevsk", "Europe/Samara"),
    ("Барнаул", "barnaul", "Asia/Barnaul"),
    ("Ульяновск", "ulyanovsk", "Europe/Ulyanovsk"),
    ("Иркутск", "irkutsk", "Asia/Irkutsk"),
    ("Хабаровск", "khabarovsk", "Asia/Vladivostok"),
    ("Ярославль", "yaroslavl", "Europe/Moscow"),
    ("Владивосток", "vladivostok", "Asia/Vladivostok"),
    ("Махачкала", "makhachkala", "Europe/Moscow"),
    ("Томск", "tomsk", "Asia/Tomsk"),
    ("Оренбург", "orenburg", "Asia/Yekaterinburg"),
    ("Кемерово", "kemerovo", "Asia/Novokuznetsk"),
    ("Новокузнецк", "novokuznetsk", "Asia/Novokuznetsk"),
    ("Рязань", "ryazan", "Europe/Moscow"),
    ("Астрахань", "astrakhan", "Europe/Astrakhan"),
    ("Набережные Челны", "naberezhnye-chelny", "Europe/Moscow"),
    ("Пенза", "penza", "Europe/Moscow"),
    ("Липецк", "lipetsk", "Europe/Moscow"),
    ("Киров", "kirov", "Europe/Kirov"),
    ("Чебоксары", "cheboksary", "Europe/Moscow"),
    ("Тула", "tula", "Europe/Moscow"),
    ("Калининград", "kaliningrad", "Europe/Kaliningrad"),
    ("Курск", "kursk", "Europe/Moscow"),
    ("Ставрополь", "stavropol", "Europe/Moscow"),
    ("Улан-Удэ", "ulan-ude", "Asia/Irkutsk"),
    ("Сочи", "sochi", "Europe/Moscow"),
    ("Тверь", "tver", "Europe/Moscow"),
    ("Магнитогорск", "magnitogorsk", "Asia/Yekaterinburg"),
    ("Иваново", "ivanovo", "Europe/Moscow"),
    ("Брянск", "bryansk", "Europe/Moscow"),
    ("Белгород", "belgorod", "Europe/Moscow"),
    ("Сургут", "surgut", "Asia/Yekaterinburg"),
    ("Владимир", "vladimir", "Europe/Moscow"),
    ("Нижний Тагил", "nizhny-tagil", "Asia/Yekaterinburg"),
    ("Архангельск", "arkhangelsk", "Europe/Moscow"),
    ("Чита", "chita", "Asia/Chita"),
    ("Калуга", "kaluga", "Europe/Moscow"),
    ("Смоленск", "smolensk", "Europe/Moscow"),
    ("Волжский", "volzhsky", "Europe/Volgograd"),
    ("Саранск", "saransk", "Europe/Moscow"),
    ("Череповец", "cherepovets", "Europe/Moscow"),
    ("Курган", "kurgan", "Asia/Yekaterinburg"),
    ("Орёл", "orel", "Europe/Moscow"),
    ("Вологда", "vologda", "Europe/Moscow"),
    ("Якутск", "yakutsk", "Asia/Yakutsk"),
    ("Владикавказ", "vladikavkaz", "Europe/Moscow"),
    ("Подольск", "podolsk", "Europe/Moscow"),
    ("Мурманск", "murmansk", "Europe/Moscow"),
    ("Грозный", "grozny", "Europe/Moscow"),
    ("Тамбов", "tambov", "Europe/Moscow"),
    ("Стерлитамак", "sterlitamak", "Asia/Yekaterinburg"),
    ("Петрозаводск", "petrozavodsk", "Europe/Moscow"),
    ("Кострома", "kostroma", "Europe/Moscow"),
    ("Нижневартовск", "nizhnevartovsk", "Asia/Yekaterinburg"),
    ("Новороссийск", "novorossiysk", "Europe/Moscow"),
    ("Йошкар-Ола", "yoshkar-ola", "Europe/Moscow"),
    ("Комсомольск-на-Амуре", "komsomolsk-on-amur", "Asia/Vladivostok"),
    ("Таганрог", "taganrog", "Europe/Moscow"),
    ("Сыктывкар", "syktyvkar", "Europe/Moscow"),
    ("Нальчик", "nalchik", "Europe/Moscow"),
    ("Нижнекамск", "nizhnekamsk", "Europe/Moscow"),
    ("Шахты", "shakhty", "Europe/Moscow"),
    ("Дзержинск", "dzerzhinsk", "Europe/Moscow"),
    ("Братск", "bratsk", "Asia/Irkutsk"),
    ("Энгельс", "engels", "Europe/Saratov"),
    ("Орск", "orsk", "Asia/Yekaterinburg"),
    ("Ангарск", "angarsk", "Asia/Irkutsk"),
    ("Старый Оскол", "stary-oskol", "Europe/Moscow"),
    ("Великий Новгород", "veliky-novgorod", "Europe/Moscow"),
    ("Благовещенск", "blagoveshchensk", "Asia/Yakutsk"),
    ("Королёв", "korolyov", "Europe/Moscow"),
    ("Псков", "pskov", "Europe/Moscow"),
    ("Мытищи", "mytishchi", "Europe/Moscow"),
    ("Люберцы", "lyubertsy", "Europe/Moscow"),
    ("Южно-Сахалинск", "yuzhno-sakhalinsk", "Asia/Sakhalin"),
    ("Балашиха", "balashikha", "Europe/Moscow"),
    ("Армавир", "armavir", "Europe/Moscow"),
    ("Абакан", "abakan", "Asia/Krasnoyarsk"),
    ("Северодвинск", "severodvinsk", "Europe/Moscow"),
    ("Петропавловск-Камчатский", "petropavlovsk-kamchatsky", "Asia/Kamchatka"),
    ("Норильск", "norilsk", "Asia/Krasnoyarsk"),
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

    op.add_column("users", sa.Column(
        "city_id", sa.Integer(), nullable=False, server_default="1",
    ))
    op.create_index(op.f("ix_users_city_id"), "users", ["city_id"])
    op.create_foreign_key(
        "fk_users_city_id_cities",
        "users",
        "cities",
        ["city_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_city_id_cities", "users", type_="foreignkey")
    op.drop_index(op.f("ix_users_city_id"), table_name="users")
    op.drop_column("users", "city_id")
    op.execute("DELETE FROM cities WHERE slug != 'moscow'")
