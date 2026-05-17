"""
查看我的小组命令处理器
"""

from typing import Any
from .utils import plain_result_with_tip

from astrbot.api.event import AstrMessageEvent


async def handle_whoami(
    plugin: Any,
    event: AstrMessageEvent,
) -> Any:
    """
    处理查看我的小组命令
    
    Args:
        plugin: 插件实例
        event: 消息事件
    
    Yields:
        消息结果
    """
    try:
        sender_id = plugin._get_sender_id(event)
    except ValueError:
        yield plain_result_with_tip(plugin, event, "无法识别发送者，请稍后重试。")
        return

    group_no, group_data = await plugin._find_group_by_member(sender_id)
    if not group_no or not group_data:
        yield plain_result_with_tip(plugin, event, "你当前还没有加入任何小组。")
        return

    lines = [
        "【我的小组信息】",
        plugin._build_group_summary(group_no, group_data),
    ]

    task_overview = await plugin._build_current_group_task_overview(group_no)
    summary_text = str(task_overview.get("summary_text", "")).strip()
    if summary_text:
        lines.extend(["", summary_text])
        block_message = str(task_overview.get("block_message", "")).strip()
        if block_message and task_overview.get("has_active_draw"):
            lines.append(f"提醒：{block_message}")

    # 添加盲盒系统简介
    lines.extend([
        "",
        "💡 【盲盒任务系统简介】",
        "• 每周可抽取一次任务，从3个选项中选择1个",
        "• 选定的任务需在7天内完成并提交材料",
        "• 提交时需要文字说明+图片证明（双重验证）",
        "• 完成任务可获得相应积分",
        "• 使用 /blindbox submit 提交任务材料",
    ])

    yield plain_result_with_tip(plugin, event, "\n".join(lines))
