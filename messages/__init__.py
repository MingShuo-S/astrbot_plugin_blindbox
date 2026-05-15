"""
消息模块 - 模板和帮助信息生成
"""

from .help import format_help, format_task, generate_commands_help


def append_tip_to_message(message: str, tips_list: list[str] | None = None) -> str:
    """
    为消息添加随机提示语
    
    Args:
        message: 原始消息内容
        tips_list: 自定义提示语列表，如果为 None 则使用默认列表
    
    Returns:
        添加了提示语的消息
    """
    from ..config import get_random_tip
    
    tip = get_random_tip(tips_list)
    if tip:
        return f"{message}\n\n{tip}"
    return message
from .templates import (
    AI_REVIEW_ERROR_TEMPLATE,
    AI_REVIEW_FAILED_TEMPLATE,
    DRAW_RESULT_TEMPLATE,
    EXPORT_SUCCESS_TEMPLATE,
    GROUP_INFO_TEMPLATE,
    GROUP_SUMMARY_TEMPLATE,
    HELP_TEMPLATE,
    MY_GROUP_TEMPLATE,
    REVIEW_APPROVED_TEMPLATE,
    REVIEW_REJECTED_TEMPLATE,
    SELECTION_CONFIRMED_TEMPLATE,
    SUBMISSION_SUCCESS_TEMPLATE,
    TASK_TEMPLATE,
)

__all__ = [
    "format_help",
    "format_task",
    "generate_commands_help",
    "append_tip_to_message",
    # Templates
    "HELP_TEMPLATE",
    "GROUP_SUMMARY_TEMPLATE",
    "GROUP_INFO_TEMPLATE",
    "TASK_TEMPLATE",
    "DRAW_RESULT_TEMPLATE",
    "SELECTION_CONFIRMED_TEMPLATE",
    "SUBMISSION_SUCCESS_TEMPLATE",
    "REVIEW_APPROVED_TEMPLATE",
    "REVIEW_REJECTED_TEMPLATE",
    "EXPORT_SUCCESS_TEMPLATE",
    "AI_REVIEW_FAILED_TEMPLATE",
    "AI_REVIEW_ERROR_TEMPLATE",
    "MY_GROUP_TEMPLATE",
]
