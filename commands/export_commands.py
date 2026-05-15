"""
导出命令处理器
"""

from typing import Any
from .utils import plain_result_with_tip

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


async def handle_export(
    plugin: Any,
    event: AstrMessageEvent,
    args: list[str],
) -> Any:
    """
    处理导出命令
    
    Args:
        plugin: 插件实例
        event: 消息事件
        args: 命令参数
    
    Yields:
        消息结果
    """
    sender_id = plugin._get_sender_id(event)

    if not args:
        yield plain_result_with_tip(plugin, event, 
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
        state = await plugin._get_state()
        groups = state.get("groups", {})
        group_data = groups.get(group_no) if isinstance(groups, dict) else None
        if not isinstance(group_data, dict):
            yield plain_result_with_tip(plugin, event, f"小组 {group_no} 不存在。")
            return
    else:
        group_no, group_data = await plugin._find_group_by_member(sender_id)
        if not group_no or not group_data:
            yield plain_result_with_tip(plugin, event, f"QQ 号 {sender_id} 还没有绑定到任何小组。")
            return

    try:
        if arg == "all":
            records = plugin._load_submission_records(group_no)
            if not records:
                yield plain_result_with_tip(plugin, event, f"小组 {group_no} 还没有提交记录。")
                return
            zip_path = plugin._export_group_zip(group_no)
            url = await plugin._register_for_download(zip_path)
            yield plain_result_with_tip(plugin, event, 
                f"导出小组 {group_no} 全部提交：\n"
                f"共 {len(records)} 条记录\n\n"
                f"下载链接（5分钟内有效，仅可下载一次）：\n{url}"
            )
        else:
            submission_id = arg
            records = plugin._load_submission_records(group_no)
            matched = [r for r in records if str(r.get("submission_id", "")).startswith(submission_id)]
            if not matched:
                yield plain_result_with_tip(plugin, event, f"找不到以 {submission_id} 开头的提交记录。")
                return
            if len(matched) > 1:
                yield plain_result_with_tip(plugin, event, f"找到 {len(matched)} 条匹配记录，请使用更精确的编号。")
                return
            full_id = str(matched[0]["submission_id"])
            zip_path = plugin._export_submission_zip(group_no, full_id)
            url = await plugin._register_for_download(zip_path)
            yield plain_result_with_tip(plugin, event, 
                f"导出提交 {full_id[:8]}...\n"
                f"下载链接（5分钟内有效，仅可下载一次）：\n{url}"
            )
    except ValueError as exc:
        yield plain_result_with_tip(plugin, event, str(exc))
    except Exception as exc:
        logger.exception("导出失败: %s", exc)
        yield plain_result_with_tip(plugin, event, f"导出失败：{exc}")
