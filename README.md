<div align="center">

# 📢 举报通知插件

<i>🚀 一键通知，高效管理！</i>

![License](https://img.shields.io/badge/license-AGPL--3.0-green?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10+-blue?style=flat-square&logo=python&logoColor=white)
![AstrBot](https://img.shields.io/badge/framework-AstrBot-ff6b6b?style=flat-square)

</div>

## ✨ 简介

一款为 [**AstrBot**](https://github.com/AstrBotDevs/AstrBot) 设计的举报通知插件，群友可以通过指令快速 @ 所有管理员，并支持引用被举报消息，方便管理员及时处理违规内容。

---

## ✨ 功能特性

- 🚨 支持 `/举报 [原因]` 指令快速通知所有管理员
- 💬 支持回复某条消息进行举报
- 📝 显示举报人信息和举报原因
- 👤 自动过滤通知举报事件当事人
- ✅ 支持白名单群聊设置
- 🛡️ 举报白名单：受保护的用户无法被举报
- 🚫 指令黑名单：黑名单用户无法使用举报指令

---

## 📖 使用方法

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

| 配置项 | 类型 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- |
| **`whitelist_groups`** | `list` | `[]` | 仅在这些群组中启用。为空则全局启用。 |
| **`report_whitelist`** | `list` | `[]` | 举报白名单。列表中的用户无法被举报。 |
| **`command_blacklist`** | `list` | `[]` | 指令黑名单。列表中的用户无法使用举报功能。 |

---

## 📅 更新日志

**v1.1**

- 新增 `举报白名单`
- 新增 `指令黑名单`

**v1.0**

- 实现基本举报功能
- 支持白名单群聊

---

## ❤️ 支持

* [AstrBot 帮助文档](https://astrbot.app)
* 如果您在使用中遇到问题，欢迎在本仓库提交 [Issue](https://github.com/Foolllll-J/astrbot_plugin_admin_notifier/issues)。

---

<div align="center">

**如果本插件对你有帮助，欢迎点个 ⭐ Star 支持一下！**

</div>
