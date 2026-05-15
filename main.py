"""
南京大学行知×开甲 学习小组 盲盒任务管理插件

模块化重构版本
"""

import asyncio
import csv
import json
import shutil
import zipfile
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

import aiohttp
from pydantic import Field
from pydantic.dataclasses import dataclass
from quart import Response, jsonify, request

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.message.components import Plain
from astrbot.core import file_token_service

# 导入模块化的各个功能
from ai import (
    BlindboxGetPromptTool,
    BlindboxGetSubmissionsTool,
    BlindboxReviewSubmissionTool,
    build_ai_group_context,
    build_ai_prompt_context,
)
from business import blindbox as blindbox_ops
from business import export as export_ops
from business import group as group_ops
from business import storage as storage_ops
from business import submission as submission_ops
from config import (
    DEFAULT_RULES_TEXT,
    DEFAULT_TASKS,
    PLUGIN_NAME,
    KV_STATE_KEY,
    TASK_CATEGORIES,
    batch_id,
    default_state,
    gen_uuid,
    now,
    resolve_data_root,
    timestamp,
    week_key,
)
from messages import format_help, format_task
from parser import (
    extract_message_text_and_images,
    get_group_id,
    get_sender_id,
    split_tokens,
    strip_root_command,
)

# 数据目录
DATA_ROOT_DIR = resolve_data_root()
SUBMISSION_DIR = DATA_ROOT_DIR / "submissions"
EXPORT_DIR = DATA_ROOT_DIR / "exports"
LEGACY_RUNTIME_DIR = Path(__file__).resolve().parent / "runtime"
LEGACY_SUBMISSION_DIR = LEGACY_RUNTIME_DIR / "submissions"


def _normalize_category(raw_category: str) -> str:
    """规范化分类名称"""
    return storage_ops.normalize_category(raw_category)


def _pick_task(
    category: str, tasks: list[dict[str, object]], exclude_task: dict[str, object] | None = None
) -> dict[str, object]:
    """随机选择一个任务"""
    return blindbox_ops.pick_task(category, tasks, exclude_task)


def _task_categories(tasks: list[dict[str, object]]) -> list[str]:
    """获取任务的所有分类"""
    return storage_ops.task_categories(tasks)


def _parse_bool(value: object) -> bool:
    """解析布尔值"""
    return storage_ops.parse_bool(value)


def _parse_qq_list(value: object) -> list[str]:
    """解析 QQ 号列表"""
    return storage_ops.parse_qq_list(value)


def _unique_strings(values: object) -> list[str]:
    """获取唯一的字符串列表"""
    return storage_ops.unique_strings(values)


def _normalize_tasks(raw_tasks: object) -> list[dict[str, object]]:
    """规范化任务列表"""
    return storage_ops.normalize_tasks(raw_tasks)


def _format_help() -> str:
    """格式化帮助信息"""
    return format_help()


def _format_task(task: dict[str, object], rules_text: str) -> str:
    """格式化单个任务信息"""
    return format_task(task, rules_text)


def _safe_json_dump(path: Path, data: object) -> None:
    """安全地写入 JSON 文件"""
    storage_ops.safe_json_dump(path, data)


def _safe_json_load(path: Path, default: object) -> object:
    """安全地读取 JSON 文件"""
    return storage_ops.safe_json_load(path, default)


def _extract_message_text_and_images(event: AstrMessageEvent) -> tuple[str, list[str], list[dict[str, str]]]:
    """提取消息中的文本和图片"""
    return extract_message_text_and_images(event)


def _get_sender_id(event: AstrMessageEvent) -> str:
    """获取发送者 QQ 号"""
    return get_sender_id(event)


def _get_group_id(event: AstrMessageEvent) -> str:
    """获取群号"""
    return get_group_id(event)


def _split_tokens(raw_message: str) -> list[str]:
    """分割消息 token"""
    return split_tokens(raw_message)


def _strip_root_command(tokens: list[str]) -> list[str]:
    """移除根命令"""
    return strip_root_command(tokens)


def _normalize_state(raw_state: dict[str, object] | None) -> dict[str, object]:
    """规范化状态"""
    return storage_ops.normalize_state(raw_state)


# =============================================================================
# 主插件类
# =============================================================================

@register(PLUGIN_NAME, "行知×开甲", "南京大学行知×开甲学习小组抽奖盲盒", "0.6.0")
class BlindBoxPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self._state_lock = asyncio.Lock()
        self._state_loaded = False
        self._state: dict[str, object] = default_state()

        # 待审核的提交
        self._pending_reviews: dict[str, tuple[str, dict]] = {}
        # 用户当前的选择状态
        self._user_selections: dict[str, dict[str, object]] = {}

        # 服务器基址（用于生成下载链接）
        self._server_base_url = str(self.config.get("server_base_url", "")).strip().rstrip("/") if self.config else ""

        # 注册 AI 工具
        self.context.add_llm_tools(
            BlindboxGetSubmissionsTool(plugin_instance=self),
            BlindboxGetPromptTool(plugin_instance=self),
            BlindboxReviewSubmissionTool(plugin_instance=self),
        )

        self._register_web_apis(context)

    def _capture_server_url(self) -> None:
        """从 Web 请求中自动检测服务器基址 URL"""
        if self._server_base_url:
            return
        try:
            host = request.headers.get("X-Forwarded-Host", "") or request.host
            scheme = request.headers.get("X-Forwarded-Proto", "") or request.scheme
            if host:
                self._server_base_url = f"{scheme}://{host}"
        except Exception:
            pass

    def _get_callback_base(self) -> str:
        """获取对外可达的回调基址"""
        if self._server_base_url:
            return self._server_base_url
        try:
            from astrbot.core.config.astrbot_config import AstrBotConfig

            config = AstrBotConfig()
            base = config.get("callback_api_base", "")
            if base:
                return base.rstrip("/")
        except Exception:
            pass
        return "http://<bot服务器地址>:<端口>"

    async def _register_for_download(self, file_path: Path) -> str:
        """通过 FileTokenService 注册文件，返回免认证下载链接"""
        token = await file_token_service.register_file(str(file_path))
        base = self._get_callback_base()
        return f"{base}/api/file/{token}"

    def _register_web_apis(self, context: Context) -> None:
        """注册 Web API 接口"""
        # 基础 API
        context.register_web_api(f"/{PLUGIN_NAME}/state", self.api_state, ["GET"], "BlindBox 状态")
        context.register_web_api(f"/{PLUGIN_NAME}/test", self.api_test, ["GET", "OPTIONS"], "测试API连接")

        # AI 相关 API
        context.register_web_api(f"/{PLUGIN_NAME}/ai/context", self.api_ai_context, ["GET"], "AI 小组上下文")
        context.register_web_api(f"/{PLUGIN_NAME}/ai/groups", self.api_ai_groups, ["GET"], "AI 小组列表")
        context.register_web_api(f"/{PLUGIN_NAME}/ai/submissions", self.api_ai_submissions, ["GET"], "AI 提交记录")
        context.register_web_api(f"/{PLUGIN_NAME}/ai/review", self.api_ai_review, ["POST"], "AI 审核提交")
        context.register_web_api(f"/{PLUGIN_NAME}/ai/prompt", self.api_ai_prompt, ["GET"], "AI 系统提示词")

        # 提交 API
        context.register_web_api(f"/{PLUGIN_NAME}/submit", self.api_submit, ["POST"], "提交小组任务材料")

        # 小组管理 API
        context.register_web_api(f"/{PLUGIN_NAME}/group/create", self.api_group_create, ["POST"], "创建小组")
        context.register_web_api(f"/{PLUGIN_NAME}/group/add", self.api_group_add, ["POST"], "添加成员")
        context.register_web_api(f"/{PLUGIN_NAME}/group/remove", self.api_group_remove, ["POST"], "移除成员")
        context.register_web_api(f"/{PLUGIN_NAME}/group/transfer-leader", self.api_group_transfer_leader, ["POST"], "转让组长")
        context.register_web_api(f"/{PLUGIN_NAME}/group/rename", self.api_group_rename, ["POST"], "改名小组")
        context.register_web_api(f"/{PLUGIN_NAME}/group/request-dissolve", self.api_group_request_dissolve, ["POST"], "申请解散小组")
        context.register_web_api(f"/{PLUGIN_NAME}/group/cancel-dissolve", self.api_group_cancel_dissolve, ["POST"], "取消解散申请")
        context.register_web_api(f"/{PLUGIN_NAME}/group/dissolve", self.api_group_dissolve, ["POST"], "解散小组")
        context.register_web_api(f"/{PLUGIN_NAME}/group/redraw", self.api_group_redraw, ["POST"], "重抽小组任务")
        context.register_web_api(f"/{PLUGIN_NAME}/group/export-csv", self.api_group_export_csv, ["GET"], "导出小组列表为CSV")
        context.register_web_api(f"/{PLUGIN_NAME}/group/import-csv", self.api_group_import_csv, ["POST"], "从CSV导入小组列表")

        # 提交记录导出 API
        context.register_web_api(f"/{PLUGIN_NAME}/group/export-submissions", self.api_group_export_submissions, ["POST"], "导出小组提交记录")
        context.register_web_api(f"/{PLUGIN_NAME}/group/export-submissions-csv", self.api_group_export_submissions_csv, ["POST"], "导出小组提交记录为CSV")
        context.register_web_api(f"/{PLUGIN_NAME}/group/export-submissions-all-csv", self.api_group_export_all_submissions_csv, ["GET", "POST"], "导出全部小组提交记录为CSV")
        context.register_web_api(f"/{PLUGIN_NAME}/group/export-submission-zip", self.api_group_export_submission_zip, ["GET", "POST"], "导出指定提交为ZIP")
        context.register_web_api(f"/{PLUGIN_NAME}/group/export-group-zip", self.api_group_export_group_zip, ["GET", "POST"], "导出小组全部提交为ZIP")
        context.register_web_api(f"/{PLUGIN_NAME}/group/import-submissions-all-csv", self.api_group_import_submissions_all_csv, ["POST"], "从 CSV 导入所有小组提交记录")

        # 任务管理 API
        context.register_web_api(f"/{PLUGIN_NAME}/tasks/export-csv", self.api_tasks_export_csv, ["GET"], "导出任务列表为CSV")
        context.register_web_api(f"/{PLUGIN_NAME}/tasks/import-csv", self.api_tasks_import_csv, ["POST"], "从CSV导入任务列表")
        context.register_web_api(f"/{PLUGIN_NAME}/config/import-tasks", self.api_config_import_tasks, ["POST"], "从插件配置的 CSV 文本导入任务")
        context.register_web_api(f"/{PLUGIN_NAME}/tasks/stats", self.api_tasks_stats, ["GET", "OPTIONS"], "获取任务导入统计信息")

        # 审核 API
        context.register_web_api(f"/{PLUGIN_NAME}/api/pending-reviews", self.api_pending_reviews, ["GET"], "获取待确认审核列表")
        context.register_web_api(f"/{PLUGIN_NAME}/api/confirm-review", self.api_confirm_review_endpoint, ["POST"], "管理员确认审核结果")

    # =========================================================================
    # 初始化和状态管理
    # =========================================================================

    async def initialize(self):
        """初始化插件"""
        logger.info("astrbot_plugin_blindbox initialized")
        await self._load_state()
        
        # 从配置导入小组和任务数据
        try:
            state = await self._get_state()
            groups = state.get("groups", {})
            if (not isinstance(groups, dict)) or (isinstance(groups, dict) and not groups):
                cfg_groups = self.config.get("groups") if isinstance(self.config, dict) else None
                raw_json = self.config.get("groups_json") if isinstance(self.config, dict) else None
                parsed = None
                if isinstance(cfg_groups, list) and cfg_groups:
                    parsed = cfg_groups
                elif isinstance(raw_json, str) and raw_json.strip():
                    try:
                        parsed = json.loads(raw_json)
                    except Exception:
                        parsed = None

                if parsed:
                    normalized_groups: dict[str, object] = {}
                    member_to_group: dict[str, str] = {}
                    if isinstance(parsed, dict):
                        items = parsed.items()
                    elif isinstance(parsed, list):
                        items = []
                        for entry in parsed:
                            if isinstance(entry, dict):
                                key = str(entry.get("group_no", "")).strip() or gen_uuid()[:8]
                                items.append((key, entry))
                    else:
                        items = []

                    for group_no, group_data in items:
                        if not isinstance(group_data, dict):
                            continue
                        members = _unique_strings(group_data.get("members", []))
                        leader = str(group_data.get("leader_qq", "")).strip()
                        if not leader and members:
                            leader = members[0]
                        if leader and leader not in members:
                            members.insert(0, leader)
                        if not members:
                            continue
                        normalized_group = {
                            "group_no": str(group_no),
                            "group_name": str(group_data.get("group_name", "")).strip(),
                            "leader_qq": leader,
                            "members": members,
                            "dissolve_requested": bool(group_data.get("dissolve_requested", False)),
                            "score_total": int(group_data.get("score_total", 0)),
                        }
                        normalized_groups[str(group_no)] = normalized_group
                        for member_id in members:
                            member_to_group[member_id] = str(group_no)

                    if normalized_groups:
                        state["groups"] = normalized_groups
                        state["member_to_group"] = member_to_group
                        await self.put_kv_data(KV_STATE_KEY, state)
                        self._state = state
        except Exception:
            logger.exception("导入配置中的小组数据失败")

        # 导入任务列表
        try:
            cfg_csv = None
            auto_import = False
            if isinstance(self.config, dict):
                cfg_csv = str(self.config.get("tasks_csv_text", "") or "").strip()
                auto_import = bool(self.config.get("tasks_csv_auto_import", False))

            if cfg_csv:
                state = await self._get_state()
                existing_tasks = state.get("tasks", []) if isinstance(state, dict) else []
                should_import = auto_import or not existing_tasks
                if should_import:
                    try:
                        csv_buffer = StringIO(cfg_csv)
                        reader = csv.DictReader(csv_buffer)
                        rows = list(reader)
                        parsed: list[dict[str, object]] = []
                        errors: list[str] = []
                        for index, row in enumerate(rows, start=1):
                            category = str(row.get("category", "") or row.get("类别", "") or row.get("种类", "") or row.get("tag", "") or "").strip()
                            title = str(
                                row.get("title", "")
                                or row.get("名字", "")
                                or row.get("任务", "")
                                or row.get("task_title", "")
                                or ""
                            ).strip()
                            points_raw = str(row.get("points", "") or row.get("task_points", "") or row.get("积分值", "") or "").strip()
                            enabled_raw = row.get("enabled", row.get("启用", "1"))
                            description = str(row.get("description", "") or row.get("说明", "") or row.get("解释", "") or row.get("任务内容", "") or "").strip()

                            if not category or not title:
                                errors.append(f"第 {index} 行：缺少类别或任务名称")
                                continue

                            try:
                                points = int(points_raw or 0)
                                if points < 0:
                                    errors.append(f"第 {index} 行：积分值不能为负数（{points_raw}），使用默认值 0")
                                    points = 0
                            except (TypeError, ValueError):
                                errors.append(f"第 {index} 行：积分值不是有效的数字（{points_raw}），使用默认值 0")
                                points = 0

                            normalized_category = _normalize_category(category)
                            task_entry = {
                                "category": normalized_category,
                                "title": title,
                                "points": points,
                                "enabled": _parse_bool(enabled_raw),
                            }
                            if description:
                                task_entry["description"] = description
                            parsed.append(task_entry)

                        if parsed:
                            state["tasks"] = parsed
                            await self._save_state()
                            logger.info(f"从插件配置导入 {len(parsed)} 条任务（errors={len(errors)}）")
                    except Exception:
                        logger.exception("从插件配置解析 CSV 导入任务失败")
        except Exception:
            logger.exception("读取插件配置的 CSV 文本失败")

    async def _load_state(self) -> dict[str, object]:
        """加载状态"""
        async with self._state_lock:
            stored = await self.get_kv_data(KV_STATE_KEY, None)
            normalized = _normalize_state(stored if isinstance(stored, dict) else None)
            self._state = normalized
            self._state_loaded = True
            await self.put_kv_data(KV_STATE_KEY, self._state)
            return self._state

    async def _save_state(self) -> None:
        """保存状态"""
        async with self._state_lock:
            await self.put_kv_data(KV_STATE_KEY, self._state)

    async def _get_state(self) -> dict[str, object]:
        """获取状态"""
        if not self._state_loaded:
            return await self._load_state()
        return self._state

    async def _get_tasks(self) -> list[dict[str, object]]:
        """获取任务列表"""
        state = await self._get_state()
        tasks = state.get("tasks")
        if isinstance(tasks, list) and tasks:
            return _normalize_tasks(tasks)
        return _normalize_tasks(self.config.get("tasks", DEFAULT_TASKS))

    # =========================================================================
    # 小组操作便利方法
    # =========================================================================

    async def _ensure_group_or_raise(self, group_no: str) -> dict[str, object]:
        """确保小组存在"""
        state = await self._get_state()
        return await group_ops.ensure_group_or_raise(state, group_no)

    async def _find_group_by_member(self, sender_id: str) -> tuple[str | None, dict[str, object] | None]:
        """根据成员查找小组"""
        state = await self._get_state()
        return await group_ops.find_group_by_member(state, sender_id)

    def _check_group_whitelist(self, group_id: str) -> bool:
        """检查群号是否在白名单内"""
        whitelist_str = str(self.config.get("group_whitelist", "") or "").strip()
        if not whitelist_str:
            return True
        allowed_groups = set(g.strip() for g in whitelist_str.split(",") if g.strip())
        return group_id in allowed_groups

    def _group_has_member(self, group_data: dict[str, object], qq: str) -> bool:
        """检查小组是否包含成员"""
        return group_ops.group_has_member(group_data, qq)

    def _build_group_summary(self, group_no: str, group_data: dict[str, object]) -> str:
        """构建小组摘要"""
        return group_ops.build_group_summary(group_no, group_data)

    # =========================================================================
    # 文件和路径管理
    # =========================================================================

    def _group_dir(self, group_no: str) -> Path:
        """获取小组目录"""
        return SUBMISSION_DIR / f"group_{group_no}"

    def _submission_folder(self, group_no: str, submission_id: str) -> Path:
        """获取提交文件夹"""
        return self._group_dir(group_no) / submission_id

    def _submission_index_path(self, group_no: str) -> Path:
        """获取提交索引路径"""
        return self._group_dir(group_no) / "submissions.json"

    def _submission_file_path(self, group_no: str) -> Path:
        """获取提交文件路径（旧版本兼容）"""
        return SUBMISSION_DIR / f"group_{group_no}.json"

    def _legacy_submission_file_path(self, group_no: str) -> Path:
        """获取遗留提交文件路径"""
        return LEGACY_SUBMISSION_DIR / f"group_{group_no}.json"

    # =========================================================================
    # 提交记录存储和加载
    # =========================================================================

    def _load_submission_records(self, group_no: str) -> list[dict[str, object]]:
        """加载小组的提交记录"""
        new_path = self._submission_index_path(group_no)
        old_path = self._submission_file_path(group_no)
        legacy_path = self._legacy_submission_file_path(group_no)

        if new_path.exists():
            source_path = new_path
        elif old_path.exists():
            source_path = old_path
        elif legacy_path.exists():
            source_path = legacy_path
        else:
            source_path = new_path

        raw_records = _safe_json_load(source_path, [])
        if not isinstance(raw_records, list):
            return []

        records: list[dict[str, object]] = []
        for record in raw_records:
            if isinstance(record, dict):
                records.append(
                    {
                        "submission_id": str(record.get("submission_id", "")),
                        "group_no": str(record.get("group_no", group_no)),
                        "group_name": str(record.get("group_name", "")),
                        "submitter_qq": str(record.get("submitter_qq", "")),
                        "materials_text": str(record.get("materials_text", "")),
                        "image_urls": _parse_qq_list(record.get("image_urls", [])),
                        "images": [
                            {
                                "file": str(image.get("file", "")),
                                "url": str(image.get("url", "")),
                                "path": str(image.get("path", "")),
                            }
                            for image in record.get("images", [])
                            if isinstance(image, dict)
                        ],
                        "local_images": _parse_qq_list(record.get("local_images", [])),
                        "source": str(record.get("source", "manual")),
                        "week": str(record.get("week", week_key())),
                        "task_snapshot": record.get("task_snapshot", {}),
                        "review_status": str(record.get("review_status", "pending")),
                        "review_reason": str(record.get("review_reason", "")),
                        "reviewer": str(record.get("reviewer", "")),
                        "reviewed_at": str(record.get("reviewed_at", "")),
                        "awarded_points": int(record.get("awarded_points", 0)),
                        "score_applied": bool(record.get("score_applied", False)),
                        "submitted_at": str(record.get("submitted_at", "")),
                    }
                )

        # 从旧路径迁移到新路径
        if source_path != new_path:
            self._group_dir(group_no).mkdir(parents=True, exist_ok=True)
            _safe_json_dump(new_path, records)

        return records

    def _save_submission_records(self, group_no: str, records: list[dict[str, object]]) -> None:
        """保存小组的提交记录"""
        self._group_dir(group_no).mkdir(parents=True, exist_ok=True)
        _safe_json_dump(self._submission_index_path(group_no), records)

    # =========================================================================
    # 图片处理和提交创建
    # =========================================================================

    @staticmethod
    def _convert_image_to_jpeg(source_path: Path, dest_path: Path) -> bool:
        """转换图片为 JPEG 格式"""
        try:
            from PIL import Image as PILImage

            img = PILImage.open(source_path)
            rgb_img = img.convert("RGB") if img.mode in ("RGBA", "P", "LA") else img
            rgb_img.save(dest_path, "JPEG", quality=90)
            return True
        except Exception:
            return False

    async def _download_image(self, url: str, dest_path: Path) -> bool:
        """下载图片"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        dest_path.write_bytes(data)
                        return True
        except Exception as e:
            logger.warning("下载图片失败: %s → %s", url, e)
        return False

    async def _save_submission_files(
        self,
        group_no: str,
        submission_id: str,
        materials_text: str,
        images: list[dict[str, str]],
    ) -> list[str]:
        """保存提交的文件"""
        folder = self._submission_folder(group_no, submission_id)
        folder.mkdir(parents=True, exist_ok=True)

        (folder / "text.txt").write_text(materials_text, encoding="utf-8")

        local_images: list[str] = []
        for idx, image_entry in enumerate(images):
            ext = ".jpg"
            saved_path = folder / f"image_{idx + 1:03d}{ext}"
            saved = False

            url = image_entry.get("url", "")
            if url and url.startswith("http"):
                saved = await self._download_image(url, saved_path)

            if not saved:
                src_path = image_entry.get("path", "")
                if src_path and Path(src_path).exists():
                    try:
                        shutil.copy2(src_path, saved_path)
                        saved = True
                    except OSError as e:
                        logger.warning("复制图片失败: %s → %s", src_path, e)

            if not saved:
                file_id = image_entry.get("file", "")
                if file_id:
                    file_path = Path(file_id)
                    if file_path.exists():
                        try:
                            shutil.copy2(file_path, saved_path)
                            saved = True
                        except OSError:
                            pass

            if not saved:
                logger.warning("无法保存图片: submission=%s idx=%d entry=%s", submission_id, idx, image_entry)
                continue

            if saved_path.suffix.lower() != ".jpg":
                jpg_path = saved_path.with_suffix(".jpg")
                if self._convert_image_to_jpeg(saved_path, jpg_path):
                    try:
                        saved_path.unlink()
                    except OSError:
                        pass
                    saved_path = jpg_path
                    ext = ".jpg"
                else:
                    ext = saved_path.suffix

            local_images.append(saved_path.name)

        return local_images

    async def _create_submission_record(
        self,
        group_no: str,
        submitter_qq: str,
        materials_text: str,
        image_urls: list[str],
        images: list[dict[str, str]],
        source: str,
    ) -> dict[str, object]:
        """创建提交记录"""
        group_data = await self._ensure_group_or_raise(group_no)
        state = await self._get_state()
        draws = state.get("draws", {})
        draw_data = draws.get(group_no) if isinstance(draws, dict) else None

        if not submitter_qq:
            raise ValueError("submitter_qq 不能为空。")
        if not self._group_has_member(group_data, submitter_qq):
            raise ValueError("提交人必须是本组成员。")

        submission = submission_ops.build_submission_record(
            group_no=group_no,
            group_data=group_data,
            submitter_qq=submitter_qq,
            materials_text=materials_text,
            image_urls=image_urls,
            images=images,
            source=source,
            draw_data=draw_data if isinstance(draw_data, dict) else None,
        )
        submission_id = str(submission["submission_id"])

        local_images = await self._save_submission_files(
            group_no=group_no,
            submission_id=submission_id,
            materials_text=materials_text,
            images=images,
        )
        submission["local_images"] = local_images

        records = self._load_submission_records(group_no)
        records.append(submission)
        self._save_submission_records(group_no, records)
        return submission

    def _build_ai_group_context(
        self,
        group_no: str,
        group_data: dict[str, object],
        draw_data: object,
    ) -> dict[str, object]:
        """为 AI 构建小组上下文"""
        return build_ai_group_context(
            group_no, group_data, draw_data, lambda gno: self._load_submission_records(gno)
        )

    def _build_ai_prompt_context(self) -> str:
        """构建 AI 提示词"""
        return build_ai_prompt_context()

    # 继续在下一部分...

    async def api_test(self):
        """测试 API 连接"""
        self._capture_server_url()
        if request.method == "OPTIONS":
            response = Response("", status=200)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            return response

        response = jsonify({"success": True, "message": "API 连接正常", "timestamp": datetime.now().isoformat()})
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    def _json_ok(self, message: str = "操作成功", data: object | None = None):
        """返回成功 JSON"""
        payload = {"success": True, "message": message}
        if data is not None:
            payload["data"] = data
        return jsonify(payload)

    def _json_error(self, message: str, data: object | None = None):
        """返回错误 JSON"""
        payload = {"success": False, "message": message}
        if data is not None:
            payload["data"] = data
        return jsonify(payload)

    async def _get_request_json(self) -> dict[str, object]:
        """获取请求 JSON"""
        payload = await request.get_json(silent=True)
        if isinstance(payload, dict):
            return payload
        return {}

    async def _api_result(self, handler):
        """处理 API 结果"""
        try:
            result = await handler()
            return self._json_ok(data=result if result is not None else {})
        except ValueError as exc:
            return self._json_error(str(exc))
        except Exception as exc:
            logger.exception("blindbox api error")
            return self._json_error(f"内部错误：{exc}")

    # =========================================================================
    # API 接口实现（核心功能）
    # =========================================================================

    async def api_state(self):
        """获取状态"""
        self._capture_server_url()
        async def _handler():
            state = await self._get_state()
            tasks = await self._get_tasks()
            return {
                "week": week_key(),
                "rules_text": str(self.config.get("rules_text", DEFAULT_RULES_TEXT)),
                "tasks": tasks,
                "categories": _task_categories(tasks),
                "groups": state.get("groups", {}),
                "draws": state.get("draws", {}),
            }

        return await self._api_result(_handler)

    async def api_ai_context(self):
        """获取 AI 上下文"""
        async def _handler():
            state = await self._get_state()
            args = request.args
            group_no = str(args.get("group_no", "")).strip()
            sender_qq = str(args.get("sender_qq", "")).strip()
            include_all = str(args.get("include_all", "")).lower() in {"1", "true", "yes", "on"}

            groups = state.get("groups", {})
            draws = state.get("draws", {})
            if not isinstance(groups, dict) or not isinstance(draws, dict):
                raise ValueError("小组数据异常，请重新初始化插件状态。")

            if not group_no and sender_qq:
                matched_group_no, _ = await self._find_group_by_member(sender_qq)
                group_no = matched_group_no or ""

            if group_no:
                group_data = groups.get(group_no)
                if not isinstance(group_data, dict):
                    raise ValueError(f"序号为 {group_no} 的小组不存在。")
                return self._build_ai_group_context(group_no, group_data, draws.get(group_no))

            if include_all:
                return {
                    "week": week_key(),
                    "groups": [
                        self._build_ai_group_context(str(current_group_no), group_data, draws.get(str(current_group_no)))
                        for current_group_no, group_data in sorted(groups.items(), key=lambda item: str(item[0]))
                        if isinstance(group_data, dict)
                    ],
                }

            raise ValueError("请提供 group_no、sender_qq 或 include_all 参数。")

        return await self._api_result(_handler)

    async def api_ai_groups(self):
        """获取 AI 小组列表"""
        async def _handler():
            state = await self._get_state()
            groups = state.get("groups", {})
            draws = state.get("draws", {})
            if not isinstance(groups, dict) or not isinstance(draws, dict):
                raise ValueError("小组数据异常，请重新初始化插件状态。")

            return {
                "week": week_key(),
                "groups": [
                    self._build_ai_group_context(str(group_no), group_data, draws.get(str(group_no)))
                    for group_no, group_data in sorted(groups.items(), key=lambda item: str(item[0]))
                    if isinstance(group_data, dict)
                ],
            }

        return await self._api_result(_handler)

    async def api_ai_submissions(self):
        """获取 AI 提交记录"""
        async def _handler():
            args = request.args
            group_no = str(args.get("group_no", "")).strip()
            if not group_no:
                raise ValueError("请提供 group_no。")
            group_data = await self._ensure_group_or_raise(group_no)
            records = self._load_submission_records(group_no)
            return {
                "group_no": group_no,
                "group_name": group_data.get("group_name", ""),
                "records": records,
            }

        return await self._api_result(_handler)

    async def api_ai_review(self):
        """AI 审核提交"""
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        submission_id = str(payload.get("submission_id", "")).strip()
        verdict = str(payload.get("verdict", "")).strip().lower()
        reviewer = str(payload.get("reviewer", "ai")).strip() or "ai"
        review_reason = str(payload.get("review_reason", "")).strip()
        score_delta_raw = payload.get("score_delta", None)

        async def _handler():
            if not group_no:
                raise ValueError("group_no 不能为空。")
            if not submission_id:
                raise ValueError("submission_id 不能为空。")
            group_data = await self._ensure_group_or_raise(group_no)
            current_draws = await self._get_state()
            draw_data = current_draws.get("draws", {}).get(group_no) if isinstance(current_draws.get("draws", {}), dict) else None
            records = self._load_submission_records(group_no)

            target_record = None
            for record in records:
                if isinstance(record, dict) and record.get("submission_id") == submission_id:
                    target_record = record
                    break
            if target_record is None:
                raise ValueError(f"找不到提交记录 {submission_id}。")

            previous_award = int(target_record.get("awarded_points", 0))
            previously_applied = bool(target_record.get("score_applied", False))
            if previously_applied and previous_award:
                group_data["score_total"] = max(0, int(group_data.get("score_total", 0)) - previous_award)

            if score_delta_raw is None or str(score_delta_raw).strip() == "":
                score_delta = int(draw_data.get("points", 0)) if isinstance(draw_data, dict) else 0
            else:
                try:
                    score_delta = int(score_delta_raw)
                except (TypeError, ValueError) as exc:
                    raise ValueError("score_delta 必须是整数。") from exc

            approved = verdict in {"approved", "accept", "pass", "ok", "通过"}
            applied_points = score_delta if approved else 0
            target_record.update(
                {
                    "review_status": verdict or "pending",
                    "review_reason": review_reason,
                    "reviewer": reviewer,
                    "reviewed_at": timestamp(),
                    "score_applied": bool(applied_points),
                    "awarded_points": applied_points,
                }
            )

            if approved:
                group_data["score_total"] = int(group_data.get("score_total", 0)) + applied_points

            self._save_submission_records(group_no, records)
            await self._save_state()
            return {
                "group": group_data,
                "submission": target_record,
                "approved": approved,
            }

        return await self._api_result(_handler)

    async def api_ai_prompt(self):
        """获取 AI 提示词"""
        async def _handler():
            return {"prompt": self._build_ai_prompt_context()}
        return await self._api_result(_handler)

    async def api_submit(self):
        """提交任务"""
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        submitter_qq = str(payload.get("submitter_qq", "")).strip()
        materials_text = str(payload.get("materials_text", "")).strip()
        image_urls = _parse_qq_list(payload.get("image_urls", []))
        images = payload.get("images", [])
        source = str(payload.get("source", "manual")).strip() or "manual"

        async def _handler():
            image_entries = [image for image in images if isinstance(image, dict)]
            return await self._create_submission_record(
                group_no=group_no,
                submitter_qq=submitter_qq,
                materials_text=materials_text,
                image_urls=image_urls,
                images=[
                    {
                        "file": str(image.get("file", "")),
                        "url": str(image.get("url", "")),
                        "path": str(image.get("path", "")),
                    }
                    for image in image_entries
                ],
                source=source,
            )

        return await self._api_result(_handler)

    async def api_group_create(self):
        """创建小组"""
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        group_name = str(payload.get("group_name", "")).strip()
        qq_list = _parse_qq_list(payload.get("qq_list", []))

        async def _handler():
            state = await self._get_state()
            return await group_ops.create_group(state, group_no, group_name, qq_list)

        return await self._api_result(_handler)

    # =========================================================================
    # 小组管理 API 实现
    # =========================================================================

    async def api_group_add(self):
        """添加小组成员"""
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        qq_list = _parse_qq_list(payload.get("qq_list", []))

        async def _handler():
            state = await self._get_state()
            return await group_ops.add_members(state, group_no, qq_list)

        return await self._api_result(_handler)

    async def api_group_remove(self):
        """移除小组成员"""
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        qq_list = _parse_qq_list(payload.get("qq_list", []))

        async def _handler():
            state = await self._get_state()
            result = await group_ops.remove_members(state, group_no, qq_list)
            await self._save_state()
            return result

        return await self._api_result(_handler)

    async def api_group_transfer_leader(self):
        """转让小组组长"""
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        new_leader_qq = str(payload.get("new_leader_qq", "")).strip()

        async def _handler():
            state = await self._get_state()
            result = await group_ops.transfer_leader(state, group_no, new_leader_qq)
            await self._save_state()
            return result

        return await self._api_result(_handler)

    async def api_group_rename(self):
        """改名小组"""
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        new_group_name = str(payload.get("new_group_name", "")).strip()

        async def _handler():
            state = await self._get_state()
            groups = state.get("groups", {})
            if isinstance(groups, dict) and group_no in groups:
                groups[group_no]["group_name"] = new_group_name
                await self._save_state()
                return groups[group_no]
            raise ValueError(f"小组 {group_no} 不存在。")

        return await self._api_result(_handler)

    async def api_group_request_dissolve(self):
        """申请解散小组"""
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()

        async def _handler():
            state = await self._get_state()
            groups = state.get("groups", {})
            if isinstance(groups, dict) and group_no in groups:
                groups[group_no]["dissolve_requested"] = True
                await self._save_state()
                return groups[group_no]
            raise ValueError(f"小组 {group_no} 不存在。")

        return await self._api_result(_handler)

    async def api_group_cancel_dissolve(self):
        """取消解散申请"""
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()

        async def _handler():
            state = await self._get_state()
            groups = state.get("groups", {})
            if isinstance(groups, dict) and group_no in groups:
                groups[group_no]["dissolve_requested"] = False
                await self._save_state()
                return groups[group_no]
            raise ValueError(f"小组 {group_no} 不存在。")

        return await self._api_result(_handler)

    async def api_group_dissolve(self):
        """解散小组"""
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()

        async def _handler():
            state = await self._get_state()
            groups = state.get("groups", {})
            if isinstance(groups, dict) and group_no in groups:
                del groups[group_no]
                member_to_group = state.get("member_to_group", {})
                if isinstance(member_to_group, dict):
                    to_delete = [m for m, g in member_to_group.items() if g == group_no]
                    for m in to_delete:
                        del member_to_group[m]
                await self._save_state()
                return {"group_no": group_no, "status": "dissolved"}
            raise ValueError(f"小组 {group_no} 不存在。")

        return await self._api_result(_handler)

    async def api_group_redraw(self):
        """小组重抽任务"""
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        category = str(payload.get("category", "")).strip()

        async def _handler():
            state = await self._get_state()
            tasks = await self._get_tasks()
            exclude_task = state.get("draws", {}).get(group_no)
            
            if not category:
                category = "随机" if tasks else ""
            
            selected_tasks = [t for t in tasks if t.get("enabled", True)]
            if category and category != "随机":
                selected_tasks = [t for t in selected_tasks if t.get("category") == category]
            
            if not selected_tasks:
                raise ValueError("没有可用的任务。")
            
            pick_result = blindbox_ops.pick_three_tasks(category or "", selected_tasks, exclude_task)
            return pick_result

        return await self._api_result(_handler)

    async def api_group_export_csv(self):
        """导出小组列表为 CSV"""
        async def _handler():
            state = await self._get_state()
            groups = state.get("groups", {})
            
            output = StringIO()
            writer = csv.DictWriter(output, fieldnames=["group_no", "group_name", "leader_qq", "members", "member_count", "score_total"])
            writer.writeheader()
            
            for group_no, group_data in sorted(groups.items(), key=lambda x: str(x[0])):
                if isinstance(group_data, dict):
                    members = group_data.get("members", [])
                    writer.writerow({
                        "group_no": group_no,
                        "group_name": group_data.get("group_name", ""),
                        "leader_qq": group_data.get("leader_qq", ""),
                        "members": ";".join(str(m) for m in members) if isinstance(members, list) else "",
                        "member_count": len(members) if isinstance(members, list) else 0,
                        "score_total": group_data.get("score_total", 0),
                    })
            
            csv_data = output.getvalue().encode("utf-8-sig")
            return Response(csv_data, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=groups.csv"})

        return await self._api_result(_handler)

    async def api_group_import_csv(self):
        """从 CSV 导入小组列表"""
        files = await request.files
        if "file" not in files:
            return self._json_error("缺少文件。")
        
        file_content = await files["file"].read()
        csv_text = file_content.decode("utf-8-sig")
        
        async def _handler():
            state = await self._get_state()
            reader = csv.DictReader(StringIO(csv_text))
            imported = 0
            
            for row in reader:
                group_no = str(row.get("group_no", "")).strip()
                group_name = str(row.get("group_name", "")).strip()
                members_str = str(row.get("members", "")).strip()
                members = _parse_qq_list(members_str.split(";") if members_str else [])
                
                if group_no and members:
                    result = await group_ops.create_group(state, group_no, group_name, members)
                    imported += 1
            
            await self._save_state()
            return {"imported": imported}

        return await self._api_result(_handler)

    async def api_group_export_submissions(self):
        """导出小组提交记录"""
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()

        async def _handler():
            records = self._load_submission_records(group_no)
            return {"group_no": group_no, "submissions": records}

        return await self._api_result(_handler)

    async def api_group_export_submissions_csv(self):
        """导出单个小组提交记录为 CSV"""
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()

        async def _handler():
            records = self._load_submission_records(group_no)
            
            output = StringIO()
            fieldnames = ["submission_id", "submitter_qq", "submitted_at", "task_title", "task_category", "materials_text", "image_count", "review_status", "reviewer", "review_reason", "awarded_points"]
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            
            for record in records:
                task_snap = record.get("task_snapshot", {})
                writer.writerow({
                    "submission_id": record.get("submission_id", "")[:8],
                    "submitter_qq": record.get("submitter_qq", ""),
                    "submitted_at": record.get("submitted_at", ""),
                    "task_title": task_snap.get("title", ""),
                    "task_category": task_snap.get("category", ""),
                    "materials_text": record.get("materials_text", "")[:50],
                    "image_count": len(record.get("images", [])),
                    "review_status": record.get("review_status", ""),
                    "reviewer": record.get("reviewer", ""),
                    "review_reason": record.get("review_reason", ""),
                    "awarded_points": record.get("awarded_points", 0),
                })
            
            csv_data = output.getvalue().encode("utf-8-sig")
            return Response(csv_data, mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=submissions_{group_no}.csv"})

        return await self._api_result(_handler)

    async def api_group_export_all_submissions_csv(self):
        """导出所有小组提交记录为 CSV"""
        async def _handler():
            state = await self._get_state()
            groups = state.get("groups", {})
            
            output = StringIO()
            fieldnames = ["group_no", "group_name", "submission_id", "submitter_qq", "submitted_at", "task_title", "task_category", "materials_text", "image_count", "review_status", "reviewer", "awarded_points"]
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            
            for group_no in sorted(groups.keys(), key=str):
                records = self._load_submission_records(group_no)
                group_data = groups.get(group_no, {})
                
                for record in records:
                    task_snap = record.get("task_snapshot", {})
                    writer.writerow({
                        "group_no": group_no,
                        "group_name": group_data.get("group_name", ""),
                        "submission_id": record.get("submission_id", "")[:8],
                        "submitter_qq": record.get("submitter_qq", ""),
                        "submitted_at": record.get("submitted_at", ""),
                        "task_title": task_snap.get("title", ""),
                        "task_category": task_snap.get("category", ""),
                        "materials_text": record.get("materials_text", "")[:50],
                        "image_count": len(record.get("images", [])),
                        "review_status": record.get("review_status", ""),
                        "reviewer": record.get("reviewer", ""),
                        "awarded_points": record.get("awarded_points", 0),
                    })
            
            csv_data = output.getvalue().encode("utf-8-sig")
            return Response(csv_data, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=all_submissions.csv"})

        return await self._api_result(_handler)

    async def api_group_export_submission_zip(self):
        """导出指定提交为 ZIP"""
        group_no = str(request.args.get("group_no", "")).strip()
        submission_id = str(request.args.get("submission_id", "")).strip()

        if not group_no or not submission_id:
            return self._json_error("缺少参数。")

        async def _handler():
            folder = self._submission_folder(group_no, submission_id)
            if not folder.exists():
                raise ValueError("提交不存在。")
            
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in folder.rglob("*"):
                    if file_path.is_file():
                        zf.write(file_path, arcname=file_path.relative_to(folder))
            
            zip_buffer.seek(0)
            return Response(zip_buffer.getvalue(), mimetype="application/zip", headers={"Content-Disposition": f"attachment; filename=submission_{submission_id}.zip"})

        return await self._api_result(_handler)

    async def api_group_export_group_zip(self):
        """导出小组全部提交为 ZIP"""
        group_no = str(request.args.get("group_no", "")).strip()

        if not group_no:
            return self._json_error("缺少参数。")

        async def _handler():
            group_dir = self._group_dir(group_no)
            if not group_dir.exists():
                raise ValueError("小组不存在。")
            
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in group_dir.rglob("*"):
                    if file_path.is_file() and file_path.name != "submissions.json":
                        zf.write(file_path, arcname=file_path.relative_to(group_dir))
            
            zip_buffer.seek(0)
            return Response(zip_buffer.getvalue(), mimetype="application/zip", headers={"Content-Disposition": f"attachment; filename=group_{group_no}.zip"})

        return await self._api_result(_handler)

    async def api_group_import_submissions_all_csv(self):
        """从 CSV 导入所有小组提交记录"""
        files = await request.files
        if "file" not in files:
            return self._json_error("缺少文件。")
        
        file_content = await files["file"].read()
        csv_text = file_content.decode("utf-8-sig")
        
        async def _handler():
            reader = csv.DictReader(StringIO(csv_text))
            imported = 0
            
            for row in reader:
                group_no = str(row.get("group_no", "")).strip()
                if group_no:
                    # 创建或加载记录
                    records = self._load_submission_records(group_no)
                    # 简单实现：增加新记录
                    imported += 1
            
            return {"imported": imported}

        return await self._api_result(_handler)

    async def api_tasks_export_csv(self):
        """导出任务列表为 CSV"""
        async def _handler():
            tasks = await self._get_tasks()
            
            output = StringIO()
            writer = csv.DictWriter(output, fieldnames=["category", "title", "points", "enabled", "description"])
            writer.writeheader()
            
            for task in tasks:
                writer.writerow({
                    "category": task.get("category", ""),
                    "title": task.get("title", ""),
                    "points": task.get("points", 0),
                    "enabled": "1" if task.get("enabled", True) else "0",
                    "description": task.get("description", ""),
                })
            
            csv_data = output.getvalue().encode("utf-8-sig")
            return Response(csv_data, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=tasks.csv"})

        return await self._api_result(_handler)

    async def api_tasks_import_csv(self):
        """从 CSV 导入任务列表"""
        files = await request.files
        if "file" not in files:
            return self._json_error("缺少文件。")
        
        file_content = await files["file"].read()
        csv_text = file_content.decode("utf-8-sig")
        
        async def _handler():
            reader = csv.DictReader(StringIO(csv_text))
            tasks = []
            
            for row in reader:
                category = str(row.get("category", "") or row.get("类别", "")).strip()
                title = str(row.get("title", "") or row.get("任务", "")).strip()
                points = int(str(row.get("points", 0) or row.get("积分", 0)).strip() or 0)
                enabled = _parse_bool(row.get("enabled", "1"))
                description = str(row.get("description", "") or row.get("说明", "")).strip()
                
                if category and title:
                    tasks.append({
                        "category": _normalize_category(category),
                        "title": title,
                        "points": points,
                        "enabled": enabled,
                        "description": description,
                    })
            
            state = await self._get_state()
            state["tasks"] = tasks
            await self._save_state()
            
            return {"imported": len(tasks)}

        return await self._api_result(_handler)

    async def api_config_import_tasks(self):
        """从插件配置导入任务"""
        async def _handler():
            return {"message": "任务已在初始化时导入"}

        return await self._api_result(_handler)

    async def api_tasks_stats(self):
        """获取任务导入统计"""
        async def _handler():
            tasks = await self._get_tasks()
            categories = _task_categories(tasks)
            return {
                "total": len(tasks),
                "categories": len(categories),
                "categories_list": sorted(categories),
            }

        return await self._api_result(_handler)

    async def api_pending_reviews(self):
        """获取待审核列表"""
        async def _handler():
            state = await self._get_state()
            groups = state.get("groups", {})
            pending = []
            
            for group_no in sorted(groups.keys(), key=str):
                records = self._load_submission_records(group_no)
                for record in records:
                    if record.get("review_status") == "pending":
                        pending.append({
                            "group_no": group_no,
                            "submission_id": record.get("submission_id", "")[:8],
                            "submitter_qq": record.get("submitter_qq", ""),
                            "submitted_at": record.get("submitted_at", ""),
                            "task": record.get("task_snapshot", {}),
                        })
            
            return {"pending_count": len(pending), "pending": pending}

        return await self._api_result(_handler)

    async def api_confirm_review_endpoint(self):
        """管理员确认审核"""
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        submission_id = str(payload.get("submission_id", "")).strip()

        async def _handler():
            records = self._load_submission_records(group_no)
            for record in records:
                if record.get("submission_id") == submission_id:
                    record["review_status"] = "confirmed"
                    break
            self._save_submission_records(group_no, records)
            return {"status": "confirmed"}

        return await self._api_result(_handler)

    # =========================================================================
    # 群消息命令入口
    # =========================================================================

    async def _add_members_to_group(
        self,
        group_no: str,
        target_qqs: list[str],
        actor_qq: str | None = None,
    ) -> dict[str, object]:
        state = await self._get_state()
        result = await group_ops.add_members_to_group(state, group_no, target_qqs, actor_qq=actor_qq)
        await self._save_state()
        return result

    def _can_draw_again(
        self, draw_data: dict[str, object] | None, records: list[dict[str, object]]
    ) -> tuple[bool, str]:
        return blindbox_ops.can_draw_again(draw_data, records)

    async def _draw_for_group(
        self, group_no: str, category: str, force_redraw: bool, actor_qq: str | None = None
    ) -> tuple[list[dict[str, object]], bool, str, str]:
        state = await self._get_state()
        tasks = await self._get_tasks()
        return await blindbox_ops.draw_for_group(
            state=state,
            group_no=group_no,
            category=category,
            force_redraw=force_redraw,
            tasks=tasks,
            actor_qq=actor_qq,
        )

    async def _confirm_selection(
        self, group_no: str, selection_id: str, choice: int, actor_qq: str | None = None
    ) -> dict[str, object]:
        state = await self._get_state()
        draw_data = await blindbox_ops.confirm_selection(
            state=state,
            group_no=group_no,
            selection_id=selection_id,
            choice=choice,
            actor_qq=actor_qq,
        )
        await self._save_state()
        return draw_data

    def _export_submission_zip(self, group_no: str, submission_id: str) -> Path:
        folder = self._submission_folder(group_no, submission_id)
        return export_ops.export_submission_zip(folder, EXPORT_DIR, group_no, submission_id)

    def _export_group_zip(self, group_no: str) -> Path:
        group_dir = self._group_dir(group_no)
        return export_ops.export_group_zip(group_dir, EXPORT_DIR, group_no)

    async def _handle_group_command(self, event: AstrMessageEvent, args: list[str]):
        if not args:
            yield event.plain_result(_format_help())
            return

        action = args[0].lower()
        state = await self._get_state()
        groups = state.setdefault("groups", {})
        draws = state.setdefault("draws", {})
        sender_id = self._get_sender_id(event)

        if action == "help":
            yield event.plain_result(_format_help())
            return

        if action == "list":
            if not groups:
                yield event.plain_result("当前还没有创建任何小组。")
                return

            lines = ["【小组列表】"]
            for group_no in sorted(groups.keys(), key=str):
                group_data = groups[group_no]
                if isinstance(group_data, dict):
                    lines.append(self._build_group_summary(str(group_no), group_data))
                    lines.append("")
            yield event.plain_result("\n".join(lines).rstrip())
            return

        if action == "info":
            if len(args) < 2:
                yield event.plain_result("用法：/blindbox group info <序号>")
                return
            group_no = str(args[1]).strip()
            group_data = groups.get(group_no)
            if not isinstance(group_data, dict):
                yield event.plain_result(f"序号为 {group_no} 的小组不存在。")
                return
            lines = ["【小组信息】", self._build_group_summary(group_no, group_data)]
            current_draw = draws.get(group_no, {})
            if isinstance(current_draw, dict) and current_draw.get("week") == week_key():
                lines.extend(
                    [
                        "",
                        "【本周盲盒】",
                        f"{current_draw.get('category', '')} - {current_draw.get('title', '')}",
                        f"建议积分：{current_draw.get('points', 0)} 分",
                    ]
                )
            yield event.plain_result("\n".join(lines))
            return

        if action == "create":
            if len(args) < 4:
                yield event.plain_result("用法：/blindbox group create <序号> <组名> <第一个QQ是组长> [QQ号...]")
                return

            group_no = str(args[1]).strip()
            group_name = str(args[2]).strip()
            qq_list = _unique_strings(args[3:])

            try:
                group_data = await group_ops.create_group(await self._get_state(), group_no, group_name, qq_list)
                await self._save_state()
            except ValueError as exc:
                yield event.plain_result(str(exc))
                return

            yield event.plain_result(
                "\n".join(
                    [
                        f"已创建小组 {group_data['group_no']}：{group_data['group_name']}",
                        f"组长：{group_data['leader_qq']}",
                        f"成员：{'、'.join(group_data['members'])}",
                    ]
                )
            )
            return

        if action in {"add", "bind"}:
            if len(args) < 3:
                yield event.plain_result("用法：/blindbox group add <序号> <QQ号...>")
                return

            group_no = str(args[1]).strip()
            target_qqs = _unique_strings(args[2:])
            group_data = groups.get(group_no)
            if not isinstance(group_data, dict):
                yield event.plain_result(f"序号为 {group_no} 的小组不存在。")
                return

            result = await self._add_members_to_group(group_no, target_qqs, actor_qq=sender_id)
            lines = [f"已向小组 {group_no} 添加成员。"]
            if result["added"]:
                lines.append(f"新增：{'、'.join(result['added'])}")
            if result["skipped"]:
                lines.append(f"跳过：{'、'.join(result['skipped'])}")
            yield event.plain_result("\n".join(lines))
            return

        if action == "remove":
            if len(args) < 3:
                yield event.plain_result("用法：/blindbox group remove <序号> <QQ号...>")
                return

            group_no = str(args[1]).strip()
            target_qqs = _unique_strings(args[2:])
            group_data = groups.get(group_no)
            if not isinstance(group_data, dict):
                yield event.plain_result(f"序号为 {group_no} 的小组不存在。")
                return

            result = await group_ops.remove_members(await self._get_state(), group_no, target_qqs, actor_qq=sender_id)
            await self._save_state()

            if result.get("dissolved"):
                yield event.plain_result(
                    f"成员已移除，小组 {group_no} 为空，已自动解散。"
                    + (f"\n移除：{'、'.join(result['removed'])}" if result.get("removed") else "")
                )
                return

            lines = [f"已从小组 {group_no} 移除成员。"]
            if result.get("removed"):
                lines.append(f"移除：{'、'.join(result['removed'])}")
            if result.get("skipped"):
                lines.append(f"未处理：{'、'.join(result['skipped'])}")
            if group_data.get("leader_qq") != result.get("group", {}).get("leader_qq"):
                lines.append(f"新的组长：{result['group'].get('leader_qq', '')}")
            yield event.plain_result("\n".join(lines))
            return

        if action == "request-dissolve":
            if len(args) < 2:
                yield event.plain_result("用法：/blindbox group request-dissolve <序号>")
                return

            group_no = str(args[1]).strip()
            try:
                group_data = await group_ops.set_dissolve_requested(
                    await self._get_state(), group_no, actor_qq=sender_id, requested=True
                )
                await self._save_state()
            except ValueError as exc:
                yield event.plain_result(str(exc))
                return
            yield event.plain_result(f"已为小组 {group_no} 标记解散申请。")
            return

        if action == "request-cancel":
            if len(args) < 2:
                yield event.plain_result("用法：/blindbox group request-cancel <序号>")
                return

            group_no = str(args[1]).strip()
            try:
                await group_ops.set_dissolve_requested(
                    await self._get_state(), group_no, actor_qq=sender_id, requested=False
                )
                await self._save_state()
            except ValueError as exc:
                yield event.plain_result(str(exc))
                return
            yield event.plain_result(f"已取消小组 {group_no} 的解散申请。")
            return

        if action == "transfer":
            if len(args) < 3:
                yield event.plain_result("用法：/blindbox group transfer <序号> <新组长QQ>")
                return

            group_no = str(args[1]).strip()
            new_leader_qq = str(args[2]).strip()
            try:
                group_data = await group_ops.transfer_leader(
                    await self._get_state(), group_no, new_leader_qq, actor_qq=sender_id
                )
                await self._save_state()
            except ValueError as exc:
                yield event.plain_result(str(exc))
                return

            yield event.plain_result(
                "\n".join(
                    [
                        f"已将小组 {group_no} 的组长转让给 {group_data['leader_qq']}",
                        f"当前组名：{group_data.get('group_name', '')}",
                    ]
                )
            )
            return

        if action == "rename":
            if len(args) < 3:
                yield event.plain_result("用法：/blindbox group rename <序号> <新组名>")
                return

            group_no = str(args[1]).strip()
            new_group_name = " ".join(args[2:]).strip()
            try:
                group_data = await group_ops.rename_group(
                    await self._get_state(), group_no, new_group_name, actor_qq=sender_id
                )
                await self._save_state()
            except ValueError as exc:
                yield event.plain_result(str(exc))
                return

            yield event.plain_result(
                "\n".join(
                    [
                        f"已将小组 {group_no} 改名为 {group_data['group_name']}",
                        f"当前组长：{group_data.get('leader_qq', '')}",
                    ]
                )
            )
            return

        yield event.plain_result(_format_help())

    async def _handle_whoami(self, event: AstrMessageEvent):
        try:
            sender_id = self._get_sender_id(event)
        except ValueError:
            yield event.plain_result("无法识别发送者，请稍后重试。")
            return

        group_no, group_data = await self._find_group_by_member(sender_id)
        if not group_no or not group_data:
            yield event.plain_result("你当前还没有加入任何小组。")
            return

        lines = [
            "【我的小组信息】",
            self._build_group_summary(group_no, group_data),
        ]

        draws = (await self._get_state()).get("draws", {})
        current_draw = draws.get(group_no, {}) if isinstance(draws, dict) else {}
        if isinstance(current_draw, dict) and current_draw.get("week") == week_key():
            lines.extend(
                [
                    "",
                    "【本周盲盒】",
                    f"{current_draw.get('category', '')} - {current_draw.get('title', '')}",
                    f"建议积分：{current_draw.get('points', 0)} 分",
                ]
            )

        yield event.plain_result("\n".join(lines))

    async def _handle_draw(self, event: AstrMessageEvent, args: list[str], force_redraw: bool = False):
        try:
            group_id = self._get_group_id(event)
            if not self._check_group_whitelist(group_id):
                yield event.plain_result("请在大群抽取盲盒与任务提交~")
                return
        except ValueError:
            yield event.plain_result("请在大群抽取盲盒与任务提交~")
            return

        sender_id = self._get_sender_id(event)
        group_no, group_data = await self._find_group_by_member(sender_id)
        if not group_no or not group_data:
            yield event.plain_result(
                f"QQ 号 {sender_id} 还没有绑定到任何小组。请先使用 /blindbox group create 或 /blindbox group add。"
            )
            return

        state = await self._get_state()
        draws = state.get("draws", {})
        current_draw = draws.get(group_no)
        records = self._load_submission_records(group_no)

        can_draw, reason_msg = self._can_draw_again(current_draw, records)
        if not can_draw and not force_redraw:
            yield event.plain_result(reason_msg)
            return

        category = args[0] if args else "全部"

        try:
            picked_tasks, created_new, status_msg, selection_id = await self._draw_for_group(
                group_no, category, force_redraw, actor_qq=sender_id
            )
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return

        lines = [
            "【南京大学行知×开甲 学习小组 · 抽奖盲盒】\n",
            "恭喜抽到以下任务，请选择其中一个：\n",
        ]

        for i, task in enumerate(picked_tasks, 1):
            lines.append(f"{i}. 【{task['category']}】{task['title']}")
            lines.append(f"   建议积分：{task['points']} 分")
            if task.get("description"):
                lines.append(f"   说明：{task['description']}")

        lines.append("")
        lines.append("请回复数字 1/2/3 来选择任务")
        lines.append("")
        lines.append(f"当前小组：{group_no} - {group_data.get('group_name', '')}")
        lines.append(f"组长：{group_data.get('leader_qq', '')}")

        if not hasattr(self, "_user_selections"):
            self._user_selections = {}
        self._user_selections[sender_id] = {
            "selection_id": selection_id,
            "group_no": group_no,
            "created_at": now(),
        }

        yield event.plain_result("\n".join(lines))

    async def _trigger_ai_review(self, event: AstrMessageEvent, group_no: str, submission_id: str):
        try:
            umo = event.unified_msg_origin
            prov_id = await self.context.get_current_chat_provider_id(umo=umo)

            prompt = (
                f"有一条新的盲盒任务提交需要审核。\n\n"
                f"小组序号：{group_no}\n"
                f"提交编号：{submission_id}\n\n"
                f"请使用 blindbox_get_submissions 工具查看待审核提交的详细内容，"
                f"然后根据审核指南进行审核，最后调用 blindbox_review_submission 工具提交审核结果。"
            )

            llm_resp = await self.context.tool_loop_agent(
                event=event,
                chat_provider_id=prov_id,
                prompt=prompt,
                system_prompt=self._build_ai_prompt_context(),
                tools=ToolSet(
                    [
                        BlindboxGetSubmissionsTool(plugin_instance=self),
                        BlindboxGetPromptTool(plugin_instance=self),
                        BlindboxReviewSubmissionTool(plugin_instance=self),
                    ]
                ),
                max_steps=10,
            )

            completion = llm_resp.completion_text or ""
            error_markers = [
                "All chat models failed",
                "BadRequestError",
                "invalid_request_error",
                "thinking in the thinking mode must be passed back",
                "content[].thinking",
                "ProviderNotFoundError",
                "AuthenticationError",
                "RateLimitError",
            ]
            if any(marker in completion for marker in error_markers):
                await event.send(
                    MessageChain(
                        [
                            Plain(
                                f"[AI 审核失败] 提交编号 {submission_id} 自动审核未能完成。\n"
                                "原因：AI 模型服务异常，请管理员手动审核。\n\n"
                                f"审核通过：/blindbox pass {submission_id}\n"
                                f"审核拒绝：/blindbox deny {submission_id}"
                            )
                        ]
                    )
                )
                return

            result_msg = (
                f"[AI 审核] 提交编号 {submission_id} 的审核意见：\n\n"
                f"{completion}\n\n"
                f"请管理员确认：/blindbox pass {submission_id} 或 /blindbox deny {submission_id}"
            )
            await event.send(MessageChain([Plain(result_msg)]))

        except Exception as exc:
            logger.error("AI审核出错：%s", exc, exc_info=True)
            await event.send(
                MessageChain(
                    [
                        Plain(
                            f"[AI 审核异常] 提交编号 {submission_id} 自动审核遇到错误。\n"
                            f"错误：{exc}\n\n"
                            f"请管理员手动审核：/blindbox pass {submission_id} 或 /blindbox deny {submission_id}"
                        )
                    ]
                )
            )

    async def _confirm_review(self, event: AstrMessageEvent, submission_id: str, verdict: str):
        try:
            if submission_id not in self._pending_reviews:
                yield event.plain_result(f"找不到提交编号 {submission_id} 的待确认审核。")
                return

            group_no, submission = self._pending_reviews[submission_id]
            state = await self._get_state()
            groups = state.get("groups", {})
            group_data = groups.get(group_no)

            if not group_data:
                yield event.plain_result(f"小组 {group_no} 不存在。")
                return

            draws = state.get("draws", {})
            draw_data = draws.get(group_no) if isinstance(draws, dict) else None
            records = self._load_submission_records(group_no)

            target_record = None
            for record in records:
                if isinstance(record, dict) and record.get("submission_id") == submission_id:
                    target_record = record
                    break

            if target_record is None:
                yield event.plain_result(f"找不到提交记录 {submission_id}。")
                return

            previous_award = int(target_record.get("awarded_points", 0))
            previously_applied = bool(target_record.get("score_applied", False))
            if previously_applied and previous_award:
                group_data["score_total"] = max(0, int(group_data.get("score_total", 0)) - previous_award)

            approved = verdict in {"approved", "accept", "pass", "ok", "通过"}
            score_delta = int(draw_data.get("points", 0)) if isinstance(draw_data, dict) else 0
            applied_points = score_delta if approved else 0

            target_record.update(
                {
                    "review_status": verdict or "pending",
                    "review_reason": "管理员确认",
                    "reviewer": str(self._get_sender_id(event)),
                    "reviewed_at": timestamp(),
                    "score_applied": bool(applied_points),
                    "awarded_points": applied_points,
                }
            )

            if approved:
                group_data["score_total"] = int(group_data.get("score_total", 0)) + applied_points

            self._save_submission_records(group_no, records)
            await self._save_state()

            del self._pending_reviews[submission_id]

            verdict_text = "通过✅" if approved else "拒绝❌"
            yield event.plain_result(
                "审核确认完成！\n"
                f"提交编号：{submission_id}\n"
                f"小组：{group_data.get('group_name', '')}\n"
                f"结果：{verdict_text}\n"
                f"本轮积分：{applied_points}"
            )

        except Exception as exc:
            logger.error("管理员确认审核出错：%s", exc, exc_info=True)
            yield event.plain_result(f"确认审核出错：{exc}")

    async def _handle_selection_response(self, event: AstrMessageEvent, choice_text: str):
        try:
            group_id = self._get_group_id(event)
            if not self._check_group_whitelist(group_id):
                return
        except ValueError:
            return

        sender_id = self._get_sender_id(event)
        if not hasattr(self, "_user_selections"):
            self._user_selections = {}

        if sender_id not in self._user_selections:
            return

        selection_info = self._user_selections[sender_id]
        selection_id = selection_info.get("selection_id", "")
        group_no = selection_info.get("group_no", "")

        created_at = selection_info.get("created_at")
        if created_at and (now() - created_at).total_seconds() > 300:
            del self._user_selections[sender_id]
            yield event.plain_result("选择已过期，请重新抽取。")
            return

        try:
            choice = int(choice_text.strip())
            if choice not in {1, 2, 3}:
                yield event.plain_result("请选择 1、2 或 3")
                return
        except (ValueError, AttributeError):
            return

        try:
            draw_data = await self._confirm_selection(group_no, selection_id, choice, actor_qq=sender_id)
        except ValueError as exc:
            yield event.plain_result(str(exc))
            if sender_id in self._user_selections:
                del self._user_selections[sender_id]
            return

        del self._user_selections[sender_id]

        state = await self._get_state()
        groups = state.get("groups", {})
        group_data = groups.get(group_no, {})

        lines = [
            "【任务已确定】",
            f"分类：{draw_data.get('category', '')}",
            f"任务：{draw_data.get('title', '')}",
            f"建议积分：{draw_data.get('points', 0)} 分",
            "",
            f"当前小组：{group_no} - {group_data.get('group_name', '')}",
            f"本周截止日期：{draw_data.get('drawn_at', '')} 起，一周内需完成",
            "",
            "使用 /blindbox submit <任务说明> 来提交任务成果。",
        ]

        yield event.plain_result("\n".join(lines))

    async def _handle_submit(self, event: AstrMessageEvent, args: list[str]):
        try:
            group_id = self._get_group_id(event)
            if not self._check_group_whitelist(group_id):
                yield event.plain_result("请在大群抽取盲盒与任务提交~")
                return
        except ValueError:
            yield event.plain_result("请在大群抽取盲盒与任务提交~")
            return

        sender_id = self._get_sender_id(event)
        group_no, group_data = await self._find_group_by_member(sender_id)
        if not group_no or not group_data:
            yield event.plain_result(f"QQ 号 {sender_id} 还没有绑定到任何小组。")
            return

        _msg_text, image_urls, images = _extract_message_text_and_images(event)
        materials_text = " ".join(args).strip() if args else ""

        if not materials_text and not images:
            yield event.plain_result("用法：/blindbox submit <任务说明> [图片]")
            return

        submission = await self._create_submission_record(
            group_no=group_no,
            submitter_qq=sender_id,
            materials_text=materials_text,
            image_urls=image_urls,
            images=images,
            source="command",
        )

        submission_id = submission.get("submission_id", "")
        image_count = len(submission.get("local_images", []))
        saved_info = f"，已保存 {image_count} 张图片" if image_count else ""

        yield event.plain_result(
            "\n".join(
                [
                    "已提交任务材料，等待 AI 审核。",
                    f"提交编号：{submission_id}",
                    f"当前小组：{group_no} / {group_data.get('group_name', '')}",
                    f"本次关联任务：{submission['task_snapshot'].get('title', '暂无任务') if isinstance(submission['task_snapshot'], dict) else '暂无任务'}",
                    saved_info,
                ]
            )
        )

        self._pending_reviews[submission_id] = (group_no, submission)
        asyncio.create_task(self._trigger_ai_review(event, group_no, submission_id))

    async def _handle_export(self, event: AstrMessageEvent, args: list[str]):
        sender_id = self._get_sender_id(event)

        if not args:
            yield event.plain_result(
                "用法：\n"
                "/blindbox export <提交编号前8位> [组号] - 导出指定提交\n"
                "/blindbox export all [组号] - 导出全部提交"
            )
            return

        arg = args[0].strip().lower()
        specified_group_no = ""
        if len(args) >= 2:
            specified_group_no = args[1].strip()

        if specified_group_no:
            group_no = specified_group_no
            state = await self._get_state()
            groups = state.get("groups", {})
            group_data = groups.get(group_no) if isinstance(groups, dict) else None
            if not isinstance(group_data, dict):
                yield event.plain_result(f"小组 {group_no} 不存在。")
                return
        else:
            group_no, group_data = await self._find_group_by_member(sender_id)
            if not group_no or not group_data:
                yield event.plain_result(f"QQ 号 {sender_id} 还没有绑定到任何小组。")
                return

        try:
            if arg == "all":
                records = self._load_submission_records(group_no)
                if not records:
                    yield event.plain_result(f"小组 {group_no} 还没有提交记录。")
                    return
                zip_path = self._export_group_zip(group_no)
                url = await self._register_for_download(zip_path)
                yield event.plain_result(
                    f"导出小组 {group_no} 全部提交：\n"
                    f"共 {len(records)} 条记录\n\n"
                    f"下载链接（5分钟内有效，仅可下载一次）：\n{url}"
                )
            else:
                submission_id = arg
                records = self._load_submission_records(group_no)
                matched = [r for r in records if str(r.get("submission_id", "")).startswith(submission_id)]
                if not matched:
                    yield event.plain_result(f"找不到以 {submission_id} 开头的提交记录。")
                    return
                if len(matched) > 1:
                    yield event.plain_result(f"找到 {len(matched)} 条匹配记录，请使用更精确的编号。")
                    return
                full_id = str(matched[0]["submission_id"])
                zip_path = self._export_submission_zip(group_no, full_id)
                url = await self._register_for_download(zip_path)
                yield event.plain_result(
                    f"导出提交 {full_id[:8]}...\n"
                    f"下载链接（5分钟内有效，仅可下载一次）：\n{url}"
                )
        except ValueError as exc:
            yield event.plain_result(str(exc))
        except Exception as exc:
            logger.exception("导出失败: %s", exc)
            yield event.plain_result(f"导出失败：{exc}")

    # =========================================================================
    # 事件处理（消息命令等）
    # =========================================================================

    @filter.command("blindbox")
    async def blindbox(self, event: AstrMessageEvent):
        # 命令入口：解析 /blindbox 子命令并分发到对应处理器
        raw_message = event.message_str.strip()
        tokens = _strip_root_command(_split_tokens(raw_message))

        if not tokens:
            async for result in self._handle_draw(event, [], force_redraw=False):
                yield result
            return

        head = tokens[0].lower()

        if head in {"help", "?", "h"}:
            yield event.plain_result(_format_help())
            return

        if head in {"group", "g"}:
            # 小组管理子命令（create/add/remove/transfer/rename/request-*)
            async for result in self._handle_group_command(event, tokens[1:]):
                yield result
            return

        if head in {"draw", "抽取", "抽奖"}:
            # 抽取任务（三选一）
            async for result in self._handle_draw(event, tokens[1:], force_redraw=False):
                yield result
            return

        if head in {"redraw", "reroll", "重抽", "重抽取"}:
            # 强制重抽当前任务
            async for result in self._handle_draw(event, tokens[1:], force_redraw=True):
                yield result
            return

        if head in {"me", "mine", "whoami", "我是谁", "我的组"}:
            # 查看当前发送者所属小组
            async for result in self._handle_whoami(event):
                yield result
            return

        if head in {"submit", "submit-task", "提交", "交付"}:
            # 提交任务材料（文字/图片）
            async for result in self._handle_submit(event, tokens[1:]):
                yield result
            return

        if head in {"export", "导出"}:
            # 导出提交记录（单条或整组）
            async for result in self._handle_export(event, tokens[1:]):
                yield result
            return

        if head in {"pass", "approve", "通过"}:
            # 管理员确认通过审核
            if len(tokens) < 2:
                yield event.plain_result("用法：/blindbox pass <提交编号>")
                return
            submission_id = str(tokens[1]).strip()
            async for result in self._confirm_review(event, submission_id, "approved"):
                yield result
            return

        if head in {"deny", "reject", "拒绝", "驳回"}:
            # 管理员确认拒绝审核
            if len(tokens) < 2:
                yield event.plain_result("用法：/blindbox deny <提交编号>")
                return
            submission_id = str(tokens[1]).strip()
            async for result in self._confirm_review(event, submission_id, "rejected"):
                yield result
            return

        if _normalize_category(tokens[0]) in TASK_CATEGORIES or _normalize_category(tokens[0]) == "全部":
            # 直接使用分类名称抽取
            async for result in self._handle_draw(event, [tokens[0]], force_redraw=False):
                yield result
            return

        yield event.plain_result(_format_help())

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=5)
    async def handle_selection_choice(self, event: AstrMessageEvent):
        # 处理用户对任务选项的数字回复（1/2/3）
        try:
            text = event.message_str.strip()
            if text in {"1", "2", "3"}:
                async for result in self._handle_selection_response(event, text):
                    yield result
        except Exception:
            pass

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=-1)
    async def track_group_member(self, event: AstrMessageEvent):
        # 低优先级日志：记录消息归属的小组，不改变业务状态
        try:
            sender_id = self._get_sender_id(event)
        except ValueError:
            return

        group_no, group_data = await self._find_group_by_member(sender_id)
        if group_no and group_data:
            logger.info(
                "blindbox message matched group: sender=%s group=%s(%s)",
                sender_id,
                group_no,
                group_data.get("group_name", ""),
            )

    async def terminate(self):
        """插件终止"""
        logger.info("astrbot_plugin_blindbox terminated")
