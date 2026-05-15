"""
小组管理模块
"""

from typing import Any

from .storage import parse_qq_list, unique_strings


def build_group_summary(group_no: str, group_data: dict[str, object]) -> str:
    """构建小组摘要信息"""
    members = group_data.get("members", [])
    member_text = "、".join(str(member) for member in members) if members else "无"
    leader_qq = str(group_data.get("leader_qq", "")) or "未设置"
    request_text = "是" if group_data.get("dissolve_requested") else "否"
    score_total = int(group_data.get("score_total", 0))
    return (
        f"组序号：{group_no}\n"
        f"组名：{group_data.get('group_name', '')}\n"
        f"组长：{leader_qq}\n"
        f"累计积分：{score_total}\n"
        f"申请解散：{request_text}\n"
        f"组员：{member_text}"
    )


def group_has_member(group_data: dict[str, object], qq: str) -> bool:
    """检查小组是否包含该成员"""
    members = group_data.get("members", [])
    return isinstance(members, list) and qq in members


def can_modify_member(group_data: dict[str, object], actor_qq: str | None, target_qq: str) -> bool:
    """检查操作者是否有权限修改成员"""
    if actor_qq is None:
        return True
    leader_qq = str(group_data.get("leader_qq", ""))
    return actor_qq == leader_qq or actor_qq == target_qq


async def create_group(
    state: dict[str, object], group_no: str, group_name: str, qq_list: list[str]
) -> dict[str, object]:
    """创建小组"""
    if not group_no.strip():
        raise ValueError("组序号不能为空。")
    if not group_name.strip():
        raise ValueError("组名不能为空。")
    if not qq_list:
        raise ValueError("至少要提供一个 QQ 号，第一个 QQ 号会自动作为组长。")

    groups = state.setdefault("groups", {})
    member_to_group = state.setdefault("member_to_group", {})
    group_no = str(group_no).strip()

    if group_no in groups:
        raise ValueError(f"序号为 {group_no} 的小组已存在。")

    leader_qq = qq_list[0]
    members = []
    for member_id in qq_list:
        if member_id in member_to_group:
            raise ValueError(f"QQ 号 {member_id} 已经属于小组 {member_to_group[member_id]}。")
        if member_id not in members:
            members.append(member_id)

    group_data = {
        "group_no": group_no,
        "group_name": group_name.strip(),
        "leader_qq": leader_qq,
        "members": members,
        "dissolve_requested": False,
        "score_total": 0,
    }
    groups[group_no] = group_data
    for member_id in members:
        member_to_group[member_id] = group_no
    return group_data


async def dissolve_group(state: dict[str, object], group_no: str) -> dict[str, object]:
    """解散小组"""
    groups = state.get("groups", {})
    member_to_group = state.get("member_to_group", {})
    draws = state.get("draws", {})
    if not isinstance(groups, dict) or not isinstance(member_to_group, dict) or not isinstance(draws, dict):
        raise ValueError("小组数据异常，请重新初始化插件状态。")

    group_data = groups.pop(str(group_no), None)
    if not isinstance(group_data, dict):
        raise ValueError(f"序号为 {group_no} 的小组不存在。")

    for member_id in group_data.get("members", []):
        member_id = str(member_id)
        if member_to_group.get(member_id) == str(group_no):
            member_to_group.pop(member_id, None)
    draws.pop(str(group_no), None)
    return group_data


async def remove_members(
    state: dict[str, object], group_no: str, target_qqs: list[str], actor_qq: str | None = None
) -> dict[str, object]:
    """从小组中移除成员"""
    groups = state.get("groups", {})
    member_to_group = state.get("member_to_group", {})
    draws = state.get("draws", {})
    if not isinstance(groups, dict) or not isinstance(member_to_group, dict) or not isinstance(draws, dict):
        raise ValueError("小组数据异常，请重新初始化插件状态。")

    group_data = groups.get(str(group_no))
    if not isinstance(group_data, dict):
        raise ValueError(f"序号为 {group_no} 的小组不存在。")

    removed: list[str] = []
    skipped: list[str] = []
    members = group_data.setdefault("members", [])
    leader_qq = str(group_data.get("leader_qq", ""))

    for target_qq in unique_strings(target_qqs):
        if not group_has_member(group_data, target_qq):
            skipped.append(f"{target_qq}(未在组内)")
            continue
        if not can_modify_member(group_data, actor_qq, target_qq):
            skipped.append(f"{target_qq}(无权限)")
            continue
        members.remove(target_qq)
        if member_to_group.get(target_qq) == str(group_no):
            member_to_group.pop(target_qq, None)
        removed.append(target_qq)

    if not members:
        group_data["dissolve_requested"] = False
        groups.pop(str(group_no), None)
        draws.pop(str(group_no), None)
        return {"dissolved": True, "removed": removed, "skipped": skipped, "group": group_data}

    if leader_qq not in members:
        new_leader = members[0]
        group_data["leader_qq"] = new_leader
    return {"dissolved": False, "removed": removed, "skipped": skipped, "group": group_data}


async def set_dissolve_requested(
    state: dict[str, object], group_no: str, actor_qq: str | None = None, requested: bool = True
) -> dict[str, object]:
    """设置解散申请状态"""
    groups = state.get("groups", {})
    if not isinstance(groups, dict):
        raise ValueError("小组数据异常，请重新初始化插件状态。")

    group_data = groups.get(str(group_no))
    if not isinstance(group_data, dict):
        raise ValueError(f"序号为 {group_no} 的小组不存在。")

    if actor_qq is not None and actor_qq != str(group_data.get("leader_qq", "")):
        raise ValueError("只有组长可以申请解散该小组。")

    group_data["dissolve_requested"] = requested
    return group_data


async def transfer_leader(
    state: dict[str, object],
    group_no: str,
    new_leader_qq: str,
    actor_qq: str | None = None,
) -> dict[str, object]:
    """转让组长"""
    groups = state.get("groups", {})
    if not isinstance(groups, dict):
        raise ValueError("小组数据异常，请重新初始化插件状态。")

    group_data = groups.get(str(group_no))
    if not isinstance(group_data, dict):
        raise ValueError(f"序号为 {group_no} 的小组不存在。")

    current_leader = str(group_data.get("leader_qq", ""))
    if actor_qq is not None and actor_qq != current_leader:
        raise ValueError("只有组长可以转让组长身份。")

    new_leader_qq = str(new_leader_qq).strip()
    if not new_leader_qq:
        raise ValueError("新组长 QQ 不能为空。")
    if not group_has_member(group_data, new_leader_qq):
        raise ValueError("新组长必须是本组成员。")

    group_data["leader_qq"] = new_leader_qq
    group_data["dissolve_requested"] = False
    return group_data


async def rename_group(
    state: dict[str, object],
    group_no: str,
    new_group_name: str,
    actor_qq: str | None = None,
) -> dict[str, object]:
    """改名小组"""
    groups = state.get("groups", {})
    if not isinstance(groups, dict):
        raise ValueError("小组数据异常，请重新初始化插件状态。")

    group_data = groups.get(str(group_no))
    if not isinstance(group_data, dict):
        raise ValueError(f"序号为 {group_no} 的小组不存在。")

    current_leader = str(group_data.get("leader_qq", ""))
    if actor_qq is not None and actor_qq != current_leader:
        raise ValueError("只有组长可以改名小组。")

    new_group_name = str(new_group_name).strip()
    if not new_group_name:
        raise ValueError("新组名不能为空。")

    group_data["group_name"] = new_group_name
    return group_data


async def add_members_to_group(
    state: dict[str, object], group_no: str, target_qqs: list[str], actor_qq: str | None = None
) -> dict[str, object]:
    """添加成员到小组"""
    groups = state.get("groups", {})
    member_to_group = state.get("member_to_group", {})
    if not isinstance(groups, dict) or not isinstance(member_to_group, dict):
        raise ValueError("小组数据异常，请重新初始化插件状态。")

    group_data = groups.get(str(group_no))
    if not isinstance(group_data, dict):
        raise ValueError(f"序号为 {group_no} 的小组不存在。")

    added: list[str] = []
    skipped: list[str] = []
    members = group_data.setdefault("members", [])
    leader_qq = str(group_data.get("leader_qq", ""))

    for target_qq in unique_strings(target_qqs):
        if not can_modify_member(group_data, actor_qq, target_qq):
            skipped.append(f"{target_qq}(无权限)")
            continue
        existing_group = member_to_group.get(target_qq)
        if existing_group and str(existing_group) != str(group_no):
            skipped.append(f"{target_qq}(已在 {existing_group})")
            continue
        if target_qq not in members:
            members.append(target_qq)
            added.append(target_qq)
        member_to_group[target_qq] = str(group_no)

    if leader_qq and leader_qq not in members:
        members.insert(0, leader_qq)
        member_to_group[leader_qq] = str(group_no)

    return {"added": added, "skipped": skipped, "group": group_data}


async def find_group_by_member(state: dict[str, object], sender_id: str) -> tuple[str | None, dict[str, object] | None]:
    """根据成员查找其所属小组"""
    member_to_group = state.get("member_to_group", {})
    groups = state.get("groups", {})
    group_no = member_to_group.get(sender_id) if isinstance(member_to_group, dict) else None
    if not group_no or not isinstance(groups, dict):
        return None, None
    group_data = groups.get(str(group_no))
    if not isinstance(group_data, dict):
        return None, None
    return str(group_no), group_data


async def ensure_group_or_raise(state: dict[str, object], group_no: str) -> dict[str, object]:
    """确保小组存在，否则抛出异常"""
    groups = state.get("groups", {})
    if not isinstance(groups, dict) or group_no not in groups or not isinstance(groups[group_no], dict):
        raise ValueError(f"序号为 {group_no} 的小组不存在。")
    return groups[group_no]
