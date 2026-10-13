"""
VTube Studio WebSocket API 客户端
负责与 VTube Studio 建立连接、认证，并提供控制 Live2D 模型的方法
"""

import asyncio
import json
import uuid
from typing import Optional, Dict, Any, List

try:
    import websockets
    from websockets.exceptions import ConnectionClosed, WebSocketException
except ImportError:
    websockets = None

from astrbot.api import logger


class VTSClientError(Exception):
    """VTS 客户端异常基类"""
    pass


class VTSConnectionError(VTSClientError):
    """连接异常"""
    pass


class VTSTimeoutError(VTSClientError):
    """超时异常"""
    pass


class VTSResponseError(VTSClientError):
    """响应解析异常"""
    pass


class VTSClient:
    """VTube Studio WebSocket API 客户端"""

    API_NAME = "VTubeStudioPublicAPI"
    API_VERSION = "1.0"
    DEFAULT_TIMEOUT = 10.0
    CONNECT_TIMEOUT = 5.0

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8001,
        plugin_name: str = "AstrBot VTS Plugin",
        plugin_developer: str = "AstrBot",
    ):
        self.url = f"ws://{host}:{port}"
        self.plugin_name = plugin_name
        self.plugin_developer = plugin_developer
        self.auth_token: Optional[str] = None
        self._ws = None
        self._lock = asyncio.Lock()
        self._is_connected = False
        self._authenticated = False
        self.last_auth_error = ""

    # ------------------------------------------------------------------ #
    #  底层通信
    # ------------------------------------------------------------------ #

    def _build_request(self, message_type: str, data: Dict[str, Any] = None) -> str:
        payload = {
            "apiName": self.API_NAME,
            "apiVersion": self.API_VERSION,
            "requestID": str(uuid.uuid4())[:8],
            "messageType": message_type,
            "data": data or {},
        }
        return json.dumps(payload)

    async def _send_request(
        self, message_type: str, data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """发送请求并等待响应，超时时强制断开连接防止状态污染"""
        if websockets is None:
            raise VTSClientError("请先安装 websockets 库：pip install websockets")

        async with self._lock:
            # 如果连接断开则重新建立
            if self._ws is None or not self.is_connected:
                await self._connect()
                if message_type not in {
                    "AuthenticationTokenRequest",
                    "AuthenticationRequest",
                } and self.auth_token:
                    await self._authenticate_current_connection()

            payload = self._build_request(message_type, data)

            try:
                await self._ws.send(payload)
            except asyncio.CancelledError:
                await self._force_disconnect()
                raise
            except Exception as e:
                # 发送失败，尝试重连一次
                logger.warning(f"[VTS] 发送失败，尝试重连: {e}")
                await self._force_disconnect()
                await self._connect()
                if message_type not in {
                    "AuthenticationTokenRequest",
                    "AuthenticationRequest",
                } and self.auth_token:
                    await self._authenticate_current_connection()
                try:
                    await self._ws.send(payload)
                except asyncio.CancelledError:
                    await self._force_disconnect()
                    raise
                except Exception as retry_error:
                    await self._force_disconnect()
                    raise VTSConnectionError(
                        f"VTube Studio 重连后发送失败: {retry_error}"
                    ) from retry_error

            try:
                response_raw = await asyncio.wait_for(
                    self._ws.recv(), timeout=self.DEFAULT_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.warning("[VTS] 请求超时，强制断开连接以防止状态污染")
                await self._force_disconnect()
                raise VTSTimeoutError(
                    f"VTube Studio API 请求超时（{self.DEFAULT_TIMEOUT}秒），"
                    "连接已重置，请检查 VTS 是否响应正常"
                )
            except asyncio.CancelledError:
                # Do not let a late response leak into the next request.
                await self._force_disconnect()
                raise
            except Exception as e:
                await self._force_disconnect()
                raise VTSConnectionError(f"VTube Studio 接收响应失败: {e}") from e

            # 安全解析 JSON
            try:
                response = json.loads(response_raw)
            except json.JSONDecodeError as e:
                logger.error(f"[VTS] 响应 JSON 解析失败: {e}")
                await self._force_disconnect()
                raise VTSResponseError(f"VTube Studio 返回了无效的响应格式: {e}")
            if response.get("messageType") == "APIError":
                error = response.get("data") if isinstance(response.get("data"), dict) else {}
                error_id = error.get("errorID", "?")
                error_message = error.get("message") or error.get("errorMessage") or "未知错误"
                if error_id == 8:
                    self._authenticated = False
                    self.last_auth_error = str(error_message)
                raise VTSResponseError(f"VTube Studio APIError {error_id}: {error_message}")
            return response

    async def _connect(self):
        """建立 WebSocket 连接"""
        if websockets is None:
            raise VTSClientError("websockets 库未安装")

        # Realtime parameter layers may retry every few seconds while VTS is
        # offline. Keep attempts available for diagnostics without flooding
        # the normal AstrBot log; failures and recovery are logged by callers.
        logger.debug(f"[VTS] 正在连接 VTube Studio: {self.url}")

        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(self.url),
                timeout=self.CONNECT_TIMEOUT
            )
            self._is_connected = True
            self._authenticated = False
            logger.info("VTube Studio 连接成功")
        except asyncio.TimeoutError:
            self._is_connected = False
            raise VTSConnectionError(
                f"连接 VTube Studio 超时（{self.CONNECT_TIMEOUT}秒），"
                "请确认 VTS 已启动并开启了 API"
            )
        except ConnectionRefusedError:
            self._is_connected = False
            raise VTSConnectionError(
                f"连接被拒绝，请确认 VTube Studio 已启动并开启了 WebSocket API "
                f"（地址: {self.url}）"
            )
        except Exception as e:
            self._is_connected = False
            raise VTSConnectionError(f"连接 VTube Studio 失败: {e}")

    async def _force_disconnect(self):
        """强制断开连接"""
        self._is_connected = False
        self._authenticated = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None

    async def disconnect(self):
        """正常断开连接"""
        async with self._lock:
            await self._force_disconnect()
        logger.info("已断开与 VTube Studio 的连接")

    async def reset_connection(self):
        """重置连接状态（供外部调用的公开方法）"""
        async with self._lock:
            await self._force_disconnect()
        logger.info("[VTS] 连接已重置")

    @property
    def is_connected(self) -> bool:
        """检查连接状态"""
        if self._ws is None:
            return False
        if not self._is_connected:
            return False
        try:
            if hasattr(self._ws, 'closed'):
                return not self._ws.closed
            elif hasattr(self._ws, 'state'):
                from websockets import State
                return self._ws.state == State.OPEN
            return True
        except Exception:
            return False

    @property
    def is_authenticated(self) -> bool:
        return self.is_connected and self._authenticated

    async def _authenticate_current_connection(self) -> None:
        """Authenticate a freshly reconnected socket while the request lock is held."""
        if not self._ws or not self.auth_token:
            raise VTSConnectionError("VTube Studio 重连后缺少认证 Token")
        payload = self._build_request(
            "AuthenticationRequest",
            {
                "pluginName": self.plugin_name,
                "pluginDeveloper": self.plugin_developer,
                "authenticationToken": self.auth_token,
            },
        )
        try:
            await self._ws.send(payload)
            response_raw = await asyncio.wait_for(
                self._ws.recv(), timeout=self.DEFAULT_TIMEOUT
            )
            response = json.loads(response_raw)
        except asyncio.CancelledError:
            await self._force_disconnect()
            raise
        except (asyncio.TimeoutError, json.JSONDecodeError) as exc:
            await self._force_disconnect()
            raise VTSConnectionError(f"VTube Studio 重连认证失败: {exc}") from exc
        except Exception as exc:
            await self._force_disconnect()
            raise VTSConnectionError(f"VTube Studio 重连认证失败: {exc}") from exc
        if response.get("messageType") == "APIError":
            error = response.get("data") if isinstance(response.get("data"), dict) else {}
            self.last_auth_error = str(
                error.get("message") or error.get("errorMessage") or "未知错误"
            )
            await self._force_disconnect()
            raise VTSResponseError(
                f"VTube Studio 重连认证失败: {self.last_auth_error}"
            )
        authenticated = bool(response.get("data", {}).get("authenticated", False))
        self._authenticated = authenticated
        if not authenticated:
            self.last_auth_error = str(
                response.get("data", {}).get("reason")
                or response.get("data", {}).get("message")
                or "VTube Studio 未接受当前认证 Token"
            )
            await self._force_disconnect()
            raise VTSConnectionError("VTube Studio 重连认证未通过")
        self.last_auth_error = ""

    # ------------------------------------------------------------------ #
    #  认证
    # ------------------------------------------------------------------ #

    async def request_auth_token(self) -> str:
        """向 VTube Studio 申请认证 Token"""
        resp = await self._send_request(
            "AuthenticationTokenRequest",
            {
                "pluginName": self.plugin_name,
                "pluginDeveloper": self.plugin_developer,
            },
        )
        if resp.get("data", {}).get("authenticationToken"):
            token = resp["data"]["authenticationToken"]
            self.auth_token = token
            self.last_auth_error = ""
            logger.info("成功获取 VTS 认证 Token")
            return token
        raise VTSClientError(f"获取 Token 失败: {resp}")

    async def authenticate(self, token: str) -> bool:
        """使用已有 Token 进行认证"""
        self.auth_token = token
        resp = await self._send_request(
            "AuthenticationRequest",
            {
                "pluginName": self.plugin_name,
                "pluginDeveloper": self.plugin_developer,
                "authenticationToken": token,
            },
        )
        authenticated = resp.get("data", {}).get("authenticated", False)
        self._authenticated = bool(authenticated)
        if authenticated:
            self.last_auth_error = ""
            logger.info("VTS 认证成功")
        else:
            self.last_auth_error = str(
                resp.get("data", {}).get("reason")
                or resp.get("data", {}).get("message")
                or "VTube Studio 未接受当前认证 Token"
            )
            logger.warning(f"VTS 认证失败: {resp}")
        return authenticated

    def forget_authentication(self) -> None:
        """丢弃失效 Token，但保留 WebSocket 以便立即重新申请授权。"""
        self.auth_token = None
        self._authenticated = False

    # ------------------------------------------------------------------ #
    #  查询接口
    # ------------------------------------------------------------------ #

    async def get_hotkeys(self) -> List[Dict[str, Any]]:
        """获取当前模型可用的热键列表"""
        resp = await self._send_request("HotkeysInCurrentModelRequest", {})
        return resp.get("data", {}).get("availableHotkeys", [])

    async def get_expressions(self) -> List[Dict[str, Any]]:
        """获取当前模型可用的表情列表"""
        resp = await self._send_request("ExpressionStateRequest", {"details": True})
        return resp.get("data", {}).get("expressions", [])

    async def get_input_parameters(self) -> List[Dict[str, Any]]:
        """获取所有可用的输入参数"""
        resp = await self._send_request("InputParameterListRequest", {})
        data = resp.get("data", {})
        parameters: List[Dict[str, Any]] = []
        for kind, key in (("default", "defaultParameters"), ("custom", "customParameters")):
            for item in data.get(key, []) or []:
                if isinstance(item, dict):
                    parameters.append({**item, "kind": kind})
        return parameters

    async def get_live2d_parameters(self) -> List[Dict[str, Any]]:
        """获取当前模型的 Live2D 输出参数，用于校准输入映射。"""
        resp = await self._send_request("Live2DParameterListRequest", {})
        return resp.get("data", {}).get("parameters", [])

    async def create_parameter(
        self,
        name: str,
        *,
        explanation: str = "",
        minimum: float = -1.0,
        maximum: float = 1.0,
        default_value: float = 0.0,
    ) -> Dict[str, Any]:
        """创建或刷新一个由本插件拥有的 VTS 自定义追踪参数。"""
        resp = await self._send_request(
            "ParameterCreationRequest",
            {
                "parameterName": name,
                "explanation": explanation[:255],
                "min": float(minimum),
                "max": float(maximum),
                "defaultValue": float(default_value),
            },
        )
        return resp.get("data", {})

    async def get_model_info(self) -> Dict[str, Any]:
        """获取当前加载的模型信息"""
        resp = await self._send_request("CurrentModelRequest", {})
        return resp.get("data", {})

    # ------------------------------------------------------------------ #
    #  控制接口
    # ------------------------------------------------------------------ #

    async def trigger_hotkey(self, hotkey_id: str) -> Dict[str, Any]:
        """触发指定热键"""
        resp = await self._send_request(
            "HotkeyTriggerRequest", {"hotkeyID": hotkey_id}
        )
        logger.info(f"触发热键: {hotkey_id}")
        return resp.get("data", {})

    async def set_expression(
        self, expression_file: str, active: bool = True, fade_time: float = 0.25
    ) -> Dict[str, Any]:
        """激活或停用指定表情"""
        resp = await self._send_request(
            "ExpressionActivationRequest",
            {
                "expressionFile": expression_file,
                "active": active,
                "fadeTime": fade_time,
            },
        )
        logger.info(f"设置表情 {expression_file} active={active}")
        return resp.get("data", {})

    async def inject_parameters(
        self,
        parameters: List[Dict[str, Any]],
        mode: str = "set",
        face_found: bool = True,
    ) -> Dict[str, Any]:
        """注入 Live2D 参数值"""
        resp = await self._send_request(
            "InjectParameterDataRequest",
            {
                "faceFound": face_found,
                "mode": mode,
                "parameterValues": parameters,
            },
        )
        return resp.get("data", {})

    async def move_model(
        self,
        position_x: float = 0.0,
        position_y: float = 0.0,
        rotation: float = 0.0,
        size: float = 0.0,
        time_in_seconds: float = 0.5,
    ) -> Dict[str, Any]:
        """移动/旋转/缩放模型"""
        resp = await self._send_request(
            "MoveModelRequest",
            {
                "timeInSeconds": time_in_seconds,
                "valuesAreRelativeToModel": False,
                "positionX": position_x,
                "positionY": position_y,
                "rotation": rotation,
                "size": size,
            },
        )
        logger.info(f"移动模型 pos=({position_x},{position_y})")
        return resp.get("data", {})


class VTSRealtimeClient(VTSClient):
    """VTS client that drains injection acknowledgements off the send cadence."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._response_task: asyncio.Task | None = None
        self._stream_error = ""

    async def authenticate(self, token: str) -> bool:
        await self._stop_response_drain()
        authenticated = await super().authenticate(token)
        if authenticated:
            self._start_response_drain()
        return authenticated

    def _start_response_drain(self) -> None:
        if self._response_task is None or self._response_task.done():
            self._response_task = asyncio.create_task(self._drain_responses())

    async def _stop_response_drain(self) -> None:
        task = self._response_task
        self._response_task = None
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _force_disconnect(self):
        await self._stop_response_drain()
        await super()._force_disconnect()

    async def _drop_stream_socket(self, socket) -> None:
        if self._ws is not socket:
            return
        self._is_connected = False
        self._authenticated = False
        self._ws = None
        try:
            await socket.close()
        except Exception:
            pass

    async def _drain_responses(self) -> None:
        socket = self._ws
        current_task = asyncio.current_task()
        try:
            while socket is not None and self._ws is socket:
                response_raw = await socket.recv()
                try:
                    response = json.loads(response_raw)
                except json.JSONDecodeError as exc:
                    self._stream_error = f"VTube Studio 返回了无效的响应格式: {exc}"
                    continue
                if response.get("messageType") != "APIError":
                    continue
                error = response.get("data") if isinstance(response.get("data"), dict) else {}
                error_id = error.get("errorID", "?")
                error_message = error.get("message") or error.get("errorMessage") or "未知错误"
                self._stream_error = (
                    f"VTube Studio APIError {error_id}: {error_message}"
                )
                if error_id == 8:
                    await self._drop_stream_socket(socket)
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._stream_error = f"VTube Studio 实时响应连接中断: {exc}"
            await self._drop_stream_socket(socket)
        finally:
            if self._response_task is current_task:
                self._response_task = None

    async def inject_parameters(
        self,
        parameters: List[Dict[str, Any]],
        mode: str = "set",
        face_found: bool = True,
    ) -> Dict[str, Any]:
        async with self._lock:
            if not self.is_authenticated or self._ws is None:
                raise VTSConnectionError("VTube Studio 实时参数连接未认证")
            if self._stream_error:
                error = self._stream_error
                self._stream_error = ""
                raise VTSResponseError(error)
            self._start_response_drain()
            payload = self._build_request(
                "InjectParameterDataRequest",
                {
                    "faceFound": face_found,
                    "mode": mode,
                    "parameterValues": parameters,
                },
            )
            try:
                await self._ws.send(payload)
            except asyncio.CancelledError:
                await self._force_disconnect()
                raise
            except Exception as exc:
                await self._force_disconnect()
                raise VTSConnectionError(
                    f"VTube Studio 实时参数发送失败: {exc}"
                ) from exc
            return {}
