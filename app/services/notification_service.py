from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories import HomeworkRepository

_MONTHS_RU = (
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


@dataclass(frozen=True)
class DigestItem:
    subject: str
    title: str


class NotificationService:
    """Сбор и форматирование информации о дедлайнах для рассылки в группу."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = HomeworkRepository(session)

    async def collect_digest(self, group_id: int, target: date) -> list[DigestItem]:
        homeworks = await self._repo.list_due_on(group_id, target)
        subject_names = await self._repo.subject_names_grouped(group_id, homeworks)
        return [
            DigestItem(subject=subject_names[h.subject_id], title=h.title)
            for h in homeworks
        ]

    def build_digest_text(self, target: date, items: list[DigestItem]) -> str:
        if not items:
            return ""
        lines = [
            "🔔 ДЕДЛАЙНЫ НА ЗАВТРА",
            "",
            f"📅 {target.day} {_MONTHS_RU[target.month - 1]}",
            "",
        ]
        for item in items:
            lines.append(f"📚 {item.subject}")
            lines.append(item.title)
            lines.append("")
        lines.append(f"📊 Всего заданий: {len(items)}")
        return "\n".join(lines).rstrip()


def format_deadline(deadline: date) -> str:
    return f"{deadline.day}.{deadline.month:02d}.{deadline.year}"
