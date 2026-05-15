"""
AI 上下文构建模块
"""


def build_ai_group_context(
    group_no: str,
    group_data: dict[str, object],
    draw_data: object,
    submissions_loader,  # 函数，可获取提交记录
) -> dict[str, object]:
    """为 AI 构建小组上下文信息
    
    返回只读视图，仅包含审核所需字段。
    """
    members = group_data.get("members", [])
    try:
        submissions = submissions_loader(group_no)
    except Exception:
        submissions = []

    pending_submissions = [
        record for record in submissions if record.get("review_status") == "pending"
    ]
    current_task = draw_data if isinstance(draw_data, dict) else {}
    return {
        "group_no": group_no,
        "group_name": str(group_data.get("group_name", "")),
        "leader_qq": str(group_data.get("leader_qq", "")),
        "members": [str(member) for member in members] if isinstance(members, list) else [],
        "member_count": len(members) if isinstance(members, list) else 0,
        "score_total": int(group_data.get("score_total", 0)),
        "dissolve_requested": bool(group_data.get("dissolve_requested", False)),
        "current_task": current_task,
        "current_task_points": int(current_task.get("points", 0)) if isinstance(current_task, dict) else 0,
        "current_task_week": str(current_task.get("week", "")) if isinstance(current_task, dict) else "",
        "current_task_batch": str(current_task.get("batch_id", "")) if isinstance(current_task, dict) else "",
        "current_task_draw_count": int(current_task.get("draw_count", 0)) if isinstance(current_task, dict) else 0,
        "submission_count": len(submissions),
        "pending_submission_count": len(pending_submissions),
        "pending_submissions": pending_submissions,
    }


def build_ai_prompt_context() -> str:
    """构建给 AI 的系统提示词"""
    return (
        "你是南京大学行知×开甲学习小组的盲盒任务审核助手。\n\n"
        "【插件功能说明】\n"
        "- 本插件管理学习小组的'盲盒任务'机制\n"
        "- 每个小组每周可以抽取 1 次任务，需要从 3 个选项中选择 1 个\n"
        "- 选定的任务需要在一周内（7天）完成\n"
        "- 任务按照盲盒清单中定义的分类分组，例如德育、智育、体育、美育、劳动等\n"
        "- 每个任务都附带建议积分\n"
        "- 任务完成后或超过一周未完成，可以抽取下一个任务\n\n"
        "【你的职责】\n"
        "1. 根据小组提交的材料和当前分配的任务进行审核\n"
        "2. 判断提交内容是否满足任务要求\n"
        "3. 作出审核决定（通过/拒绝）并可选择调整积分\n"
        "4. 提供审核意见或拒绝理由\n\n"
        "【审核建议】\n"
        "- 根据任务标题和分类要求判断提交材料是否满足任务目的\n"
        "- 重点关注材料是否真实、完整，并符合当前抽取任务的类别方向\n\n"
        "【操作指令】\n"
        "/blindbox - 抽取任务（显示 3 个选项）\n"
        "/blindbox <分类名称> - 指定分类抽取\n"
        "/blindbox group list - 查看所有小组\n"
        "/blindbox group info <序号> - 查看小组详情\n"
        "/blindbox submit <说明> - 提交任务材料\n\n"
        "【重要】\n"
        "- 不要调用 shell/命令行工具\n"
        "- 不要输出 function_call、tool_call 或带 name/arguments 的结构体\n"
        "- 如果需要说明审核结果，只返回自然语言或规范化 JSON\n\n"
        "祝审核顺利！"
    )
