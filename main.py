from __future__ import annotations

import asyncio
import csv
import json
import shlex
from datetime import datetime
from io import StringIO
from pathlib import Path
from random import choice
from uuid import uuid4

from quart import Response, jsonify, request

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import At, BaseMessageComponent, Image, Plain


PLUGIN_NAME = "astrbot_plugin_blindbox"
KV_STATE_KEY = "blindbox_state"


def _resolve_data_root() -> Path:
    current_dir = Path(__file__).resolve().parent
    for ancestor in [current_dir, *current_dir.parents]:
        data_dir = ancestor / "data"
        if data_dir.is_dir():
            return data_dir / "plugins" / PLUGIN_NAME
    return current_dir / "data" / "plugins" / PLUGIN_NAME


DATA_ROOT_DIR = _resolve_data_root()
SUBMISSION_DIR = DATA_ROOT_DIR / "submissions"
LEGACY_RUNTIME_DIR = Path(__file__).resolve().parent / "runtime"
LEGACY_SUBMISSION_DIR = LEGACY_RUNTIME_DIR / "submissions"

# 默认规则和任务池，WebUI 里的配置会覆盖这里的内容。
DEFAULT_RULES_TEXT = (
    "据行为心理学的‘可变比率强化’学说，不确定的任务和奖励能持续激发参与者的期待感。\n"
    "本期学习小组引入‘盲盒任务’机制：每小组每周可抽取一次盲盒任务，为一周的小组学习设置目标激励。\n\n"
    "小组完成盲盒任务后可以获得对应积分，这些积分可用于兑换精美奖品、评选优秀小组。"
)

DEFAULT_TASKS = [
    {"category": "学习类", "title": "自习地点抽签", "points": 10, "enabled": True},
    {"category": "学习类", "title": "好书分享挑战", "points": 12, "enabled": True},
    {"category": "学习类", "title": "错题交换挑战", "points": 12, "enabled": True},
    {
        "category": "学习类",
        "title": "技能交换市场：每个人挑自己最近使用的学习工具或技能，做基本介绍",
        "points": 15,
        "enabled": True,
    },
    {"category": "体育类", "title": "跑 2.4 个 2k4", "points": 20, "enabled": True},
    {"category": "体育类", "title": "占领健身房一天", "points": 18, "enabled": True},
    {
        "category": "体育类",
        "title": "2k4 接力：不准 6 个人一人跑一圈带六个手机一起上传校园跑",
        "points": 22,
        "enabled": True,
    },
    {"category": "体育类", "title": "挑战校内校园跑最诡异路线", "points": 20, "enabled": True},
    {"category": "交流类", "title": "一起看电影、剧本杀、桌游", "points": 12, "enabled": True},
    {"category": "交流类", "title": "垃圾话漂流瓶：匿名收集盒，一周结束一起读", "points": 10, "enabled": True},
    {"category": "交流类", "title": "传话游戏 / 传画游戏：接龙完成一个故事或连环画", "points": 14, "enabled": True},
    {
        "category": "交流类",
        "title": "让 AI 胡乱生成一个 PPT，再找个空教室或南青格庐乱讲 PPT",
        "points": 16,
        "enabled": True,
    },
    {"category": "交流类", "title": "探索校园里的小动物：神奇动物在哪里", "points": 12, "enabled": True},
    {"category": "吃喝类", "title": "一起吃疯狂星期四", "points": 8, "enabled": True},
]

TASK_CATEGORIES = ["学习类", "体育类", "交流类", "吃喝类"]
CATEGORY_ALIASES = {
    "学习": "学习类",
    "学习类": "学习类",
    "体育": "体育类",
    "运动": "体育类",
    "体育类": "体育类",
    "交流": "交流类",
    "交流类": "交流类",
    "吃喝": "吃喝类",
    "吃喝类": "吃喝类",
    "全部": "全部",
    "all": "全部",
    "random": "全部",
}


def _default_state() -> dict[str, object]:
    return {"groups": {}, "member_to_group": {}, "draws": {}}


def _now() -> datetime:
    return datetime.now()


def _week_key(now: datetime | None = None) -> str:
    current = now or _now()
    iso = current.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _batch_id(now: datetime | None = None) -> str:
    """生成批次ID，基于周数。每周一个新批次。"""
    return _week_key(now)


def _timestamp(now: datetime | None = None) -> str:
    return (now or _now()).strftime("%Y-%m-%d %H:%M:%S")


def _safe_json_dump(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_json_load(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _message_components(event: AstrMessageEvent) -> list[BaseMessageComponent]:
    message_obj = getattr(event, "message_obj", None)
    message = getattr(message_obj, "message", None)
    return message if isinstance(message, list) else []


def _extract_message_text_and_images(event: AstrMessageEvent) -> tuple[str, list[str], list[dict[str, str]]]:
    text_parts: list[str] = []
    image_urls: list[str] = []
    images: list[dict[str, str]] = []

    for component in _message_components(event):
        if isinstance(component, Plain):
            text = str(getattr(component, "text", "")).strip()
            if text:
                text_parts.append(text)
        elif isinstance(component, Image):
            file_value = str(getattr(component, "file", "") or "").strip()
            url_value = str(getattr(component, "url", "") or "").strip()
            path_value = str(getattr(component, "path", "") or "").strip()
            image_entry = {"file": file_value, "url": url_value, "path": path_value}
            images.append(image_entry)
            image_url = url_value or file_value or path_value
            if image_url:
                image_urls.append(image_url)

    text = " ".join(text_parts).strip()
    return text, image_urls, images


def _message_mentions_bot(event: AstrMessageEvent) -> bool:
    if bool(getattr(event, "is_at_or_wake_command", False)):
        return True

    message_obj = getattr(event, "message_obj", None)
    self_id = str(getattr(message_obj, "self_id", "") or "").strip()
    if not self_id:
        return False

    for component in _message_components(event):
        if isinstance(component, At) and str(getattr(component, "qq", "")).strip() in {self_id, "all"}:
            return True
    return False


def _message_starts_with_bot_at(event: AstrMessageEvent) -> bool:
    """判断消息的第一个非 Plain 组件是否为 @ 机器人（更严格的触发条件）。

    仅当消息以 @ 机器人 开头时返回 True，避免在对话中间随便 @ 就触发提交。
    """
    message_obj = getattr(event, "message_obj", None)
    self_id = str(getattr(message_obj, "self_id", "") or "").strip()
    if not self_id:
        return False

    for component in _message_components(event):
        if isinstance(component, Plain):
            # 忽略开头的纯文本空白
            text = str(getattr(component, "text", "") or "").strip()
            if text:
                # 开头是文本，非 @
                return False
            continue
        if isinstance(component, At):
            qq = str(getattr(component, "qq", "") or "").strip()
            return qq in {self_id, "all"}
        # 其他组件（如图片、回复等）视为未以 @ 开头
        return False
    return False


def _split_tokens(raw_message: str) -> list[str]:
    try:
        return shlex.split(raw_message)
    except ValueError:
        return raw_message.split()


def _strip_root_command(tokens: list[str]) -> list[str]:
    if tokens and tokens[0].lstrip("/").lower() == "blindbox":
        return tokens[1:]
    return tokens


def _normalize_category(raw_category: str) -> str:
    return CATEGORY_ALIASES.get(raw_category.strip(), raw_category.strip())


def _normalize_tasks(raw_tasks: object) -> list[dict[str, object]]:
    tasks: list[dict[str, object]] = []
    # 支持从字符串（JSON）或包含 tasks 键的 dict 中恢复任务列表
    if isinstance(raw_tasks, str):
        try:
            parsed = json.loads(raw_tasks)
            raw_tasks = parsed
        except Exception:  # noqa: BLE001
            return tasks
    if isinstance(raw_tasks, dict) and "tasks" in raw_tasks:
        raw_tasks = raw_tasks.get("tasks")
    if not isinstance(raw_tasks, list):
        return tasks

    for item in raw_tasks:
        if not isinstance(item, dict):
            continue

        category = str(item.get("category", "")).strip()
        title = str(item.get("title", "")).strip()
        try:
            points = int(item.get("points", 0))
        except (TypeError, ValueError):
            points = 0
        enabled = bool(item.get("enabled", True))

        if category and title:
            tasks.append({"category": category, "title": title, "points": points, "enabled": enabled})

    return tasks


def _pick_task(
    category: str, tasks: list[dict[str, object]], exclude_task: dict[str, object] | None = None
) -> dict[str, object]:
    active_tasks = [task for task in tasks if task.get("enabled", True)]
    if category == "全部":
        active_tasks = [task for task in active_tasks if task["category"] in TASK_CATEGORIES]
    else:
        active_tasks = [task for task in active_tasks if task["category"] == category]

    # 排除上一次抽到的任务，确保每次抽的内容不同
    if exclude_task and isinstance(exclude_task, dict):
        exclude_title = str(exclude_task.get("title", "")).strip()
        exclude_category = str(exclude_task.get("category", "")).strip()
        active_tasks = [
            task
            for task in active_tasks
            if not (str(task.get("title", "")).strip() == exclude_title and str(task.get("category", "")).strip() == exclude_category)
        ]

    if not active_tasks:
        raise ValueError("没有可用的盲盒任务，请先在插件配置里添加任务。")
    return choice(active_tasks)


def _unique_strings(values: object) -> list[str]:
    if isinstance(values, str):
        tokens = [values]
    elif isinstance(values, list):
        tokens = values
    else:
        return []

    result: list[str] = []
    for value in tokens:
        item = str(value).strip()
        if item and item not in result:
            result.append(item)
    return result


def _parse_qq_list(value: object) -> list[str]:
    if isinstance(value, list):
        return _unique_strings(value)
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace("\n", ",").replace(" ", ",").split(",")]
        return [part for part in parts if part]
    return []


def _format_task(task: dict[str, object], rules_text: str) -> str:
    base_text = rules_text.strip() or DEFAULT_RULES_TEXT
    return (
        "【南京大学行知×开甲 学习小组 · 抽奖盲盒】\n"
        f"本次抽到：{task['category']} - {task['title']}\n"
        f"建议积分：{task['points']} 分\n\n"
        "具体规则：\n"
        f"{base_text}\n\n"
        "发送 /blindbox 学习、/blindbox 体育、/blindbox 交流、/blindbox 吃喝 或 /blindbox 全部 可再次抽取。"
    )


def _format_help() -> str:
    return (
        "【BlindBox 小组管理】\n"
        "盲盒抽取：/blindbox 或 /blindbox 学习 / 体育 / 交流 / 吃喝 / 全部\n"
        "小组创建：/blindbox group create <序号> <组名> <第一个QQ是组长> [QQ号...]\n"
        "添加成员：/blindbox group add <序号> <QQ号...>\n"
        "移除成员：/blindbox group remove <序号> <QQ号...>\n"
        "转让组长：/blindbox group transfer <序号> <新组长QQ>\n"
        "申请解散：/blindbox group request-dissolve <序号>\n"
        "取消解散：/blindbox group request-cancel <序号>\n"
        "提交任务：/blindbox submit <任务说明>\n"
        "说明：仅支持使用命令 `/blindbox submit <任务说明>` 来提交材料，命令会自动识别消息中的文字与图片并创建待审核记录。\n"
        "在群里直接 @ 机器人不会触发提交。\n"
        "查看小组：/blindbox group info <序号>\n"
        "小组列表：/blindbox group list\n"
        "我的小组：/blindbox me\n"
        "重抽任务：/blindbox redraw [学习|体育|交流|吃喝|全部]\n\n"
        "提示：群里每个 QQ 号只能属于一个小组。"
    )


# ----------------------------
# AstrBot 插件主体
# ----------------------------
@register(PLUGIN_NAME, "YourName", "南京大学行知×开甲学习小组抽奖盲盒", "0.5.0")
class BlindBoxPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self._state_lock = asyncio.Lock()
        self._state_loaded = False
        self._state: dict[str, object] = _default_state()
        self._register_web_apis(context)

    def _register_web_apis(self, context: Context) -> None:
        # 这里统一暴露给 WebUI 和外部 AI 调用的接口。
        context.register_web_api(f"/{PLUGIN_NAME}/state", self.api_state, ["GET"], "BlindBox 状态")
        context.register_web_api(f"/{PLUGIN_NAME}/ai/context", self.api_ai_context, ["GET"], "AI 小组上下文")
        context.register_web_api(f"/{PLUGIN_NAME}/ai/groups", self.api_ai_groups, ["GET"], "AI 小组列表")
        context.register_web_api(f"/{PLUGIN_NAME}/ai/submissions", self.api_ai_submissions, ["GET"], "AI 提交记录")
        context.register_web_api(f"/{PLUGIN_NAME}/ai/review", self.api_ai_review, ["POST"], "AI 审核提交")
        context.register_web_api(f"/{PLUGIN_NAME}/ai/prompt", self.api_ai_prompt, ["GET"], "AI 系统提示词")
        context.register_web_api(f"/{PLUGIN_NAME}/submit", self.api_submit, ["POST"], "提交小组任务材料")
        context.register_web_api(
            f"/{PLUGIN_NAME}/group/export-submissions",
            self.api_group_export_submissions,
            ["POST"],
            "导出小组提交记录",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/group/export-submissions-csv",
            self.api_group_export_submissions_csv,
            ["POST"],
            "导出小组提交记录为CSV",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/group/export-submissions-all-csv",
            self.api_group_export_all_submissions_csv,
            ["POST"],
            "导出全部小组提交记录为CSV",
        )
        context.register_web_api(f"/{PLUGIN_NAME}/group/create", self.api_group_create, ["POST"], "创建小组")
        context.register_web_api(f"/{PLUGIN_NAME}/group/add", self.api_group_add, ["POST"], "添加成员")
        context.register_web_api(f"/{PLUGIN_NAME}/group/remove", self.api_group_remove, ["POST"], "移除成员")
        context.register_web_api(
            f"/{PLUGIN_NAME}/group/transfer-leader",
            self.api_group_transfer_leader,
            ["POST"],
            "转让组长",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/group/request-dissolve",
            self.api_group_request_dissolve,
            ["POST"],
            "申请解散小组",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/group/cancel-dissolve",
            self.api_group_cancel_dissolve,
            ["POST"],
            "取消解散申请",
        )
        context.register_web_api(f"/{PLUGIN_NAME}/group/dissolve", self.api_group_dissolve, ["POST"], "解散小组")
        context.register_web_api(f"/{PLUGIN_NAME}/group/redraw", self.api_group_redraw, ["POST"], "重抽小组任务")
        context.register_web_api(f"/{PLUGIN_NAME}/group/export-csv", self.api_group_export_csv, ["GET"], "导出小组列表为CSV")
        context.register_web_api(f"/{PLUGIN_NAME}/group/import-csv", self.api_group_import_csv, ["POST"], "从CSV导入小组列表")

    async def initialize(self):
        logger.info("astrbot_plugin_blindbox initialized")
        await self._load_state()

    # ----------------------------
    # 状态读写：KV 里保存小组、映射和抽取结果
    # ----------------------------
    async def _load_state(self) -> dict[str, object]:
        async with self._state_lock:
            stored = await self.get_kv_data(KV_STATE_KEY, None)
            normalized = self._normalize_state(stored if isinstance(stored, dict) else None)
            self._state = normalized
            self._state_loaded = True
            await self.put_kv_data(KV_STATE_KEY, self._state)
            return self._state

    async def _save_state(self) -> None:
        async with self._state_lock:
            await self.put_kv_data(KV_STATE_KEY, self._state)

    async def _get_state(self) -> dict[str, object]:
        if not self._state_loaded:
            return await self._load_state()
        return self._state

    def _normalize_state(self, raw_state: dict[str, object] | None) -> dict[str, object]:
        # 兼容旧状态，把所有结构整理成统一格式后再使用。
        if not isinstance(raw_state, dict):
            return _default_state()

        groups = raw_state.get("groups", {})
        draws = raw_state.get("draws", {})
        normalized_groups: dict[str, object] = {}
        member_to_group: dict[str, str] = {}
        normalized_draws: dict[str, object] = {}

        if isinstance(groups, dict):
            for group_no, group_data in groups.items():
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

        if isinstance(draws, dict):
            for group_no, draw_data in draws.items():
                if str(group_no) not in normalized_groups or not isinstance(draw_data, dict):
                    continue
                current_batch = _batch_id()
                last_batch = str(draw_data.get("batch_id", ""))
                # 如果是旧批次（不同周），重置计数
                if last_batch and last_batch != current_batch:
                    draw_count = 0
                else:
                    draw_count = int(draw_data.get("draw_count", 0))
                normalized_draws[str(group_no)] = {
                    "week": str(draw_data.get("week", "")),
                    "batch_id": current_batch,
                    "draw_count": draw_count,
                    "group_no": str(group_no),
                    "group_name": str(draw_data.get("group_name", "")),
                    "category": str(draw_data.get("category", "")),
                    "title": str(draw_data.get("title", "")),
                    "points": int(draw_data.get("points", 0)),
                    "drawn_at": str(draw_data.get("drawn_at", "")),
                }

        return {"groups": normalized_groups, "member_to_group": member_to_group, "draws": normalized_draws}

    def _json_ok(self, message: str = "操作成功", data: object | None = None):
        payload = {"success": True, "message": message}
        if data is not None:
            payload["data"] = data
        return jsonify(payload)

    def _json_error(self, message: str, data: object | None = None):
        payload = {"success": False, "message": message}
        if data is not None:
            payload["data"] = data
        return jsonify(payload)

    async def _get_request_json(self) -> dict[str, object]:
        payload = await request.get_json(silent=True)
        if isinstance(payload, dict):
            return payload
        return {}

    @staticmethod
    def _get_sender_id(event: AstrMessageEvent) -> str:
        # 兼容不同平台适配器的 sender 字段命名。
        sender = getattr(getattr(event, "message_obj", None), "sender", None)
        for attr in ("user_id", "qq", "id", "uid"):
            value = getattr(sender, attr, None)
            if value is not None:
                return str(value)
        raise ValueError("无法获取发送者 QQ 号。")

    @staticmethod
    def _build_group_summary(group_no: str, group_data: dict[str, object]) -> str:
        members = group_data.get("members", [])
        member_text = "、".join(str(member) for member in members) if members else "无"
        leader_qq = str(group_data.get("leader_qq", "")) or "未设置"
        request_text = "是" if group_data.get("dissolve_requested") else "否"
        score_total = int(group_data.get("score_total", 0))
        return (
            f"组序号：{group_no}\n"
            f"组名：{group_data.get('group_name', '')}\n"
            f"组长：{leader_qq}\n"
            f"累计积分：{score_total}\n"
            f"申请解散：{request_text}\n"
            f"组员：{member_text}"
        )

    def _submission_file_path(self, group_no: str) -> Path:
        # 每个小组单独一个提交文件，方便导出和人工核查。
        return SUBMISSION_DIR / f"group_{group_no}.json"

    def _legacy_submission_file_path(self, group_no: str) -> Path:
        return LEGACY_SUBMISSION_DIR / f"group_{group_no}.json"

    @staticmethod
    def _submission_record_to_csv_row(record: dict[str, object]) -> list[str]:
        task_snapshot = record.get("task_snapshot", {})
        task_snapshot_dict = task_snapshot if isinstance(task_snapshot, dict) else {}
        task_snapshot_json = json.dumps(task_snapshot_dict, ensure_ascii=False) if task_snapshot_dict else "{}"
        return [
            str(record.get("submission_id", "")),
            str(record.get("group_no", "")),
            str(record.get("group_name", "")),
            str(record.get("submitter_qq", "")),
            str(record.get("source", "")),
            str(record.get("week", "")),
            str(record.get("review_status", "pending")),
            str(record.get("review_reason", "")),
            str(record.get("reviewer", "")),
            str(record.get("reviewed_at", "")),
            str(int(record.get("awarded_points", 0))),
            str(bool(record.get("score_applied", False))),
            str(record.get("submitted_at", "")),
            str(task_snapshot_dict.get("category", "")),
            str(task_snapshot_dict.get("title", "")),
            str(task_snapshot_dict.get("points", 0)),
            "|".join(_parse_qq_list(record.get("image_urls", []))),
            str(record.get("materials_text", "")),
            task_snapshot_json,
        ]

    def _load_submission_records(self, group_no: str) -> list[dict[str, object]]:
        path = self._submission_file_path(group_no)
        legacy_path = self._legacy_submission_file_path(group_no)
        source_path = path if path.exists() else legacy_path if legacy_path.exists() else path
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
                        "source": str(record.get("source", "manual")),
                        "week": str(record.get("week", _week_key())),
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
        if source_path == legacy_path and path != legacy_path:
            _safe_json_dump(path, records)
        return records

    def _save_submission_records(self, group_no: str, records: list[dict[str, object]]) -> None:
        _safe_json_dump(self._submission_file_path(group_no), records)

    def _build_submission_record(
        self,
        group_no: str,
        group_data: dict[str, object],
        submitter_qq: str,
        materials_text: str,
        image_urls: list[str],
        images: list[dict[str, str]],
        source: str,
        draw_data: dict[str, object] | None,
    ) -> dict[str, object]:
        # 提交记录同时保留文本、图片、任务快照和审核状态。
        return {
            "submission_id": uuid4().hex,
            "group_no": group_no,
            "group_name": str(group_data.get("group_name", "")),
            "submitter_qq": submitter_qq,
            "materials_text": materials_text,
            "image_urls": image_urls,
            "images": images,
            "source": source,
            "week": _week_key(),
            "task_snapshot": draw_data if isinstance(draw_data, dict) else {},
            "review_status": "pending",
            "review_reason": "",
            "reviewer": "",
            "reviewed_at": "",
            "awarded_points": 0,
            "score_applied": False,
            "submitted_at": _timestamp(),
        }

    async def _create_submission_record(
        self,
        group_no: str,
        submitter_qq: str,
        materials_text: str,
        image_urls: list[str],
        images: list[dict[str, str]],
        source: str,
    ) -> dict[str, object]:
        # 命令提交和 @ 机器人提交都走同一个写入入口，避免数据结构分叉。
        group_data = await self._ensure_group_or_raise(group_no)
        state = await self._get_state()
        draws = state.get("draws", {})
        draw_data = draws.get(group_no) if isinstance(draws, dict) else None

        if not submitter_qq:
            raise ValueError("submitter_qq 不能为空。")
        if not self._group_has_member(group_data, submitter_qq):
            raise ValueError("提交人必须是本组成员。")

        submission = self._build_submission_record(
            group_no=group_no,
            group_data=group_data,
            submitter_qq=submitter_qq,
            materials_text=materials_text,
            image_urls=image_urls,
            images=images,
            source=source,
            draw_data=draw_data if isinstance(draw_data, dict) else None,
        )
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
        # 给 AI 的只读视图只保留审核所需字段，避免暴露无关内部状态。
        members = group_data.get("members", [])
        submissions = self._load_submission_records(group_no)
        pending_submissions = [record for record in submissions if record.get("review_status") == "pending"]
        current_task = draw_data if isinstance(draw_data, dict) else {}
        return {
            "group_no": group_no,
            "group_name": str(group_data.get("group_name", "")),
            "leader_qq": str(group_data.get("leader_qq", "")),
            "members": [str(member) for member in members] if isinstance(members, list) else [],
            "member_count": len(members) if isinstance(members, list) else 0,
            "score_total": int(group_data.get("score_total", 0)),
            "dissolve_requested": bool(group_data.get("dissolve_requested", False)),
            "current_task": current_task,
            "current_task_points": int(current_task.get("points", 0)) if isinstance(current_task, dict) else 0,
            "current_task_week": str(current_task.get("week", "")) if isinstance(current_task, dict) else "",
            "current_task_batch": str(current_task.get("batch_id", "")) if isinstance(current_task, dict) else "",
            "current_task_draw_count": int(current_task.get("draw_count", 0)) if isinstance(current_task, dict) else 0,
            "submission_count": len(submissions),
            "pending_submission_count": len(pending_submissions),
            "pending_submissions": pending_submissions,
        }
    
    def _build_ai_prompt_context(self) -> str:
        """生成给 AI 的系统提示词，包含插件功能说明。"""
        return (
            "你是南京大学行知×开甲学习小组的盲盒任务审核助手。\n\n"
            "【插件功能说明】\n"
            "- 本插件管理学习小组的'盲盒任务'机制\n"
            "- 每个小组每周可以抽取 1-3 次任务（同一批次上限 3 次）\n"
            "- 任务分为四类：学习类、体育类、交流类、吃喝类\n"
            "- 每个任务都附带建议积分\n\n"
            "【你的职责】\n"
            "1. 根据小组提交的材料和当前分配的任务进行审核\n"
            "2. 判断提交内容是否满足任务要求\n"
            "3. 作出审核决定（通过/拒绝）并可选择调整积分\n"
            "4. 提供审核意见或拒绝理由\n\n"
            "【审核建议】\n"
            "- 学习类任务：检查是否提供了实质性的学习内容或交流\n"
            "- 体育类任务：验证运动相关的证据或截图\n"
            "- 交流类任务：确认小组成员的参与和互动\n"
            "- 吃喝类任务：看小组聚餐的证明（照片/截图）\n\n"
            "【操作指令】\n"
            "/blindbox - 抽取任务\n"
            "/blindbox 学习/体育/交流/吃喝 - 指定分类抽取\n"
            "/blindbox group list - 查看所有小组\n"
            "/blindbox group info <序号> - 查看小组详情\n"
            "/blindbox submit <说明> - 提交任务材料\n\n"
            "祝审核顺利！"
        )

    def _group_has_member(self, group_data: dict[str, object], qq: str) -> bool:
        members = group_data.get("members", [])
        return isinstance(members, list) and qq in members

    def _can_modify_member(self, group_data: dict[str, object], actor_qq: str | None, target_qq: str) -> bool:
        if actor_qq is None:
            return True
        leader_qq = str(group_data.get("leader_qq", ""))
        return actor_qq == leader_qq or actor_qq == target_qq

    async def _ensure_group_or_raise(self, group_no: str) -> dict[str, object]:
        state = await self._get_state()
        groups = state.get("groups", {})
        if not isinstance(groups, dict) or group_no not in groups or not isinstance(groups[group_no], dict):
            raise ValueError(f"序号为 {group_no} 的小组不存在。")
        return groups[group_no]
    async def _find_group_by_member(self, sender_id: str) -> tuple[str | None, dict[str, object] | None]:
        state = await self._get_state()
        member_to_group = state.get("member_to_group", {})
        groups = state.get("groups", {})
        group_no = member_to_group.get(sender_id) if isinstance(member_to_group, dict) else None
        if not group_no or not isinstance(groups, dict):
            return None, None
        group_data = groups.get(str(group_no))
        if not isinstance(group_data, dict):
            return None, None
        return str(group_no), group_data

    async def _create_group(self, group_no: str, group_name: str, qq_list: list[str]) -> dict[str, object]:
        if not group_no.strip():
            raise ValueError("组序号不能为空。")
        if not group_name.strip():
            raise ValueError("组名不能为空。")
        if not qq_list:
            raise ValueError("至少要提供一个 QQ 号，第一个 QQ 号会自动作为组长。")

        state = await self._get_state()
        groups = state.setdefault("groups", {})
        member_to_group = state.setdefault("member_to_group", {})
        group_no = str(group_no).strip()

        if group_no in groups:
            raise ValueError(f"序号为 {group_no} 的小组已存在。")

        leader_qq = qq_list[0]
        members = []
        for member_id in qq_list:
            if member_id in member_to_group:
                raise ValueError(f"QQ 号 {member_id} 已经属于小组 {member_to_group[member_id]}。")
            if member_id not in members:
                members.append(member_id)

        group_data = {
            "group_no": group_no,
            "group_name": group_name.strip(),
            "leader_qq": leader_qq,
            "members": members,
            "dissolve_requested": False,
            "score_total": 0,
        }
        groups[group_no] = group_data
        for member_id in members:
            member_to_group[member_id] = group_no
        await self._save_state()
        return group_data

    async def _dissolve_group(self, group_no: str) -> dict[str, object]:
        state = await self._get_state()
        groups = state.get("groups", {})
        member_to_group = state.get("member_to_group", {})
        draws = state.get("draws", {})
        if not isinstance(groups, dict) or not isinstance(member_to_group, dict) or not isinstance(draws, dict):
            raise ValueError("小组数据异常，请重新初始化插件状态。")

        group_data = groups.pop(str(group_no), None)
        if not isinstance(group_data, dict):
            raise ValueError(f"序号为 {group_no} 的小组不存在。")

        for member_id in group_data.get("members", []):
            member_id = str(member_id)
            if member_to_group.get(member_id) == str(group_no):
                member_to_group.pop(member_id, None)
        draws.pop(str(group_no), None)
        await self._save_state()
        return group_data

    async def _remove_members(self, group_no: str, target_qqs: list[str], actor_qq: str | None = None) -> dict[str, object]:
        state = await self._get_state()
        groups = state.get("groups", {})
        member_to_group = state.get("member_to_group", {})
        draws = state.get("draws", {})
        if not isinstance(groups, dict) or not isinstance(member_to_group, dict) or not isinstance(draws, dict):
            raise ValueError("小组数据异常，请重新初始化插件状态。")

        group_data = groups.get(str(group_no))
        if not isinstance(group_data, dict):
            raise ValueError(f"序号为 {group_no} 的小组不存在。")

        removed: list[str] = []
        skipped: list[str] = []
        members = group_data.setdefault("members", [])
        leader_qq = str(group_data.get("leader_qq", ""))

        for target_qq in _unique_strings(target_qqs):
            if not self._group_has_member(group_data, target_qq):
                skipped.append(f"{target_qq}(未在组内)")
                continue
            if not self._can_modify_member(group_data, actor_qq, target_qq):
                skipped.append(f"{target_qq}(无权限)")
                continue
            members.remove(target_qq)
            if member_to_group.get(target_qq) == str(group_no):
                member_to_group.pop(target_qq, None)
            removed.append(target_qq)

        if not members:
            group_data["dissolve_requested"] = False
            groups.pop(str(group_no), None)
            draws.pop(str(group_no), None)
            await self._save_state()
            return {"dissolved": True, "removed": removed, "skipped": skipped, "group": group_data}

        if leader_qq not in members:
            new_leader = members[0]
            group_data["leader_qq"] = new_leader
        await self._save_state()
        return {"dissolved": False, "removed": removed, "skipped": skipped, "group": group_data}

    async def _set_dissolve_requested(self, group_no: str, actor_qq: str | None = None, requested: bool = True) -> dict[str, object]:
        state = await self._get_state()
        groups = state.get("groups", {})
        if not isinstance(groups, dict):
            raise ValueError("小组数据异常，请重新初始化插件状态。")

        group_data = groups.get(str(group_no))
        if not isinstance(group_data, dict):
            raise ValueError(f"序号为 {group_no} 的小组不存在。")

        if actor_qq is not None and actor_qq != str(group_data.get("leader_qq", "")):
            raise ValueError("只有组长可以申请解散该小组。")

        group_data["dissolve_requested"] = requested
        await self._save_state()
        return group_data

    async def _transfer_leader(
        self,
        group_no: str,
        new_leader_qq: str,
        actor_qq: str | None = None,
    ) -> dict[str, object]:
        state = await self._get_state()
        groups = state.get("groups", {})
        if not isinstance(groups, dict):
            raise ValueError("小组数据异常，请重新初始化插件状态。")

        group_data = groups.get(str(group_no))
        if not isinstance(group_data, dict):
            raise ValueError(f"序号为 {group_no} 的小组不存在。")

        current_leader = str(group_data.get("leader_qq", ""))
        if actor_qq is not None and actor_qq != current_leader:
            raise ValueError("只有组长可以转让组长身份。")

        new_leader_qq = str(new_leader_qq).strip()
        if not new_leader_qq:
            raise ValueError("新组长 QQ 不能为空。")
        if not self._group_has_member(group_data, new_leader_qq):
            raise ValueError("新组长必须是本组成员。")

        group_data["leader_qq"] = new_leader_qq
        group_data["dissolve_requested"] = False
        await self._save_state()
        return group_data

    async def _draw_for_group(
        self,
        group_no: str,
        category: str,
        force_redraw: bool,
        actor_qq: str | None = None,
    ) -> tuple[dict[str, object], bool, str]:
        state = await self._get_state()
        groups = state.get("groups", {})
        draws = state.setdefault("draws", {})
        if not isinstance(groups, dict) or not isinstance(draws, dict):
            raise ValueError("小组数据异常，请重新初始化插件状态。")

        group_data = groups.get(str(group_no))
        if not isinstance(group_data, dict):
            raise ValueError(f"序号为 {group_no} 的小组不存在。")

        leader_qq = str(group_data.get("leader_qq", ""))
        if actor_qq is not None and actor_qq != leader_qq:
            raise ValueError("只有组长可以抽取或重抽本组任务。")

        normalized_category = _normalize_category(category)
        if normalized_category != "全部" and normalized_category not in TASK_CATEGORIES:
            raise ValueError("可用分类只有：学习类、体育类、交流类、吃喝类、全部。")

        week = _week_key()
        current_batch = _batch_id()
        current_draw = draws.get(str(group_no))
        
        # 检查本批次是否已经抽了3次（仅在非强制重抽时检查）
        if not force_redraw and isinstance(current_draw, dict):
            if current_draw.get("week") == week and current_draw.get("batch_id") == current_batch:
                draw_count = int(current_draw.get("draw_count", 0))
                if draw_count >= 3:
                    raise ValueError(f"本批次（{current_batch}）已经抽取了 {draw_count} 次，达到上限 3 次。")
                # 本周已有任务，返回当前任务
                return current_draw, False, ""
        
        tasks = _normalize_tasks(self.config.get("tasks", DEFAULT_TASKS))
        # 排除上一次抽到的任务
        exclude_task = current_draw if isinstance(current_draw, dict) else None
        picked = _pick_task(normalized_category, tasks, exclude_task=exclude_task)
        
        # 计算新的抽取次数
        if force_redraw or not isinstance(current_draw, dict) or current_draw.get("batch_id") != current_batch:
            # 强制重抽或切换批次，重置计数
            new_draw_count = 1
        else:
            # 同批次继续抽取
            new_draw_count = int(current_draw.get("draw_count", 0)) + 1
        
        draw_data = {
            "week": week,
            "batch_id": current_batch,
            "draw_count": new_draw_count,
            "group_no": str(group_no),
            "group_name": str(group_data.get("group_name", "")),
            "category": str(picked["category"]),
            "title": str(picked["title"]),
            "points": int(picked["points"]),
            "drawn_at": _timestamp(),
        }
        draws[str(group_no)] = draw_data
        await self._save_state()
        status_msg = f"(本批次第 {new_draw_count}/3 次抽取)" if new_draw_count <= 3 else ""
        return draw_data, True, status_msg

    async def _api_result(self, handler):
        try:
            result = await handler()
            return self._json_ok(data=result if result is not None else {})
        except ValueError as exc:
            return self._json_error(str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("blindbox api error")
            return self._json_error(f"内部错误：{exc}")

    async def api_state(self):
        async def _handler():
            state = await self._get_state()
            return {
                "week": _week_key(),
                "rules_text": str(self.config.get("rules_text", DEFAULT_RULES_TEXT)),
                "tasks": _normalize_tasks(self.config.get("tasks", DEFAULT_TASKS)),
                "groups": state.get("groups", {}),
                "draws": state.get("draws", {}),
            }

        return await self._api_result(_handler)

    async def api_ai_context(self):
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
                    "week": _week_key(),
                    "groups": [
                        self._build_ai_group_context(str(current_group_no), group_data, draws.get(str(current_group_no)))
                        for current_group_no, group_data in sorted(groups.items(), key=lambda item: str(item[0]))
                        if isinstance(group_data, dict)
                    ],
                }

            raise ValueError("请提供 group_no、sender_qq 或 include_all 参数。")

        return await self._api_result(_handler)

    async def api_ai_groups(self):
        async def _handler():
            state = await self._get_state()
            groups = state.get("groups", {})
            draws = state.get("draws", {})
            if not isinstance(groups, dict) or not isinstance(draws, dict):
                raise ValueError("小组数据异常，请重新初始化插件状态。")

            return {
                "week": _week_key(),
                "groups": [
                    self._build_ai_group_context(str(group_no), group_data, draws.get(str(group_no)))
                    for group_no, group_data in sorted(groups.items(), key=lambda item: str(item[0]))
                    if isinstance(group_data, dict)
                ],
            }

        return await self._api_result(_handler)

    async def api_ai_submissions(self):
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

    async def api_group_export_submissions(self):
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()

        async def _handler():
            if not group_no:
                raise ValueError("group_no 不能为空。")

            group_data = await self._ensure_group_or_raise(group_no)
            state = await self._get_state()
            draws = state.get("draws", {})
            draw_data = draws.get(group_no) if isinstance(draws, dict) else None
            submissions = self._load_submission_records(group_no)

            export_data = {
                "exported_at": _timestamp(),
                "week": _week_key(),
                "group": self._build_ai_group_context(group_no, group_data, draw_data),
                "submissions": submissions,
            }
            return export_data

        return await self._api_result(_handler)

    async def api_group_export_submissions_csv(self):
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()

        async def _handler():
            if not group_no:
                raise ValueError("group_no 不能为空。")

            group_data = await self._ensure_group_or_raise(group_no)
            records = self._load_submission_records(group_no)

            csv_buffer = StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow([
                "submission_id",
                "group_no",
                "group_name",
                "submitter_qq",
                "source",
                "week",
                "review_status",
                "review_reason",
                "reviewer",
                "reviewed_at",
                "awarded_points",
                "score_applied",
                "submitted_at",
                "task_category",
                "task_title",
                "task_points",
                "image_urls",
                "materials_text",
                "task_snapshot_json",
            ])

            for record in records:
                if isinstance(record, dict):
                    writer.writerow(self._submission_record_to_csv_row(record))

            csv_text = csv_buffer.getvalue()
            filename = f"blindbox_group_{group_no}_submissions.csv"
            return Response(
                "\ufeff" + csv_text,
                content_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-Group-No": group_no,
                    "X-Group-Name": str(group_data.get("group_name", "")),
                    "X-Record-Count": str(len(records)),
                },
            )

        try:
            return await _handler()
        except ValueError as exc:
            return self._json_error(str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("blindbox api error")
            return self._json_error(f"内部错误：{exc}")

    async def api_group_export_all_submissions_csv(self):
        async def _handler():
            state = await self._get_state()
            groups = state.get("groups", {})
            draws = state.get("draws", {})
            if not isinstance(groups, dict):
                raise ValueError("小组数据异常，请重新初始化插件状态。")

            csv_buffer = StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow([
                "group_no",
                "group_name",
                "leader_qq",
                "submission_id",
                "submitter_qq",
                "source",
                "week",
                "review_status",
                "review_reason",
                "reviewer",
                "reviewed_at",
                "awarded_points",
                "score_applied",
                "submitted_at",
                "task_category",
                "task_title",
                "task_points",
                "image_urls",
                "materials_text",
                "task_snapshot_json",
            ])

            total_records = 0
            for group_no in sorted(groups.keys(), key=str):
                group_data = groups[group_no]
                if not isinstance(group_data, dict):
                    continue
                group_no_str = str(group_no)
                submissions = self._load_submission_records(group_no_str)
                _ = draws.get(group_no_str) if isinstance(draws, dict) else None
                for record in submissions:
                    if not isinstance(record, dict):
                        continue
                    task_snapshot = record.get("task_snapshot", {})
                    task_snapshot_dict = task_snapshot if isinstance(task_snapshot, dict) else {}
                    writer.writerow([
                        group_no_str,
                        str(group_data.get("group_name", "")),
                        str(group_data.get("leader_qq", "")),
                        str(record.get("submission_id", "")),
                        str(record.get("submitter_qq", "")),
                        str(record.get("source", "")),
                        str(record.get("week", "")),
                        str(record.get("review_status", "pending")),
                        str(record.get("review_reason", "")),
                        str(record.get("reviewer", "")),
                        str(record.get("reviewed_at", "")),
                        str(int(record.get("awarded_points", 0))),
                        str(bool(record.get("score_applied", False))),
                        str(record.get("submitted_at", "")),
                        str(task_snapshot_dict.get("category", "")),
                        str(task_snapshot_dict.get("title", "")),
                        str(task_snapshot_dict.get("points", 0)),
                        "|".join(_parse_qq_list(record.get("image_urls", []))),
                        str(record.get("materials_text", "")),
                        json.dumps(task_snapshot_dict, ensure_ascii=False) if task_snapshot_dict else "{}",
                    ])
                    total_records += 1

            filename = f"blindbox_all_groups_submissions_{_week_key()}.csv"
            return Response(
                "\ufeff" + csv_buffer.getvalue(),
                content_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-Record-Count": str(total_records),
                },
            )

        try:
            return await _handler()
        except ValueError as exc:
            return self._json_error(str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("blindbox api error")
            return self._json_error(f"内部错误：{exc}")

    async def api_ai_review(self):
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
                    "reviewed_at": _timestamp(),
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

    async def api_submit(self):
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
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        group_name = str(payload.get("group_name", "")).strip()
        qq_list = _parse_qq_list(payload.get("qq_list", []))

        async def _handler():
            return await self._create_group(group_no, group_name, qq_list)

        return await self._api_result(_handler)

    async def api_group_add(self):
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        qq_list = _parse_qq_list(payload.get("qq_list", []))
        actor_qq = str(payload.get("actor_qq", "")).strip() or None

        async def _handler():
            group_data = await self._ensure_group_or_raise(group_no)
            added_result = await self._add_members_to_group(group_no, qq_list, actor_qq=actor_qq)
            return {"group": group_data, **added_result}

        return await self._api_result(_handler)

    async def api_group_remove(self):
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        qq_list = _parse_qq_list(payload.get("qq_list", []))
        actor_qq = str(payload.get("actor_qq", "")).strip() or None

        async def _handler():
            group_data = await self._ensure_group_or_raise(group_no)
            removed_result = await self._remove_members(group_no, qq_list, actor_qq=actor_qq)
            removed_result["group_name"] = group_data.get("group_name", "")
            return removed_result

        return await self._api_result(_handler)

    async def api_group_request_dissolve(self):
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        actor_qq = str(payload.get("actor_qq", "")).strip() or None

        async def _handler():
            group_data = await self._set_dissolve_requested(group_no, actor_qq=actor_qq, requested=True)
            return group_data

        return await self._api_result(_handler)

    async def api_group_cancel_dissolve(self):
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        actor_qq = str(payload.get("actor_qq", "")).strip() or None

        async def _handler():
            group_data = await self._set_dissolve_requested(group_no, actor_qq=actor_qq, requested=False)
            return group_data

        return await self._api_result(_handler)

    async def api_group_transfer_leader(self):
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        new_leader_qq = str(payload.get("new_leader_qq", "")).strip()
        actor_qq = str(payload.get("actor_qq", "")).strip() or None

        async def _handler():
            return await self._transfer_leader(group_no, new_leader_qq, actor_qq=actor_qq)

        return await self._api_result(_handler)

    async def api_group_dissolve(self):
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()

        async def _handler():
            group_data = await self._dissolve_group(group_no)
            return group_data

        return await self._api_result(_handler)

    async def api_group_redraw(self):
        payload = await self._get_request_json()
        group_no = str(payload.get("group_no", "")).strip()
        category = str(payload.get("category", "全部")).strip() or "全部"
        force_redraw = bool(payload.get("force_redraw", True))
        actor_qq = str(payload.get("actor_qq", "")).strip() or None

        async def _handler():
            draw_data, created_new, status_msg = await self._draw_for_group(group_no, category, force_redraw, actor_qq=actor_qq)
            draw_data["created_new"] = created_new
            draw_data["status_message"] = status_msg
            return draw_data

        return await self._api_result(_handler)
    
    async def api_ai_prompt(self):
        """返回给 AI 的系统提示词。"""
        async def _handler():
            return {"prompt": self._build_ai_prompt_context()}
        return await self._api_result(_handler)
    
    async def api_group_export_csv(self):
        """导出小组列表为 CSV 格式。"""
        async def _handler():
            state = await self._get_state()
            groups = state.get("groups", {})
            if not isinstance(groups, dict):
                raise ValueError("小组数据异常，请重新初始化插件状态。")
            
            # 生成 CSV
            csv_buffer = StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(["序号", "组名", "组长QQ", "成员QQ列表"])
            
            for group_no in sorted(groups.keys(), key=str):
                group_data = groups[group_no]
                if not isinstance(group_data, dict):
                    continue
                group_no_str = str(group_no)
                group_name = str(group_data.get("group_name", ""))
                leader_qq = str(group_data.get("leader_qq", ""))
                members = group_data.get("members", [])
                members_str = ",".join(str(m) for m in members) if isinstance(members, list) else ""
                
                writer.writerow([group_no_str, group_name, leader_qq, members_str])
            
            csv_content = csv_buffer.getvalue()
            return {"csv": csv_content, "filename": "blindbox_groups.csv"}
        
        return await self._api_result(_handler)
    
    async def api_group_import_csv(self):
        """从 CSV 导入小组列表。覆盖已有小组。"""
        payload = await self._get_request_json()
        csv_content = str(payload.get("csv", "")).strip()
        
        async def _handler():
            if not csv_content:
                raise ValueError("CSV 内容不能为空。")
            
            # 解析 CSV
            csv_buffer = StringIO(csv_content)
            reader = csv.DictReader(csv_buffer)
            rows = list(reader)
            
            if not rows:
                raise ValueError("CSV 文件为空或格式错误。")
            
            state = await self._get_state()
            groups = state.setdefault("groups", {})
            member_to_group = state.setdefault("member_to_group", {})
            
            # 先清空现有映射（仅清除 CSV 中提到的小组对应的成员）
            new_groups: dict[str, object] = {}
            new_member_to_group: dict[str, str] = {}
            
            # 处理 CSV 中的每一行
            import_count = 0
            errors: list[str] = []
            
            for row in rows:
                group_no = str(row.get("序号", "")).strip()
                group_name = str(row.get("组名", "")).strip()
                leader_qq = str(row.get("组长QQ", "")).strip()
                members_str = str(row.get("成员QQ列表", "")).strip()
                
                if not group_no or not group_name or not leader_qq:
                    errors.append(f"行 {row} 缺少必要字段（序号/组名/组长QQ）。")
                    continue
                
                # 解析成员列表
                members = [m.strip() for m in members_str.split(",") if m.strip()] if members_str else []
                
                # 确保组长在成员列表中
                if leader_qq not in members:
                    members.insert(0, leader_qq)
                
                group_data = {
                    "group_no": group_no,
                    "group_name": group_name,
                    "leader_qq": leader_qq,
                    "members": members,
                    "dissolve_requested": False,
                    "score_total": 0,
                }
                new_groups[group_no] = group_data
                
                for member in members:
                    new_member_to_group[member] = group_no
                
                import_count += 1
            
            # 更新状态：只替换涉及的小组，保留其他小组
            for group_no in list(groups.keys()):
                if group_no not in new_groups:
                    # 保留原有的其他小组
                    new_groups[group_no] = groups[group_no]
                    members = groups[group_no].get("members", [])
                    if isinstance(members, list):
                        for member in members:
                            new_member_to_group[member] = group_no
            
            state["groups"] = new_groups
            state["member_to_group"] = new_member_to_group
            await self._save_state()
            
            result = {
                "success": True,
                "import_count": import_count,
                "errors": errors,
                "message": f"成功导入 {import_count} 个小组。"
            }
            if errors:
                result["message"] += f"有 {len(errors)} 行出错。"
            return result
        
        return await self._api_result(_handler)

    # ----------------------------
    # 群消息命令入口
    # ----------------------------
    async def _add_members_to_group(self, group_no: str, target_qqs: list[str], actor_qq: str | None = None) -> dict[str, object]:
        state = await self._get_state()
        groups = state.get("groups", {})
        member_to_group = state.get("member_to_group", {})
        if not isinstance(groups, dict) or not isinstance(member_to_group, dict):
            raise ValueError("小组数据异常，请重新初始化插件状态。")

        group_data = groups.get(str(group_no))
        if not isinstance(group_data, dict):
            raise ValueError(f"序号为 {group_no} 的小组不存在。")

        added: list[str] = []
        skipped: list[str] = []
        members = group_data.setdefault("members", [])
        leader_qq = str(group_data.get("leader_qq", ""))

        for target_qq in _unique_strings(target_qqs):
            if not self._can_modify_member(group_data, actor_qq, target_qq):
                skipped.append(f"{target_qq}(无权限)")
                continue
            existing_group = member_to_group.get(target_qq)
            if existing_group and str(existing_group) != str(group_no):
                skipped.append(f"{target_qq}(已在 {existing_group})")
                continue
            if target_qq not in members:
                members.append(target_qq)
                added.append(target_qq)
            member_to_group[target_qq] = str(group_no)

        if leader_qq and leader_qq not in members:
            members.insert(0, leader_qq)
            member_to_group[leader_qq] = str(group_no)

        await self._save_state()
        return {"added": added, "skipped": skipped, "group": group_data}

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
            if isinstance(current_draw, dict) and current_draw.get("week") == _week_key():
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
                group_data = await self._create_group(group_no, group_name, qq_list)
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

            result = await self._remove_members(group_no, target_qqs, actor_qq=sender_id)
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
            group_data = groups.get(group_no)
            if not isinstance(group_data, dict):
                yield event.plain_result(f"序号为 {group_no} 的小组不存在。")
                return
            if sender_id != str(group_data.get("leader_qq", "")):
                yield event.plain_result("只有组长可以申请解散该小组。")
                return

            group_data["dissolve_requested"] = True
            await self._save_state()
            yield event.plain_result(f"已为小组 {group_no} 标记解散申请。")
            return

        if action == "request-cancel":
            if len(args) < 2:
                yield event.plain_result("用法：/blindbox group request-cancel <序号>")
                return

            group_no = str(args[1]).strip()
            group_data = groups.get(group_no)
            if not isinstance(group_data, dict):
                yield event.plain_result(f"序号为 {group_no} 的小组不存在。")
                return
            if sender_id != str(group_data.get("leader_qq", "")):
                yield event.plain_result("只有组长可以取消解散申请。")
                return

            group_data["dissolve_requested"] = False
            await self._save_state()
            yield event.plain_result(f"已取消小组 {group_no} 的解散申请。")
            return

        if action == "transfer":
            if len(args) < 3:
                yield event.plain_result("用法：/blindbox group transfer <序号> <新组长QQ>")
                return

            group_no = str(args[1]).strip()
            new_leader_qq = str(args[2]).strip()
            try:
                group_data = await self._transfer_leader(group_no, new_leader_qq, actor_qq=sender_id)
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

        yield event.plain_result(_format_help())

    async def _handle_draw(self, event: AstrMessageEvent, args: list[str], force_redraw: bool = False):
        sender_id = self._get_sender_id(event)
        group_no, group_data = await self._find_group_by_member(sender_id)
        if not group_no or not group_data:
            yield event.plain_result(f"QQ 号 {sender_id} 还没有绑定到任何小组。请先使用 /blindbox group create 或 /blindbox group add。")
            return

        category = args[0] if args else "全部"
        draw_data, created_new, status_msg = await self._draw_for_group(group_no, category, force_redraw, actor_qq=sender_id)
        rules_text = str(self.config.get("rules_text", DEFAULT_RULES_TEXT))
        task = {
            "category": draw_data.get("category", ""),
            "title": draw_data.get("title", ""),
            "points": draw_data.get("points", 0),
        }

        lines = [
            _format_task(task, rules_text),
            "",
            f"当前小组：{group_no} - {group_data.get('group_name', '')}",
            f"组长：{group_data.get('leader_qq', '')}",
            f"本周抽取状态：{draw_data.get('week', '')}",
        ]
        if status_msg:
            lines.append(status_msg)
        if force_redraw:
            lines.append("本次操作：重抽并覆盖本周任务")
        elif not created_new:
            lines.append("本周已存在任务，返回当前任务；如需更换请使用 /blindbox redraw。")
        yield event.plain_result("\n".join(lines))

    async def _handle_whoami(self, event: AstrMessageEvent):
        sender_id = self._get_sender_id(event)
        group_no, group_data = await self._find_group_by_member(sender_id)
        if not group_no or not group_data:
            yield event.plain_result(f"QQ 号 {sender_id} 还没有绑定到任何小组。")
            return

        yield event.plain_result(
            "【我的小组】\n"
            f"QQ 号：{sender_id}\n"
            f"{self._build_group_summary(group_no, group_data)}"
        )

    async def _handle_submit(self, event: AstrMessageEvent, args: list[str]):
        sender_id = self._get_sender_id(event)
        group_no, group_data = await self._find_group_by_member(sender_id)
        if not group_no or not group_data:
            yield event.plain_result(f"QQ 号 {sender_id} 还没有绑定到任何小组。")
            return

        if not args:
            yield event.plain_result("用法：/blindbox submit <任务说明>")
            return

        materials_text = " ".join(args).strip()
        submission = await self._create_submission_record(
            group_no=group_no,
            submitter_qq=sender_id,
            materials_text=materials_text,
            image_urls=[],
            images=[],
            source="command",
        )

        yield event.plain_result(
            "\n".join(
                [
                    "已提交任务材料，等待 AI 审核。",
                    f"提交编号：{submission['submission_id']}",
                    f"当前小组：{group_no} / {group_data.get('group_name', '')}",
                    f"本次关联任务：{submission['task_snapshot'].get('title', '暂无任务') if isinstance(submission['task_snapshot'], dict) else '暂无任务'}",
                ]
            )
        )

    async def _handle_at_submission(self, event: AstrMessageEvent):
        # @ 机器人提交功能已被移除：不再处理通过 @ 发来的消息作为提交。
        # 仅接受命令形式 `/blindbox submit <任务说明>` 来创建提交记录，命令将自动识别消息中的文字与图片。
        return

    @filter.command("blindbox")
    async def blindbox(self, event: AstrMessageEvent):
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
            async for result in self._handle_group_command(event, tokens[1:]):
                yield result
            return

        if head in {"draw", "抽取", "抽奖"}:
            async for result in self._handle_draw(event, tokens[1:], force_redraw=False):
                yield result
            return

        if head in {"redraw", "reroll", "重抽", "重抽取"}:
            async for result in self._handle_draw(event, tokens[1:], force_redraw=True):
                yield result
            return

        if head in {"me", "mine", "whoami", "我是谁", "我的组"}:
            async for result in self._handle_whoami(event):
                yield result
            return

        if head in {"submit", "submit-task", "提交", "交付"}:
            async for result in self._handle_submit(event, tokens[1:]):
                yield result
            return

        if _normalize_category(tokens[0]) in TASK_CATEGORIES or _normalize_category(tokens[0]) == "全部":
            async for result in self._handle_draw(event, [tokens[0]], force_redraw=False):
                yield result
            return

        yield event.plain_result(_format_help())

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=-1)
    async def track_group_member(self, event: AstrMessageEvent):
        # 低优先级日志监听，只记录消息归属，不改变业务状态。
        try:
            sender_id = self._get_sender_id(event)
        except ValueError:
            return

        group_no, group_data = await self._find_group_by_member(sender_id)
        if group_no and group_data:
            logger.info("blindbox message matched group: sender=%s group=%s(%s)", sender_id, group_no, group_data.get("group_name", ""))

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=0)
    async def handle_at_submission(self, event: AstrMessageEvent):
        # @ 提交已禁用，保持空处理以避免误触发
        return

    async def terminate(self):
        logger.info("astrbot_plugin_blindbox terminated")
