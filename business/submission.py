"""
提交记录构建模块
"""

from __future__ import annotations

from config import gen_uuid, timestamp, week_key


def build_submission_record(
    group_no: str,
    group_data: dict[str, object],
    submitter_qq: str,
    materials_text: str,
    image_urls: list[str],
    images: list[dict[str, str]],
    source: str,
    draw_data: dict[str, object] | None,
    local_images: list[str] | None = None,
) -> dict[str, object]:
    """构建提交记录"""
    return {
        "submission_id": gen_uuid(),
        "group_no": group_no,
        "group_name": str(group_data.get("group_name", "")),
        "submitter_qq": submitter_qq,
        "materials_text": materials_text,
        "image_urls": image_urls,
        "images": images,
        "local_images": local_images or [],
        "source": source,
        "week": week_key(),
        "task_snapshot": draw_data if isinstance(draw_data, dict) else {},
        "review_status": "pending",
        "review_reason": "",
        "reviewer": "",
        "reviewed_at": "",
        "awarded_points": 0,
        "score_applied": False,
        "submitted_at": timestamp(),
    }
