import json
import logging
import sys
from typing import Any

logging.basicConfig(
    level=logging.DEBUG if "--debug" in sys.argv else logging.WARNING,
)

logger = logging.getLogger("linodecli")


def _format_entry(
    detail: str,
    **kwargs: Any,
):
    return json.dumps(
        {
            "_detail": detail,
            **kwargs,
        },
        sort_keys=True,
    )


def debug(
    detail: str,
    **kwargs: Any,
):
    logger.debug(_format_entry(detail, **kwargs))


def info(
    detail: str,
    **kwargs: Any,
):
    logger.info(_format_entry(detail, **kwargs))


def warning(
    detail: str,
    **kwargs: Any,
):
    logger.warning(_format_entry(detail, **kwargs))


def error(
    detail: str,
    **kwargs: Any,
):
    logger.error(_format_entry(detail, **kwargs))
