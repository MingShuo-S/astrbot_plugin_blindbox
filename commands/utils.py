"""
命令处理器辅助工具
"""

from typing import Any

from astrbot.api.event import AstrMessageEvent


def plain_result_with_tip(plugin: Any, event: AstrMessageEvent, message: str) -> Any:
    """
    发送带随机提示语的纯文本消息
    
    Args:
        plugin: 插件实例
        event: 消息事件
        message: 消息内容
    
    Returns:
        消息结果对象
    """
    tipped_message = plugin._append_tip(message)
    return event.plain_result(tipped_message)
