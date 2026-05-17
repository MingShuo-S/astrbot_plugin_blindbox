"""
提交任务命令处理器
"""

import asyncio
from typing import Any
from .utils import plain_result_with_tip

from astrbot.api.event import AstrMessageEvent


async def handle_submit(
    plugin: Any,
    event: AstrMessageEvent,
    args: list[str],
) -> Any:
    """
    处理提交任务命令
    
    Args:
        plugin: 插件实例
        event: 消息事件
        args: 命令参数
    
    Yields:
        消息结果
    """
    from ..parser import extract_message_text_and_images
    
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
        yield plain_result_with_tip(plugin, event, f"QQ 号 {sender_id} 还没有绑定到任何小组。")
        return

    # 检查小组是否有进行中的任务
    task_overview = await plugin._build_current_group_task_overview(group_no)
    if not task_overview.get("has_active_draw"):
        yield plain_result_with_tip(plugin, event, "当前小组没有进行中的任务，请先抽取盲盒任务后再提交。")
        return
    
    # 如果任务已过期（超过7天），也不允许提交
    if task_overview.get("block_draw"):
        summary_text = str(task_overview.get("summary_text", "")).strip()
        block_message = str(task_overview.get("block_message", "")).strip()
        message_parts = [summary_text] if summary_text else []
        if block_message:
            message_parts.append(block_message)
        yield plain_result_with_tip(plugin, event, "\n\n".join(message_parts) if message_parts else block_message)
        return

    _msg_text, image_urls, images = extract_message_text_and_images(event)
    materials_text = " ".join(args).strip() if args else ""

    if not materials_text and not images:
        yield plain_result_with_tip(plugin, event, "用法：/blindbox submit <任务说明> [图片]")
        return

    submission = await plugin._create_submission_record(
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

    yield plain_result_with_tip(plugin, event, 
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

    plugin._pending_reviews[submission_id] = (group_no, submission)
    asyncio.create_task(plugin._trigger_ai_review(event, group_no, submission_id))
