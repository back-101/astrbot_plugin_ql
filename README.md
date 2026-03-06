# AstrBot 青龙面板管理插件

通过 AstrBot 管理青龙面板的环境变量和定时任务。

## 功能

- ✅ 环境变量管理
- ✅ 定时任务管理
- ✅ 可直接对机器人说“帮我运行美团脚本”或“看看昨天的执行日志”。


## 安装

### 方式一：通过 GitHub 安装（推荐）
在 AstrBot 管理面板的插件市场中搜索 `qinglong` 或输入仓库地址安装。

### 方式二：手动安装
1. 下载本仓库
2. 将文件夹放入 `AstrBot/data/plugins/` 目录
3. 重启 AstrBot

## 配置

在青龙面板创建应用：
1. 进入 `系统设置` → `应用设置`
2. 创建应用，获取 `Client ID` 和 `Client Secret`
3. 在 AstrBot 插件配置中填入：
   - 青龙面板地址（如 `http://192.168.1.100:5700`）
   - Client ID
   - Client Secret

## 命令

/ql help 查看所有命令
```

## 开发说明

- 使用 `httpx` 异步 HTTP 客户端（符合 AstrBot 开发规范）
- 遵循 AstrBot 插件开发指南

## 许可

MIT License
