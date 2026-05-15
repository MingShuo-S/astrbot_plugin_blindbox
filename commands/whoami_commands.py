"""
查看我的小组命令处理器
"""

from typing import Any

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
    from ..config import week_key
    
    try:
        sender_id = plugin._get_sender_id(event)
    except ValueError:
        yield event.plain_result("无法识别发送者，请稍后重试。")
        return

    group_no, group_data = await plugin._find_group_by_member(sender_id)
    if not group_no or not group_data:
        yield event.plain_result("你当前还没有加入任何小组。")
        return

    lines = [
        "【我的小组信息】",
        plugin._build_group_summary(group_no, group_data),
    ]

    draws = (await plugin._get_state()).get("draws", {})
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
