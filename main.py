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
            self._client = httpx.AsyncClient(timeout=10)
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
            # 青龙 API 有时成功码是 200，有时是 201
            return (True, res.get('data', {})) if res.get('code') in [200, 201] else (False, res.get('message', '未知错误'))
        except Exception as e:
            return False, str(e)

    # --- 环境变量 API ---
    async def env_get(self, kw=""): return await self._request("GET", "/open/envs", params={"searchValue": kw})
    async def env_add(self, data: List[Dict]): return await self._request("POST", "/open/envs", json_data=data)
    async def env_update(self, data: Dict): return await self._request("PUT", "/open/envs", json_data=data)
    async def env_delete(self, ids: List[int]): return await self._request("DELETE", "/open/envs", json_data=ids)
    async def env_op(self, action: str, ids: List[int]): return await self._request("PUT", f"/open/envs/{action}", json_data=ids)

    # --- 定时任务 API ---
    async def cron_get(self, kw=""): 
        success, data = await self._request("GET", "/open/crons", params={"searchValue": kw})
        return data.get('data', []) if success and isinstance(data, dict) else (data if success else [])
    async def cron_op(self, action: str, ids: List[int]): return await self._request("PUT", f"/open/crons/{action}", json_data=ids)
    async def cron_log(self, id: int): return await self._request("GET", f"/open/crons/{id}/log")
    async def cron_pin(self, ids: List[int]): return await self._request("PUT", "/open/crons/pin", json_data=ids)
    async def cron_unpin(self, ids: List[int]): return await self._request("PUT", "/open/crons/unpin", json_data=ids)
    async def cron_delete(self, ids: List[int]): return await self._request("DELETE", "/open/crons", json_data=ids)

    # --- 系统信息 ---
    async def sys_info(self): return await self._request("GET", "/open/system")

@register("astrbot_plugin_qinglong", "Haitun", "青龙全能 AI 管家", "1.2.0")
class QinglongPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.ql_api = QinglongAPI(config.get("qinglong_host", ""), config.get("qinglong_client_id", ""), config.get("qinglong_client_secret", ""))

    # ==========================================
    # 核心 AI 工具：环境变量大师
    # ==========================================
    @filter.llm_tool(name="ql_env_expert")
    async def ql_env_expert(self, event: AstrMessageEvent, action: str, ids: List[int] = None, name: str = "", value: str = "", remarks: str = ""):
        """
        环境变量管理专家。
        action: 'search'(查), 'add'(增), 'update'(改), 'delete'(删), 'enable'(启), 'disable'(禁)
        """
        if not event.is_admin: return "🚫 抱歉，非管理员不能操作环境变量。"
        
        # 统一处理单个 ID 传错的情况
        if isinstance(ids, int): ids = [ids]

        if action == "search":
            data = await self.ql_api.env_get(name or "")
            return "\n".join([f"ID: {e['id']} | {e['name']}={e['value'][:20]}... | {'🟢' if e['status']==0 else '🔴'}" for e in data[:15]]) or "🔍 没找到相关变量。"
        
        elif action == "add":
            res, msg = await self.ql_api.env_add([{"name": name, "value": value, "remarks": remarks or f"AI添加于{time.strftime('%m-%d')}"}])
            return f"✅ 变量 {name} 添加成功！" if res else f"❌ 失败：{msg}"
            
        elif action == "update":
            # 更新通常需要 ID
            res, msg = await self.ql_api.env_update({"id": ids[0], "name": name, "value": value, "remarks": remarks})
            return f"✅ ID:{ids[0]} 更新成功！" if res else f"❌ 失败：{msg}"
            
        elif action in ["enable", "disable", "delete"]:
            if not ids: return "需要提供 ID 列表喔！"
            func = self.ql_api.env_delete if action == "delete" else lambda x: self.ql_api.env_op(action, x)
            res, msg = await func(ids)
            return f"✅ 执行 {action} 成功！" if res else f"❌ 失败：{msg}"

    # ==========================================
    # 核心 AI 工具：任务调度专家
    # ==========================================
    @filter.llm_tool(name="ql_cron_expert")
    async def ql_cron_expert(self, event: AstrMessageEvent, action: str, ids: List[int] = None, keyword: str = ""):
        """
        定时任务管理专家。
        action: 'search'(查), 'run'(执行), 'stop'(停止), 'enable'(启), 'disable'(禁), 'pin'(置顶), 'unpin'(取消置顶), 'delete'(删), 'log'(看日志)
        """
        if not event.is_admin: return "🚫 权限不足。"
        if isinstance(ids, int): ids = [ids]

        if action == "search":
            data = await self.ql_api.cron_get(keyword)
            return "\n".join([f"ID: {t['id']} | {t['name']} | {'🟢' if t['status']==0 else '🔴'}" for t in data[:10]]) or "🔍 未找到相关任务。"
        
        elif action == "log":
            if not ids: return "看日志需要提供 ID 喔。"
            res, log = await self.ql_api.cron_log(ids[0])
            return f"📄 任务 {ids[0]} 日志尾部：\n{log[-600:]}" if res else f"❌ 获取失败：{log}"
            
        elif action in ["run", "stop", "enable", "disable", "pin", "unpin", "delete"]:
            if not ids: return "请指定任务 ID。"
            dispatch = {
                "run": self.ql_api.cron_op, "stop": self.ql_api.cron_op,
                "enable": self.ql_api.cron_op, "disable": self.ql_api.cron_op,
                "pin": lambda x: self.ql_api.cron_pin(x), "unpin": lambda x: self.ql_api.cron_unpin(x),
                "delete": lambda x: self.ql_api.cron_delete(x)
            }
            # 特殊处理 cron_op 需要传两个参数
            if action in ["run", "stop", "enable", "disable"]:
                res, msg = await self.ql_api.cron_op(action, ids)
            else:
                res, msg = await dispatch[action](ids)
            return f"✅ 任务操作 {action} 已下发！" if res else f"❌ 失败：{msg}"

    # ==========================================
    # 系统查询
    # ==========================================
    @filter.llm_tool(name="ql_sys_info")
    async def ql_sys_info(self, event: AstrMessageEvent):
        """查询青龙面板系统版本和运行信息。"""
        res, data = await self.ql_api.sys_info()
        if not res: return "无法获取系统信息。"
        return f"🖥️ 系统信息：\n版本：{data.get('version')}\n多机并发：{'开启' if data.get('is_cluster') else '关闭'}"

    async def terminate(self):
        if self.ql_api._client: await self.ql_api._client.aclose()
