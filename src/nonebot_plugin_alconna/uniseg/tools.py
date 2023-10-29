from base64 import b64decode
from typing import TYPE_CHECKING, List, Type, Union, Optional, overload

from yarl import URL
from nonebot import get_bots
from nonebot.typing import T_State
from nonebot import get_bot as _get_bot
from nonebot.internal.driver.model import Request
from nonebot.internal.adapter import Bot, Event, Adapter

from .segment import Image


async def image_fetch(event: Event, bot: Bot, state: T_State, img: Image):
    adapter_name = bot.adapter.get_name()
    if adapter_name == "RedProtocol":
        origin = img.origin
        if TYPE_CHECKING:
            from nonebot.adapters.red.bot import Bot
            from nonebot.adapters.red.message import MediaMessageSegment

            assert isinstance(bot, Bot)
            assert isinstance(origin, MediaMessageSegment)

        return await origin.download(bot)

    if img.url:  # mirai2, qqguild, kook, villa, feishu, minecraft, ding
        req = Request("GET", img.url)
        resp = await bot.adapter.request(req)
        return resp.content
    if not img.id:
        return None
    if adapter_name == "OneBot V11":
        if TYPE_CHECKING:
            from nonebot.adapters.onebot.v11.bot import Bot

            assert isinstance(bot, Bot)
        url = (await bot.get_image(file=img.id))["data"]["url"]
        req = Request("GET", url)
        resp = await bot.adapter.request(req)
        return resp.content
    if adapter_name == "OneBot V12":
        if TYPE_CHECKING:
            from nonebot.adapters.onebot.v12.bot import Bot

            assert isinstance(bot, Bot)
        resp = (await bot.get_file(type="data", file_id=img.id))["data"]
        return b64decode(resp) if isinstance(resp, str) else bytes(resp)
    if adapter_name == "mirai2":
        url = f"https://gchat.qpic.cn/gchatpic_new/0/0-0-" f"{img.id.replace('-', '').upper()}/0"
        req = Request("GET", url)
        resp = await bot.adapter.request(req)
        return resp.content
    if adapter_name == "Telegram":
        if TYPE_CHECKING:
            from nonebot.adapters.telegram.bot import Bot

            assert isinstance(bot, Bot)
        url = URL(bot.bot_config.api_server) / "file" / f"bot{bot.bot_config.token}" / img.id
        req = Request("GET", url)
        resp = await bot.adapter.request(req)
        return resp.content
    if adapter_name == "ntchat":
        raise NotImplementedError("ntchat image fetch not implemented")


@overload
def get_bot(*, adapter: Union[Type[Adapter], str]) -> List[Bot]:
    ...


@overload
def get_bot(*, bot_id: str) -> Bot:
    ...


@overload
def get_bot(*, adapter: Union[Type[Adapter], str], bot_id: str) -> Bot:
    ...


def get_bot(
    *, adapter: Union[Type[Adapter], str, None] = None, bot_id: Optional[str] = None
) -> Union[List[Bot], Bot]:
    if not adapter:
        return _get_bot(bot_id)
    bots = []
    for bot in get_bots().values():
        _adapter = bot.adapter
        if isinstance(adapter, str):
            if _adapter.get_name() == adapter:
                bots.append(bot)
        elif isinstance(_adapter, adapter):
            bots.append(bot)
    if not bot_id:
        return bots
    return next(bot for bot in bots if bot.self_id == bot_id)