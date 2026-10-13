# iKuai for Home Assistant

[简体中文](README.md) | [English](README.en.md)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=noahBin23&repository=hass-ikuai&category=integration)
[![Release](https://img.shields.io/github/v/release/noahBin23/hass-ikuai)](https://github.com/noahBin23/hass-ikuai/releases)
[![HACS validation](https://github.com/noahBin23/hass-ikuai/actions/workflows/action.yml/badge.svg)](https://github.com/noahBin23/hass-ikuai/actions/workflows/action.yml)
[![hassfest](https://github.com/noahBin23/hass-ikuai/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/noahBin23/hass-ikuai/actions/workflows/hassfest.yaml)

将爱快路由器的运行状态接入 Home Assistant。**iKuai 4.x 使用原生 REST API 和 API Token，仅提供只读传感器。**

本仓库基于 [dscao/ikuai](https://github.com/dscao/ikuai) 维护，保留原来的 `ikuai` 集成域和实体唯一标识，便于已有用户升级。

## 支持范围

| 项目 | 当前支持情况 |
| --- | --- |
| Home Assistant | 2026.10.0 及以上；本版在 2026.10.0 验证 |
| iKuai 4.x | 已验证 `4.0.313 x64 Build202609281457`；其他 4.x 固件需自行验证接口兼容性 |
| iKuai 3.x | 保留原账号密码 / Cookie 协议；通过模拟协议回归，未重新做 3.x 真机验收 |
| 安装方式 | HACS 自定义仓库，或手动复制集成目录 |
| 更新间隔 | 默认 10 秒，可在集成选项中调整，最短 5 秒 |

### 4.x 的 13 类传感器

| 传感器 | 单位 / 含义 |
| --- | --- |
| CPU | 使用率，% |
| CPU 温度 | °C |
| 内存 | 使用率，% |
| 在线终端 | 个 |
| 在线 AP | 个 |
| 连接数 | 个 |
| 上传速率 | MB/s |
| 下载速率 | MB/s |
| 累计上传 | GB |
| 累计下载 | GB |
| WAN IPv4 | 唯一默认路由对应的 IPv4 地址 |
| 设备运行时间 | 格式化时长 |
| WAN 运行时间 | 格式化时长 |

流量换算沿用原集成：速率除以 `1024²`，累计流量除以 `1024³`；累计值来自路由器，**不是 HA 按月累计**。运行时间为时长文本，不是时间戳。

4.x 不提供 MAC control、Tracker、路由重启、WAN 重连、ARP 绑定开关、智能流控、IPv6 地址或自定义 RPC 开关。不会查询 MAC 规则或终端明细，也不会向 4.x API 发送写请求。3.x 的原有功能保留在独立兼容分支。

## HACS 安装

本仓库支持 **HACS 自定义仓库**，不表示已被 HACS 默认仓库列表收录。

1. 打开 HACS，在菜单中选择 **自定义仓库**。
2. 添加 `https://github.com/noahBin23/hass-ikuai`，类型选择 **Integration / 集成**。
3. 查找 **iKuai**，下载最新正式版本。
4. 重启 Home Assistant。
5. 在 **设置 → 设备与服务 → 添加集成** 中搜索 **iKuai**。

也可通过 [此 HACS 链接](https://my.home-assistant.io/redirect/hacs_repository/?owner=noahBin23&repository=hass-ikuai&category=integration) 打开仓库。

### 手动安装

从 [Releases](https://github.com/noahBin23/hass-ikuai/releases) 下载 `ikuai-<version>.zip`，解压到 HA 配置目录，最终路径应为：

```text
<config>/custom_components/ikuai/manifest.json
```

压缩包已包含 `custom_components/ikuai/` 层级。替换代码前备份原目录，完成后重启 HA，不要把整个 GitHub 仓库复制进 `custom_components`。

## 配置 iKuai 4.x

1. 在路由器中启用 4.x API，并准备 API Token。管理入口和权限选项可能因固件不同而不同，请以该设备的管理界面为准。
2. 确认 **HA 所在主机或容器** 能访问路由器管理地址。
3. 添加集成时选择 **iKuai 4.x (API token)**，填写管理地址、Token 和证书校验选项。

地址示例：`https://router.example:8443`。也接受以 `/api/v4.0` 结尾的 API 根地址；不接受在 URL 中携带账号、密码或查询参数。

只需要以下读取权限：

```text
GET /api/v4.0/monitoring/system
GET /api/v4.0/interfaces/wan-config
GET /api/v4.0/monitoring/interfaces-status
GET /api/v4.0/monitoring/wireless-statistics
```

默认验证 HTTPS 证书。只有确认连接的是可信自签名设备时，才关闭该选项；设置只影响本集成连接。

Token 失效会提示重新认证；也可在集成菜单选择 **重新配置** 来修改连接地址或 Token。修改连接地址会保留原有设备和实体身份。不要把 Token 写进 Issues、截图或日志。

## 从旧版 / 上游仓库升级

1. 备份原集成目录和 Home Assistant 配置。
2. 在 HACS 中停止使用原 `dscao/ikuai` 仓库管理这份集成，再添加本仓库。两个仓库使用相同的 `ikuai` 目录，不能同时负责更新。**保留 HA“设备与服务”中的既有 iKuai 配置条目，不要删除并重新添加。**
3. 若使用 3.x 的 Const Tracker，单独保存个人 `DEVICE_TRACKERS` 配置；更新会覆盖 `const.py`。优先使用原有的 UI 配置方式。
4. 安装本仓库版本并重启 HA。升级路由器至 4.x 后，在原条目菜单选择 **重新配置**，填入新的管理地址和 Token。
5. 检查传感器状态及原来的禁用设置。需要设备 / WAN 运行时间时，可在实体设置中启用它们。
6. 4.x 不再加载的旧控制实体可能仍保留在注册表中。先移除仪表盘和自动化对它们的引用，再在实体设置中删除这些不再提供的记录。集成不会自动删除注册记录、统计或历史，也不会更改路由器 MAC 规则。

## 常见问题

- **全部不可用**：检查 HA 到管理地址的网络连通性、API 是否启用、Token 和证书设置。
- **只有 WAN 或 AP 不可用**：检查对应接口的读取权限和固件返回值。接口失败不应影响 CPU 等其他有效数据。
- **WAN 地址为空**：需要能唯一确认默认 WAN；多条默认路由或接口未连接时不会猜测地址。
- **看到旧按钮 / MAC control**：确认已重启 HA 加载新版，再按升级步骤清理旧注册记录。
- **更新后实体 ID 改变**：先检查是否删除重建过配置条目、是否装了两个管理同一目录的仓库。提交脱敏信息到 [Issues](https://github.com/noahBin23/hass-ikuai/issues)。

反馈时请提供 HA 版本、路由固件版本、集成版本和脱敏错误摘要。不要上传完整 `.storage`、配置备份、Token、Cookie、真实 MAC 或含凭据的响应内容。

## 开发与验证

使用 Python 3.14：

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m ruff check custom_components tests scripts
python -m ruff format --check custom_components tests scripts
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider
python scripts/package.py
python scripts/package.py --output dist/ikuai-2026.10.13.4.zip
```

测试只连接本机模拟服务，覆盖 Bearer 鉴权、分页、缺失值、局部失败、禁止写请求、配置流程、重新认证、实体身份、加载 / 卸载及禁用状态保留。打包脚本仅包含可安装的集成目录，并拒绝覆盖已有文件。HACS 和 hassfest 使用仓库既有的 GitHub Actions 校验。

```text
custom_components/ikuai/  集成运行代码、翻译和品牌素材
tests/                   虚构数据与本地模拟服务测试
scripts/                 本地校验和发布打包
```

发布不包含生产环境配置、真实凭据、部署脚本或私有截图。

## 来源与许可证

- 集成代码基于 [dscao/ikuai](https://github.com/dscao/ikuai)，按 [Apache-2.0](LICENSE) 发布；修改说明见 [CHANGELOG.md](CHANGELOG.md)，归属见 [NOTICE](NOTICE)。
- 4.x 接口参考 [iKuai-Console OpenAPI](https://github.com/adminlby/iKuai-Console/tree/main/openapi)。
- 品牌素材来自 [Home Assistant Brands](https://github.com/home-assistant/brands/tree/master/custom_integrations/ikuai)，仅用于识别所连接的产品；相关商标属于各自权利人。本项目不代表 iKuai 官方。

## English summary

A Home Assistant custom integration for iKuai routers. The 4.x branch uses the native REST API and a Bearer token to expose 13 read-only sensor types. MAC controls, trackers and router actions are not exposed on 4.x. Existing entity identities are preserved when reconfiguring an existing entry. The legacy 3.x protocol remains available.

Install `noahBin23/hass-ikuai` as an **Integration** custom repository in HACS, download it, restart Home Assistant, and add or reconfigure **iKuai**. Tested with Home Assistant 2026.10.0 and iKuai 4.0.313. This repository is not listed in the HACS default store.
