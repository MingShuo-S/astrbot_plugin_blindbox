"""
AI 交互工具定义
"""

from typing import Any

from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.agent.run_context import ContextWrapper
from pydantic import Field
from pydantic.dataclasses import dataclass


@dataclass
class BlindboxGetSubmissionsTool(FunctionTool[AstrAgentContext]):
    """获取小组待审核提交记录的 AI 工具"""

    plugin_instance: Any = None
    name: str = "blindbox_get_submissions"
    description: str = "查询小组的盲盒任务提交记录，包括待审核和已审核的提交"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "group_no": {
                    "type": "string",
                    "description": "小组序号",
                },
            },
            "required": ["group_no"],
        }
    )

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        group_no = str(kwargs.get("group_no", "")).strip()

        try:
            if not group_no:
                return ToolExecResult(error="group_no 不能为空")

            group_data = await self.plugin_instance._ensure_group_or_raise(group_no)
            records = self.plugin_instance._load_submission_records(group_no)
            pending = [r for r in records if r.get("review_status") == "pending"]

            return ToolExecResult(
                data={
                    "group_no": group_no,
                    "group_name": group_data.get("group_name", ""),
                    "pending_count": len(pending),
                    "submissions": pending,
                }
            )
        except Exception as e:
            return ToolExecResult(error=str(e))


@dataclass
class BlindboxGetPromptTool(FunctionTool[AstrAgentContext]):
    """获取 AI 审核的系统提示词"""

    plugin_instance: Any = None
    name: str = "blindbox_get_prompt"
    description: str = "获取盲盒任务审核的系统提示词和规则说明"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {},
            "required": [],
        }
    )

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        try:
            prompt = self.plugin_instance._build_ai_prompt_context()
            return ToolExecResult(data={"prompt": prompt})
        except Exception as e:
            return ToolExecResult(error=str(e))


@dataclass
class BlindboxReviewSubmissionTool(FunctionTool[AstrAgentContext]):
    """提交审核结果的 AI 工具"""

    plugin_instance: Any = None
    name: str = "blindbox_review_submission"
    description: str = "提交盲盒任务的审核结果（通过或拒绝），并可选择调整积分"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "group_no": {
                    "type": "string",
                    "description": "小组序号",
                },
                "submission_id": {
                    "type": "string",
                    "description": "提交编号",
                },
                "verdict": {
                    "type": "string",
                    "description": "审核结果，可以是 'approved' 或 'rejected'",
                },
                "review_reason": {
                    "type": "string",
                    "description": "审核意见或拒绝理由（可选）",
                },
                "score_delta": {
                    "type": "number",
                    "description": "如果通过，给多少积分（可选，默认为任务建议积分）",
                },
            },
            "required": ["group_no", "submission_id", "verdict"],
        }
    )

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        group_no = str(kwargs.get("group_no", "")).strip()
        submission_id = str(kwargs.get("submission_id", "")).strip()
        verdict = str(kwargs.get("verdict", "")).strip().lower()
        review_reason = str(kwargs.get("review_reason", "")).strip()
        score_delta_raw = kwargs.get("score_delta", None)

        try:
            if not group_no:
                return ToolExecResult(error="group_no 不能为空")
            if not submission_id:
                return ToolExecResult(error="submission_id 不能为空")

            group_data = await self.plugin_instance._ensure_group_or_raise(group_no)
            current_draws = await self.plugin_instance._get_state()
            draw_data = (
                current_draws.get("draws", {}).get(group_no)
                if isinstance(current_draws.get("draws", {}), dict)
                else None
            )
            records = self.plugin_instance._load_submission_records(group_no)

            target_record = None
            for record in records:
                if isinstance(record, dict) and record.get("submission_id") == submission_id:
                    target_record = record
                    break

            if target_record is None:
                return ToolExecResult(error=f"找不到提交记录 {submission_id}")

            previous_award = int(target_record.get("awarded_points", 0))
            previously_applied = bool(target_record.get("score_applied", False))
            if previously_applied and previous_award:
                group_data["score_total"] = max(
                    0, int(group_data.get("score_total", 0)) - previous_award
                )

            approved = verdict in {"approved", "accept", "pass", "ok", "通过"}
            score_delta = int(draw_data.get("points", 0)) if isinstance(draw_data, dict) else 0
            applied_points = score_delta if approved else 0

            target_record.update(
                {
                    "review_status": verdict or "pending",
                    "review_reason": review_reason or "AI 自动审核",
                    "reviewer": "ai",
                    "reviewed_at": self.plugin_instance._timestamp(),
                    "score_applied": bool(applied_points),
                    "awarded_points": applied_points,
                }
            )

            if approved:
                group_data["score_total"] = int(group_data.get("score_total", 0)) + applied_points

            self.plugin_instance._save_submission_records(group_no, records)
            await self.plugin_instance._save_state()

            return ToolExecResult(
                data={
                    "success": True,
                    "group": group_data,
                    "submission": target_record,
                    "approved": approved,
                }
            )
        except Exception as e:
            return ToolExecResult(error=str(e))
