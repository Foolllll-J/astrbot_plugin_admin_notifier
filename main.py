from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, MessageEventResult, filter
from astrbot.api.platform import MessageType
from astrbot.api.star import Context, Star
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


@dataclass
class GroupRule:
    """群规则配置。"""

    groups: Set[str]
    notify_target: str
    custom_notify_ids: List[str]
    exclude_notify_ids: Set[str]
    notify_group_ids: List[str]
    notify_private_ids: List[str]
    level_threshold: int
    suppress_group_mention_when_forward: bool


@dataclass
class NotifyTarget:
    """最终需要通知的对象。"""

    user_id: str
    name: str


class AdminNotifier(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}

        self.whitelist_groups: List[int] = [
            int(g)
            for g in self.config.get("whitelist_groups", [])
            if str(g).strip().isdigit()
        ]
        self.report_whitelist: Set[str] = set(
            self._normalize_id_list(self.config.get("report_whitelist", []))
        )
        self.command_blacklist: Set[str] = set(
            self._normalize_id_list(self.config.get("command_blacklist", []))
        )
        self.group_rules: List[GroupRule] = self._load_group_rules(
            self.config.get("group_rules", [])
        )

        logger.info(
            "举报通知插件已加载：白名单群=%s，规则数=%s",
            len(self.whitelist_groups),
            len(self.group_rules),
        )

    @staticmethod
    def _normalize_id_list(values: Any) -> List[str]:
        """将任意列表配置归一化为字符串 ID 列表。"""
        if not isinstance(values, list):
            return []

        result: List[str] = []
        for value in values:
            text = str(value).strip()
            if text:
                result.append(text)
        return result

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _load_group_rules(self, rules_raw: Any) -> List[GroupRule]:
        """读取并规范化规则配置。"""
        if not isinstance(rules_raw, list):
            return []

        rules: List[GroupRule] = []
        for item in rules_raw:
            if not isinstance(item, dict):
                continue

            groups = {
                str(g).strip()
                for g in item.get("groups", [])
                if str(g).strip()
            }

            notify_target = self._normalize_notify_target(
                item.get("notify_target", "管理员")
            )

            rules.append(
                GroupRule(
                    groups=groups,
                    notify_target=notify_target,
                    custom_notify_ids=self._normalize_id_list(
                        item.get("custom_notify_ids", [])
                    ),
                    exclude_notify_ids=set(
                        self._normalize_id_list(item.get("exclude_notify_ids", []))
                    ),
                    notify_group_ids=self._normalize_id_list(
                        item.get("notify_group_ids", [])
                    ),
                    notify_private_ids=self._normalize_id_list(
                        item.get("notify_private_ids", [])
                    ),
                    level_threshold=max(self._safe_int(item.get("level_threshold", 0), 0), 0),
                    suppress_group_mention_when_forward=bool(
                        item.get("suppress_group_mention_when_forward", True)
                    ),
                )
            )

        return rules

    @staticmethod
    def _normalize_notify_target(value: Any) -> str:
        """仅接受中文通知对象配置。"""
        raw = str(value).strip()
        if raw in {"管理员", "群主", "仅自定义"}:
            return raw
        return "管理员"

    def _resolve_group_rule(self, group_id: str) -> Optional[GroupRule]:
        """根据群号匹配规则：指定群规则优先，全局规则兜底。"""
        # 先匹配显式指定了群号的规则
        for rule in self.group_rules:
            if rule.groups and group_id in rule.groups:
                return rule

        # 再匹配全局规则（groups 为空）
        for rule in self.group_rules:
            if not rule.groups:
                return rule
        return None

    def _is_group_enabled(
        self,
        group_id_int: int,
        matched_rule: Optional[GroupRule],
    ) -> bool:
        """判断当前群是否允许触发插件。"""
        if self.group_rules:
            return matched_rule is not None
        if self.whitelist_groups and group_id_int not in self.whitelist_groups:
            return False
        return True

    async def _get_group_admins(
        self,
        event: AiocqhttpMessageEvent,
    ) -> Optional[List[Dict[str, Any]]]:
        """获取群主与管理员列表。"""
        try:
            group_id = event.get_group_id()
            if not group_id:
                return None

            members_info = await event.bot.api.call_action(
                "get_group_member_list", group_id=int(group_id)
            )
            if not members_info:
                logger.warning("获取群成员失败：group_id=%s", group_id)
                return None

            return [
                member
                for member in members_info
                if member.get("role") in {"owner", "admin"}
            ]
        except Exception as e:
            logger.error("获取管理员列表异常：%s", e)
            return None

    async def _check_group_level_permission(
        self,
        event: AiocqhttpMessageEvent,
        level_threshold: int,
    ) -> Tuple[bool, int]:
        """检查群成员等级权限。返回(是否允许, 当前等级)。"""
        if level_threshold <= 0:
            return True, 0

        try:
            group_id = int(event.get_group_id())
            user_id = int(event.get_sender_id())
            info = await event.bot.api.call_action(
                "get_group_member_info",
                group_id=group_id,
                user_id=user_id,
                no_cache=True,
            )
            level = int(info.get("level", 0))
            role = str(info.get("role", "member"))

            # 群主和管理员默认放行
            if role in {"owner", "admin"}:
                return True, level

            return level >= level_threshold, level
        except Exception as e:
            logger.warning("获取群成员等级失败，默认放行：%s", e)
            return True, 0

    @staticmethod
    def _extract_admin_display_name(admin: Dict[str, Any], user_id: str) -> str:
        return (
            str(admin.get("card", "")).strip()
            or str(admin.get("nickname", "")).strip()
            or f"管理员{user_id}"
        )

    def _build_notify_targets(
        self,
        admins: List[Dict[str, Any]],
        rule: Optional[GroupRule],
        reporter_id: str,
        bot_id: str,
        reported_user_id: Optional[str],
    ) -> List[NotifyTarget]:
        """根据规则与上下文生成通知对象列表。"""
        notify_target = "管理员"
        custom_notify_ids: List[str] = []
        exclude_notify_ids: Set[str] = set()

        if rule:
            notify_target = rule.notify_target
            custom_notify_ids = list(rule.custom_notify_ids)
            exclude_notify_ids = set(rule.exclude_notify_ids)

        names: Dict[str, str] = {}
        candidates: List[str] = []

        for admin in admins:
            user_id = str(admin.get("user_id", "")).strip()
            if not user_id:
                continue

            role = str(admin.get("role", "")).strip()
            names[user_id] = self._extract_admin_display_name(admin, user_id)

            if notify_target == "群主" and role == "owner":
                candidates.append(user_id)
            elif notify_target == "管理员" and role in {"owner", "admin"}:
                candidates.append(user_id)

        candidates.extend(custom_notify_ids)

        always_excluded = {reporter_id, bot_id}
        if reported_user_id:
            always_excluded.add(reported_user_id)

        final_targets: List[NotifyTarget] = []
        seen: Set[str] = set()
        for user_id in candidates:
            uid = str(user_id).strip()
            if not uid or uid in seen:
                continue
            seen.add(uid)

            if uid in exclude_notify_ids or uid in always_excluded:
                continue

            final_targets.append(NotifyTarget(uid, names.get(uid, f"管理员{uid}")))

        return final_targets

    def _parse_notify_ids(
        self,
        raw_values: List[str],
        target_type_name: str,
    ) -> List[str]:
        """将目标配置解析为纯数字 ID。"""
        notify_ids: List[str] = []
        seen: Set[str] = set()

        for raw_value in raw_values:
            text = str(raw_value).strip()
            if not text:
                continue

            if not text.isdigit():
                logger.warning("通知%sID不是纯数字，已忽略：%s", target_type_name, text)
                continue

            if text in seen:
                continue
            seen.add(text)
            notify_ids.append(text)

        return notify_ids

    def _resolve_forward_targets(
        self,
        rule: Optional[GroupRule],
    ) -> Tuple[List[str], List[str], bool]:
        """汇总并解析转发目标（群聊/私聊）。"""
        if not rule:
            return [], [], False

        group_ids = self._parse_notify_ids(rule.notify_group_ids, "群聊")
        private_ids = self._parse_notify_ids(rule.notify_private_ids, "私聊")
        return group_ids, private_ids, rule.suppress_group_mention_when_forward

    @staticmethod
    def _build_forward_text(
        group_id: str,
        reporter_name: str,
        reporter_id: str,
        report_reason: str,
        reported_user_id: Optional[str],
    ) -> str:
        reported_text = reported_user_id or "未知"
        return (
            "【举报通知】\n"
            f"来源群：{group_id}\n"
            f"举报人：{reporter_name}({reporter_id})\n"
            f"被举报人：{reported_text}\n"
            f"举报内容：{report_reason}"
        )

    async def _send_to_targets(
        self,
        event: AiocqhttpMessageEvent,
        group_ids: List[str],
        private_ids: List[str],
        text: str,
    ) -> int:
        """将通知文本转发到配置的群聊/私聊目标。"""
        sent_count = 0
        chain = MessageChain()
        chain.chain = [Comp.Plain(text=text)]

        for group_id in group_ids:
            try:
                await AiocqhttpMessageEvent.send_message(
                    bot=event.bot,
                    message_chain=chain,
                    is_group=True,
                    session_id=group_id,
                )
                sent_count += 1
            except Exception as e:
                logger.error("转发到群失败：group_id=%s, err=%s", group_id, e)

        for user_id in private_ids:
            try:
                await AiocqhttpMessageEvent.send_message(
                    bot=event.bot,
                    message_chain=chain,
                    is_group=False,
                    session_id=user_id,
                )
                sent_count += 1
            except Exception as e:
                logger.error("转发到私聊失败：user_id=%s, err=%s", user_id, e)

        return sent_count

    async def _forward_replied_message_to_targets(
        self,
        event: AiocqhttpMessageEvent,
        reply_message_id: Any,
        group_ids: List[str],
        private_ids: List[str],
    ) -> int:
        """将被引用原消息转发到目标会话。"""
        if not reply_message_id:
            return 0

        message_id = str(reply_message_id).strip()
        if not message_id:
            return 0

        sent_count = 0
        for group_id in group_ids:
            try:
                await event.bot.api.call_action(
                    "forward_group_single_msg",
                    group_id=int(group_id),
                    message_id=message_id,
                )
                sent_count += 1
            except Exception as e:
                logger.error("单条转发原消息到群失败：group_id=%s, err=%s", group_id, e)

        for user_id in private_ids:
            try:
                await event.bot.api.call_action(
                    "forward_friend_single_msg",
                    user_id=int(user_id),
                    message_id=message_id,
                )
                sent_count += 1
            except Exception as e:
                logger.error("单条转发原消息到私聊失败：user_id=%s, err=%s", user_id, e)

        return sent_count

    @staticmethod
    def _build_group_mention_message(
        event: AstrMessageEvent,
        reporter_name: str,
        reporter_id: str,
        report_reason: str,
        targets: List[NotifyTarget],
        reply_component: Optional[Comp.Reply],
    ) -> List[Any]:
        """构造群内 @ 管理员的消息链。"""
        components: List[Any] = []

        if reply_component:
            components.append(Comp.Reply(id=reply_component.id))
        else:
            components.append(Comp.Reply(id=event.message_obj.message_id))

        components.append(
            Comp.Plain(
                text=(
                    "【举报通知】\n"
                    f"举报人：{reporter_name}({reporter_id})\n"
                    f"举报内容：{report_reason}\n"
                    "已通知管理员："
                )
            )
        )

        for idx, target in enumerate(targets):
            components.append(Comp.At(qq=target.user_id, name=target.name))
            if idx < len(targets) - 1:
                components.append(Comp.Plain(text="\u200b \u200b"))

        return components

    async def _extract_reported_user_id(
        self,
        event: AiocqhttpMessageEvent,
    ) -> Tuple[Optional[Comp.Reply], Optional[str], bool]:
        """解析回复消息，提取被举报人 ID。返回(回复组件, 被举报ID, 是否被保护)。"""
        reply_component: Optional[Comp.Reply] = None
        reported_user_id: Optional[str] = None

        for segment in event.get_messages() or []:
            if not isinstance(segment, Comp.Reply):
                continue
            reply_component = segment
            try:
                replied_msg = await event.bot.api.call_action(
                    "get_msg", message_id=reply_component.id
                )
                if replied_msg and "sender" in replied_msg:
                    reported_user_id = str(
                        replied_msg["sender"].get("user_id", "")
                    ).strip()
                    if reported_user_id and reported_user_id in self.report_whitelist:
                        return reply_component, reported_user_id, True
            except Exception as e:
                logger.warning("获取被回复消息发送者失败：%s", e)
            break

        return reply_component, reported_user_id, False

    @filter.command("举报", alias={"举办"})
    async def report_command(
        self,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[MessageEventResult, None]:
        """举报指令入口。"""
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            yield event.plain_result("此指令仅可在群聊中使用")
            return

        if not isinstance(event, AiocqhttpMessageEvent):
            yield event.plain_result("此功能仅支持 OneBot v11 群聊")
            return

        group_id = str(event.get_group_id() or "").strip()
        if not group_id.isdigit():
            yield event.plain_result("无法识别当前群号")
            return

        rule = self._resolve_group_rule(group_id)
        if not self._is_group_enabled(int(group_id), rule):
            logger.info("群未启用举报通知：group_id=%s", group_id)
            return

        # 规则内群等级限制：0 表示不限制
        if rule and rule.level_threshold > 0:
            is_allowed, current_level = await self._check_group_level_permission(
                event, rule.level_threshold
            )
            if not is_allowed:
                yield event.plain_result(
                    f"你的群等级 ({current_level}) 不足，需要达到 {rule.level_threshold} 级才能使用此指令"
                )
                return

        reporter_id = str(event.get_sender_id()).strip()
        reporter_name = event.get_sender_name() or reporter_id

        if reporter_id in self.command_blacklist:
            logger.info("举报指令被黑名单拦截：user_id=%s", reporter_id)
            event.stop_event()
            return

        bot_id = str(event.get_self_id()).strip()
        parts = event.message_str.strip().split(maxsplit=1)
        report_reason = parts[1].strip() if len(parts) > 1 else "未说明"

        reply_component, reported_user_id, is_protected = await self._extract_reported_user_id(
            event
        )
        if is_protected:
            yield event.plain_result("该用户受保护，无法被举报")
            return

        admins = await self._get_group_admins(event)
        if not admins:
            yield event.plain_result("获取管理员列表失败，请稍后再试")
            return

        targets = self._build_notify_targets(
            admins=admins,
            rule=rule,
            reporter_id=reporter_id,
            bot_id=bot_id,
            reported_user_id=reported_user_id,
        )

        # 无可通知对象时直接结束，不再执行目标会话转发
        if not targets:
            yield event.plain_result("没有可通知的管理员")
            return

        forward_group_ids, forward_private_ids, suppress_group_mention = (
            self._resolve_forward_targets(rule)
        )

        forwarded_count = 0
        if forward_group_ids or forward_private_ids:
            forward_text = self._build_forward_text(
                group_id=group_id,
                reporter_name=reporter_name,
                reporter_id=reporter_id,
                report_reason=report_reason,
                reported_user_id=reported_user_id,
            )
            forwarded_count = await self._send_to_targets(
                event=event,
                group_ids=forward_group_ids,
                private_ids=forward_private_ids,
                text=forward_text,
            )

            logger.info(
                "举报转发完成：group_id=%s, 成功=%s, 目标群=%s, 目标私聊=%s",
                group_id,
                forwarded_count,
                len(forward_group_ids),
                len(forward_private_ids),
            )

            if suppress_group_mention and forwarded_count > 0:
                # 仅通知目标会话时：若本次举报引用了消息，则额外转发被引用原消息
                if reply_component:
                    raw_forwarded = await self._forward_replied_message_to_targets(
                        event=event,
                        reply_message_id=reply_component.id,
                        group_ids=forward_group_ids,
                        private_ids=forward_private_ids,
                    )
                    if raw_forwarded > 0:
                        logger.info(
                            "举报原消息转发完成：group_id=%s, 成功=%s, reply_message_id=%s",
                            group_id,
                            raw_forwarded,
                            reply_component.id,
                        )
                yield event.plain_result("已通知管理员")
                return

        message_components = self._build_group_mention_message(
            event=event,
            reporter_name=reporter_name,
            reporter_id=reporter_id,
            report_reason=report_reason,
            targets=targets,
            reply_component=reply_component,
        )
        yield event.chain_result(message_components)

        logger.info(
            "举报处理完成：group_id=%s, reporter_id=%s, @目标=%s, 转发成功=%s",
            group_id,
            reporter_id,
            len(targets),
            forwarded_count,
        )

    async def terminate(self):
        logger.info("举报通知插件已卸载")
