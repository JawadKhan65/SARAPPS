"""
Schedule Helper - Convert between cron and human-readable schedules
"""

from typing import Dict, Optional


def cron_to_human(cron_expression: str) -> Dict[str, any]:
    """
    Convert cron expression to human-readable format
    
    Args:
        cron_expression: Cron format like "0 2 1 */3 *"
        
    Returns:
        Dict with keys: interval_type, interval_value, time_hour, time_minute, day_of_month
    """
    if not cron_expression:
        return {
            "interval_type": "manual",
            "interval_value": 0,
            "time_hour": 2,
            "time_minute": 0,
            "day_of_month": 1
        }
    
    parts = cron_expression.split()
    if len(parts) != 5:
        return None
    
    minute, hour, day, month, weekday = parts
    
    result = {
        "time_minute": int(minute) if minute.isdigit() else 0,
        "time_hour": int(hour) if hour.isdigit() else 2,
        "day_of_month": int(day) if day.isdigit() else 1,
    }
    
    # Determine interval type
    if month == "*" and day == "*" and weekday == "*":
        result["interval_type"] = "daily"
        result["interval_value"] = 1
    elif month == "*" and day == "*" and weekday != "*":
        result["interval_type"] = "weekly"
        result["interval_value"] = 1
    elif month == "*" and day != "*":
        result["interval_type"] = "monthly"
        result["interval_value"] = 1
    elif "*/3" in month:
        result["interval_type"] = "quarterly"
        result["interval_value"] = 3
    elif "*/6" in month:
        result["interval_type"] = "biannually"
        result["interval_value"] = 6
    elif "*/12" in month or month == "1":
        result["interval_type"] = "yearly"
        result["interval_value"] = 12
    elif "*/" in month:
        # Custom interval in months
        result["interval_type"] = "custom_months"
        result["interval_value"] = int(month.split("/")[1])
    else:
        result["interval_type"] = "custom"
        result["interval_value"] = 0
    
    return result


def human_to_cron(
    interval_type: str,
    interval_value: int = 1,
    time_hour: int = 2,
    time_minute: int = 0,
    day_of_month: int = 1,
    day_of_week: Optional[int] = None
) -> str:
    """
    Convert human-readable schedule to cron expression
    
    Args:
        interval_type: One of: daily, weekly, monthly, quarterly, biannually, yearly, manual
        interval_value: Number value for interval (e.g., 3 for quarterly)
        time_hour: Hour to run (0-23)
        time_minute: Minute to run (0-59)
        day_of_month: Day of month to run (1-31)
        day_of_week: Day of week to run (0-6, 0=Sunday) for weekly schedules
        
    Returns:
        Cron expression string
    """
    minute = str(time_minute)
    hour = str(time_hour)
    
    if interval_type == "manual":
        return ""  # No automatic schedule
    elif interval_type == "daily":
        return f"{minute} {hour} * * *"
    elif interval_type == "weekly":
        day = str(day_of_week if day_of_week is not None else 0)
        return f"{minute} {hour} * * {day}"
    elif interval_type == "monthly":
        return f"{minute} {hour} {day_of_month} * *"
    elif interval_type == "quarterly":
        return f"{minute} {hour} {day_of_month} */3 *"
    elif interval_type == "biannually":
        return f"{minute} {hour} {day_of_month} */6 *"
    elif interval_type == "yearly":
        return f"{minute} {hour} {day_of_month} 1 *"  # January 1st
    elif interval_type == "custom_months":
        return f"{minute} {hour} {day_of_month} */{interval_value} *"
    else:
        # Default to manual
        return ""


def get_schedule_display_text(cron_expression: str) -> str:
    """
    Get user-friendly display text for a cron schedule
    
    Args:
        cron_expression: Cron format string
        
    Returns:
        Human-readable string like "Every 3 months at 2:00 AM"
    """
    if not cron_expression:
        return "Manual only (no automatic schedule)"
    
    schedule = cron_to_human(cron_expression)
    if not schedule:
        return "Invalid schedule"
    
    time_str = f"{schedule['time_hour']:02d}:{schedule['time_minute']:02d}"
    
    if schedule["interval_type"] == "daily":
        return f"Daily at {time_str}"
    elif schedule["interval_type"] == "weekly":
        days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        # Extract day from cron if possible
        return f"Weekly at {time_str}"
    elif schedule["interval_type"] == "monthly":
        return f"Monthly on day {schedule['day_of_month']} at {time_str}"
    elif schedule["interval_type"] == "quarterly":
        return f"Every 3 months on day {schedule['day_of_month']} at {time_str}"
    elif schedule["interval_type"] == "biannually":
        return f"Every 6 months on day {schedule['day_of_month']} at {time_str}"
    elif schedule["interval_type"] == "yearly":
        return f"Yearly on day {schedule['day_of_month']} at {time_str}"
    elif schedule["interval_type"] == "custom_months":
        return f"Every {schedule['interval_value']} months on day {schedule['day_of_month']} at {time_str}"
    else:
        return "Custom schedule"


# Preset schedule options for UI
SCHEDULE_PRESETS = [
    {"value": "manual", "label": "Manual Only", "description": "Run only when started manually"},
    {"value": "daily", "label": "Daily", "description": "Run once per day"},
    {"value": "weekly", "label": "Weekly", "description": "Run once per week"},
    {"value": "monthly", "label": "Monthly", "description": "Run once per month"},
    {"value": "quarterly", "label": "Quarterly", "description": "Run every 3 months"},
    {"value": "biannually", "label": "Twice a Year", "description": "Run every 6 months"},
    {"value": "yearly", "label": "Yearly", "description": "Run once per year"},
]

