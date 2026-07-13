from typing import AsyncGenerator, Optional

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.api.event.filter import EventMessageType, PlatformAdapterType
from astrbot.api.star import Context, Star

from .core.demerit import DemeritHandler
from .core.reporting import ReportHandler


KV_REPORT_RECORDS_KEY = "report_records"


class AdminNotifier(Star):
    def __init__(self, context: Context, config: Optional[dict] = None):
        super().__init__(context)
        self.config = config or {}
        self.report_handler = ReportHandler(self.config)
        self.demerit_handler = DemeritHandler(self.config)

    async def initialize(self):
        records = await self.get_kv_data(KV_REPORT_RECORDS_KEY, default={})
        if records:
            self.report_handler.set_report_records(records)
            logger.info("已从 KV 恢复举报禁言记录，共 %s 个群记录", len(records))

    async def terminate(self):
        records = self.report_handler.get_report_records()
        await self.put_kv_data(KV_REPORT_RECORDS_KEY, records)
        logger.info("举报禁言记录已保存到 KV，共 %s 个群记录", len(records))
        logger.info("QQ 群举报插件已卸载")

    @filter.command("举报", alias={"举办"})
    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    async def report_command(
        self,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[MessageEventResult, None]:
        """处理举报通知并通知对应管理员"""
        async for result in self.report_handler.handle_report(event):
            yield result

    @filter.command("警告", alias={"记过"})
    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    async def warning_command(
        self,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[MessageEventResult, None]:
        """记录指定群成员的警告信息"""
        yield await self.demerit_handler.add_record(
            event,
            record_type="警告",
            command_names=("警告", "记过"),
        )

    @filter.command("查看劣迹", alias={"查前科"})
    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    async def show_demerit_command(
        self,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[MessageEventResult, None]:
        """查看指定群成员的劣迹记录"""
        yield await self.demerit_handler.show_user_records(event)

    @filter.command(
        "查看劣迹群友",
        alias={"查看群友前科"},
    )
    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    async def show_group_demerit_command(
        self,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[MessageEventResult, None]:
        """查看当前群所有有记录的群成员"""
        yield await self.demerit_handler.show_group_summary(event)

    @filter.command(
        "撤销警告",
        alias={"撤销劣迹", "撤销记过"},
    )
    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    async def revoke_warning_command(
        self,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[MessageEventResult, None]:
        """撤销指定群成员的某一条劣迹记录"""
        yield await self.demerit_handler.revoke_latest_record(event)
