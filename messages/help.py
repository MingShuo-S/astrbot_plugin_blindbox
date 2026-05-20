"""
帮助信息生成（代码生成，避免手写漏掉）
"""

from .templates import HELP_TEMPLATE


def generate_commands_help() -> str:
    """生成命令帮助信息"""
    commands = [
        "📋 基础命令：",
        "  /blindbox - 抽取盲盒任务（随机分类）",
        "  /blindbox <分类> - 指定分类抽取",
        "  /blindbox <分类简称> - 支持【智/体/德/美/劳】",
        "  /blindbox redraw - 强制重抽当前任务",
        "",
        "👤 小组命令：",
        "  /blindbox group list - 查看所有小组",
        "  /blindbox group info <序号> - 查看小组详情",
        "  /blindbox group create <序号> <组名> <QQ...> - 创建小组（首个QQ为组长）",
        "  /blindbox group add <序号> <QQ...> - 添加成员",
        "  /blindbox group remove <序号> <QQ...> - 移除成员",
        "  /blindbox group transfer <序号> <新组长QQ> - 转让组长",
        "  /blindbox group rename <序号> <新组名> - 改名小组",
        "  /blindbox group request-dissolve <序号> - 申请解散",
        "  /blindbox group request-cancel <序号> - 取消解散",
        "",
        "📝 提交命令：",
        "  /blindbox submit <说明> - 提交任务材料（支持附带图片）",
        "  /blindbox gsubmit <说明> - 过期任务补交（积分 -1，需管理员审核）",
        "  /blindbox me - 查看我的小组信息",
        "",
        "💾 导出命令：",
        "  /blindbox export all [组号] - 导出小组全部提交",
        "  /blindbox export <编号前8位> [组号] - 导出指定提交",
        "",
        "✅ 审核命令（管理员）：",
        "  /blindbox pass <提交编号> - 通过审核",
        "  /blindbox deny <提交编号> - 拒绝审核",
        "",
        "❓ 帮助：",
        "  /blindbox help - 显示此帮助信息",
    ]
    return "\n".join(commands)


def format_help() -> str:
    """格式化帮助信息"""
    commands = generate_commands_help()
    return HELP_TEMPLATE.format(commands=commands)


def format_task(task: dict[str, object], rules_text: str) -> str:
    """格式化单个任务信息"""
    category = str(task.get("category", ""))
    title = str(task.get("title", ""))
    points = int(task.get("points", 0))
    description = str(task.get("description", "")).strip()

    result = f"【{category}】{title}\n积分：{points} 分"
    if description:
        result += f"\n说明：{description}"
    if rules_text:
        result += f"\n\n【规则说明】\n{rules_text}"
    return result
