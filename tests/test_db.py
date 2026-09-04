import pytest
from backend.database.db import init_db, AsyncSessionLocal
from backend.database.models import Reminder, Task
from sqlalchemy import select

@pytest.mark.asyncio
async def test_db_init_and_crud():
    """Verify SQLite tables and async CRUD operations."""
    await init_db()
    
    async with AsyncSessionLocal() as session:
        # Create Reminder
        rem = Reminder(title="Test Reminder", datetime="2026-09-05 10:00")
        session.add(rem)
        
        # Create Task
        tsk = Task(title="Test Task", priority="medium", due_date="Next Week")
        session.add(tsk)
        
        await session.commit()
        await session.refresh(rem)
        await session.refresh(tsk)
        
        assert rem.id is not None
        assert tsk.id is not None
        
        # Query items
        rem_res = await session.execute(select(Reminder).where(Reminder.id == rem.id))
        queried_rem = rem_res.scalar_one_or_none()
        assert queried_rem is not None
        assert queried_rem.title == "Test Reminder"
        
        tsk_res = await session.execute(select(Task).where(Task.id == tsk.id))
        queried_tsk = tsk_res.scalar_one_or_none()
        assert queried_tsk is not None
        assert queried_tsk.title == "Test Task"
