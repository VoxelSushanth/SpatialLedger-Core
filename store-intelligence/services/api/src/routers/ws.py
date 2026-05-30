"""WebSocket router for real-time updates."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Dict
import asyncio
import json
import structlog
from datetime import datetime, timezone

from ..config import get_settings
from ..db.redis_client import get_redis_client
from ..services.metrics_svc import get_store_metrics

logger = structlog.get_logger()
settings = get_settings()

router = APIRouter()

# Connected clients
connected_clients: List[WebSocket] = []
MAX_CONNECTIONS = 100


@router.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time event streaming."""
    await websocket.accept()
    
    if len(connected_clients) >= MAX_CONNECTIONS:
        await websocket.close(code=1013, reason="Too many connections")
        return
    
    connected_clients.append(websocket)
    logger.info("WebSocket client connected", total_clients=len(connected_clients))
    
    try:
        # Send initial metrics snapshot
        try:
            initial_metrics = await get_store_metrics()
            await websocket.send_json({
                "type": "metrics_update",
                "data": initial_metrics
            })
        except Exception as e:
            logger.error("Failed to send initial metrics", error=str(e))
        
        # Subscribe to Redis pub/sub channels
        redis = get_redis_client()
        pubsub = redis.pubsub()
        await pubsub.psubscribe("store:*")
        
        # Listen for messages from Redis and forward to WebSocket clients
        while True:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                
                if message and message["type"] == "pmessage":
                    channel = message["channel"]
                    data = message["data"]
                    
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    
                    try:
                        event_data = json.loads(data)
                        msg_type = "event"
                        if "anomaly" in channel.decode() if isinstance(channel, bytes) else channel:
                            msg_type = "anomaly"
                        
                        await websocket.send_json({
                            "type": msg_type,
                            "data": event_data
                        })
                    except json.JSONDecodeError:
                        pass
                
                # Send periodic metrics update every 30 seconds
                await asyncio.sleep(30)
                try:
                    metrics = await get_store_metrics()
                    await websocket.send_json({
                        "type": "metrics_update",
                        "data": metrics
                    })
                except Exception as e:
                    logger.error("Failed to send metrics update", error=str(e))
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("WebSocket message handling error", error=str(e))
                await asyncio.sleep(1)
                
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error("WebSocket error", error=str(e))
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        logger.info("WebSocket client removed", total_clients=len(connected_clients))
        
        try:
            await pubsub.punsubscribe()
        except:
            pass
