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
    from ..config import timestamp
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
    
    # 已有待审核的提交时，不允许重复提交
    review_status = str(task_overview.get("review_status", "")).strip().lower()
    if review_status == "pending":
        summary_text = str(task_overview.get("summary_text", "")).strip()
        yield plain_result_with_tip(plugin, event, summary_text or "当前任务已提交，等待审核中，请勿重复提交。")
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

    plugin._pending_reviews[submission_id] = (group_no, submission, timestamp())
    asyncio.create_task(plugin._trigger_ai_review(event, group_no, submission_id))


async def handle_gsubmit(
    plugin: Any,
    event: AstrMessageEvent,
    args: list[str],
) -> Any:
    """
    处理过期盲盒任务补交

    三步校验：
    1. state["draws"][group_no] 是否存在
    2. 该 draw 是否已过期（expired=True 或 deadline 已过）
    3. 该过期任务是否已有 pending 补交

    Yield:
        消息结果
    """
    from datetime import datetime

    from ..config import now, timestamp
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

    # 校验1: 是否有历史盲盒记录
    state = await plugin._get_state()
    draws = state.get("draws", {})
    draw_data = draws.get(group_no) if isinstance(draws, dict) else None
    if not isinstance(draw_data, dict):
        yield plain_result_with_tip(plugin, event, "当前小组没有历史盲盒记录，请先抽取盲盒任务。")
        return

    # 校验2: 是否已过期
    expired = bool(draw_data.get("expired", False))
    if not expired:
        deadline_str = str(draw_data.get("deadline", "")).strip()
        if deadline_str:
            try:
                deadline_dt = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M:%S")
                if now() > deadline_dt:
                    expired = True
            except Exception:
                pass

    if not expired:
        yield plain_result_with_tip(plugin, event, "当前盲盒任务尚未过期，请使用 /blindbox submit 提交。")
        return

    # 校验3: 该过期任务是否已有 pending 补交
    records = plugin._load_submission_records(group_no)
    draw_title = str(draw_data.get("title", "")).strip()
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("review_status") != "pending":
            continue
        task_snapshot = record.get("task_snapshot", {})
        if isinstance(task_snapshot, dict) and str(task_snapshot.get("title", "")).strip() == draw_title:
            yield plain_result_with_tip(plugin, event, "该过期任务已有待审核的补交，请等待管理员审核。")
            return

    # 提取材料
    _msg_text, image_urls, images = extract_message_text_and_images(event)
    materials_text = " ".join(args).strip() if args else ""

    if not materials_text and not images:
        yield plain_result_with_tip(plugin, event, "用法：/blindbox gsubmit <任务说明> [图片]")
        return

    # 构造 task_snapshot：从过期 draw 复制，积分减 1
    task_snapshot = {
        k: v for k, v in draw_data.items()
        if k not in ("expired", "draw_count", "batch_id")
    }
    task_snapshot["points"] = max(0, int(draw_data.get("points", 0)) - 1)

    # 创建提交记录（task_override 参数见 main.py _create_submission_record）
    submission = await plugin._create_submission_record(
        group_no=group_no,
        submitter_qq=sender_id,
        materials_text=materials_text,
        image_urls=image_urls,
        images=images,
        source="gsubmit",
        task_override=task_snapshot,
    )

    submission_id = submission.get("submission_id", "")
    image_count = len(submission.get("local_images", []))
    saved_info = f"，已保存 {image_count} 张图片" if image_count else ""

    yield plain_result_with_tip(plugin, event,
        "\n".join(
            [
                "已提交过期任务补交，等待管理员审核。",
                f"提交编号：{submission_id}",
                f"当前小组：{group_no} / {group_data.get('group_name', '')}",
                f"补交任务：{task_snapshot.get('title', '')}",
                f"补交积分：{task_snapshot.get('points', 0)} 分（原任务分 - 1）",
                saved_info,
            ]
        )
    )

    # 存入待审核列表，不触发 AI 自动审核
    if not hasattr(plugin, "_pending_reviews"):
        plugin._pending_reviews = {}
    plugin._pending_reviews[submission_id] = (group_no, submission, timestamp())
