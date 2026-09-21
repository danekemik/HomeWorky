"""Русские названия месяцев в разных падежах (единый источник)."""

_MONTHS_NOMINATIVE = (
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)

_MONTHS_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

_MONTHS_GENITIVE_SHORT = (
    "янв.",
    "февр.",
    "марта",
    "апр.",
    "мая",
    "июня",
    "июля",
    "авг.",
    "сент.",
    "окт.",
    "нояб.",
    "дек.",
)


def month_nominative(month: int) -> str:
    return _MONTHS_NOMINATIVE[month - 1]


def russian_month_name(month: int) -> str:
    return _MONTHS_GENITIVE[month - 1]


def russian_month_name_short(month: int) -> str:
    return _MONTHS_GENITIVE_SHORT[month - 1]
