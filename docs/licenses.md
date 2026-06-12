# 版权与许可证

## 项目许可证

基于 [MIT 许可](https://github.com/phil616/dst-server-icp/blob/main/LICENSE) 发布。

Copyright (c) 2026 phil616

> 适用项目：dst-serverd — 饥荒联机版(DST)专用服务器管理系统
> 
> 最后更新：2026-06-12

>  本项目（dst-serverd）是独立开发的第三方饥荒联机版（Don't Starve Together）
>
>  服务器管理工具，与 Klei Entertainment Inc. 没有任何关联、赞助或背书。
>
>  "Don't Starve Together" 是 Klei Entertainment Inc. 的商标。
>
>  游戏内容、资产及相关知识产权均归 Klei Entertainment Inc. 所有。
>
>  使用本工具需要用户持有正版 Don't Starve Together 并遵守：
>
>  - Klei Entertainment 最终用户许可协议
>  - Steam 用户协议
>  - Klei Entertainment 玩家创作指南


## 核心法律框架

| 层级 | 文件 | 发布方 |
|------|------|--------|
| 1 | DST 最终用户许可协议 (EULA) | Klei Entertainment |
| 2 | Steam 用户协议 (SSA) | Valve Corporation |
| 3 | Klei 玩家创作指南 / Mod 指南 | Klei Entertainment |
| 4 | Klei 隐私政策 | Klei Entertainment |

## DST 最终用户许可协议 (EULA)

官方链接：https://store.steampowered.com/eula/322330_eula_0

### 授权范围

Klei 授予用户的是一项**有限的、非排他性、不可转让、不可再授权的使用权**，仅限于个人非商业性游戏为目的。

### 禁止行为

| 禁止行为 | 说明 |
|----------|------|
| 商业利用 | 不得对工具本身收费 |
| 转让或分授权 | 不得将 Klei 服务器二进制文件打包再分发 |
| 逆向工程 | 不得解包游戏数据、反编译服务器可执行文件 |
| 修改游戏 | 不得直接 patch/修改服务器二进制文件 |
| 未授权第三方程序 | 工具只能通过官方接口交互 |

### 服务中止权

Klei 可以随时关闭认证服务器或废止 cluster token，无需通知、无需赔偿。

## 专用服务器许可要求

| 服务器类型 | 是否需要购买 DST | Cluster Token |
|------------|------------------|---------------|
| 在线公开服务器 | 必须 | 必须 |
| 离线/局域网服务器 | 不需要 | 不需要 |

- 一份 DST 购买可运行无限个服务器实例（服务端软件本身免费）
- Token 生成地址：https://accounts.klei.com/account/game/servers?game=DontStarveTogether

## Steam 用户协议 (SSA)

官方链接：https://store.steampowered.com/subscriber_agreement/

### 自动化限制

禁止使用脚本、机器人、宏或其他非人为控制系统与 Steam 交互。本项目：
- 允许：通过 SteamCMD 更新服务器（Valve 官方工具）
- 允许：管理服务器进程（不涉及 Steam 平台交互）
- 禁止：模拟 Steam 登录、自动抓取商店数据、自动操作账户

## Klei 玩家创作指南

官方链接：https://support.klei.com/hc/en-us/articles/360029880791-Player-Creation-Guidelines

本项目属于"工具/应用"类玩家创作，需遵守：

- 必须声明**非官方项目，与 Klei Entertainment 无关联**
- 不得使用 Klei 官方 logo 或暗示 Klei 背书
- **开源且免费发布**允许，向工具本身收费不允许

## 知识产权归属

Klei 拥有游戏源代码、美术资源、角色名称、商标、声音资产等全部知识产权。工具开发中：
- 不得将游戏原始美术素材用于工具 UI 设计
- 不得使用游戏角色图像作为工具品牌形象
- 可以使用游戏名称作为描述性说明

## 服务器管理工具的合规边界

### 明确允许

| 操作 | 依据 |
|------|------|
| 调用 SteamCMD 更新服务器 | Valve 官方工具，SSA 允许 |
| 管理服务器进程（启/停/重启） | 系统层面，不涉及协议 |
| 读写服务器配置文件 | 用户自有文件 |
| 通过 Lua console 发送命令 | 官方支持的管理接口 |
| 管理 Workshop Mod 列表 | 用户行为，通过官方接口 |
| 开源发布工具（免费） | 玩家创作指南允许 |

### 明确禁止

| 操作 | 禁止依据 |
|------|----------|
| 反编译服务器二进制文件 | EULA 逆向工程条款 |
| 自动登录 Klei/Steam 账号 | SSA 自动化禁令 |
| 分发服务器二进制文件副本 | EULA 禁止再分发 |
| 对工具核心功能收费 | 玩家创作指南商业限制 |
| 使用 Klei 官方 logo/美术素材 | 商标+版权 |
| 绕过 cluster token 认证 | EULA 反作弊条款 |

## 参考链接

| 文件 | 链接 |
|------|------|
| DST EULA | https://store.steampowered.com/eula/322330_eula_0 |
| Steam 用户协议 | https://store.steampowered.com/subscriber_agreement/ |
| Klei 隐私政策 | https://www.klei.com/privacy-policy |
| 玩家创作指南 | https://support.klei.com/hc/en-us/articles/360029880791 |
| Mod 与 UGC 指南 | https://support.klei.com/hc/en-us/articles/27787028069012 |
| Cluster Token 管理 | https://accounts.klei.com/account/game/servers |
