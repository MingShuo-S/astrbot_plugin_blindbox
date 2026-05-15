"""
消息解析模块 - 提取群号、发送者ID等信息
"""

import shlex
from typing import Any

from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.components import At, BaseMessageComponent, Image, Plain


def get_message_components(event: AstrMessageEvent) -> list[BaseMessageComponent]:
    """获取消息的组件列表"""
    message_obj = getattr(event, "message_obj", None)
    message = getattr(message_obj, "message", None)
    return message if isinstance(message, list) else []


def extract_message_text_and_images(
    event: AstrMessageEvent,
) -> tuple[str, list[str], list[dict[str, str]]]:
    """提取消息中的文本和图片
    
    返回：(文本, 图片URL列表, 图片详细信息)
    """
    text_parts: list[str] = []
    image_urls: list[str] = []
    images: list[dict[str, str]] = []

    for component in get_message_components(event):
        if isinstance(component, Plain):
            text = str(getattr(component, "text", "")).strip()
            if text:
                text_parts.append(text)
        elif isinstance(component, Image):
            file_value = str(getattr(component, "file", "") or "").strip()
            url_value = str(getattr(component, "url", "") or "").strip()
            path_value = str(getattr(component, "path", "") or "").strip()
            image_entry = {"file": file_value, "url": url_value, "path": path_value}
            images.append(image_entry)
            image_url = url_value or file_value or path_value
            if image_url:
                image_urls.append(image_url)

    text = " ".join(text_parts).strip()
    return text, image_urls, images


def message_mentions_bot(event: AstrMessageEvent) -> bool:
    """判断消息是否提及了机器人"""
    if bool(getattr(event, "is_at_or_wake_command", False)):
        return True

    message_obj = getattr(event, "message_obj", None)
    self_id = str(getattr(message_obj, "self_id", "") or "").strip()
    if not self_id:
        return False

    for component in get_message_components(event):
        if isinstance(component, At):
            qq = str(getattr(component, "qq", "")).strip()
            if qq in {self_id, "all"}:
                return True
    return False


def message_starts_with_bot_at(event: AstrMessageEvent) -> bool:
    """判断消息的第一个非 Plain 组件是否为 @ 机器人
    
    仅当消息以 @ 机器人 开头时返回 True，避免在对话中间随便 @ 就触发提交。
    """
    message_obj = getattr(event, "message_obj", None)
    self_id = str(getattr(message_obj, "self_id", "") or "").strip()
    if not self_id:
        return False

    for component in get_message_components(event):
        if isinstance(component, Plain):
            text = str(getattr(component, "text", "") or "").strip()
            if text:
                return False
            continue
        if isinstance(component, At):
            qq = str(getattr(component, "qq", "") or "").strip()
            return qq in {self_id, "all"}
        return False
    return False


def split_tokens(raw_message: str) -> list[str]:
    """将消息分割成 token 列表"""
    try:
        return shlex.split(raw_message)
    except ValueError:
        return raw_message.split()


def strip_root_command(tokens: list[str]) -> list[str]:
    """移除根命令 /blindbox"""
    if tokens and tokens[0].lstrip("/").lower() == "blindbox":
        return tokens[1:]
    return tokens


def get_sender_id(event: AstrMessageEvent) -> str:
    """获取发送者 QQ 号"""
    sender = getattr(getattr(event, "message_obj", None), "sender", None)
    for attr in ("user_id", "qq", "id", "uid"):
        value = getattr(sender, attr, None)
        if value is not None:
            return str(value)
    raise ValueError("无法获取发送者 QQ 号")


def get_group_id(event: AstrMessageEvent) -> str:
    """从事件中提取群号"""
    msg_obj = getattr(event, "message_obj", None)
    if not msg_obj:
        raise ValueError("无法获取群信息")

    for attr in ("group_id", "group", "chat_id", "room_id", "room"):
        value = getattr(msg_obj, attr, None)
        if value is not None:
            return str(value)
    raise ValueError("无法获取群号")
