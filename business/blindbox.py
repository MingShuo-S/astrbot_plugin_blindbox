"""
盲盒任务抽取和选择模块
"""

from datetime import datetime
from random import sample

from ..config import batch_id, gen_uuid, now, timestamp, week_key

from .storage import normalize_category, task_categories, unique_strings


def pick_task(
    category: str, tasks: list[dict[str, object]], exclude_task: dict[str, object] | None = None
) -> dict[str, object]:
    """随机选择一个任务"""
    active_tasks = [task for task in tasks if task.get("enabled", True)]
    if category == "全部":
        active_tasks = [task for task in active_tasks if str(task.get("category", "")).strip()]
    else:
        active_tasks = [task for task in active_tasks if str(task.get("category", "")).strip() == category]

    # 排除上一次抽到的任务
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

    return active_tasks[0] if len(active_tasks) == 1 else active_tasks[0]


async def pick_three_tasks(
    category: str,
    tasks: list[dict[str, object]],
    exclude_task: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    """随机选择3个不同的任务供用户选择"""
    active_tasks = [task for task in tasks if task.get("enabled", True)]
    if category == "全部":
        active_tasks = [task for task in active_tasks if str(task.get("category", "")).strip()]
    else:
        active_tasks = [task for task in active_tasks if str(task.get("category", "")).strip() == category]

    # 排除上一次抽到的任务
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

    # 随机选择3个任务（或更少，如果可用任务不足3个）
    count = min(3, len(active_tasks))
    return sample(active_tasks, count)


async def draw_for_group(
    state: dict[str, object],
    group_no: str,
    category: str,
    force_redraw: bool,
    tasks: list[dict[str, object]],
    actor_qq: str | None = None,
) -> tuple[list[dict[str, object]], bool, str, str]:
    """抽盲盒：返回3个任务选项供用户选择"""
    groups = state.get("groups", {})
    draws = state.setdefault("draws", {})
    if not isinstance(groups, dict) or not isinstance(draws, dict):
        raise ValueError("小组数据异常，请重新初始化插件状态。")

    group_data = groups.get(str(group_no))
    if not isinstance(group_data, dict):
        raise ValueError(f"序号为 {group_no} 的小组不存在。")

    from .group import group_has_member

    if actor_qq is not None and not group_has_member(group_data, actor_qq):
        raise ValueError("仅本组成员可以抽取本组任务。")

    normalized_category = normalize_category(category)
    available_categories = task_categories(tasks)
    if normalized_category != "全部" and normalized_category not in available_categories:
        raise ValueError(
            "可用分类只有：全部，或盲盒清单中已定义的类别。"
            + (f" 当前可用分类：{', '.join(available_categories)}" if available_categories else " 请先导入任务列表。")
        )

    current_batch = batch_id()
    current_draw = draws.get(str(group_no))

    # 检查本周是否已经有未完成的任务
    if not force_redraw and isinstance(current_draw, dict):
        if current_draw.get("batch_id") == current_batch:
            raise ValueError("本周已经抽取过任务了，请先提交当前任务，或使用 /blindbox redraw 强制重抽。")

    # 排除上一次抽到的任务
    exclude_task = current_draw if isinstance(current_draw, dict) else None
    picked_tasks = await pick_three_tasks(normalized_category, tasks, exclude_task=exclude_task)

    # 生成临时选择ID和三个任务选项
    selection_id = gen_uuid()
    selection_data = {
        "group_no": str(group_no),
        "category": normalized_category,
        "tasks": picked_tasks,
        "created_at": timestamp(),
    }

    # 保存待选择状态
    pending_selections = state.setdefault("pending_selections", {})
    pending_selections[selection_id] = selection_data

    status_msg = "请选择任务：回复 1/2/3"
    return picked_tasks, True, status_msg, selection_id


async def confirm_selection(
    state: dict[str, object],
    group_no: str,
    selection_id: str,
    choice: int,
    actor_qq: str | None = None,
) -> dict[str, object]:
    """用户选择任务后，确认并保存任务"""
    if choice not in {1, 2, 3}:
        raise ValueError("请选择 1/2/3")

    pending_selections = state.get("pending_selections", {})

    if selection_id not in pending_selections:
        raise ValueError("选择已过期，请重新抽取。")

    selection_data = pending_selections[selection_id]
    if str(selection_data.get("group_no")) != str(group_no):
        raise ValueError("选择ID与小组不匹配。")

    tasks = selection_data.get("tasks", [])
    if not tasks or choice > len(tasks):
        raise ValueError("选择无效。")

    selected_task = tasks[choice - 1]

    groups = state.get("groups", {})
    draws = state.setdefault("draws", {})

    group_data = groups.get(str(group_no))
    if not isinstance(group_data, dict):
        raise ValueError(f"序号为 {group_no} 的小组不存在。")

    current_batch = batch_id()

    draw_data = {
        "week": week_key(),
        "batch_id": current_batch,
        "draw_count": 1,
        "group_no": str(group_no),
        "group_name": str(group_data.get("group_name", "")),
        "category": str(selected_task["category"]),
        "title": str(selected_task["title"]),
        "points": int(selected_task["points"]),
        "drawn_at": timestamp(),
    }
    if "description" in selected_task:
        draw_data["description"] = str(selected_task["description"])

    draws[str(group_no)] = draw_data

    # 清除选择状态
    del pending_selections[selection_id]

    return draw_data


def can_draw_again(draw_data: dict[str, object] | None, records: list[dict[str, object]]) -> tuple[bool, str]:
    """检查是否可以抽新任务
    
    返回：(是否可以, 原因消息)
    """
    if not draw_data or not isinstance(draw_data, dict):
        return True, ""

    # 检查是否已提交过该任务（任何已审核的提交）
    for record in records:
        if isinstance(record, dict):
            task_snapshot = record.get("task_snapshot", {})
            if isinstance(task_snapshot, dict):
                record_task_title = task_snapshot.get("title", "")
                draw_task_title = draw_data.get("title", "")
                if record_task_title == draw_task_title:
                    # 如果提交已通过或已拒绝（已审核），则可以重新抽
                    review_status = record.get("review_status", "")
                    if review_status in {"approved", "rejected"}:
                        return True, "上周任务已完成，可以抽取新任务"
                    elif review_status == "pending":
                        return False, "上周任务仍在审核中，请等待审核结果"

    # 检查是否超过一周（7天）
    drawn_at_str = draw_data.get("drawn_at", "")
    if drawn_at_str:
        try:
            drawn_at = datetime.strptime(drawn_at_str, "%Y-%m-%d %H:%M:%S")
            time_elapsed = now() - drawn_at
            if time_elapsed.total_seconds() > 7 * 24 * 3600:  # 7天
                return True, "任务已超期，可以抽取新任务"
        except Exception:
            pass

    # 都不满足条件，无法抽新任务
    return False, "本周任务未完成，无法抽取新任务。请先提交当前任务。"
