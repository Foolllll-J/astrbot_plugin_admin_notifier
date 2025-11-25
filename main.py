from typing import AsyncGenerator, List, Optional, Dict, Any
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.platform import MessageType
import astrbot.api.message_components as Comp
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent

@register("astrbot_plugin_admin_notifier", "Foolllll", "群聊举报通知插件", "0.1")
class AdminNotifier(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config if config else {}
        self.whitelist_groups: List[int] = [int(g) for g in self.config.get("whitelist_groups", [])]
        logger.info("举报通知插件已加载")

    async def _get_group_admins(self, event: AiocqhttpMessageEvent) -> Optional[List[Dict[str, Any]]]:
        """获取群管理员列表（包括群主和管理员）"""
        try:
            group_id = event.get_group_id()
            if not group_id:
                return None

            client = event.bot
            params = {"group_id": group_id}
            members_info = await client.api.call_action('get_group_member_list', **params)
            
            if not members_info:
                logger.warning(f"无法获取群 {group_id} 的成员信息")
                return None
            
            # 筛选出管理员和群主
            admins = [
                member for member in members_info 
                if member.get("role") in ["owner", "admin"]
            ]
            
            logger.info(f"成功获取群 {group_id} 的 {len(admins)} 名管理员")
            return admins
        except Exception as e:
            logger.error(f"获取群管理员列表失败: {e}")
            return None

    @filter.command("举报")
    async def report_command(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """举报指令：@所有管理员"""
        # 检查是否为群聊
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            yield event.plain_result("此指令仅在群聊中可用")
            return
        
        # 检查平台是否为 aiocqhttp
        if not isinstance(event, AiocqhttpMessageEvent):
            yield event.plain_result("此功能仅支持QQ群聊")
            return
        
        group_id = int(event.get_group_id())
        
        # 检查白名单
        if self.whitelist_groups and group_id not in self.whitelist_groups:
            logger.info(f"群 {group_id} 不在白名单中，忽略举报指令")
            return
        
        # 获取举报人信息
        reporter_id = event.get_sender_id()
        reporter_name = event.get_sender_name()
        
        # 获取bot自身ID
        bot_id = event.get_self_id()
        
        # 解析举报内容
        report_reason = event.message_str.strip()
        if not report_reason:
            report_reason = "未说明"
        
        # 获取群管理员列表
        admins = await self._get_group_admins(event)
        if not admins:
            yield event.plain_result("获取管理员列表失败，请稍后再试")
            return
        
        # 过滤掉bot自己和举报人（如果他们也是管理员）
        admins_to_notify = [
            admin for admin in admins 
            if str(admin.get("user_id")) != str(reporter_id) 
            and str(admin.get("user_id")) != str(bot_id)
        ]
        
        logger.info(f"群 {group_id} 管理员总数: {len(admins)}, 过滤后需通知: {len(admins_to_notify)} (已排除举报人{reporter_id}和Bot{bot_id})")
        
        if not admins_to_notify:
            yield event.plain_result("没有可通知的管理员")
            return
        
        # 检查是否回复了某条消息
        reply_component = None
        for segment in event.get_messages():
            if isinstance(segment, Comp.Reply):
                reply_component = segment
                break
        
        # 构建艾特管理员的消息
        message_components = []
        
        # 如果回复了消息，引用那条消息；否则引用举报人的消息
        if reply_component:
            # 用户回复了某条消息进行举报
            message_components.append(Comp.Reply(id=reply_component.id))
        else:
            # 用户没有回复消息，引用他发的举报消息
            message_components.append(Comp.Reply(id=event.message_obj.message_id))
        
        # 添加通知文本
        notification_text = f"【举报通知】\n举报人：{reporter_name}({reporter_id})\n举报内容：{report_reason}\n\n"
        message_components.append(Comp.Plain(text=notification_text))
        
        # 艾特所有管理员
        for i, admin in enumerate(admins_to_notify):
            admin_id = str(admin.get("user_id"))
            admin_name = admin.get("card") or admin.get("nickname") or f"管理员{admin_id}"
            message_components.append(Comp.At(qq=admin_id, name=admin_name))
            # 在每个@之间加个空格，避免粘连
            if i < len(admins_to_notify) - 1:
                message_components.append(Comp.Plain(text=" "))
        
        # 发送消息
        yield event.chain_result(message_components)
        logger.info(f"群 {group_id} 中用户 {reporter_name}({reporter_id}) 使用举报功能，已通知 {len(admins_to_notify)} 名管理员")

    async def terminate(self):
        """插件卸载时调用"""
        logger.info("管理员举报通知插件已卸载")
