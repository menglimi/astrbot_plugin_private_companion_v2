import enum
from dataclasses import dataclass, field
from typing import Any, Optional

from . import open_live as open_models
from . import web as web_models


class MessageType(enum.Enum):
    """消息类型枚举"""

    DANMAKU = "danmaku"  # 弹幕
    GIFT = "gift"  # 礼物
    SUPER_CHAT = "super_chat"  # 醒目留言
    LIKE = "like"  # 点赞
    ENTER_ROOM = "enter_room"  # 进入直播间
    GUARD_BUY = "guard_buy"  # 上舰


@dataclass
class BiliMessage:
    """
    B站消息标准化基类
    所有平台的消息都会被转换为此类的子类实例
    """

    type: MessageType = MessageType.DANMAKU
    """消息类型"""
    platform: str = ""
    """消息来源平台，如 'web', 'open_live'"""
    room_id: int = 0
    """直播间ID"""
    timestamp: int = 0
    """消息时间戳（秒）"""
    msg_id: str = ""
    """消息唯一ID"""
    user_id: str = ""
    """用户ID"""
    user_name: str = ""
    """用户名"""
    raw_data: Optional[dict[str, Any]] = None
    """原始消息数据"""


@dataclass
class DanmakuMessage(BiliMessage):
    """弹幕消息"""

    type: MessageType = MessageType.DANMAKU
    user_id: str = ""
    """用户ID"""
    user_name: str = ""
    """用户名"""
    user_face: str = ""
    """用户头像URL"""
    content: str = ""
    """弹幕内容"""
    guard_level: int = 0
    """舰队等级，0非舰队，1总督，2提督，3舰长"""
    medal_level: int = 0
    """粉丝勋章等级"""
    medal_name: str = ""
    """粉丝勋章名称"""
    is_admin: bool = False
    """是否为房管"""
    dm_type: int = 0
    """弹幕类型：0文本，1表情，2语音"""
    emoticon: dict[str, Any] = field(default_factory=dict)
    """表情信息（dm_type 为 1 时包含 emoticon_unique/url 等）"""

    @classmethod
    def from_web_message(
        cls, message: web_models.DanmakuMessage, room_id: int, raw_data: dict
    ) -> "DanmakuMessage":
        """从Web平台消息转换"""
        return cls(
            platform="web",
            room_id=room_id,
            timestamp=message.timestamp,
            msg_id=str(message.rnd),
            raw_data=raw_data,
            user_id=str(message.uid),
            user_name=message.uname,
            user_face=message.face,
            content=message.msg,
            guard_level=message.privilege_type,
            medal_level=message.medal_level,
            medal_name=message.medal_name,
            is_admin=message.admin == 1,
            dm_type=getattr(message, "dm_type", 0),
            emoticon=getattr(message, "emoticon_options_dict", {}),
        )

    @classmethod
    def from_open_live_message(
        cls, message: open_models.DanmakuMessage, raw_data: dict
    ) -> "DanmakuMessage":
        """从开放平台消息转换"""
        emoticon: dict[str, Any] = {}
        if (
            getattr(message, "dm_type", 0) == 1
            and getattr(message, "emoji_img_url", "")
        ):
            emoticon = {"url": message.emoji_img_url}
        return cls(
            platform="open_live",
            room_id=message.room_id,
            timestamp=message.timestamp,
            msg_id=message.msg_id,
            raw_data=raw_data,
            user_id=message.open_id,
            user_name=message.uname,
            user_face=message.uface,
            content=message.msg,
            guard_level=message.guard_level,
            medal_level=message.fans_medal_level,
            medal_name=message.fans_medal_name,
            is_admin=message.is_admin == 1,
            dm_type=getattr(message, "dm_type", 0),
            emoticon=emoticon,
        )


@dataclass
class GiftMessage(BiliMessage):
    """礼物消息"""

    type: MessageType = MessageType.GIFT
    user_id: str = ""
    """用户ID"""
    user_name: str = ""
    """用户名"""
    user_face: str = ""
    """用户头像URL"""
    gift_id: int = 0
    """礼物ID"""
    gift_name: str = ""
    """礼物名称"""
    gift_num: int = 0
    """礼物数量"""
    price: int = 0
    """礼物单价（1000 = 1元）"""
    paid: bool = False
    """是否为付费礼物"""

    @classmethod
    def from_web_message(
        cls, message: web_models.GiftMessage, room_id: int, raw_data: dict
    ) -> "GiftMessage":
        """从Web平台消息转换"""
        return cls(
            platform="web",
            room_id=room_id,
            timestamp=message.timestamp,
            msg_id=str(message.rnd),  # 既然上面的rnd当msg_id了这个也当了
            raw_data=raw_data,
            user_id=str(message.uid),
            user_name=message.uname,
            user_face=message.face,
            gift_id=message.gift_id,
            gift_name=message.gift_name,
            gift_num=message.num,
            price=message.price,
            paid=True if message.coin_type == "gold" else False,
        )

    @classmethod
    def from_open_live_message(
        cls, message: open_models.GiftMessage, raw_data: dict
    ) -> "GiftMessage":
        """从开放平台消息转换"""
        return cls(
            platform="open_live",
            room_id=message.room_id,
            timestamp=message.timestamp,
            msg_id=message.msg_id,
            raw_data=raw_data,
            user_id=message.open_id,
            user_name=message.uname,
            user_face=message.uface,
            gift_id=message.gift_id,
            gift_name=message.gift_name,
            gift_num=message.gift_num,
            price=message.price,
            paid=message.paid,
        )


@dataclass
class SuperChatMessage(BiliMessage):
    """醒目留言消息"""

    type: MessageType = MessageType.SUPER_CHAT
    user_id: str = ""
    """用户ID"""
    user_name: str = ""
    """用户名"""
    user_face: str = ""
    """用户头像URL"""
    message_id: int = 0
    """留言ID"""
    message: str = ""
    """留言内容"""
    price: int = 0
    """价格（元）"""
    start_time: int = 0
    """开始时间戳"""
    end_time: int = 0
    """结束时间戳"""

    @classmethod
    def from_web_message(
        cls, message: web_models.SuperChatMessage, room_id: int, raw_data: dict
    ) -> "SuperChatMessage":
        """从Web平台消息转换"""
        return cls(
            platform="web",
            room_id=room_id,
            timestamp=message.start_time,
            msg_id=str(message.id),
            raw_data=raw_data,
            user_id=str(message.uid),
            user_name=message.uname,
            user_face=message.face,
            message_id=message.id,
            message=message.message,
            price=message.price,
            start_time=message.start_time,
            end_time=message.end_time,
        )

    @classmethod
    def from_open_live_message(
        cls, message: open_models.SuperChatMessage, raw_data: dict
    ) -> "SuperChatMessage":
        """从开放平台消息转换"""
        return cls(
            platform="open_live",
            room_id=message.room_id,
            timestamp=message.timestamp,
            msg_id=message.msg_id,
            raw_data=raw_data,
            user_id=message.open_id,
            user_name=message.uname,
            user_face=message.uface,
            message_id=message.message_id,
            message=message.message,
            price=message.rmb,
            start_time=message.start_time,
            end_time=message.end_time,
        )


@dataclass
class LikeMessage(BiliMessage):
    """点赞消息"""

    type: MessageType = MessageType.LIKE
    user_id: str = ""
    """用户ID"""
    user_name: str = ""
    """用户名"""
    user_face: str = ""
    """用户头像URL"""
    like_text: str = ""
    """点赞文案"""
    like_count: int = 0
    """点赞次数"""

    @classmethod
    def from_web_message(
        cls, message: web_models.InteractWordMessage, room_id: int, raw_data: dict
    ) -> "LikeMessage":
        """从Web平台消息转换"""
        return cls(
            platform="web",
            room_id=room_id,
            timestamp=message.timestamp,
            msg_id="",  # 不抓包了
            raw_data=raw_data,
            user_id=str(message.uid),
            user_name=message.username,
            user_face=message.face,
            like_text="为主播点赞了",
            like_count=1,  # 不抓包了
        )

    @classmethod
    def from_open_live_message(
        cls, message: open_models.LikeMessage, raw_data: dict
    ) -> "LikeMessage":
        """从开放平台消息转换"""
        return cls(
            platform="open_live",
            room_id=message.room_id,
            timestamp=message.timestamp,
            msg_id=message.msg_id,
            raw_data=raw_data,
            user_id=message.open_id,
            user_name=message.uname,
            user_face=message.uface,
            like_text=message.like_text,
            like_count=message.like_count,
        )


@dataclass
class EnterRoomMessage(BiliMessage):
    """进入直播间消息"""

    type: MessageType = MessageType.ENTER_ROOM
    user_id: str = ""
    """用户ID"""
    user_name: str = ""
    """用户名"""
    user_face: str = ""
    """用户头像URL"""

    @classmethod
    def from_web_message(
        cls, message: web_models.InteractWordMessage, room_id: int, raw_data: dict
    ) -> Optional["EnterRoomMessage"]:
        """从Web平台消息转换"""
        return cls(
            platform="web",
            room_id=room_id,
            timestamp=message.timestamp,
            msg_id="",  # 不抓包了
            raw_data=raw_data,
            user_id=str(message.uid),
            user_name=message.username,
            user_face=message.face,
        )

    @classmethod
    def from_open_live_message(
        cls, message: open_models.EnterRoomMessage, raw_data: dict
    ) -> "EnterRoomMessage":
        """从开放平台消息转换"""
        return cls(
            platform="open_live",
            room_id=message.room_id,
            timestamp=message.timestamp,
            msg_id=message.msg_id,
            raw_data=raw_data,
            user_id=message.open_id,
            user_name=message.uname,
            user_face=message.uface,
        )


@dataclass
class GuardBuyMessage(BiliMessage):
    """上舰消息"""

    type: MessageType = MessageType.GUARD_BUY
    user_id: str = ""
    """用户ID"""
    user_name: str = ""
    """用户名"""
    user_face: str | None = ""
    """用户头像URL"""
    guard_level: int = 0
    """大航海等级，0非舰队，1总督，2提督，3舰长"""
    guard_num: int = 0
    """上舰数量（月数）"""
    guard_unit: str = "月"
    """大航海单位(正常单位为"月"，如为其他内容则以此为准)"""
    price: int = 0
    """价格（金瓜子）"""
    gift_id: int = 0
    """礼物ID"""
    gift_name: str = ""
    """礼物名称"""

    @classmethod
    def from_web_message(
        cls, message: web_models.GuardBuyMessage, room_id: int, raw_data: dict
    ) -> "GuardBuyMessage":
        """从Web平台消息转换"""
        return cls(
            platform="web",
            room_id=room_id,
            timestamp=message.start_time,
            msg_id="",  # Web平台没有这个字段
            raw_data=raw_data,
            user_id=str(message.uid),
            user_name=message.username,
            user_face="",  # Web平台没有这个字段
            guard_level=message.guard_level,
            guard_num=message.num,
            guard_unit="月",  # Web平台没有这个字段，默认为"月"
            price=message.price,
            gift_id=message.gift_id,
            gift_name=message.gift_name,
        )

    @classmethod
    def from_open_live_message(
        cls, message: open_models.GuardBuyMessage, raw_data: dict
    ) -> "GuardBuyMessage":
        """从开放平台消息转换"""
        return cls(
            platform="open_live",
            room_id=message.room_id,
            timestamp=message.timestamp,
            msg_id=message.msg_id,
            raw_data=raw_data,
            user_id=message.user_info.open_id,
            user_name=message.user_info.uname,
            user_face=message.user_info.uface,
            guard_level=message.guard_level,
            guard_num=message.guard_num,
            guard_unit=message.guard_unit,
            price=0,  # 开放平台没有这个字段
            gift_id=0,  # 开放平台没有这个字段
            gift_name="",  # 开放平台没有这个字段
        )
