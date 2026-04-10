from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет. Каркас бота запущен — дальше сценарии из <code>bot.md</code>.",
    )
