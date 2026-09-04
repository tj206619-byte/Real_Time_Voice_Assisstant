import pytest
from backend.database.db import init_db
from backend.tools.weather_tool import execute_get_weather
from backend.tools.reminder_tool import execute_create_reminder, get_all_reminders
from backend.tools.task_tool import execute_create_task, get_all_tasks

@pytest.mark.asyncio
async def test_weather_tool_success():
    """Test get_weather tool returns real weather data."""
    res = await execute_get_weather("Bangalore")
    assert res["success"] is True
    assert "Bangalore" in res["location"]
    assert "temperature" in res
    assert "condition" in res
    assert "tomorrow_forecast" in res

@pytest.mark.asyncio
async def test_weather_tool_invalid_location():
    """Test get_weather tool with empty string."""
    res = await execute_get_weather("")
    assert res["success"] is False
    assert "error" in res

@pytest.mark.asyncio
async def test_reminder_tool():
    """Test create_reminder tool and database persistence."""
    await init_db()
    res = await execute_create_reminder("Study DBMS", "tomorrow at 9 AM")
    assert res["success"] is True
    assert res["reminder"]["title"] == "Study DBMS"
    assert res["reminder"]["datetime"] == "tomorrow at 9 AM"
    
    all_reminders = await get_all_reminders()
    assert any(r["title"] == "Study DBMS" for r in all_reminders)

@pytest.mark.asyncio
async def test_task_tool():
    """Test create_task tool with priority and due date."""
    await init_db()
    res = await execute_create_task("Finish Python assignment", priority="high", due_date="Friday")
    assert res["success"] is True
    assert res["task"]["title"] == "Finish Python assignment"
    assert res["task"]["priority"] == "high"
    assert res["task"]["due_date"] == "Friday"
    
    all_tasks = await get_all_tasks()
    assert any(t["title"] == "Finish Python assignment" for t in all_tasks)
