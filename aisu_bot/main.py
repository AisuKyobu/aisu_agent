import asyncio
import json

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register

AGENT_URL = "http://host.docker.internal:7890"
WS_URL = "ws://host.docker.internal:7890/ws"


@register("aisu-agent", "AisuKyobu", "个人 AI 助手", "v1.0.0")
class AisuPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self._ws = None
        self._ums = {}           # session_id → unified_msg_origin
        self._buffer = ""        # 当前正在积累的回复文本
        self._pending_umo = None # 当前会话的 unified_msg_origin
        self._running = False

    async def initialize(self):
        self._running = True
        asyncio.create_task(self._ws_loop())

    async def _ws_loop(self):
        import websockets
        while self._running:
            try:
                async with websockets.connect(WS_URL) as ws:
                    self._ws = ws
                    self._buffer = ""
                    self._pending_umo = None
                    logger.info(f"Aisu WS connected: {WS_URL}")
                    while self._running:
                        raw = await ws.recv()
                        data = json.loads(raw)
                        await self._handle_ws(data)
            except Exception as e:
                logger.warning(f"Aisu WS disconnected: {e}, retrying in 3s...")
                self._ws = None
                self._buffer = ""
                self._pending_umo = None
                await asyncio.sleep(3)

    async def _handle_ws(self, data: dict):
        t = data.get("type", "")
        sid = data.get("session_id", "")

        if t == "token":
            self._buffer += data.get("content", "")

        elif t == "done":
            text = self._buffer
            self._buffer = ""
            if text and self._pending_umo:
                try:
                    await self.context.send_message(
                        self._pending_umo,
                        MessageChain().message(text),
                    )
                except Exception as e:
                    logger.error(f"send failed: {e}")
                self._pending_umo = None

        elif t == "error":
            logger.error(f"Agent error: {data.get('content','')}")
            if self._pending_umo:
                try:
                    await self.context.send_message(
                        self._pending_umo,
                        MessageChain().message(f"❌ {data.get('content', '发生错误')}"),
                    )
                except Exception:
                    pass
            self._buffer = ""
            self._pending_umo = None

        elif t == "cron_result":
            logger.info(f"cron_result received: sid={sid} task={data.get('task','')[:40]}")
            if sid and sid in self._ums:
                text = f"⏰ {data.get('task','')} — {data.get('status','completed')}"
                try:
                    await self.context.send_message(
                        self._ums[sid],
                        MessageChain().message(text),
                    )
                    logger.info(f"cron sent to QQ: {sid}")
                except Exception as e:
                    logger.error(f"cron send failed: {e}")
            else:
                logger.warning(f"cron_result: no umo for sid={sid}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        msg = event.message_str.strip()
        if not msg:
            return

        user_id = event.get_sender_id()
        session_id = f"qq_{user_id}"
        self._ums[session_id] = event.unified_msg_origin
        self._pending_umo = event.unified_msg_origin

        profile = "qq" if event.get_group_id() else "dev"

        if not self._ws:
            yield event.plain_result("服务连接中，请稍后再试")
            return

        try:
            await self._ws.send(json.dumps({
                "type": "message",
                "content": msg,
                "session_id": session_id,
                "source": "qq",
                "profile": profile,
            }))
        except Exception as e:
            logger.error(f"WS send failed: {e}")
            yield event.plain_result(f"发送失败: {e}")

    async def terminate(self):
        self._running = False
        if self._ws:
            await self._ws.close()
