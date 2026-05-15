"""
消息模板常量
"""

# 命令帮助模板（动态生成）
HELP_TEMPLATE = """【南京大学行知×开甲 · 盲盒任务系统】

{commands}

💡 【使用小贴士】
• /blindbox submit 提交时需要有文字和图片的双重证明~
• 每个小组每周只能抽取一次任务，完成后或超时后可重抽
• 提交后会自动触发 AI 审核，也可手动使用 pass/deny 审核
• 使用 /blindbox me 查看当前任务和小组信息
• 任务分类支持简称：智/体/德/美/劳

更多帮助请访问：https://docs.astrbot.app/
"""

# 小组摘要模板
GROUP_SUMMARY_TEMPLATE = """组序号：{group_no}
组名：{group_name}
组长：{leader_qq}
累计积分：{score_total}
申请解散：{dissolve_requested}
组员：{members}"""

# 小组信息完整模板
GROUP_INFO_TEMPLATE = """【小组信息】
{summary}

【本周盲盒】
{category} - {title}
建议积分：{points} 分"""

# 任务格式模板
TASK_TEMPLATE = """{i}. 【{category}】{title}
   建议积分：{points} 分
{description_line}"""

# 抽取结果模板
DRAW_RESULT_TEMPLATE = """【南京大学行知×开甲 学习小组 · 抽奖盲盒】

恭喜抽到以下任务，请选择其中一个：

{tasks}

请回复数字 1/2/3 来选择任务

当前小组：{group_no} - {group_name}
组长：{leader_qq}"""

# 任务确认模板
SELECTION_CONFIRMED_TEMPLATE = """【任务已确定】
分类：{category}
任务：{title}
建议积分：{points} 分

当前小组：{group_no} - {group_name}
本周截止日期：{drawn_at} 起，一周内需完成

使用 /blindbox submit <任务说明> 来提交任务成果。"""

# 提交成功模板
SUBMISSION_SUCCESS_TEMPLATE = """已提交任务材料，等待 AI 审核。
提交编号：{submission_id}
当前小组：{group_no} / {group_name}
本次关联任务：{task_title}
{image_info}"""

# 审核通过模板
REVIEW_APPROVED_TEMPLATE = """审核确认完成！
提交编号：{submission_id}
小组：{group_name}
结果：通过✅
本轮积分：{awarded_points}"""

# 审核拒绝模板
REVIEW_REJECTED_TEMPLATE = """审核确认完成！
提交编号：{submission_id}
小组：{group_name}
结果：拒绝❌
拒绝原因：{reason}"""

# 导出成功模板
EXPORT_SUCCESS_TEMPLATE = """导出{type}：
共 {count} 条记录

下载链接（5分钟内有效，仅可下载一次）：
{url}"""

# AI 审核失败模板
AI_REVIEW_FAILED_TEMPLATE = """[AI 审核失败] 提交编号 {submission_id} 自动审核未能完成。
原因：{reason}

请管理员手动审核：
/blindbox pass {submission_id} - 通过审核
/blindbox deny {submission_id} - 拒绝审核"""

# AI 审核异常模板
AI_REVIEW_ERROR_TEMPLATE = """[AI 审核异常] 提交编号 {submission_id} 自动审核遇到错误。
错误：{error}

请管理员手动审核：
/blindbox pass {submission_id} - 通过审核
/blindbox deny {submission_id} - 拒绝审核"""

# 我的小组信息模板
MY_GROUP_TEMPLATE = """【我的小组信息】
{summary}{task_info}"""
