"""
抽取任务命令处理器
"""

from typing import Any
from .utils import plain_result_with_tip

from astrbot.api.event import AstrMessageEvent


async def handle_draw(
    plugin: Any,
    event: AstrMessageEvent,
    args: list[str],
    force_redraw: bool = False,
) -> Any:
    """
    处理抽取任务命令
    
    Args:
        plugin: 插件实例
        event: 消息事件
        args: 命令参数
        force_redraw: 是否强制重抽
    
    Yields:
        消息结果
    """
    from ..config import now
    
    try:
        group_id = plugin._get_group_id(event)
        if not plugin._check_group_whitelist(group_id):
            yield plain_result_with_tip(plugin, event, "请在大群抽取盲盒与任务提交~")
            return
    except ValueError:
        yield plain_result_with_tip(plugin, event, "请在大群抽取盲盒与任务提交~")
        return

    sender_id = plugin._get_sender_id(event)
    group_no, group_data = await plugin._find_group_by_member(sender_id)
    if not group_no or not group_data:
        yield plain_result_with_tip(plugin, event, 
            f"QQ 号 {sender_id} 还没有绑定到任何小组。请先使用 /blindbox group create 或 /blindbox group add。"
        )
        return

    state = await plugin._get_state()
    draws = state.get("draws", {})
    current_draw = draws.get(group_no)
    records = plugin._load_submission_records(group_no)

    can_draw, reason_msg = plugin._can_draw_again(current_draw, records)
    if not can_draw and not force_redraw:
        yield plain_result_with_tip(plugin, event, reason_msg)
        return

    category = args[0] if args else "全部"

    try:
        picked_tasks, created_new, status_msg, selection_id = await plugin._draw_for_group(
            group_no, category, force_redraw, actor_qq=sender_id
        )
    except ValueError as exc:
        yield plain_result_with_tip(plugin, event, str(exc))
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

    if not hasattr(plugin, "_user_selections"):
        plugin._user_selections = {}
    plugin._user_selections[sender_id] = {
        "selection_id": selection_id,
        "group_no": group_no,
        "created_at": now(),
    }

    yield plain_result_with_tip(plugin, event, "\n".join(lines))


async def handle_selection_response(
    plugin: Any,
    event: AstrMessageEvent,
    choice_text: str,
) -> Any:
    """
    处理用户对任务选项的数字回复（1/2/3）
    
    Args:
        plugin: 插件实例
        event: 消息事件
        choice_text: 用户选择的文本（"1", "2", 或 "3"）
    
    Yields:
        消息结果
    """
    from ..config import now
    
    try:
        group_id = plugin._get_group_id(event)
        if not plugin._check_group_whitelist(group_id):
            return
    except ValueError:
        return

    sender_id = plugin._get_sender_id(event)
    if not hasattr(plugin, "_user_selections"):
        plugin._user_selections = {}

    if sender_id not in plugin._user_selections:
        return

    selection_info = plugin._user_selections[sender_id]
    selection_id = selection_info.get("selection_id", "")
    group_no = selection_info.get("group_no", "")

    created_at = selection_info.get("created_at")
    if created_at and (now() - created_at).total_seconds() > 300:
        del plugin._user_selections[sender_id]
        yield plain_result_with_tip(plugin, event, "选择已过期，请重新抽取。")
        return

    try:
        choice = int(choice_text.strip())
        if choice not in {1, 2, 3}:
            yield plain_result_with_tip(plugin, event, "请选择 1、2 或 3")
            return
    except (ValueError, AttributeError):
        return

    try:
        draw_data = await plugin._confirm_selection(group_no, selection_id, choice, actor_qq=sender_id)
    except ValueError as exc:
        yield plain_result_with_tip(plugin, event, str(exc))
        if sender_id in plugin._user_selections:
            del plugin._user_selections[sender_id]
        return

    del plugin._user_selections[sender_id]

    state = await plugin._get_state()
    groups = state.get("groups", {})
    group_data = groups.get(group_no, {})

    lines = [
        "【任务已确定】",
        f"分类：{draw_data.get('category', '')}",
        f"任务：{draw_data.get('title', '')}",
        f"建议积分：{draw_data.get('points', 0)} 分",
        "",
        f"当前小组：{group_no} - {group_data.get('group_name', '')}",
        f"截止时间：{draw_data.get('deadline', '')}（确认任务后七天内需完成）",
        "",
        "使用 /blindbox submit <任务说明> 来提交任务成果。",
    ]

    yield plain_result_with_tip(plugin, event, "\n".join(lines))
