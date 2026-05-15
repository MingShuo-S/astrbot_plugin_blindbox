"""
提交文件存储模块
"""

from __future__ import annotations

from pathlib import Path
import shutil

import aiohttp
from astrbot.api import logger


def _convert_image_to_jpeg(source_path: Path, dest_path: Path) -> bool:
    """转换图片为 JPEG 格式"""
    try:
        from PIL import Image as PILImage

        img = PILImage.open(source_path)
        rgb_img = img.convert("RGB") if img.mode in ("RGBA", "P", "LA") else img
        rgb_img.save(dest_path, "JPEG", quality=90)
        return True
    except Exception:
        return False


async def _download_image(url: str, dest_path: Path) -> bool:
    """下载图片"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    dest_path.write_bytes(data)
                    return True
    except Exception as exc:
        logger.warning("下载图片失败: %s → %s", url, exc)
    return False


async def save_submission_files(
    folder: Path,
    submission_id: str,
    materials_text: str,
    images: list[dict[str, str]],
) -> list[str]:
    """保存提交的文件"""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "text.txt").write_text(materials_text, encoding="utf-8")

    local_images: list[str] = []
    for idx, image_entry in enumerate(images):
        saved_path = folder / f"image_{idx + 1:03d}.jpg"
        saved = False

        url = image_entry.get("url", "")
        if url and url.startswith("http"):
            saved = await _download_image(url, saved_path)

        if not saved:
            src_path = image_entry.get("path", "")
            if src_path and Path(src_path).exists():
                try:
                    shutil.copy2(src_path, saved_path)
                    saved = True
                except OSError as exc:
                    logger.warning("复制图片失败: %s → %s", src_path, exc)

        if not saved:
            file_id = image_entry.get("file", "")
            if file_id:
                file_path = Path(file_id)
                if file_path.exists():
                    try:
                        shutil.copy2(file_path, saved_path)
                        saved = True
                    except OSError:
                        pass

        if not saved:
            logger.warning("无法保存图片: submission=%s idx=%d entry=%s", submission_id, idx, image_entry)
            continue

        if saved_path.suffix.lower() != ".jpg":
            jpg_path = saved_path.with_suffix(".jpg")
            if _convert_image_to_jpeg(saved_path, jpg_path):
                try:
                    saved_path.unlink()
                except OSError:
                    pass
                saved_path = jpg_path

        local_images.append(saved_path.name)

    return local_images
