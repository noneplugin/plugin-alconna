"""通用标注, 无法用于创建 MS对象"""

import re
import abc
import json
import contextlib
from io import BytesIO
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from dataclasses import field, asdict, dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Type,
    Tuple,
    Union,
    Generic,
    Literal,
    TypeVar,
    Callable,
    Iterable,
    Optional,
    overload,
)

from nonebot.internal.adapter import Message, MessageSegment
from nepattern import MatchMode, BasePattern, create_local_patterns

from .utils import fleep

if TYPE_CHECKING:
    from .message import UniMessage


TS = TypeVar("TS", bound="Segment")
TS1 = TypeVar("TS1", bound="Segment")


class UniPattern(BasePattern[TS, MessageSegment], Generic[TS]):
    additional: Optional[Callable[..., bool]] = None

    def __init__(self):
        origin: Type[TS] = self.__class__.__orig_bases__[0].__args__[0]  # type: ignore

        def _converter(_, seg: MessageSegment) -> Optional[TS]:
            if (res := self.solve(seg)) and not hasattr(res, "origin"):
                res.origin = seg
            return res

        super().__init__(
            mode=MatchMode.TYPE_CONVERT,
            origin=origin,
            converter=_converter,
            alias=origin.__name__,
            accepts=MessageSegment,
            validators=[self.additional] if self.additional else [],
        )

    def solve(self, seg: MessageSegment) -> Optional[TS]:
        raise NotImplementedError


class Segment:
    """基类标注"""

    if TYPE_CHECKING:
        origin: MessageSegment  # = field(init=False, repr=False, compare=False)

    def __str__(self):
        return f"[{self.__class__.__name__.lower()}]"

    def __repr__(self):
        attrs = ", ".join(f"{k}={v!r}" for k, v in self.data.items())
        return f"{self.__class__.__name__}({attrs})"

    @overload
    def __add__(self: TS, item: str) -> "UniMessage[Union[TS, Text]]": ...

    @overload
    def __add__(self: TS, item: Union[TS, Iterable[TS]]) -> "UniMessage[TS]": ...

    @overload
    def __add__(self: TS, item: Union[TS1, Iterable[TS1]]) -> "UniMessage[Union[TS, TS1]]": ...

    def __add__(self: TS, item: Union[str, Union[TS, TS1], Iterable[Union[TS, TS1]]]) -> "UniMessage":
        from .message import UniMessage

        return UniMessage(self) + item

    @overload
    def __radd__(self: TS, item: str) -> "UniMessage[Union[Text, TS]]": ...

    @overload
    def __radd__(self: TS, item: Union[TS, Iterable[TS]]) -> "UniMessage[TS]": ...

    @overload
    def __radd__(self: TS, item: Union[TS1, Iterable[TS1]]) -> "UniMessage[Union[TS1, TS]]": ...

    def __radd__(self: TS, item: Union[str, Union[TS, TS1], Iterable[Union[TS, TS1]]]) -> "UniMessage":
        from .message import UniMessage

        return UniMessage(item) + self

    def is_text(self) -> bool:
        return False

    @property
    def type(self) -> str:
        return self.__class__.__name__.lower()

    @property
    def data(self) -> Dict[str, Any]:
        try:
            return asdict(self)  # type: ignore
        except TypeError:
            return vars(self)


@dataclass
class Text(Segment):
    """Text对象, 表示一类文本元素"""

    text: str
    styles: Dict[Tuple[int, int], List[str]] = field(default_factory=dict)

    def __post_init__(self):
        self.text = str(self.text)

    def is_text(self) -> bool:
        return True

    def __merge__(self):
        data = {}
        styles = self.styles
        if not styles:
            return
        for scale, _styles in styles.items():
            for i in range(*scale):
                if i not in data:
                    data[i] = _styles[:]
                else:
                    data[i].extend(s for s in _styles if s not in data[i])
        styles.clear()
        data1 = {}
        for i, _styles in data.items():
            key = "\x01".join(_styles)
            data1.setdefault(key, []).append(i)
        data.clear()
        for key, indexes in data1.items():
            start = indexes[0]
            end = start
            for i in indexes[1:]:
                if i - end == 1:
                    end = i
                else:
                    data[(start, end + 1)] = key.split("\x01")
                    start = end = i
            if end >= start:
                data[(start, end + 1)] = key.split("\x01")
        for scale in sorted(data.keys()):
            styles[scale] = data[scale]

    def mark(self, start: int, end: int, *styles: str):
        _styles = self.styles.setdefault((start, end), [])
        for sty in styles:
            if sty not in _styles:
                _styles.append(sty)
        self.__merge__()
        return self

    def __str__(self) -> str:
        result = []
        text = self.text
        styles = self.styles
        if not styles:
            return text
        self.__merge__()
        scales = sorted(styles.keys(), key=lambda x: x[0])
        left = scales[0][0]
        result.append(text[:left])
        for scale in scales:
            prefix = "".join(f"<{style}>" for style in styles[scale])
            suffix = "".join(f"</{style}>" for style in reversed(styles[scale]))
            result.append(prefix + text[scale[0] : scale[1]] + suffix)
        right = scales[-1][1]
        result.append(text[right:])
        text = "".join(result)
        pat = re.compile(r"</(\w+)(?<!/p)><\1>")
        for _ in range(max(map(len, styles.values()))):
            text = pat.sub("", text)
        return text

    def extract_most_style(self):
        if not self.styles:
            return ""
        max_scale = max(self.styles, key=lambda x: x[1] - x[0], default=(0, 0))
        return self.styles[max_scale][0]


@dataclass
class At(Segment):
    """At对象, 表示一类提醒某用户的元素"""

    flag: Literal["user", "role", "channel"]
    target: str
    display: Optional[str] = field(default=None)


@dataclass
class AtAll(Segment):
    """AtAll对象, 表示一类提醒所有人的元素"""

    here: bool = field(default=False)


@dataclass
class Emoji(Segment):
    """Emoji对象, 表示一类表情元素"""

    id: str
    name: Optional[str] = field(default=None)


@dataclass
class Media(Segment):
    id: Optional[str] = field(default=None)
    url: Optional[str] = field(default=None)
    path: Optional[Union[str, Path]] = field(default=None)
    raw: Optional[Union[bytes, BytesIO]] = field(default=None)
    mimetype: Optional[str] = field(default=None)
    name: Optional[str] = field(default=None)

    def __post_init__(self):
        if self.path:
            self.name = Path(self.path).name
        if self.url and not urlparse(self.url).hostname:
            self.url = f"https://{self.url}"

    @property
    def raw_bytes(self) -> bytes:
        if not self.raw:
            raise ValueError(f"{self} has no raw data")
        raw = self.raw.getvalue() if isinstance(self.raw, BytesIO) else self.raw
        header = raw[:128]
        info = fleep.get(header)
        self.mimetype = info.mimes[0] if info.mimes else self.mimetype
        if info.types and info.extensions:
            self.name = f"{info.types[0]}.{info.extensions[0]}"
        return raw


@dataclass
class Image(Media):
    """Image对象, 表示一类图片元素"""

    name: str = field(default="image.png")


@dataclass
class Audio(Media):
    """Audio对象, 表示一类音频元素"""

    duration: Optional[int] = field(default=None)
    name: str = field(default="audio.mp3")


@dataclass
class Voice(Media):
    """Voice对象, 表示一类语音元素"""

    duration: Optional[int] = field(default=None)
    name: str = field(default="voice.wav")


@dataclass
class Video(Media):
    """Video对象, 表示一类视频元素"""

    name: str = field(default="video.mp4")


@dataclass
class File(Media):
    """File对象, 表示一类文件元素"""

    name: str = field(default="file.bin")


@dataclass
class Reply(Segment):
    """Reply对象，表示一类回复消息"""

    id: str
    """此处不一定是消息ID，可能是其他ID，如消息序号等"""
    msg: Optional[Union[Message, str]] = field(default=None)
    origin: Optional[Any] = field(default=None)


@dataclass
class RefNode:
    """表示转发消息的引用消息元素"""

    id: str
    context: Optional[str] = None


@dataclass
class CustomNode:
    """表示转发消息的自定义消息元素"""

    uid: str
    name: str
    time: datetime
    content: Union[str, List[Segment], Message]


@dataclass
class Reference(Segment):
    """Reference对象，表示一类引用消息。转发消息 (Forward) 也属于此类"""

    id: Optional[str] = field(default=None)
    """此处不一定是消息ID，可能是其他ID，如消息序号等"""
    content: Optional[Union[Message, str, List[Union[RefNode, CustomNode]]]] = field(default=None)


@dataclass
class Hyper(Segment):
    """Hyper对象，表示一类超级消息。如卡片消息、ark消息、小程序等"""

    format: Literal["xml", "json"]
    raw: Optional[str] = field(default=None)
    content: Optional[Union[dict, list]] = field(default=None)

    def __post_init__(self):
        if self.raw and not self.content and self.format == "json":
            with contextlib.suppress(json.JSONDecodeError):
                self.content = json.loads(self.raw)
        if self.content and not self.raw and self.format == "json":
            with contextlib.suppress(json.JSONDecodeError):
                self.raw = json.dumps(self.content, ensure_ascii=False)


TM = TypeVar("TM", bound=Message)


@dataclass
class Custom(Segment, abc.ABC):
    """Custom对象，表示一类自定义消息"""

    mstype: str
    content: Any

    @abc.abstractmethod
    def export(self, msg_type: Type[TM]) -> MessageSegment[TM]: ...

    @property
    def type(self) -> str:
        return self.mstype


TCustom = TypeVar("TCustom", bound=Custom)


class _Custom(UniPattern[Custom]):
    BUILDERS: Dict[Union[str, Callable[[MessageSegment], bool]], Callable[[MessageSegment], Union[Custom, None]]] = {}

    @classmethod
    def custom_register(cls, custom_type: Type[TCustom], condition: Union[str, Callable[[MessageSegment], bool]]):
        def _register(func: Callable[[MessageSegment], Union[TCustom, None]]):
            cls.BUILDERS[condition] = func
            return func

        return _register

    def solve(self, seg: MessageSegment):
        for condition, func in self.BUILDERS.items():
            if isinstance(condition, str):
                if seg.type == condition:
                    return func(seg)
            elif condition(seg):
                return func(seg)


custom = _Custom()
custom_register = custom.custom_register


@dataclass
class Other(Segment):
    """其他 Segment"""

    origin: MessageSegment

    def __str__(self):
        return f"[{self.origin.type}]"


class _Other(UniPattern[Other]): ...


other = _Other()


class _Text(UniPattern[Text]): ...


text = _Text()


class _At(UniPattern[At]): ...


at = _At()


class _AtAll(UniPattern[AtAll]): ...


at_all = _AtAll()


class _Emoji(UniPattern[Emoji]): ...


emoji = _Emoji()


class _Image(UniPattern[Image]): ...


image = _Image()


class _Video(UniPattern[Video]): ...


video = _Video()


class _Voice(UniPattern[Voice]): ...


voice = _Voice()


class _Audio(UniPattern[Audio]): ...


audio = _Audio()


class _File(UniPattern[File]): ...


file = _File()


class _Reply(UniPattern[Reply]): ...


reply = _Reply()


class _Reference(UniPattern[Reference]): ...


reference = _Reference()


class _Card(UniPattern[Hyper]): ...


card = _Card()

segments = [at_all, at, emoji, image, video, voice, audio, file, reference, card, text, custom, other]
env = create_local_patterns("nonebot")
env.sets(segments)


class _Segment(UniPattern[Segment]): ...


env[Segment] = _Segment()
