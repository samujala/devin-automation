"""python -m api — run the FastAPI server with uvicorn."""

import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("API_PORT", "8000"))
    uvicorn.run("api.server:app", host="0.0.0.0", port=port, reload=False)
