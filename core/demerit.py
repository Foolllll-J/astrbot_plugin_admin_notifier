import asyncio
import json
import re
from datetime import datetime
from typing import Any, Iterable, Optional

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.platform import MessageType
from astrbot.api.star import StarTools
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


PLUGIN_NAME = "astrbot_plugin_admin_notifier"
DATA_FILE_NAME = "demerit_records.json"
UNKNOWN_MEMBER_NAME = "未知成员"


class DemeritStore:
    def __init__(self, plugin_name: str = PLUGIN_NAME):
        self._path = StarTools.get_data_dir(plugin_name) / DATA_FILE_NAME
        self._lock = asyncio.Lock()

    async def add_record(
        self,
        *,
        group_id: str,
        target_user_id: str,
        record: dict[str, Any],
    ) -> int:
        async with self._lock:
            data = self._load()
            records = self._ensure_user_records(data, group_id, target_user_id)
            records.append(record)
            self._save(data)
            return len(records)

    async def get_records(
        self,
        *,
        group_id: str,
        target_user_id: str,
    ) -> list[dict[str, Any]]:
        async with self._lock:
            data = self._load()
            users = data.get("groups", {}).get(group_id, {}).get("users", {})
            records = users.get(target_user_id, {}).get("records", [])
            return list(records)

    async def remove_record(
        self,
        *,
        group_id: str,
        target_user_id: str,
        display_index: int = 1,
    ) -> tuple[Optional[dict[str, Any]], int]:
        async with self._lock:
            data = self._load()
            users = data.get("groups", {}).get(group_id, {}).get("users", {})
            user_entry = users.get(target_user_id)
            if not user_entry:
                return None, 0

            records = user_entry.get("records", [])
            if not records:
                return None, 0

            total_count = len(records)
            if display_index <= 0 or display_index > total_count:
                return None, total_count

            removed = records.pop(-display_index)
            if not records:
                users.pop(target_user_id, None)
            if not users:
                data.get("groups", {}).pop(group_id, None)

            self._save(data)
            return removed, total_count

    async def get_group_records(
        self,
        *,
        group_id: str,
    ) -> dict[str, list[dict[str, Any]]]:
        async with self._lock:
            data = self._load()
            users = data.get("groups", {}).get(group_id, {}).get("users", {})
            return {
                user_id: list(user_entry.get("records", []))
                for user_id, user_entry in users.items()
            }

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"groups": {}}

        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("解析劣迹数据文件失败：path=%s, err=%s", self._path, exc)
            return {"groups": {}}
        except OSError as exc:
            logger.warning("读取劣迹数据文件失败：path=%s, err=%s", self._path, exc)
            return {"groups": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )

    @staticmethod
    def _ensure_user_records(
        data: dict[str, Any],
        group_id: str,
        target_user_id: str,
    ) -> list[dict[str, Any]]:
        groups = data.setdefault("groups", {})
        group_entry = groups.setdefault(group_id, {})
        users = group_entry.setdefault("users", {})
        user_entry = users.setdefault(target_user_id, {})
        return user_entry.setdefault("records", [])


class DemeritHandler:
    def __init__(self, plugin_name: str = PLUGIN_NAME):
        self.store = DemeritStore(plugin_name)

    async def add_record(
        self,
        event: AstrMessageEvent,
        *,
        record_type: Optional[str] = None,
        command_names: Iterable[str],
    ) -> MessageEventResult:
        valid_event, group_id, error = self._validate_group_event(event)
        if error:
            return error

        permission_error = await self._ensure_operator_is_group_admin(
            valid_event,
            group_id,
        )
        if permission_error:
            return permission_error

        target = await self._resolve_target(
            valid_event,
            group_id,
            allow_reply=True,
            allow_at=True,
        )
        if target is None:
            return event.plain_result(
                "请通过 @目标或引用消息指定要记录的成员"
            )

        reason = self._extract_reason(event, command_names)
        if not reason:
            return event.plain_result(
                "请提供理由，例如：警告 @用户 打广告"
            )

        executor_name = await self._get_group_member_display_name(
            valid_event,
            group_id,
            str(valid_event.get_sender_id()),
            fallback=valid_event.get_sender_name() or UNKNOWN_MEMBER_NAME,
        )

        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        record = {
            "record_type": "警告",
            "reason": reason,
            "created_at": created_at,
            "executor_id": str(valid_event.get_sender_id()),
            "executor_name": executor_name,
            "target_name": target["name"],
        }

        total_count = await self.store.add_record(
            group_id=group_id,
            target_user_id=target["user_id"],
            record=record,
        )

        return event.plain_result(
            "\n".join(
                [
                    f"已为 {target['name']} 记录",
                    f"理由：{reason}",
                    f"当前累计：{total_count} 次",
                ]
            )
        )

    async def show_user_records(
        self,
        event: AstrMessageEvent,
    ) -> MessageEventResult:
        valid_event, group_id, error = self._validate_group_event(event)
        if error:
            return error

        target = await self._resolve_target(
            valid_event,
            group_id,
            allow_reply=True,
            allow_at=True,
        )
        if target is None:
            return event.plain_result(
                "请通过 @目标或引用消息指定要查看的成员"
            )

        records = await self.store.get_records(
            group_id=group_id,
            target_user_id=target["user_id"],
        )
        if not records:
            return event.plain_result(f"{target['name']} 目前没有劣迹记录")

        lines = [f"累计 {len(records)} 次"]

        for index, item in enumerate(reversed(records), start=1):
            lines.append("")
            lines.append(f"【{index}】")
            lines.append(f"理由：{item.get('reason', '未填写')}")
            lines.append(f"执行者：{item.get('executor_name', UNKNOWN_MEMBER_NAME)}")
            lines.append(f"时间：{self._format_time(item.get('created_at'))}")

        return event.plain_result("\n".join(lines))

    async def show_group_summary(self, event: AstrMessageEvent) -> MessageEventResult:
        valid_event, group_id, error = self._validate_group_event(event)
        if error:
            return error

        group_records = await self.store.get_group_records(group_id=group_id)
        if not group_records:
            return event.plain_result("当前群还没有劣迹记录")

        summary_items: list[tuple[str, int, str]] = []
        for user_id, records in group_records.items():
            if not records:
                continue

            name = await self._get_group_member_display_name(
                valid_event,
                group_id,
                user_id,
                fallback=str(records[-1].get("target_name", UNKNOWN_MEMBER_NAME)),
            )
            latest_at = str(records[-1].get("created_at", ""))
            summary_items.append((name, len(records), latest_at))

        if not summary_items:
            return event.plain_result("当前群还没有劣迹记录")

        summary_items.sort(key=lambda item: (item[1], item[2]), reverse=True)

        lines = ["劣迹群友"]
        for index, item in enumerate(summary_items, start=1):
            name, total_count, latest_at = item
            lines.append("")
            lines.append(f"【{index}】{name}：{total_count} 次")
            lines.append(f"最新记录：{self._format_time(latest_at)}")

        return event.plain_result("\n".join(lines))

    async def revoke_latest_record(
        self,
        event: AstrMessageEvent,
    ) -> MessageEventResult:
        valid_event, group_id, error = self._validate_group_event(event)
        if error:
            return error

        permission_error = await self._ensure_operator_is_group_admin(
            valid_event,
            group_id,
        )
        if permission_error:
            return permission_error

        target = await self._resolve_target(
            valid_event,
            group_id,
            allow_reply=True,
            allow_at=True,
        )
        if target is None:
            return event.plain_result(
                "请通过 @目标或引用消息指定要撤销的成员"
            )

        revoke_index = self._extract_revoke_index(event, ("撤销警告", "撤销劣迹", "撤销记过"))
        if revoke_index is None:
            return event.plain_result("撤销序号必须是正整数，例如：撤销警告 @用户 2")

        removed, total_count = await self.store.remove_record(
            group_id=group_id,
            target_user_id=target["user_id"],
            display_index=revoke_index,
        )
        if removed is None:
            if total_count <= 0:
                return event.plain_result(f"{target['name']} 目前没有可撤销的记录")
            return event.plain_result(
                f"{target['name']} 目前只有 {total_count} 条记录，无法撤销第 {revoke_index} 条"
            )

        return event.plain_result(
            "\n".join(
                [
                    f"已撤销 {target['name']} 的第 {revoke_index} 条记录",
                    "",
                    f"理由：{removed.get('reason', '未填写')}",
                    f"执行者：{removed.get('executor_name', UNKNOWN_MEMBER_NAME)}",
                    f"时间：{self._format_time(removed.get('created_at'))}",
                ]
            )
        )

    @staticmethod
    def _validate_group_event(
        event: AstrMessageEvent,
    ) -> tuple[Optional[AiocqhttpMessageEvent], str, Optional[MessageEventResult]]:
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return None, "", event.plain_result(
                "此指令仅可在群聊中使用"
            )

        if not isinstance(event, AiocqhttpMessageEvent):
            return None, "", event.plain_result(
                "此功能仅支持 OneBot v11 群聊"
            )

        group_id = str(event.get_group_id() or "").strip()
        if not group_id.isdigit():
            return None, "", event.plain_result(
                "无法识别当前群号"
            )

        return event, group_id, None

    async def _ensure_operator_is_group_admin(
        self,
        event: AiocqhttpMessageEvent,
        group_id: str,
    ) -> Optional[MessageEventResult]:
        try:
            info = await event.bot.api.call_action(
                "get_group_member_info",
                group_id=int(group_id),
                user_id=int(event.get_sender_id()),
                no_cache=True,
            )
        except Exception as exc:
            logger.warning(
                "获取操作者群权限失败：group_id=%s, user_id=%s, err=%s",
                group_id,
                event.get_sender_id(),
                exc,
            )
            return event.plain_result("获取你的群权限失败，请稍后再试")

        role = str(info.get("role", "")).strip().lower()
        if role in {"owner", "admin"}:
            return None

        return event.plain_result("只有群管理员才能使用这个指令")

    async def _resolve_target(
        self,
        event: AiocqhttpMessageEvent,
        group_id: str,
        *,
        allow_reply: bool,
        allow_at: bool,
    ) -> Optional[dict[str, str]]:
        if allow_at:
            mentioned_target = await self._resolve_target_from_at(event, group_id)
            if mentioned_target is not None:
                return mentioned_target

        if allow_reply:
            replied_target = await self._resolve_target_from_reply(event, group_id)
            if replied_target is not None:
                return replied_target

        return None

    async def _resolve_target_from_at(
        self,
        event: AiocqhttpMessageEvent,
        group_id: str,
    ) -> Optional[dict[str, str]]:
        for component in event.get_messages() or []:
            if not isinstance(component, Comp.At):
                continue

            user_id = str(component.qq or "").strip()
            if not user_id or user_id == "all":
                continue

            name = await self._get_group_member_display_name(
                event,
                group_id,
                user_id,
                fallback=(component.name or UNKNOWN_MEMBER_NAME),
            )
            return {"user_id": user_id, "name": name}

        return None

    async def _resolve_target_from_reply(
        self,
        event: AiocqhttpMessageEvent,
        group_id: str,
    ) -> Optional[dict[str, str]]:
        reply_component = next(
            (
                component
                for component in (event.get_messages() or [])
                if isinstance(component, Comp.Reply)
            ),
            None,
        )
        if reply_component is not None:
            reply_user_id = str(reply_component.sender_id or "").strip()
            if not reply_user_id and reply_component.id:
                reply_user_id = await self._fetch_reply_sender_id(
                    event, str(reply_component.id)
                )
            if reply_user_id:
                name = await self._get_group_member_display_name(
                    event,
                    group_id,
                    reply_user_id,
                    fallback=(reply_component.sender_nickname or UNKNOWN_MEMBER_NAME),
                )
                return {"user_id": reply_user_id, "name": name}

        raw_reply_id = self._extract_reply_id_from_raw_message(
            getattr(event.message_obj, "raw_message", None)
        )
        if raw_reply_id:
            reply_user_id = await self._fetch_reply_sender_id(event, raw_reply_id)
            if reply_user_id:
                name = await self._get_group_member_display_name(
                    event,
                    group_id,
                    reply_user_id,
                    fallback=UNKNOWN_MEMBER_NAME,
                )
                return {"user_id": reply_user_id, "name": name}

        return None

    async def _fetch_reply_sender_id(
        self,
        event: AiocqhttpMessageEvent,
        message_id: str,
    ) -> str:
        try:
            reply_message = await event.bot.api.call_action(
                "get_msg",
                message_id=int(message_id),
            )
        except Exception as exc:  # pragma: no cover - upstream API failure
            logger.warning("解析引用消息发送者失败：message_id=%s, err=%s", message_id, exc)
            return ""

        sender = reply_message.get("sender", {}) if isinstance(reply_message, dict) else {}
        return str(sender.get("user_id", "")).strip()

    @staticmethod
    def _extract_reply_id_from_raw_message(raw_message: Any) -> str:
        segments: list[Any] = []

        if isinstance(raw_message, dict):
            segments = list(raw_message.get("message", []) or [])
        elif hasattr(raw_message, "get"):
            try:
                segments = list(raw_message.get("message", []) or [])
            except Exception:
                segments = []

        for segment in segments:
            if not isinstance(segment, dict):
                continue
            if segment.get("type") != "reply":
                continue
            data = segment.get("data", {})
            if not isinstance(data, dict):
                continue
            reply_id = str(data.get("id", "")).strip()
            if reply_id:
                return reply_id

        return ""

    async def _get_group_member_display_name(
        self,
        event: AiocqhttpMessageEvent,
        group_id: str,
        user_id: str,
        *,
        fallback: str,
    ) -> str:
        try:
            info = await event.bot.api.call_action(
                "get_group_member_info",
                group_id=int(group_id),
                user_id=int(user_id),
                no_cache=False,
            )
        except Exception as exc:  # pragma: no cover - upstream API failure
            logger.warning(
                "获取群成员信息失败：group_id=%s, user_id=%s, err=%s",
                group_id,
                user_id,
                exc,
            )
            return fallback or UNKNOWN_MEMBER_NAME

        display_name = (
            str(info.get("card", "")).strip()
            or str(info.get("nickname", "")).strip()
            or fallback
        )
        return display_name or UNKNOWN_MEMBER_NAME

    @staticmethod
    def _extract_reason(
        event: AstrMessageEvent,
        command_names: Iterable[str],
    ) -> str:
        plain_parts: list[str] = []

        for component in event.get_messages() or []:
            if isinstance(component, (Comp.At, Comp.Reply)):
                continue
            if isinstance(component, Comp.Plain):
                text = component.text.strip()
                if text:
                    plain_parts.append(text)

        merged_text = re.sub(r"\s+", " ", " ".join(plain_parts)).strip()
        if not merged_text:
            return ""

        return DemeritHandler._strip_command_prefix(merged_text, command_names)

    @staticmethod
    def _extract_revoke_index(
        event: AstrMessageEvent,
        command_names: Iterable[str],
    ) -> Optional[int]:
        plain_parts: list[str] = []

        for component in event.get_messages() or []:
            if isinstance(component, (Comp.At, Comp.Reply)):
                continue
            if isinstance(component, Comp.Plain):
                text = component.text.strip()
                if text:
                    plain_parts.append(text)

        merged_text = re.sub(r"\s+", " ", " ".join(plain_parts)).strip()
        stripped_text = DemeritHandler._strip_command_prefix(merged_text, command_names)
        if not stripped_text:
            return 1
        if not stripped_text.isdigit():
            return None

        index = int(stripped_text)
        if index <= 0:
            return None
        return index

    @staticmethod
    def _strip_command_prefix(text: str, command_names: Iterable[str]) -> str:
        normalized = re.sub(r"\s+", " ", text).strip()
        names = [re.escape(name.strip()) for name in command_names if name.strip()]
        if not names:
            return normalized

        pattern = r"^(?:[/／]\s*)?(?:" + "|".join(sorted(names, key=len, reverse=True)) + r")\s*"
        return re.sub(pattern, "", normalized, count=1).strip()

    @staticmethod
    def _format_time(raw_value: Any) -> str:
        text = str(raw_value or "").strip()
        if not text:
            return "未知时间"

        try:
            return datetime.fromisoformat(text).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return text
