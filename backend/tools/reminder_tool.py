from typing import Dict, Any, List
from sqlalchemy import select
from backend.database.db import AsyncSessionLocal
from backend.database.models import Reminder

TOOL_DEFINITION = {
    "name": "create_reminder",
    "description": "Create a reminder for the user with a title and time/date",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The description or subject of the reminder, e.g. 'Study DBMS'"
            },
            "datetime": {
                "type": "string",
                "description": "The date and time for the reminder, e.g. 'tomorrow at 9 AM', '2026-09-05 09:00', 'in 2 hours'"
            }
        },
        "required": ["title", "datetime"]
    }
}

async def execute_create_reminder(title: str, datetime: str) -> Dict[str, Any]:
    """Execute create_reminder tool and save to SQLite database."""
    if not title or not title.strip():
        return {"success": False, "error": "Reminder title is required."}
    if not datetime or not datetime.strip():
        return {"success": False, "error": "Reminder datetime is required."}

    try:
        async with AsyncSessionLocal() as session:
            reminder = Reminder(
                title=title.strip(),
                datetime=datetime.strip(),
                status="pending"
            )
            session.add(reminder)
            await session.commit()
            await session.refresh(reminder)
            
            return {
                "success": True,
                "reminder": reminder.to_dict(),
                "message": f"Reminder '{reminder.title}' scheduled for {reminder.datetime}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to save reminder: {str(e)}"
        }

async def get_all_reminders() -> List[Dict[str, Any]]:
    """Retrieve all reminders from the database."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Reminder).order_by(Reminder.id.desc()))
        reminders = result.scalars().all()
        return [r.to_dict() for r in reminders]
