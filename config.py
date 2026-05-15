"""
全局配置、常量和工具函数
"""

import random
from datetime import datetime
from pathlib import Path
from uuid import uuid4

PLUGIN_NAME = "astrbot_plugin_blindbox"
KV_STATE_KEY = "blindbox_state"

# 默认提示语列表（可在配置文件中自定义）
DEFAULT_TIPS = [
    "💡 /blindbox submit 提交时需要有文字和图片的双重证明~",
    "💡 每个小组每周只能抽取一次任务，完成后或超时后可重抽",
    "💡 提交后会自动触发 AI 审核，也可手动使用 pass/deny 审核",
    "💡 使用 /blindbox me 查看当前任务和小组信息",
    "💡 任务分类支持简称：智/体/德/美/劳",
    "💡 完成任务可获得相应积分，积分可兑换奖品哦~",
    "💡 组长可以管理小组成员，使用 /blindbox group 相关命令",
    "💡 想重抽任务？使用 /blindbox redraw 强制重抽",
    "💡 导出提交记录使用 /blindbox export 命令",
    "💡 有疑问？访问帮助文档：https://ncn6z1dnpw2b.feishu.cn/wiki/JZWXwHM54iwgbfkYVgyc1GPtnOf?from=from_copylink",
]


def get_random_tip(tips_list: list[str] | None = None) -> str:
    """从 tips 列表中随机选择一条提示语"""
    tips = tips_list or DEFAULT_TIPS
    if not tips:
        return ""
    return random.choice(tips)

# 默认规则说明
DEFAULT_RULES_TEXT = (
    "据行为心理学的'可变比率强化'学说，不确定的任务和奖励能持续激发参与者的期待感。\n"
    "本期学习小组引入'盲盒任务'机制：每小组每周可抽取一次盲盒任务，为一周的小组学习设置目标激励。\n\n"
    "小组完成盲盒任务后可以获得对应积分，这些积分可用于兑换精美奖品、评选优秀小组。"
)

# 默认任务列表
DEFAULT_TASKS = [
    {"category": "以智增慧", "title": "自习风险盲盒投资", "points": 10, "enabled": True},
    {"category": "以智增慧", "title": "文理互补错题交换", "points": 10, "enabled": True},
    {"category": "以智增慧", "title": "生活好物/代码神器安利", "points": 10, "enabled": True},
    {"category": "以智增慧", "title": "仙林鼓楼校校逛散步", "points": 10, "enabled": True},
    {"category": "以智增慧", "title": "技能交换五分钟", "points": 10, "enabled": True},
    {"category": "以智增慧", "title": "四六级/期末复习搭子盲盒", "points": 10, "enabled": True},
    {"category": "以智增慧", "title": "AI胡乱生成PPT盲盒路演", "points": 10, "enabled": True},
    {"category": "以智增慧", "title": "图书馆夜读两小时", "points": 10, "enabled": True},
    {"category": "以体强身", "title": "校园跑盲盒惊喜", "points": 10, "enabled": True},
    {"category": "以体强身", "title": "操场接力跑FUN恩仇", "points": 10, "enabled": True},
    {"category": "以体强身", "title": "景点散步路线图", "points": 10, "enabled": True},
    {"category": "以体强身", "title": "操场集体跳绳/踢毽子怀旧局", "points": 10, "enabled": True},
    {"category": "以体强身", "title": "跑步废物聊天配速小组", "points": 10, "enabled": True},
    {"category": "以体强身", "title": "占领健身房一小时", "points": 10, "enabled": True},
    {"category": "以德润心", "title": "夸夸接龙暖心卡", "points": 10, "enabled": True},
    {"category": "以德润心", "title": "垃圾话漂流瓶", "points": 10, "enabled": True},
    {"category": "以德润心", "title": "民国建筑导览员体验", "points": 10, "enabled": True},
    {"category": "以德润心", "title": "志愿服务盲盒", "points": 10, "enabled": True},
    {"category": "以德润心", "title": "倾听晚安电台", "points": 10, "enabled": True},
    {"category": "以美立美", "title": "校园神奇动物通缉令", "points": 10, "enabled": True},
    {"category": "以美立美", "title": "传画接龙脑洞赛", "points": 10, "enabled": True},
    {"category": "以美立美", "title": "定格校园vlog闪现", "points": 10, "enabled": True},
    {"category": "以美立美", "title": "一起看电影/小型摄影展", "points": 10, "enabled": True},
    {"category": "以美立美", "title": "传话游戏/故事接龙", "points": 10, "enabled": True},
    {"category": "以美立美", "title": "半日市集文艺扫街", "points": 10, "enabled": True},
    {"category": "以劳励行", "title": "20元穷鬼美食探店盲盒", "points": 10, "enabled": True},
    {"category": "以劳励行", "title": "宿舍/书桌收纳大作战", "points": 10, "enabled": True},
    {"category": "以劳励行", "title": "鼓楼附近吃放心午餐", "points": 10, "enabled": True},
    {"category": "以劳励行", "title": "咖啡自由大挑战", "points": 10, "enabled": True},
    {"category": "以劳励行", "title": "期末鼓励小零食漂流瓶", "points": 10, "enabled": True},
    {"category": "以劳励行", "title": "深夜食堂盲盒操作", "points": 10, "enabled": True},
]

TASK_CATEGORIES = ["【以智增慧】", "【以体强身】", "【以德润心】", "【以美立美】", "【以劳励行】"]

# 分类别名（用于用户输入的模糊匹配）
CATEGORY_ALIASES = {
    "全部": "全部",
    "all": "全部",
    "random": "全部",
    "随机": "全部",
    "德": "【以德润心】",
    "以德润心": "【以德润心】",
    "以德润心类": "【以德润心】",
    "德育": "【以德润心】",
    "品德": "【以德润心】",
    "智": "【以智增慧】",
    "以智增慧": "【以智增慧】",
    "以智增慧类": "【以智增慧】",
    "智育": "【以智增慧】",
    "体": "【以体强身】",
    "以体强身": "【以体强身】",
    "以体强身类": "【以体强身】",
    "体育": "【以体强身】",
    "身体": "【以体强身】",
    "美": "【以美立美】",
    "以美立美": "【以美立美】",
    "以美立美类": "【以美立美】",
    "美育": "【以美立美】",
    "艺术": "【以美立美】",
    "劳": "【以劳励行】",
    "以劳励行": "【以劳励行】",
    "以劳励行类": "【以劳励行】",
    "劳育": "【以劳励行】",
    "劳动": "【以劳励行】",
}


def resolve_data_root() -> Path:
    """解析数据根目录"""
    current_dir = Path(__file__).resolve().parent
    for ancestor in [current_dir, *current_dir.parents]:
        data_dir = ancestor / "data"
        if data_dir.is_dir():
            return data_dir / "plugins" / PLUGIN_NAME
    return current_dir / "data" / "plugins" / PLUGIN_NAME


def now() -> datetime:
    """获取当前时间"""
    return datetime.now()


def week_key(now_time: datetime | None = None) -> str:
    """获取周数 key，格式：2025-W12"""
    current = now_time or now()
    iso = current.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def batch_id(now_time: datetime | None = None) -> str:
    """生成批次 ID，基于周数"""
    return week_key(now_time)


def timestamp(now_time: datetime | None = None) -> str:
    """获取时间戳字符串"""
    return (now_time or now()).strftime("%Y-%m-%d %H:%M:%S")


def gen_uuid() -> str:
    """生成 UUID hex"""
    return uuid4().hex


def default_state() -> dict[str, object]:
    """默认状态结构"""
    return {
        "groups": {},
        "member_to_group": {},
        "draws": {},
        "tasks": [],
        "pending_selections": {},
    }
