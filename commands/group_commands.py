"""
小组命令处理器
"""

from typing import Any
from .utils import plain_result_with_tip

from astrbot.api.event import AstrMessageEvent


async def handle_group_command(
    plugin: Any,
    event: AstrMessageEvent,
    args: list[str],
) -> Any:
    """
    处理小组相关命令
    
    Args:
        plugin: 插件实例，用于访问状态和辅助方法
        event: 消息事件
        args: 命令参数（不包括 "group"）
    
    Yields:
        消息结果
    """
    from ..business import group as group_ops
    from ..config import week_key
    
    if not args:
        yield plain_result_with_tip(plugin, event, plugin._format_help())
        return

    action = args[0].lower()
    state = await plugin._get_state()
    groups = state.setdefault("groups", {})
    draws = state.setdefault("draws", {})
    sender_id = plugin._get_sender_id(event)

    if action == "help":
        yield plain_result_with_tip(plugin, event, plugin._format_help())
        return

    if action == "list":
        if not groups:
            yield plain_result_with_tip(plugin, event, "当前还没有创建任何小组。")
            return

        lines = ["【小组列表】"]
        for group_no in sorted(groups.keys(), key=str):
            group_data = groups[group_no]
            if isinstance(group_data, dict):
                lines.append(plugin._build_group_summary(str(group_no), group_data))
                lines.append("")
        yield plain_result_with_tip(plugin, event, "\n".join(lines).rstrip())
        return

    if action == "info":
        if len(args) < 2:
            yield plain_result_with_tip(plugin, event, "用法：/blindbox group info <序号>")
            return
        group_no = str(args[1]).strip()
        group_data = groups.get(group_no)
        if not isinstance(group_data, dict):
            yield plain_result_with_tip(plugin, event, f"序号为 {group_no} 的小组不存在。")
            return
        lines = ["【小组信息】", plugin._build_group_summary(group_no, group_data)]
        task_overview = await plugin._build_current_group_task_overview(group_no)
        summary_text = str(task_overview.get("summary_text", "")).strip()
        if summary_text:
            lines.extend(["", summary_text])
            block_message = str(task_overview.get("block_message", "")).strip()
            if block_message and task_overview.get("has_active_draw"):
                lines.append(f"提醒：{block_message}")
        yield plain_result_with_tip(plugin, event, "\n".join(lines))
        return

    if action == "create":
        if len(args) < 4:
            yield plain_result_with_tip(plugin, event, "用法：/blindbox group create <序号> <组名> <第一个QQ是组长> [QQ号...]")
            return

        group_no = str(args[1]).strip()
        group_name = str(args[2]).strip()
        qq_list = plugin._unique_strings(args[3:])

        try:
            group_data = await group_ops.create_group(await plugin._get_state(), group_no, group_name, qq_list)
            await plugin._save_state()
        except ValueError as exc:
            yield plain_result_with_tip(plugin, event, str(exc))
            return

        yield plain_result_with_tip(plugin, event, 
            "\n".join(
                [
                    f"已创建小组 {group_data['group_no']}：{group_data['group_name']}",
                    f"组长：{group_data['leader_qq']}",
                    f"成员：{'、'.join(group_data['members'])}",
                ]
            )
        )
        return

    if action in {"add", "bind"}:
        if len(args) < 3:
            yield plain_result_with_tip(plugin, event, "用法：/blindbox group add <序号> <QQ号...>")
            return

        group_no = str(args[1]).strip()
        target_qqs = plugin._unique_strings(args[2:])
        group_data = groups.get(group_no)
        if not isinstance(group_data, dict):
            yield plain_result_with_tip(plugin, event, f"序号为 {group_no} 的小组不存在。")
            return

        result = await plugin._add_members_to_group(group_no, target_qqs, actor_qq=sender_id)
        lines = [f"已向小组 {group_no} 添加成员。"]
        if result["added"]:
            lines.append(f"新增：{'、'.join(result['added'])}")
        if result["skipped"]:
            lines.append(f"跳过：{'、'.join(result['skipped'])}")
        yield plain_result_with_tip(plugin, event, "\n".join(lines))
        return

    if action == "remove":
        if len(args) < 3:
            yield plain_result_with_tip(plugin, event, "用法：/blindbox group remove <序号> <QQ号...>")
            return

        group_no = str(args[1]).strip()
        target_qqs = plugin._unique_strings(args[2:])
        group_data = groups.get(group_no)
        if not isinstance(group_data, dict):
            yield plain_result_with_tip(plugin, event, f"序号为 {group_no} 的小组不存在。")
            return

        result = await group_ops.remove_members(await plugin._get_state(), group_no, target_qqs, actor_qq=sender_id)
        await plugin._save_state()

        if result.get("dissolved"):
            yield plain_result_with_tip(plugin, event, 
                f"成员已移除，小组 {group_no} 为空，已自动解散。"
                + (f"\n移除：{'、'.join(result['removed'])}" if result.get("removed") else "")
            )
            return

        lines = [f"已从小组 {group_no} 移除成员。"]
        if result.get("removed"):
            lines.append(f"移除：{'、'.join(result['removed'])}")
        if result.get("skipped"):
            lines.append(f"未处理：{'、'.join(result['skipped'])}")
        if group_data.get("leader_qq") != result.get("group", {}).get("leader_qq"):
            lines.append(f"新的组长：{result['group'].get('leader_qq', '')}")
        yield plain_result_with_tip(plugin, event, "\n".join(lines))
        return

    if action == "request-dissolve":
        if len(args) < 2:
            yield plain_result_with_tip(plugin, event, "用法：/blindbox group request-dissolve <序号>")
            return

        group_no = str(args[1]).strip()
        try:
            group_data = await group_ops.set_dissolve_requested(
                await plugin._get_state(), group_no, actor_qq=sender_id, requested=True
            )
            await plugin._save_state()
        except ValueError as exc:
            yield plain_result_with_tip(plugin, event, str(exc))
            return
        yield plain_result_with_tip(plugin, event, f"已为小组 {group_no} 标记解散申请。")
        return

    if action == "request-cancel":
        if len(args) < 2:
            yield plain_result_with_tip(plugin, event, "用法：/blindbox group request-cancel <序号>")
            return

        group_no = str(args[1]).strip()
        try:
            await group_ops.set_dissolve_requested(
                await plugin._get_state(), group_no, actor_qq=sender_id, requested=False
            )
            await plugin._save_state()
        except ValueError as exc:
            yield plain_result_with_tip(plugin, event, str(exc))
            return
        yield plain_result_with_tip(plugin, event, f"已取消小组 {group_no} 的解散申请。")
        return

    if action == "transfer":
        if len(args) < 3:
            yield plain_result_with_tip(plugin, event, "用法：/blindbox group transfer <序号> <新组长QQ>")
            return

        group_no = str(args[1]).strip()
        new_leader_qq = str(args[2]).strip()
        try:
            group_data = await group_ops.transfer_leader(
                await plugin._get_state(), group_no, new_leader_qq, actor_qq=sender_id
            )
            await plugin._save_state()
        except ValueError as exc:
            yield plain_result_with_tip(plugin, event, str(exc))
            return

        yield plain_result_with_tip(plugin, event, 
            "\n".join(
                [
                    f"已将小组 {group_no} 的组长转让给 {group_data['leader_qq']}",
                    f"当前组名：{group_data.get('group_name', '')}",
                ]
            )
        )
        return

    if action == "rename":
        if len(args) < 3:
            yield plain_result_with_tip(plugin, event, "用法：/blindbox group rename <序号> <新组名>")
            return

        group_no = str(args[1]).strip()
        new_group_name = " ".join(args[2:]).strip()
        try:
            group_data = await group_ops.rename_group(
                await plugin._get_state(), group_no, new_group_name, actor_qq=sender_id
            )
            await plugin._save_state()
        except ValueError as exc:
            yield plain_result_with_tip(plugin, event, str(exc))
            return

        yield plain_result_with_tip(plugin, event, 
            "\n".join(
                [
                    f"已将小组 {group_no} 改名为 {group_data['group_name']}",
                    f"当前组长：{group_data.get('leader_qq', '')}",
                ]
            )
        )
        return

    yield plain_result_with_tip(plugin, event, plugin._format_help())
