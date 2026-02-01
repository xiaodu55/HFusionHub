"""
Time Tool - Get current date and time
"""

from datetime import datetime
from typing import Any, Dict

from .base import BaseTool


class TimeTool(BaseTool):
    """Tool for getting current date and time"""

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Get current date and time

        Returns:
            Dictionary with current date and time information
        """
        now = datetime.now()

        return {
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday": ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()],
            "year": now.year,
            "month": now.month,
            "day": now.day
        }
