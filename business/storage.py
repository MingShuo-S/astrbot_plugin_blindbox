"""
存储和状态管理模块
"""

import json
from pathlib import Path
from typing import Any

from astrbot.api import logger

from config import CATEGORY_ALIASES, default_state


def safe_json_dump(path: Path, data: object) -> None:
    """安全地写入 JSON 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_json_load(path: Path, default: object) -> object:
    """安全地读取 JSON 文件"""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def normalize_category(raw_category: str) -> str:
    """规范化分类名称"""
    return CATEGORY_ALIASES.get(raw_category.strip(), raw_category.strip())


def parse_bool(value: object) -> bool:
    """解析布尔值"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def parse_qq_list(value: object) -> list[str]:
    """解析 QQ 号列表"""
    if isinstance(value, list):
        return [str(qq).strip() for qq in value if str(qq).strip()]
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        # 支持多种分隔符：逗号、竖线、空格、分号
        for sep in [",", "|", " ", ";"]:
            if sep in value:
                return [qq.strip() for qq in value.split(sep) if qq.strip()]
        return [value] if value else []
    return []


def unique_strings(values: object) -> list[str]:
    """获取唯一的字符串列表"""
    seen = set()
    result = []
    items = values if isinstance(values, list) else []
    for item in items:
        s = str(item).strip()
        if s and s not in seen:
            seen.add(s)
            result.append(s)
    return result


def normalize_tasks(raw_tasks: object) -> list[dict[str, object]]:
    """规范化任务列表"""
    tasks: list[dict[str, object]] = []

    # 支持从字符串（JSON）或包含 tasks 键的 dict 中恢复任务列表
    if isinstance(raw_tasks, str):
        try:
            parsed = json.loads(raw_tasks)
            raw_tasks = parsed
        except Exception:
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
        description = str(item.get("description", "")).strip()

        if category and title:
            normalized_category = normalize_category(category)
            task_entry = {
                "category": normalized_category,
                "title": title,
                "points": points,
                "enabled": enabled,
            }
            if description:
                task_entry["description"] = description
            tasks.append(task_entry)

    return tasks


def task_categories(tasks: list[dict[str, object]]) -> list[str]:
    """获取任务的所有分类"""
    categories = set()
    for task in tasks:
        category = str(task.get("category", "")).strip()
        if category:
            categories.add(category)
    return sorted(list(categories))


def normalize_state(raw_state: dict[str, object] | None) -> dict[str, object]:
    """规范化状态数据结构"""
    from datetime import datetime

    from config import batch_id, week_key

    if not isinstance(raw_state, dict):
        return default_state()

    groups = raw_state.get("groups", {})
    draws = raw_state.get("draws", {})
    pending_selections = raw_state.get("pending_selections", {})
    normalized_groups: dict[str, object] = {}
    member_to_group: dict[str, str] = {}
    normalized_draws: dict[str, object] = {}
    normalized_selections: dict[str, object] = {}

    if isinstance(groups, dict):
        for group_no, group_data in groups.items():
            if not isinstance(group_data, dict):
                continue

            members = unique_strings(group_data.get("members", []))
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
            current_batch = batch_id()
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
            if "description" in draw_data:
                normalized_draws[str(group_no)]["description"] = str(draw_data.get("description", ""))

    # 清理过期的待选择记录（超过5分钟）
    if isinstance(pending_selections, dict):
        from config import now

        current_time = now()
        for selection_id, selection_data in pending_selections.items():
            if isinstance(selection_data, dict):
                created_at_str = str(selection_data.get("created_at", ""))
                try:
                    created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
                    if (current_time - created_at).total_seconds() <= 300:  # 5分钟内有效
                        normalized_selections[selection_id] = selection_data
                except Exception:
                    pass

    tasks = raw_state.get("tasks", []) if isinstance(raw_state, dict) else []
    normalized_tasks = normalize_tasks(tasks) if isinstance(tasks, list) else []
    return {
        "groups": normalized_groups,
        "member_to_group": member_to_group,
        "draws": normalized_draws,
        "pending_selections": normalized_selections,
        "tasks": normalized_tasks,
    }
