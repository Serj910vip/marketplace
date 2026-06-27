import os
import uuid

UPLOAD_DIR = "/opt/marketplace/uploads"
BASE_URL = "https://157.230.251.102/uploads"

async def save_file(file) -> str:
    content = await file.read()

    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    name = f"{uuid.uuid4().hex}.{ext}"

    path = os.path.join(UPLOAD_DIR, name)

    with open(path, "wb") as f:
        f.write(content)

    return f"{BASE_URL}/{name}"