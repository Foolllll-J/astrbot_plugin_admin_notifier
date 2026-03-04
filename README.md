<div align="center">

# 📢 QQ 群举报

<i>🚀 一键通知，高效管理！</i>

![License](https://img.shields.io/badge/license-AGPL--3.0-green?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10+-blue?style=flat-square&logo=python&logoColor=white)
![AstrBot](https://img.shields.io/badge/framework-AstrBot-ff6b6b?style=flat-square)

</div>

## 📖 简介

一款为 [**AstrBot**](https://github.com/AstrBotDevs/AstrBot) 设计的举报通知插件，群友可以通过指令快速 @ 所有管理员，并支持引用被举报消息，方便管理员及时处理违规内容。

---

## ✨ 功能特性

- 🚨 支持 `/举报 [原因]` 指令快速通知所有管理员
- 💬 支持回复某条消息进行举报
- 📝 显示举报人信息和举报原因
- 👤 自动过滤通知举报事件当事人
- 🛡️ 支持群聊白名单与指令黑白名单设置
- 👥 支持自定义通知对象和排除通知对象
- 📤 支持通知转发到目标群聊/私聊会话
- 🧷 支持引用举报时转发被引用原消息
- 📶 支持按群等级限制使用举报指令

---

## 🎮 指令模块

### 基本用法

直接发送举报指令：

```
/举报 广告
```

或使用别名：

```
/举办 广告
```

### 回复消息举报

回复某条消息后使用举报指令，会引用被举报的消息：

```
[回复某条消息]
/举报 发广告
```

### 不指定原因

如果不填写举报原因，会显示"未说明"：

```
/举报
```

---

## ⚙️ 配置说明

### 全局配置

| 配置项 | 类型 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- |
| **`whitelist_groups`** | `list` | `[]` | 仅在这些群组中启用。为空则全局启用。 |
| **`report_whitelist`** | `list` | `[]` | 举报白名单。列表中的用户无法被举报。 |
| **`command_blacklist`** | `list` | `[]` | 指令黑名单。列表中的用户无法使用举报功能。 |
| **`group_rules`** | `template_list` | `[]` | 按群配置举报规则。配置后优先使用规则匹配。 |

### 群规则配置

| 字段 | 类型 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- |
| **`groups`** | `list` | `[]` | 生效群号列表。为空表示全局规则（对所有群生效）。 |
| **`level_threshold`** | `int` | `0` | 使用举报指令所需最低群等级；`0` 表示不限制。 |
| **`notify_target`** | `string` | `管理员` | 通知对象：`管理员`、`群主`、`仅自定义`。 |
| **`custom_notify_ids`** | `list` | `[]` | 额外通知账号 ID 列表。 |
| **`exclude_notify_ids`** | `list` | `[]` | 不通知账号 ID 列表。 |
| **`notify_group_ids`** | `list` | `[]` | 群聊通知会话 ID。 |
| **`notify_private_ids`** | `list` | `[]` | 私聊通知会话 ID。 |
| **`suppress_group_mention_when_forward`** | `bool` | `true` | 成功转发后原群仅提示“已通知管理员”，不再 `@`。 |

---

## ❤️ 支持

* [AstrBot 帮助文档](https://astrbot.app)
* 如果您在使用中遇到问题，欢迎在本仓库提交 [Issue](https://github.com/Foolllll-J/astrbot_plugin_admin_notifier/issues)。

---

<div align="center">

**如果本插件对你有帮助，欢迎点个 ⭐ Star 支持一下！**

</div>
