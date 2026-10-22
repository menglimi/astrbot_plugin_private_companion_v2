# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from importlib import resources as importlib_resources
import json
import mimetypes
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from astrbot.api import logger

from companion_v2.together.models import RoomSession

try:
    from aiohttp import ClientConnectionError, ClientSession, ClientTimeout, WSMsgType, web
except ImportError:  # pragma: no cover - reported clearly during plugin startup
    ClientConnectionError = ConnectionError
    ClientSession = None
    ClientTimeout = None
    WSMsgType = None
    web = None


class TogetherRoomServer:
    MAX_WEBSOCKET_MESSAGE_BYTES = 16 * 1024 * 1024
    REQUIRED_WEB_ASSETS = ("index.html", "app.css", "app.js", "lucide.min.js", "default-avatar.svg")

    def __init__(
        self,
        plugin: Any,
        *,
        host: str,
        port: int,
        web_root: Path,
        resource_package: str = "",
    ) -> None:
        self.plugin = plugin
        self.host = str(host or "127.0.0.1").strip() or "127.0.0.1"
        self.requested_port = max(1, min(int(port or 6321), 65535))
        self.port = self.requested_port
        self.web_root = Path(web_root)
        self.resource_packages = tuple(
            dict.fromkeys(
                package
                for package in (
                    str(resource_package or "").strip(),
                    __package__,
                )
                if package
            )
        )
        self._packaged_asset_cache: dict[str, bytes] = {}
        self._runner = None
        self._site = None
        self._proxy_session = None

    @property
    def running(self) -> bool:
        return self._runner is not None and self._site is not None

    @property
    def local_base_url(self) -> str:
        host = self.host
        if host in {"0.0.0.0", "::", "[::]"}:
            host = "127.0.0.1"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"http://{host}:{self.port}"

    async def start(self) -> None:
        if self.running:
            return
        if web is None:
            raise RuntimeError("缺少 aiohttp，无法启动实时房间服务")

        missing_assets = [
            name for name in self.REQUIRED_WEB_ASSETS if not self._web_asset_available(name)
        ]
        if missing_assets:
            raise RuntimeError(
                "房间静态资源不完整，缺少："
                + "、".join(missing_assets)
                + f"；已检查目录 {self.web_root} 和包资源 {', '.join(self.resource_packages)}"
            )

        novel_upload_limit = int(
            getattr(getattr(self.plugin, "novel_library", None), "max_upload_bytes", 0) or 0
        )
        app = web.Application(
            client_max_size=max(self.MAX_WEBSOCKET_MESSAGE_BYTES, novel_upload_limit + 1024 * 1024)
        )
        app.router.add_get("/", self._serve_index)
        app.router.add_get("/join/{ticket}", self._serve_index)
        app.router.add_get("/assets/{name}", self._serve_asset)
        app.router.add_get("/avatar", self._serve_avatar)
        app.router.add_get("/media/{token}/{track}", self._serve_media)
        app.router.add_get("/media/{token}", self._serve_media)
        app.router.add_post("/api/novels/import", self._import_novel)
        app.router.add_get("/health", self._serve_health)
        app.router.add_get("/ws", self._serve_websocket)

        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        last_error: Exception | None = None
        for candidate in range(self.requested_port, min(65535, self.requested_port + 10) + 1):
            site = web.TCPSite(self._runner, self.host, candidate)
            try:
                await site.start()
            except OSError as exc:
                last_error = exc
                continue
            self._site = site
            self.port = candidate
            if candidate != self.requested_port:
                logger.warning(
                    "[TogetherCompanion] 房间端口 %s 被占用，已改用 %s",
                    self.requested_port,
                    candidate,
                )
            logger.info("[TogetherCompanion] 实时房间已启动: %s", self.local_base_url)
            return

        await self.stop()
        raise RuntimeError(f"无法监听房间端口 {self.requested_port}-{self.requested_port + 10}: {last_error}")

    async def _media_session(self):
        """媒体转发共享会话：复用连接，避免每个 Range 请求新建 ClientSession。"""
        if self._proxy_session is None or self._proxy_session.closed:
            timeout = ClientTimeout(total=None, connect=15, sock_connect=15, sock_read=90)
            self._proxy_session = ClientSession(timeout=timeout)
        return self._proxy_session

    async def stop(self) -> None:
        site, runner = self._site, self._runner
        self._site = None
        self._runner = None
        if self._proxy_session is not None and not self._proxy_session.closed:
            try:
                await self._proxy_session.close()
            except Exception as exc:
                logger.debug("[TogetherCompanion] 关闭媒体转发会话失败: %s", exc)
        self._proxy_session = None
        if site is not None:
            try:
                await site.stop()
            except Exception as exc:
                logger.debug("[TogetherCompanion] 停止房间站点失败: %s", exc)
        if runner is not None:
            try:
                await runner.cleanup()
            except Exception as exc:
                logger.debug("[TogetherCompanion] 清理房间服务失败: %s", exc)

    @staticmethod
    def _security_headers(content_type: str = "") -> dict[str, str]:
        headers = {
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Permissions-Policy": "camera=(self), microphone=(self), geolocation=()",
        }
        if content_type.startswith("text/html"):
            headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; "
                "style-src 'self'; img-src 'self' data: blob:; "
                "media-src 'self' data: blob: https: http:; "
                "connect-src 'self' ws: wss:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
            )
        return headers

    def _filesystem_web_asset(self, name: str) -> Path | None:
        filename = str(name or "")
        if filename not in self.REQUIRED_WEB_ASSETS:
            return None
        candidates = [self.web_root / filename]
        candidates.append(Path(__file__).resolve().parent / "web" / filename)
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                continue
        return None

    def _packaged_web_asset(self, name: str) -> bytes | None:
        filename = str(name or "")
        if filename not in self.REQUIRED_WEB_ASSETS:
            return None
        cached = self._packaged_asset_cache.get(filename)
        if cached is not None:
            return cached
        for package in self.resource_packages:
            try:
                asset = importlib_resources.files(package).joinpath("web").joinpath(filename)
                if not asset.is_file():
                    continue
                content = asset.read_bytes()
            except (
                AttributeError,
                ImportError,
                ModuleNotFoundError,
                FileNotFoundError,
                OSError,
                TypeError,
            ):
                continue
            self._packaged_asset_cache[filename] = content
            return content
        return None

    def _web_asset_available(self, name: str) -> bool:
        return self._filesystem_web_asset(name) is not None or self._packaged_web_asset(name) is not None

    def _web_asset_diagnostic(self, name: str) -> str:
        packages = ", ".join(self.resource_packages) or "未配置"
        return f"资源={name} 文件目录={self.web_root} 包资源={packages}"

    async def _serve_index(self, request):
        path = self._filesystem_web_asset("index.html")
        if path is not None:
            return web.FileResponse(
                path,
                headers=self._security_headers("text/html; charset=utf-8"),
            )
        content = self._packaged_web_asset("index.html")
        if content is None:
            diagnostic = self._web_asset_diagnostic("index.html")
            logger.error("[TogetherCompanion] 房间页面资源缺失: %s", diagnostic)
            raise web.HTTPNotFound(text="房间页面不存在，静态资源不完整；请检查插件日志")
        return web.Response(
            body=content,
            content_type="text/html",
            charset="utf-8",
            headers=self._security_headers("text/html; charset=utf-8"),
        )

    async def _serve_asset(self, request):
        allowed = set(self.REQUIRED_WEB_ASSETS) - {"index.html"}
        name = str(request.match_info.get("name") or "")
        if name not in allowed:
            raise web.HTTPNotFound()
        path = self._filesystem_web_asset(name)
        if path is not None:
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            return web.FileResponse(path, headers=self._security_headers(content_type))
        content = self._packaged_web_asset(name)
        if content is None:
            logger.error(
                "[TogetherCompanion] 房间静态资源缺失: %s",
                self._web_asset_diagnostic(name),
            )
            raise web.HTTPNotFound()
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return web.Response(
            body=content,
            content_type=content_type,
            headers=self._security_headers(content_type),
        )

    async def _serve_avatar(self, request):
        path = await self.plugin.resolve_avatar_path(str(request.query.get("bot_id") or ""))
        if path is None or not path.is_file():
            raise web.HTTPNotFound()
        content_type = await asyncio.to_thread(self._avatar_content_type, path)
        return web.FileResponse(path, headers={**self._security_headers(content_type), "Content-Type": content_type})

    @staticmethod
    def _avatar_content_type(path: Path) -> str:
        try:
            with path.open("rb") as stream:
                header = stream.read(12)
            if header.startswith(b"\xff\xd8\xff"):
                return "image/jpeg"
            if header.startswith(b"\x89PNG\r\n\x1a\n"):
                return "image/png"
            if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
                return "image/webp"
        except OSError:
            pass
        return mimetypes.guess_type(path.name)[0] or "image/png"

    async def _serve_media(self, request):
        token = str(request.match_info.get("token") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{24,80}", token):
            raise web.HTTPNotFound(text="视频地址无效")
        source = self.plugin.resolve_media_source(token)
        if source is None:
            raise web.HTTPNotFound(text="视频地址已失效，请重新打开链接")
        if ClientSession is None or ClientTimeout is None:
            raise web.HTTPServiceUnavailable(text="媒体转发服务不可用")

        track = str(request.match_info.get("track") or "video").lower()
        if track not in {"video", "audio"}:
            raise web.HTTPNotFound(text="媒体轨道无效")
        source_url = source.source_url if track == "video" else source.audio_source_url
        content_type = source.content_type if track == "video" else source.audio_content_type
        if not source_url:
            raise web.HTTPNotFound(text="媒体轨道不存在")

        upstream_headers = dict(source.request_headers)
        for name in ("Range", "If-Range"):
            value = request.headers.get(name)
            if value:
                upstream_headers[name] = value
        session = await self._media_session()
        async with session.request(
            request.method,
            source_url,
            headers=upstream_headers,
            allow_redirects=True,
            max_redirects=5,
        ) as upstream:
            if upstream.status not in {200, 206}:
                raise web.HTTPBadGateway(text=f"视频源暂时不可用（HTTP {upstream.status}）")
            response_headers = self._security_headers(content_type)
            for name in (
                "Content-Length",
                "Content-Range",
                "Accept-Ranges",
                "ETag",
                "Last-Modified",
            ):
                value = upstream.headers.get(name)
                if value:
                    response_headers[name] = value
            response_headers.setdefault("Content-Type", content_type)
            response_headers["Content-Disposition"] = "inline"
            response = web.StreamResponse(status=upstream.status, headers=response_headers)
            try:
                await response.prepare(request)
            except (ConnectionError, ClientConnectionError):
                return response
            if request.method == "HEAD":
                return response
            try:
                async for chunk in upstream.content.iter_chunked(256 * 1024):
                    await response.write(chunk)
                await response.write_eof()
            except (ConnectionError, ClientConnectionError):
                pass
            return response

    async def _serve_health(self, request):
        return web.json_response(
            {
                "ok": True,
                "plugin": "astrbot_plugin_private_companion.together",
                "port": self.port,
                "rooms": len(self.plugin.rooms),
            },
            headers=self._security_headers("application/json"),
        )

    def _authorized_room(self, request) -> RoomSession | None:
        room_id = str(request.headers.get("X-Together-Room") or "").strip()
        resume_token = str(request.headers.get("X-Together-Resume") or "").strip()
        if not room_id or not resume_token:
            return None
        room = self.plugin.rooms.get(room_id)
        if room is None:
            room = self.plugin.detached_rooms.get(resume_token)
        if room is None or room.room_id != room_id or room.resume_token != resume_token:
            return None
        return room

    async def _import_novel(self, request):
        room = self._authorized_room(request)
        if room is None:
            raise web.HTTPUnauthorized(text="房间身份无效")
        library = self.plugin._novel_library_for(room)
        if not bool(getattr(self.plugin, "novel_library_enabled", True)):
            raise web.HTTPForbidden(text="小说书库已关闭")
        checker = getattr(self.plugin, "novel_import_allowed", None)
        if callable(checker) and not bool(checker(room)):
            raise web.HTTPForbidden(text="当前用户没有导入小说的权限")
        try:
            reader = await request.multipart()
            field = await reader.next()
            while field is not None and field.name != "file":
                field = await reader.next()
            if field is None or not field.filename:
                raise ValueError("没有收到小说文件")
            max_bytes = int(getattr(library, "max_upload_bytes", 40 * 1024 * 1024))
            chunks: list[bytes] = []
            received = 0
            while True:
                chunk = await field.read_chunk(size=64 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > max_bytes:
                    raise ValueError(f"小说文件不能超过 {max_bytes // 1024 // 1024} MB")
                chunks.append(chunk)
            result = await asyncio.to_thread(
                library.import_bytes,
                field.filename,
                b"".join(chunks),
            )
        except ValueError as exc:
            return web.json_response(
                {"ok": False, "message": str(exc)},
                status=400,
                headers=self._security_headers("application/json"),
            )
        except Exception as exc:
            logger.warning("[TogetherCompanion] 小说导入失败: %s", exc, exc_info=True)
            return web.json_response(
                {"ok": False, "message": "小说导入失败，请检查文件格式"},
                status=500,
                headers=self._security_headers("application/json"),
            )
        await self.plugin.send_room_payload(
            room,
            {
                "type": "novel_library",
                "books": await asyncio.to_thread(library.list_books, user_id=room.user_id),
            },
        )
        return web.json_response(
            {"ok": True, "book": result},
            headers=self._security_headers("application/json"),
        )

    def _origin_allowed(self, request) -> bool:
        origin = str(request.headers.get("Origin") or "").strip()
        if not origin:
            return False
        try:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                return False
            origin_value = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
            request_value = f"{str(request.scheme or 'http').lower()}://{str(request.host or '').lower()}"
        except Exception:
            return False
        if origin_value == request_value:
            return True
        quick_tunnel = getattr(self.plugin, "quick_tunnel", None)
        allowed_bases = (
            str(getattr(self.plugin, "public_base_url", "") or "").strip(),
            str(getattr(quick_tunnel, "url", "") or "").strip()
            if bool(getattr(quick_tunnel, "running", False))
            else "",
        )
        for public_base in allowed_bases:
            if not public_base:
                continue
            try:
                public = urlsplit(public_base)
                public_origin = f"{public.scheme.lower()}://{public.netloc.lower()}"
                if public.scheme and public.netloc and origin_value == public_origin:
                    return True
            except Exception:
                continue
        return False

    async def _serve_websocket(self, request):
        if not self._origin_allowed(request):
            raise web.HTTPForbidden(text="房间来源校验失败")

        resume_token = str(request.query.get("resume") or "").strip()
        token = str(request.query.get("ticket") or "").strip()
        resuming = bool(resume_token) and self.plugin.can_resume_room(resume_token)
        if not resuming:
            ticket = self.plugin.ticket_store.get(token)
            if ticket is None:
                raise web.HTTPUnauthorized(text="房间链接无效或已过期")

        websocket = web.WebSocketResponse(
            heartbeat=20,
            receive_timeout=180,
            max_msg_size=self.MAX_WEBSOCKET_MESSAGE_BYTES,
            autoping=True,
        )
        await websocket.prepare(request)
        resumed = False
        joined_room = False
        if resuming:
            room = await self.plugin.resume_room(resume_token, websocket)
            if room is None:
                await websocket.close(code=1008, message="房间已结束".encode("utf-8"))
                return websocket
            resumed = True
        else:
            ticket = self.plugin.ticket_store.consume(token)
            if ticket is None:
                await websocket.close(code=1008, message="房间链接已被使用".encode("utf-8"))
                return websocket
            try:
                joined_room = bool(ticket.room_id)
                room = await self.plugin.open_room(ticket, websocket)
            except Exception as exc:
                code = str(getattr(exc, "code", "room_join_failed"))
                logger.info("[TogetherCompanion] 拒绝房间连接: %s", code)
                message = ("房间链接缺少身份，已拒绝" if code == "together_ticket_identity_required"
                           else "邀请已失效或当前成员无法加入")
                await websocket.close(code=1008, message=message.encode("utf-8"))
                return websocket
        member = self.plugin.room_member_for_websocket(room, websocket)
        if member is None:
            await websocket.close(code=1008, message="房间成员身份无效".encode("utf-8"))
            return websocket
        try:
            await self.plugin.send_room_payload(
                room,
                {
                    "type": "ready",
                    "room": await self.plugin.room_bootstrap(room, member_role=member.role),
                    "resumed": resumed,
                    "joined": joined_room,
                    "member_role": member.role,
                    "resume_token": member.resume_token,
                },
                websocket=websocket,
            )
            if resumed:
                await self.plugin.replay_room_state(room, websocket=websocket, member_role=member.role)
            elif joined_room:
                await self.plugin.replay_room_state(room, websocket=websocket, member_role=member.role)
                await self.plugin.send_room_payload(room, {
                    "type": "room_members",
                    "members": self.plugin.public_room_members(room),
                })
            async for message in websocket:
                if message.type == WSMsgType.TEXT:
                    try:
                        payload = json.loads(message.data)
                    except json.JSONDecodeError:
                        await self.plugin.send_room_error(room, "收到的房间消息不是有效 JSON")
                        continue
                    if not isinstance(payload, dict):
                        await self.plugin.send_room_error(room, "房间消息格式无效", websocket=websocket)
                        continue
                    if not self.plugin.member_payload_allowed(member, payload):
                        await self.plugin.send_room_error(
                            room, "当前成员不能更改房间设置或共享素材", code="member_permission_denied",
                            websocket=websocket)
                        continue
                    await self.plugin.handle_room_payload(room, payload, member=member)
                elif message.type in {WSMsgType.ERROR, WSMsgType.CLOSE, WSMsgType.CLOSED}:
                    break
        except asyncio.TimeoutError:
            await websocket.close(code=1001, message="房间长时间无活动".encode("utf-8"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[TogetherCompanion] 房间连接异常: %s", exc, exc_info=True)
        finally:
            await self.plugin.detach_room(room, websocket=websocket)
        return websocket
