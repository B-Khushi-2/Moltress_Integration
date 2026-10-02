"""Run the backend:  python -m backend   (host/port come from MOLTRESS_BACKEND_HOST / _PORT)."""

import uvicorn

from backend.settings import BackendSettings, load_env


def main() -> None:
    load_env()
    s = BackendSettings.from_env()
    uvicorn.run("backend.app:get_app", factory=True, host=s.host, port=s.port, log_level=s.log_level.lower())


if __name__ == "__main__":
    main()
