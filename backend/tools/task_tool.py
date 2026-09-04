from typing import Dict, Any, List, Optional
from sqlalchemy import select
from backend.database.db import AsyncSessionLocal
from backend.database.models import Task

TOOL_DEFINITION = {
    "name": "create_task",
    "description": "Create a task for the user with title, priority, and due date",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The task title or description, e.g. 'Finish Python assignment'"
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Priority level of the task: 'low', 'medium', or 'high'"
            },
            "due_date": {
                "type": "string",
                "description": "Due date or deadline for the task, e.g. 'Friday', 'next Monday', '2026-09-10'"
            }
        },
        "required": ["title"]
    }
}

async def execute_create_task(title: str, priority: str = "medium", due_date: Optional[str] = None) -> Dict[str, Any]:
    """Execute create_task tool and save to SQLite database."""
    if not title or not title.strip():
        return {"success": False, "error": "Task title is required."}

    valid_priorities = ["low", "medium", "high"]
    priority_val = priority.lower() if priority and priority.lower() in valid_priorities else "medium"
    due_date_val = due_date.strip() if due_date else "Not specified"

    try:
        async with AsyncSessionLocal() as session:
            task = Task(
                title=title.strip(),
                priority=priority_val,
                due_date=due_date_val,
                status="pending"
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)
            
            return {
                "success": True,
                "task": task.to_dict(),
                "message": f"Task '{task.title}' created with {task.priority} priority, due: {task.due_date}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to save task: {str(e)}"
        }

async def get_all_tasks() -> List[Dict[str, Any]]:
    """Retrieve all tasks from the database."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Task).order_by(Task.id.desc()))
        tasks = result.scalars().all()
        return [t.to_dict() for t in tasks]
