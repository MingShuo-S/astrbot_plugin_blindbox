"""
导出模块：生成提交记录 ZIP 文件
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import zipfile


def _image_to_jpeg_bytes(file_path: Path) -> bytes | None:
    try:
        from PIL import Image as PILImage

        img = PILImage.open(file_path)
        rgb_img = img.convert("RGB") if img.mode in ("RGBA", "P", "LA") else img
        buf = BytesIO()
        rgb_img.save(buf, "JPEG", quality=90)
        return buf.getvalue()
    except Exception:
        return None


def export_submission_zip(folder: Path, export_dir: Path, group_no: str, submission_id: str) -> Path:
    """导出单条提交为 ZIP 文件"""
    if not folder.exists():
        raise ValueError(f"提交记录 {submission_id} 的文件不存在。")

    export_dir.mkdir(parents=True, exist_ok=True)
    zip_path = export_dir / f"group_{group_no}_{submission_id[:8]}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(folder.iterdir()):
            if file_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"):
                dest_name = file_path.stem + ".jpg"
                jpg_bytes = _image_to_jpeg_bytes(file_path)
                if jpg_bytes:
                    zf.writestr(dest_name, jpg_bytes)
                else:
                    zf.write(file_path, dest_name)
            else:
                zf.write(file_path, file_path.name)

    return zip_path


def export_group_zip(group_dir: Path, export_dir: Path, group_no: str) -> Path:
    """导出小组全部提交为 ZIP 文件"""
    if not group_dir.exists() or not any(group_dir.iterdir()):
        raise ValueError(f"小组 {group_no} 没有提交记录。")

    export_dir.mkdir(parents=True, exist_ok=True)
    zip_path = export_dir / f"group_{group_no}_all_submissions.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for sub_folder in sorted(group_dir.iterdir()):
            if sub_folder.name == "submissions.json":
                zf.write(sub_folder, sub_folder.name)
                continue
            if not sub_folder.is_dir():
                continue
            for file_path in sorted(sub_folder.iterdir()):
                arcname = f"{sub_folder.name}/{file_path.name}"
                if file_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"):
                    dest_name = f"{sub_folder.name}/{file_path.stem}.jpg"
                    jpg_bytes = _image_to_jpeg_bytes(file_path)
                    if jpg_bytes:
                        zf.writestr(dest_name, jpg_bytes)
                    else:
                        zf.write(file_path, dest_name)
                else:
                    zf.write(file_path, arcname)

    return zip_path
