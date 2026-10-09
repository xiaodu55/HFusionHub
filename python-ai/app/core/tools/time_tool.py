"""
Time Tool - Get current date and time

钟面口径（第一百零二批）：返回值一律是 **UTC**，并把口径写在结果里。
此前用的是 `datetime.now()` 的裸本地墙钟——容器没有声明 `TZ`，那个值实际等于
"镜像默认时区"，谁给进程加了 `TZ` 它就会静默平移，而调用方（模型）无从分辨。
"""

from datetime import UTC, datetime
from typing import Any

from .base import BaseTool

_WEEKDAYS_ZH = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


class TimeTool(BaseTool):
    """Tool for getting current date and time (UTC caliber)"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """
        Get current date and time on the UTC caliber

        Returns:
            Dictionary with current date and time information, plus the declared
            caliber so the caller never has to guess which wall clock produced it
        """
        now = datetime.now(UTC)

        return {
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday": _WEEKDAYS_ZH[now.weekday()],
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "caliber": "UTC",
            "iso8601": now.isoformat(),
        }
