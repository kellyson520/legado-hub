import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime

from ..core.redis_client import redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ws", tags=["websocket"])

# 连接管理器
class ConnectionManager:
    """WebSocket 连接管理器 - 支持广播和定向推送"""
    
    def __init__(self):
        # 所有活跃连接
        self.active_connections: Set[WebSocket] = set()
        # 按客户端类型分组
        self.admin_connections: Set[WebSocket] = set()
        self.user_connections: Set[WebSocket] = set()
        # 锁
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, client_type: str = "user"):
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
            if client_type == "admin":
                self.admin_connections.add(websocket)
            else:
                self.user_connections.add(websocket)
        logger.info(f"[WebSocket] 客户端连接: {client_type}, 总数: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket, client_type: str = "user"):
        async with self._lock:
            self.active_connections.discard(websocket)
            self.admin_connections.discard(websocket)
            self.user_connections.discard(websocket)
        logger.info(f"[WebSocket] 客户端断开, 剩余: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"[WebSocket] 发送消息失败: {e}")
    
    async def broadcast(self, message: dict, admin_only: bool = False):
        """广播消息给所有或仅管理员客户端"""
        targets = self.admin_connections if admin_only else self.active_connections
        disconnected = []
        
        for conn in targets:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)
        
        # 清理断开的连接
        for conn in disconnected:
            await self.disconnect(conn)
    
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
            "level": level,  # info, warning, error
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
    """
    WebSocket 实时事件推送
    
    消息格式:
    - 客户端发送: {"action": "subscribe", "channels": ["task", "source"]}
    - 服务端推送: {"type": "source_status", "source_url": "...", "status": "ok"}
    """
    client_type = "user"
    subscribed_channels = set()
    
    try:
        await manager.connect(websocket, client_type)
        
        # 发送欢迎消息
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
                    # 简单的管理员认证（通过 API Key）
                    token = data.get("token", "")
                    if token.startswith("lh_"):
                        client_type = "admin"
                        await manager.disconnect(websocket, "user")
                        await manager.connect(websocket, "admin")
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
    except Exception as e:
        logger.error(f"[WebSocket] 异常: {e}")
        await manager.disconnect(websocket, client_type)


# ==================== 后台推送任务 ====================

async def background_push_task():
    """后台任务：从 Redis 队列读取事件并推送给客户端"""
    while True:
        try:
            if redis_client.is_connected:
                msg = await redis_client.dequeue_task("ws_events", timeout=5)
                if msg:
                    await manager.broadcast(msg)
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"[WebSocket] 后台推送异常: {e}")
            await asyncio.sleep(5)
