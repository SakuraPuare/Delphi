"""python -m delphi 入口：启动 API 服务"""

import uvicorn

from delphi.core.config import settings
from delphi.core.logging import setup_logging


def main() -> None:
    setup_logging(level="DEBUG" if settings.debug else "INFO")
    uvicorn.run(
        "delphi.api.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
