from datetime import datetime
from zoneinfo import ZoneInfo

def get_current_time():
    toronto = datetime.now(ZoneInfo("America/Toronto"))

    # Time first, then date
    formatted = toronto.strftime("%I:%M:%S %p  |  %Y-%m-%d")
    return formatted  # e.g., 07:39:50 PM  |  2026-09-26
