from pathlib import Path
import base64
import hashlib
import mimetypes
import uuid
from typing import Optional
from PIL import Image, ImageDraw


def unique_name(original_name: str, prefix: str = "file", suffix: Optional[str] = None) -> str:
    ext = suffix or Path(original_name).suffix.lower() or ".png"
    return f"{prefix}_{uuid.uuid4().hex[:12]}{ext}"


def _safe_image_suffix(original_name: str) -> str:
    suffix = Path(original_name or "").suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return suffix
    return ".png"


def save_uploaded_file(uploaded_file, target_dir: Path, prefix: str = "upload") -> str:
    """Save uploaded file with content-hash deduplication.

    Re-uploading the same image bytes will return the existing local path instead
    of writing another copy to uploads/. This keeps repeated source/sketch uploads
    from filling local cache/storage.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    file_bytes = uploaded_file.getbuffer().tobytes()
    digest = hashlib.sha256(file_bytes).hexdigest()
    ext = _safe_image_suffix(uploaded_file.name)

    # Prefix intentionally not used in the filename: the same file uploaded from
    # different flows should still map to a single stored image.
    filename = f"image_{digest[:24]}{ext}"
    path = target_dir / filename

    if not path.exists():
        with open(path, "wb") as f:
            f.write(file_bytes)
    return str(path)


def image_to_data_url(path: str) -> str:
    mime_type = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


def image_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_mime_type(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "image/png"


def make_placeholder_image(text: str, output_path: str, size=(1024, 1024)) -> str:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    title = "MOCK OUTPUT"
    wrapped = wrap_text(text, max_chars=32)[:18]
    lines = [title, ""] + wrapped
    y = 80
    for i, line in enumerate(lines):
        draw.text((60, y), line, fill="black")
        y += 42 if i == 0 else 32
    img.save(output_path)
    return output_path


def wrap_text(text: str, max_chars: int = 36) -> list[str]:
    text = str(text).replace("\n", " ")
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]
