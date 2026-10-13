import asyncio
import datetime
import hashlib
import weakref
from typing import Any, Optional, Awaitable

import aiohttp

from astrbot.api import logger

from ..models import message
from ..models import web as web_models
from . import ws_base


NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
WBI_INIT_URL = NAV_URL
UID_INIT_URL = "https://api.bilibili.com/x/web-interface/nav"
BUVID_INIT_URL = "https://www.bilibili.com/"
ROOM_INIT_URL = "https://api.live.bilibili.com/room/v1/Room/get_info"
DANMAKU_SERVER_CONF_URL = "https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo"

DEFAULT_DANMAKU_SERVER_LIST = [
    {
        "host": "broadcastlv.chat.bilibili.com",
        "port": 2243,
        "wss_port": 443,
        "ws_port": 2244,
    }
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36"


_session_to_wbi_signer = weakref.WeakKeyDictionary()


def _get_wbi_signer(session: aiohttp.ClientSession) -> "_WbiSigner":
    wbi_signer = _session_to_wbi_signer.get(session, None)
    if wbi_signer is None:
        wbi_signer = _session_to_wbi_signer[session] = _WbiSigner(session)
    return wbi_signer


class _WbiSigner:
    """WBI签名器，用于对请求参数进行签名"""

    WBI_KEY_INDEX_TABLE = [
        46,
        47,
        18,
        2,
        53,
        8,
        23,
        32,
        15,
        50,
        10,
        31,
        58,
        3,
        45,
        35,
        27,
        43,
        5,
        49,
        33,
        9,
        42,
        19,
        29,
        28,
        14,
        39,
        12,
        38,
        41,
        13,
    ]
    """wbi密码表"""

    WBI_KEY_TTL = datetime.timedelta(hours=11, minutes=59, seconds=30)
    """WBI密钥有效期"""

    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        self._wbi_key = ""
        """缓存的wbi鉴权口令"""
        self._refresh_future: Optional[Awaitable] = None
        """用来避免同时刷新"""
        self._last_refresh_time: Optional[datetime.datetime] = None

    @property
    def wbi_key(self):
        """缓存的wbi鉴权口令"""
        return self._wbi_key

    def reset(self):
        """重置WBI密钥缓存"""
        self._wbi_key = ""
        self._last_refresh_time = None

    @property
    def need_refresh_wbi_key(self):
        """检查是否需要刷新WBI密钥"""
        return self._wbi_key == "" or (
                self._last_refresh_time is not None
                and datetime.datetime.now() - self._last_refresh_time >= self.WBI_KEY_TTL
        )

    def refresh_wbi_key(self) -> Awaitable:
        """刷新WBI密钥"""
        if self._refresh_future is None:
            self._refresh_future = asyncio.create_task(self._do_refresh_wbi_key())

            def on_done(_fu):
                self._refresh_future = None
            self._refresh_future.add_done_callback(on_done)

        return self._refresh_future

    async def _do_refresh_wbi_key(self):
        """执行WBI密钥刷新"""
        wbi_key = await self._get_wbi_key()
        if wbi_key == "":
            return

        self._wbi_key = wbi_key
        self._last_refresh_time = datetime.datetime.now()

    async def _get_wbi_key(self):
        """获取WBI密钥"""
        try:
            async with self._session.get(
                    WBI_INIT_URL,
                    headers={"User-Agent": USER_AGENT},
            ) as res:
                if res.status != 200:
                    logger.warning("WbiSigner failed to get wbi key: status=%d %s", res.status, res.reason)
                    return ""
                data = await res.json()
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
            logger.exception("WbiSigner failed to get wbi key:")
            return ""

        try:
            wbi_img = data["data"]["wbi_img"]
            img_key = wbi_img["img_url"].rpartition("/")[2].partition(".")[0]
            sub_key = wbi_img["sub_url"].rpartition("/")[2].partition(".")[0]
        except KeyError:
            logger.warning("WbiSigner failed to get wbi key: data=%s", data)
            return ""

        shuffled_key = img_key + sub_key
        wbi_key = []
        for index in self.WBI_KEY_INDEX_TABLE:
            if index < len(shuffled_key):
                wbi_key.append(shuffled_key[index])
        return "".join(wbi_key)

    def add_wbi_sign(self, params: dict):
        """为请求参数添加WBI签名"""
        if self._wbi_key == "":
            return params

        wts = str(int(datetime.datetime.now().timestamp()))
        params_to_sign = {**params, "wts": wts}

        # 按key字典序排序
        params_to_sign = {
            key: params_to_sign[key]
            for key in sorted(params_to_sign.keys())
        }
        # 过滤一些字符
        for key, value in params_to_sign.items():
            value = "".join(
                ch
                for ch in str(value)
                if ch not in "!'()*"
            )
            params_to_sign[key] = value

        import urllib.parse
        str_to_sign = urllib.parse.urlencode(params_to_sign) + self._wbi_key
        w_rid = hashlib.md5(str_to_sign.encode("utf-8")).hexdigest()
        return {
            **params,
            "wts": wts,
            "w_rid": w_rid
        }


class WebClient(ws_base.WebSocketClientBase):
    """
    web端客户端

    :param room_id: URL中的房间ID，可以用短ID
    :param uid: B站用户ID，0表示未登录
    :param session: 连接池
    :param heartbeat_interval: 发送心跳包的间隔时间（秒）
    :param cookie_str: cookies字符串，例如 'SESSDATA=xxx; buvid3=yyy; bili_jct=zzz'
    """

    def __init__(
            self,
            room_id: int,
            *,
            uid: Optional[int] = None,
            session: Optional[aiohttp.ClientSession] = None,
            heartbeat_interval=30,
            cookie_str: Optional[str] = None,
    ):
        super().__init__(session, heartbeat_interval)

        self._tmp_room_id = room_id
        """用来init_room的临时房间ID，可以用短ID"""
        self._uid = uid
        self._cookies = self._parse_cookie_str(cookie_str) if cookie_str else {}
        """从cookie字符串解析出的cookies字典"""

        # 在调用init_room后初始化的字段
        self._room_owner_uid: Optional[int] = None
        """主播用户ID"""
        self._host_server_list: Optional[list[dict]] = None
        """
        弹幕服务器列表

        `[{host: "tx-bj4-live-comet-04.chat.bilibili.com", port: 2243, wss_port: 443, ws_port: 2244}, ...]`
        """
        self._host_server_token: Optional[str] = None
        """连接弹幕服务器用的token"""

    @property
    def tmp_room_id(self) -> int:
        """构造时传进来的room_id参数"""
        return self._tmp_room_id

    @property
    def room_owner_uid(self) -> Optional[int]:
        """主播用户ID，调用init_room后初始化"""
        return self._room_owner_uid

    @property
    def uid(self) -> Optional[int]:
        """当前登录的用户ID，未登录则为0，调用init_room后初始化"""
        return self._uid

    @staticmethod
    def _parse_cookie_str(cookie_str: str) -> dict[str, str]:
        """
        解析cookie字符串为字典
        例如："SESSDATA=xxx; buvid3=yyy" -> {"SESSDATA": "xxx", "buvid3": "yyy"}

        :param cookie_str: cookie字符串
        :return: cookie字典
        """
        if not cookie_str:
            return {}

        cookies = {}
        for item in cookie_str.split(";"):
            item = item.strip()
            if not item:
                continue

            parts = item.split("=", 1)
            if len(parts) != 2:
                continue

            name = parts[0].strip()
            value = parts[1].strip()
            if name:
                cookies[name] = value

        return cookies

    async def init_room(self):
        """
        初始化连接房间需要的字段

        :return: True代表没有降级，如果需要降级后还可用，重载这个函数返回True
        """
        if self._cookies and self._session:
            for name, value in self._cookies.items():
                self._session.cookie_jar.update_cookies({name: value})

        result = True

        # 初始化UID
        if self._uid is None:
            if not await self._init_uid():
                logger.warning("room=%d _init_uid() failed", self._tmp_room_id)
                self._uid = 0

        # 确保有buvid
        if self._get_buvid() == "":
            logger.warning("room=%d Missing buvid", self._tmp_room_id)

        # 初始化房间信息
        room_init_success = await self._init_room_id_and_owner()
        if not room_init_success:
            result = False
            # 失败降级
            self._room_id = self._tmp_room_id
            self._room_owner_uid = 0

        # 初始化弹幕服务器信息
        host_server_success = await self._init_host_server()
        if not host_server_success:
            result = False
            # 失败降级
            self._host_server_list = DEFAULT_DANMAKU_SERVER_LIST
            self._host_server_token = None

        return result

    async def _init_uid(self):
        """初始化用户ID"""
        # 检查是否手动指定了SESSDATA cookie
        if "SESSDATA" not in self._cookies or not self._cookies["SESSDATA"]:
            return False

        try:
            response, data = await self._api_request("GET", UID_INIT_URL)
            if not response or not data:
                return False

            if data["code"] == -101:
                # 未登录
                self._uid = 0
                return True

            if data["code"] != 0:
                logger.warning(
                    "room=%d _init_uid() failed, message=%s",
                    self._tmp_room_id,
                    data["message"],
                )
                return False

            data = data["data"]
            self._uid = 0 if not data["isLogin"] else data["mid"]
            return True
        except Exception:
            logger.exception("room=%d _init_uid() failed:", self._tmp_room_id)
            return False

    def _get_buvid(self):
        """获取buvid"""
        if "buvid3" in self._cookies:
            return self._cookies["buvid3"]
        return ""

    async def _api_request(
            self, method: str, url: str, params: dict = None
    ) -> tuple[bool, Any]:
        """统一处理API请求"""
        try:
            async with self._session.request(
                    method, url, headers={"User-Agent": USER_AGENT}, params=params
            ) as res:
                if res.status != 200:
                    logger.warning(
                        "room=%d API request failed, url=%s, status=%d, reason=%s",
                        self._tmp_room_id,
                        url,
                        res.status,
                        res.reason,
                    )
                    return False, None

                data = await res.json()
                return True, data
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
            logger.exception(
                "room=%d API request failed, url=%s", self._tmp_room_id, url
            )
            return False, None

    async def _init_room_id_and_owner(self):
        """初始化房间ID和主播信息"""
        success, data = await self._api_request(
            "GET", ROOM_INIT_URL, params={"room_id": self._tmp_room_id}
        )

        if not success or not data:
            return False

        if data["code"] != 0:
            logger.warning(
                "room=%d _init_room_id_and_owner() failed, message=%s",
                self._tmp_room_id,
                data["message"],
            )
            return False

        return self._parse_room_init(data["data"])

    def _parse_room_init(self, data):
        """解析房间初始化数据"""
        self._room_id = data["room_id"]
        self._room_owner_uid = data["uid"]
        return True

    async def _init_host_server(self):
        """初始化弹幕服务器信息"""
        # 获取WBI签名器
        wbi_signer = _get_wbi_signer(self._session)

        # 检查是否需要刷新WBI密钥
        if wbi_signer.need_refresh_wbi_key:
            await wbi_signer.refresh_wbi_key()

        # 原始参数
        params = {"id": self._room_id, "type": 0}

        # 使用WBI签名
        try:
            signed_params = wbi_signer.add_wbi_sign(params)
        except Exception as e:
            logger.warning(
                f"room={self._room_id} WBI signing failed, error={e}. Falling back to original params.",
            )
            # 如果签名失败，仍然尝试使用原始参数（可能会失败，但提供了兼容性）
            signed_params = params

        # 使用签名后的参数进行请求
        success, data = await self._api_request(
            "GET", DANMAKU_SERVER_CONF_URL, params=signed_params
        )

        if not success or not data:
            return False

        # 有时返回的 message 是数字错误码，有时是字符串。
        if data.get("code", -1) != 0:
            logger.warning(
                f"room={self._room_id} _init_host_server() failed, code={data.get('code')}, message={data.get('message', 'N/A')}",
            )
            return False

        return self._parse_danmaku_server_conf(data["data"])

    def _parse_danmaku_server_conf(self, data):
        """解析弹幕服务器配置"""
        self._host_server_list = data["host_list"]
        self._host_server_token = data["token"]
        if not self._host_server_list:
            logger.warning(
                "room=%d _parse_danmaku_server_conf() failed: host_server_list is empty",
                self._room_id,
            )
            return False
        return True

    async def _on_before_ws_connect(self, retry_count):
        """
        在每次建立连接之前调用，可以用来初始化房间
        """
        # 重连次数太多则重新init_room，保险
        reinit_period = max(3, len(self._host_server_list or ()))
        if retry_count > 0 and retry_count % reinit_period == 0:
            self._need_init_room = True
        await super()._on_before_ws_connect(retry_count)

    def _get_ws_url(self, retry_count) -> str:
        """
        返回WebSocket连接的URL，可以在这里做故障转移和负载均衡
        """
        host_server = self._host_server_list[retry_count % len(self._host_server_list)]
        return f"wss://{host_server['host']}:{host_server['wss_port']}/sub"

    async def _send_auth(self):
        """
        发送认证包
        """
        auth_params = {
            "uid": self._uid,
            "roomid": self._room_id,
            "protover": 3,
            "platform": "web",
            "type": 2,
            "buvid": self._get_buvid(),
        }
        if self._host_server_token is not None:
            auth_params["key"] = self._host_server_token
        await self._websocket.send_bytes(
            self._make_packet(auth_params, ws_base.Operation.AUTH)
        )

    def _handle_command(self, command: dict) -> None:
        """
        处理业务消息
        """
        try:
            cmd = command.get("cmd", "")
            if cmd == "_HEARTBEAT":
                return

            bili_message = None

            # 根据消息类型进行转换
            if cmd == "DANMU_MSG":
                # 弹幕消息
                info = command.get("info", [])
                dm_message = web_models.DanmakuMessage.from_command(info)
                bili_message = message.DanmakuMessage.from_web_message(
                    dm_message, self._room_id, command
                )

            elif cmd == "SEND_GIFT":
                # 礼物消息
                data = command.get("data", {})
                gift_message = web_models.GiftMessage.from_command(data)
                bili_message = message.GiftMessage.from_web_message(
                    gift_message, self._room_id, command
                )

            elif cmd == "SUPER_CHAT_MESSAGE":
                # 醒目留言消息
                data = command.get("data", {})
                sc_message = web_models.SuperChatMessage.from_command(data)
                bili_message = message.SuperChatMessage.from_web_message(
                    sc_message, self._room_id, command
                )

            elif cmd == "GUARD_BUY":
                # 上舰消息
                data = command.get("data", {})
                guard_message = web_models.GuardBuyMessage.from_command(data)
                bili_message = message.GuardBuyMessage.from_web_message(
                    guard_message, self._room_id, command
                )

            elif cmd == "INTERACT_WORD":
                # 互动消息
                data = command.get("data", {})
                interact_message = web_models.InteractWordMessage.from_command(data)
                if interact_message.msg_type == 1:
                    # 进入房间
                    bili_message = message.EnterRoomMessage.from_web_message(
                        interact_message, self._room_id, command
                    )
                elif interact_message.msg_type == 6:
                    # 点赞
                    bili_message = message.LikeMessage.from_web_message(
                        interact_message, self._room_id, command
                    )

            if bili_message is not None:
                self._message_queue.put_nowait(bili_message)

        except Exception as e:
            logger.exception(
                "room=%d _handle_command() failed, command=%s",
                self._room_id,
                command,
                exc_info=e,
            )
