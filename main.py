from __future__ import annotations

import os
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - optional
    load_dotenv = None

from app.app import create_app

# Load .env if present (repo root or backend/). Simplifies local dev.
if load_dotenv is not None:
    root_env = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(dotenv_path=root_env)
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

app = create_app()


def dev():  # uvicorn entry helper
    import uvicorn

    # Bind to all interfaces by default so phones on the same LAN can connect.
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    # Run by passing the app object directly to avoid import path issues
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False,
        log_level="info",
        limit_max_request_size=5 * 1024 * 1024,
    )


if __name__ == "__main__":
    dev()
