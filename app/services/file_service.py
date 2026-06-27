import uuid
from pathlib import Path

from fastapi import UploadFile

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


async def save_file(file: UploadFile) -> str:
    content = await file.read()
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "jpg"
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = UPLOAD_DIR / filename

    with open(file_path, "wb") as f:
        f.write(content)

    return f"/uploads/{filename}"
