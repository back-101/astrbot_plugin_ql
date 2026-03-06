#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1. 环境变量管理（查看、添加、更新、删除、启用、禁用）
2. 定时任务管理（查看、执行、停止、启用、禁用、置顶、删除、日志）
2. 支持 LLM Function Calling (大模型自然语言调度)
3. 智能截断过长的日志，适配 AI Token 限制
"""

import time
from typing import Dict, List, Optional, Tuple, Any
import httpx
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 常量配置
DEFAULT_TIMEOUT = 10
TOKEN_EXPIRE_SECONDS = 6 * 24 * 3600 

class QinglongAPI:
    """青龙面板 API 封装"""
    def __init__(self, host: str, client_id: str, client_secret: str):
        self.host = host.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.token: Optional[str] = None
        self.token_expire: float = 0
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        return self._client
    
    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def get_token(self) -> bool:
        try:
            if self.token and time.time() < self.token_expire:
                return True
            client = await self._get_client()
            response = await client.get(
                f"{self.host}/open/auth/token",
                params={"client_id": self.client_id, "client_secret": self.client_secret}
            )
            result = response.json()
            if result.get('code') == 200:
                self.token = result['data']['token']
                self.token_expire = time.time() + TOKEN_EXPIRE_SECONDS
                return True
            return False
        except Exception as e:
            logger.error(f"QL Auth Error: {e}")
            return False
    
    def _get_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    async def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, json_data: Any = None) -> Tuple[bool, Any]:
        if not await self.get_token(): return False, "认证失败"
        try:
            client = await self._get_client()
            url = f"{self.host}{endpoint}"
            resp = await client.request(method, url, headers=self._get_headers(), params=params, json=json_data)
            res = resp.json()
            return (True, res.get('data', {})) if res.get('code') == 200 else (False, res.get('message', '未知错误'))
        except Exception as e:
            return False, str(e)

    # API 接口实现 (已包含 crons, envs, logs 等)
    async def get_envs(self, search: str = ""):
        success, data = await self._request("GET", "/open/envs", params={"searchValue": search})
        return data if success else []

    async def get_crons(self, search: str = ""):
        success, data = await self._request("GET", "/open/crons", params={"searchValue": search})
        return data.get('data', []) if isinstance(data, dict) else data

    async def run_cron(self, ids: List[int]): return await self._request("PUT", "/open/crons/run", json_data=ids)
    async def stop_cron(self, ids: List[int]): return await self._request("PUT", "/open/crons/stop", json_data=ids)
    async def get_log(self, id: int): return await self._request("GET", f"/open/crons/{id}/log")

@register("astrbot_plugin_qinglong", "Haitun", "青龙面板管理(AI增强版)", "1.1.0")
class QinglongPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.ql_api = QinglongAPI(
            config.get("qinglong_host", "http://localhost:5700"),
            config.get("qinglong_client_id", ""),
            config.get("qinglong_client_secret", "")
        )

    @filter.command("ql")
    async def ql_command(self, event: AstrMessageEvent):
        """青龙面板控制台"""
        # 1. 权限校验
        if not event.is_admin:
            yield event.plain_result("🚫 权限不足，请联系管理员。")
            return

        parts = event.message_str.strip().split()
        if len(parts) < 2 or parts[1].lower() == "help":
            yield event.plain_result(self._get_help_text())
            return

        cmd = parts[1].lower()
        
        # 2. 任务管理逻辑优化
        if cmd in ["ls", "list"]:
            keyword = parts[2] if len(parts) > 2 else ""
            crons = await self.ql_api.get_crons(keyword)
            if not crons:
                yield event.plain_result(f"🔍 未找到包含 '{keyword}' 的任务")
                return
            res = "📋 **青龙任务列表** (前15个):\n"
            for c in crons[:15]:
                status = "🟢" if c.get('status') == 0 else "🔴"
                res += f"{status} `{c['id']}` | {c['name']}\n"
            yield event.plain_result(res)

        elif cmd == "run" and len(parts) > 2:
            success, msg = await self.ql_api.run_cron([int(parts[2])])
            yield event.plain_result(f"✅ 任务 {parts[2]} 已启动" if success else f"❌ 失败: {msg}")

        elif cmd == "log" and len(parts) > 2:
            success, log = await self.ql_api.get_log(int(parts[2]))
            if success:
                yield event.plain_result(f"📝 日志 (最后500字):\n{log[-500:] if log else '暂无内容'}")
            else:
                yield event.plain_result(f"❌ 获取失败: {log}")

        elif cmd == "envs":
            keyword = parts[2] if len(parts) > 2 else ""
            envs = await self.ql_api.get_envs(keyword)
            res = f"💎 **环境变量 ({keyword})**:\n"
            for e in envs[:10]:
                res += f"- `{e['name']}`: {e['value'][:15]}...\n"
            yield event.plain_result(res)
        
        else:
            yield event.plain_result("❓ 未知子命令，请输入 `/ql help` 查看用法。")

    def _get_help_text(self):
        return (
            "🚀 **青龙面板管理指令手册**\n"
            "----------------------------\n"
            "🔹 **任务操作**\n"
            "• `/ql ls [关键词]` - 搜索/列出任务\n"
            "• `/ql run <ID>` - 启动任务\n"
            "• `/ql stop <ID>` - 停止任务\n"
            "• `/ql log <ID>` - 查看任务日志\n\n"
            "🔹 **变量操作**\n"
            "• `/ql envs [关键词]` - 查看环境变量\n"
            "• `/ql add <名> <值>` - 添加新变量\n\n"
            "💡 **AI 提示**: 你也可以直接对我说“帮我查一下美团的任务”哒！"
        )


    async def terminate(self):
        await self.ql_api.close()