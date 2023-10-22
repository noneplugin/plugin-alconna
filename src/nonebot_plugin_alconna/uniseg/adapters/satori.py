from typing import TYPE_CHECKING, Union

from tarina import lang
from nonebot.adapters import Bot

from ..export import MessageExporter, SerializeFailed, export
from ..segment import At, File, Text, AtAll, Audio, Image, Reply, Video, Voice, RefNode, Reference

if TYPE_CHECKING:
    from nonebot.adapters.satori.message import MessageSegment


class SatoriMessageExporter(MessageExporter["MessageSegment"]):
    def get_message_type(self):
        from nonebot.adapters.satori.message import Message

        return Message

    @classmethod
    def get_adapter(cls) -> str:
        return "Satori"

    @export
    async def text(self, seg: Text, bot: Bot) -> "MessageSegment":
        from nonebot.adapters.satori.message import STYLE_TYPE_MAP

        ms = self.segment_class

        if not seg.style:
            return ms.text(seg.text)
        if seg.style == "br" or seg.text == "\n":
            return ms.br()
        if seg.style in STYLE_TYPE_MAP:
            seg_cls, seg_type = STYLE_TYPE_MAP[seg.style]
            return seg_cls(seg_type, {"text": seg.text})
        if hasattr(ms, seg.style):
            return getattr(ms, seg.style)(seg.text)
        raise SerializeFailed(lang.require("nbp-uniseg", "invalid_segment").format(type=seg.style, seg=seg))

    @export
    async def at(self, seg: At, bot: Bot) -> "MessageSegment":
        ms = self.segment_class
        if seg.flag == "role":
            return ms.at_role(seg.target, seg.display)
        if seg.flag == "channel":
            return ms.sharp(seg.target, seg.display)
        return ms.at(seg.target, seg.display)

    @export
    async def at_all(self, seg: AtAll, bot: Bot) -> "MessageSegment":
        ms = self.segment_class
        return ms.at_all(seg.here)

    @export
    async def res(self, seg: Union[Image, Voice, Video, Audio, File], bot: Bot) -> "MessageSegment":
        ms = self.segment_class

        name = seg.__class__.__name__.lower()
        method = {
            "image": ms.image,
            "voice": ms.audio,
            "video": ms.video,
            "audio": ms.audio,
            "file": ms.file,
        }[name]
        if seg.id or seg.url:
            return method(url=seg.id or seg.url)
        if seg.path:
            return method(path=seg.path)
        if seg.raw and seg.raw.get("mimetype"):
            return method(raw={"data": seg.raw["data"], "mime": seg.raw["mimetype"]})
        raise SerializeFailed(lang.require("nbp-uniseg", "invalid_segment").format(type=name, seg=seg))

    @export
    async def reply(self, seg: Reply, bot: Bot) -> "MessageSegment":
        ms = self.segment_class

        return ms.quote(seg.id, content=seg.msg)  # type: ignore

    @export
    async def reference(self, seg: Reference, bot: Bot) -> "MessageSegment":
        ms = self.segment_class
        if isinstance(seg.content, str):
            content = self.get_message_type()(seg.content)
        elif isinstance(seg.content, list):
            content = self.get_message_type()()
            for node in seg.content:
                if isinstance(node, RefNode):
                    content.append(ms.message(node.id))
                else:
                    _content = self.get_message_type()()
                    _content.append(ms.author(node.uid, node.name))
                    if isinstance(node.content, str):
                        _content.extend(self.get_message_type()(node.content))
                    elif isinstance(node.content, list):
                        _content.extend(await self.__call__(node.content, bot, True))  # type: ignore
                    else:
                        _content.extend(node.content)
                    content.append(ms.message(content=_content))
        else:
            content = seg.content
        return ms.message(seg.id, bool(seg.content), content)
