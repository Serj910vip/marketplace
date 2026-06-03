import sys
import os
import uvicorn

sys.path.insert(0, os.path.dirname(__file__))

if __name__ == "__main__":
    uvicorn.run(
        "app.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )