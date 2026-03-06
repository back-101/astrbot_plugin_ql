import time
from typing import Dict, List, Optional, Tuple, Any
import httpx
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

class QinglongAPI:
    def __init__(self, host: str, client_id: str, client_secret: str):
        self.host = host.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expire = 0
        self._client = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15)
        return self._client

    async def get_token(self):
        if self.token and time.time() < self.token_expire: return True
        try:
            client = await self._get_client()
            resp = await client.get(f"{self.host}/open/auth/token", params={"client_id": self.client_id, "client_secret": self.client_secret})
            res = resp.json()
            if res.get('code') == 200:
                self.token = res['data']['token']
                self.token_expire = time.time() + (6 * 24 * 3600)
                return True
            return False
        except Exception as e:
            logger.error(f"QL Auth Error: {e}")
            return False

    async def _request(self, method: str, endpoint: str, params=None, json_data=None):
        if not await self.get_token(): return False, "认证失败"
        try:
            client = await self._get_client()
            headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
            resp = await client.request(method, f"{self.host}{endpoint}", headers=headers, params=params, json=json_data)
            res = resp.json()
            return (True, res.get('data', {})) if res.get('code') in [200, 201] else (False, res.get('message', '未知错误'))
        except Exception as e:
            return False, str(e)

@register("astrbot_plugin_qinglong", "Haitun", "青龙全能管家", "1.2.9")
class QinglongPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        # 强制读取你的配置文件，若无则使用默认
        self.ql_api = QinglongAPI(
            config.get("qinglong_host", ""),
            config.get("qinglong_client_id", ""),
            config.get("qinglong_client_secret", "")
        )

    def _parse_ids(self, ids_str: str) -> List[int]:
        """将 AI 传入的字符串 ID (如 '10,11' 或 '10') 转换为整数列表"""
        if not ids_str: return []
        try:
            return [int(x.strip()) for x in str(ids_str).replace("，", ",").split(",") if x.strip().isdigit()]
        except: return []

    # ==========================================
    # 工具 1：环境变量管理 (平坦化参数确保识别)
    # ==========================================
    @filter.llm_tool(name="ql_manage_env")
    async def ql_manage_env(self, event: AstrMessageEvent, action: str, target_ids: str = "", name: str = "", value: str = "", remarks: str = ""):
        """
        管理青龙环境变量。
        action: 'search'(查), 'add'(增), 'update'(改), 'delete'(删), 'enable'(启), 'disable'(禁)
        target_ids: 目标ID，多个用逗号隔开，如 "10,11"
        """
        if not event.is_admin: return "🚫 权限不足。"
        ids = self._parse_ids(target_ids)

        if action == "search":
            success, data = await self.ql_api._request("GET", "/open/envs", params={"searchValue": name or ""})
            if not success: return f"查询失败: {data}"
            return "\n".join([f"ID:{e['id']} | {e['name']} | {'🟢启用' if e['status']==0 else '🔴禁用'}" for e in data[:15]]) or "未找到相关变量。"
        
        elif action == "add":
            success, msg = await self.ql_api._request("POST", "/open/envs", json_data=[{"name": name, "value": value, "remarks": remarks or "AI添加"}])
            return f"✅ 变量 {name} 添加成功" if success else f"❌ 失败: {msg}"
            
        elif action == "update" and ids:
            success, msg = await self.ql_api._request("PUT", "/open/envs", json_data={"id": ids[0], "name": name, "value": value, "remarks": remarks})
            return f"✅ 更新成功" if success else f"❌ 失败: {msg}"
            
        elif action in ["enable", "disable", "delete"]:
            if not ids: return "需要提供 ID 号喔。"
            method = "DELETE" if action == "delete" else "PUT"
            endpoint = f"/open/envs/{action}" if method == "PUT" else "/open/envs"
            success, msg = await self.ql_api._request(method, endpoint, json_data=ids)
            return f"✅ 操作 {action} 已执行" if success else f"❌ 失败: {msg}"

    # ==========================================
    # 工具 2：定时任务管理 (平坦化参数)
    # ==========================================
    @filter.llm_tool(name="ql_manage_cron")
    async def ql_manage_cron(self, event: AstrMessageEvent, action: str, target_ids: str = "", keyword: str = ""):
        """
        管理定时任务。
        action: 'search'(查), 'run'(执行), 'stop'(停止), 'enable'(启), 'disable'(禁), 'pin'(置顶), 'unpin'(取消), 'delete'(删), 'log'(日志)
        target_ids: 任务ID，多个用逗号隔开
        """
        if not event.is_admin: return "🚫 权限不足。"
        ids = self._parse_ids(target_ids)

        if action == "search":
            success, data = await self.ql_api._request("GET", "/open/crons", params={"searchValue": keyword})
            tasks = data.get('data', []) if isinstance(data, dict) else data
            return "\n".join([f"ID:{t['id']} | {t['name']} | {'🟢' if t['status']==0 else '🔴'}" for t in tasks[:10]]) if success else "查询失败"
        
        elif action == "log" and ids:
            success, log = await self.ql_api._request("GET", f"/open/crons/{ids[0]}/log")
            return f"📄 日志尾部：\n{log[-600:]}" if success else "日志读取失败"
            
        elif action in ["run", "stop", "enable", "disable", "pin", "unpin", "delete"]:
            if not ids: return "需要任务 ID。"
            method = "DELETE" if action == "delete" else "PUT"
            # 路径映射修正
            path_map = {"pin": "pin", "unpin": "unpin", "delete": ""}
            endpoint = f"/open/crons/{path_map.get(action, action)}"
            if action == "delete": endpoint = "/open/crons"
            success, msg = await self.ql_api._request(method, endpoint, json_data=ids)
            return f"✅ 任务 {action} 成功" if success else f"❌ 失败: {msg}"

    # ==========================================
    # 工具 3：系统查询
    # ==========================================
    @filter.llm_tool(name="ql_get_sys_info")
    async def ql_get_sys_info(self, event: AstrMessageEvent):
        """查询青龙面板的版本和状态。"""
        success, data = await self.ql_api._request("GET", "/open/system")
        if not success: return "获取失败。"
        return f"🖥️ 青龙 v{data.get('version')} | 并发：{data.get('is_cluster')}"

    async def terminate(self):
        if self.ql_api._client: await self.ql_api._client.aclose()
