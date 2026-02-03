import logging
import sys
from pathlib import Path

import platformdirs

from code_cli.ui.app import CodeApp


def _setup_logging() -> None:
    log_dir = Path(platformdirs.user_log_dir("code-cli"))
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_dir / "code-cli.log"),
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    # Silence noisy HTTP debug logs
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main():
    _setup_logging()
    app = CodeApp()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
