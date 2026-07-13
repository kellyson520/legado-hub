"""
WebSocket 实时事件推送

职责：
- WebSocket 连接管理（广播、定向推送）
- 统一日志
- 后台事件推送任务
"""

import asyncio
import json
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime

from ....core.logging import get_logger
from ....core.redis_client import redis_client

logger = get_logger("ws")
router = APIRouter(prefix="/api/ws", tags=["websocket"])

# 连接管理器
class ConnectionManager:
    """WebSocket 连接管理器 - 支持广播和定向推送"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.admin_connections: Set[WebSocket] = set()
        self.user_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_type: str = "user"):
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
            if client_type == "admin":
                self.admin_connections.add(websocket)
            else:
                self.user_connections.add(websocket)
        logger.info(
            f"[WebSocket] 客户端连接: type={client_type}, total={len(self.active_connections)}",
            extra={"action": "ws_connect", "client_type": client_type, "total": len(self.active_connections)}
        )

    async def disconnect(self, websocket: WebSocket, client_type: str = "user"):
        async with self._lock:
            self.active_connections.discard(websocket)
            self.admin_connections.discard(websocket)
            self.user_connections.discard(websocket)
        logger.info(
            f"[WebSocket] 客户端断开: remaining={len(self.active_connections)}",
            extra={"action": "ws_disconnect", "remaining": len(self.active_connections)}
        )

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(
                f"[WebSocket] 发送消息失败: {type(e).__name__}: {e}",
                extra={"action": "ws_send_error", "error": str(e)}
            )

    async def broadcast(self, message: dict, admin_only: bool = False):
        """广播消息给所有或仅管理员客户端"""
        targets = self.admin_connections if admin_only else self.active_connections
        disconnected = []

        for conn in targets:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)

        for conn in disconnected:
            await self.disconnect(conn)

        if disconnected:
            logger.debug(
                f"[WebSocket] 广播清理 {len(disconnected)} 个断开连接",
                extra={"action": "ws_broadcast_cleanup", "cleaned": len(disconnected)}
            )

    async def broadcast_task_progress(self, task_id: str, progress: int, message: str = ""):
        """广播任务进度"""
        await self.broadcast({
            "type": "task_progress",
            "task_id": task_id,
            "progress": progress,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def broadcast_source_status(self, source_url: str, status: str, source_name: str = ""):
        """广播源状态变更"""
        await self.broadcast({
            "type": "source_status",
            "source_url": source_url,
            "source_name": source_name,
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def broadcast_system_notice(self, title: str, content: str, level: str = "info"):
        """广播系统通知"""
        await self.broadcast({
            "type": "system_notice",
            "title": title,
            "content": content,
            "level": level,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def broadcast_quota_alert(self, api_key_id: int, metric: str, used: int, limit: int):
        """广播配额告警"""
        await self.broadcast({
            "type": "quota_alert",
            "api_key_id": api_key_id,
            "metric": metric,
            "used": used,
            "limit": limit,
            "usage_percent": round(used / limit * 100, 1) if limit > 0 else 0,
            "timestamp": datetime.utcnow().isoformat()
        }, admin_only=True)


manager = ConnectionManager()


@router.websocket("/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket 实时事件推送"""
    client_type = "user"
    subscribed_channels = set()

    try:
        await manager.connect(websocket, client_type)

        await manager.send_personal_message({
            "type": "connected",
            "message": "WebSocket 连接成功",
            "timestamp": datetime.utcnow().isoformat()
        }, websocket)

        while True:
            try:
                data = await websocket.receive_json()
                action = data.get("action")

                if action == "subscribe":
                    channels = data.get("channels", [])
                    subscribed_channels.update(channels)
                    await manager.send_personal_message({
                        "type": "subscribed",
                        "channels": list(subscribed_channels)
                    }, websocket)

                elif action == "unsubscribe":
                    channels = data.get("channels", [])
                    subscribed_channels.difference_update(channels)
                    await manager.send_personal_message({
                        "type": "unsubscribed",
                        "channels": list(subscribed_channels)
                    }, websocket)

                elif action == "ping":
                    await manager.send_personal_message({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    }, websocket)

                elif action == "auth":
                    token = data.get("token", "")
                    if token.startswith("lh_"):
                        client_type = "admin"
                        await manager.disconnect(websocket, "user")
                        await manager.connect(websocket, "admin")
                        logger.info(
                            "[WebSocket] 管理员认证成功",
                            extra={"action": "ws_auth_success"}
                        )
                        await manager.send_personal_message({
                            "type": "auth_success",
                            "role": "admin"
                        }, websocket)

            except json.JSONDecodeError:
                await manager.send_personal_message({
                    "type": "error",
                    "message": "Invalid JSON"
                }, websocket)

    except WebSocketDisconnect:
        await manager.disconnect(websocket, client_type)
        logger.debug("[WebSocket] 客户端正常断开", extra={"action": "ws_client_disconnect"})
    except Exception as e:
        logger.error(
            f"[WebSocket] 异常: {type(e).__name__}: {e}",
            extra={"action": "ws_error", "error": str(e)},
            exc_info=True
        )
        await manager.disconnect(websocket, client_type)


async def background_push_task():
    """后台任务：从 Redis 队列读取事件并推送给客户端"""
    logger.info("[WebSocket] 后台推送任务启动", extra={"action": "ws_push_task_start"})
    while True:
        try:
            if redis_client.is_connected:
                msg = await redis_client.dequeue_task("ws_events", timeout=5)
                if msg:
                    await manager.broadcast(msg)
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(
                f"[WebSocket] 后台推送异常: {type(e).__name__}: {e}",
                extra={"action": "ws_push_error", "error": str(e)},
                exc_info=True
            )
            await asyncio.sleep(5)
