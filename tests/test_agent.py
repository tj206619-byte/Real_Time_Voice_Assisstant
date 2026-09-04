import pytest
from backend.agent.agent import VoicePilotAgent
from backend.database.db import init_db

@pytest.mark.asyncio
async def test_agent_conversation_flow():
    """Test conversational flow without tool invocation."""
    agent = VoicePilotAgent()
    tokens = []
    async for t in agent.process_turn("Hello, what can you do?"):
        tokens.append(t)
    
    response = "".join(tokens)
    assert len(response) > 0
    assert "VoicePilot" in response or "weather" in response

@pytest.mark.asyncio
async def test_agent_weather_tool_flow():
    """Test agent selects and executes weather tool."""
    await init_db()
    agent = VoicePilotAgent()
    
    tool_invocations = []
    async def on_start(name, args):
        tool_invocations.append((name, args))

    tokens = []
    async for t in agent.process_turn("What's the weather in Bangalore?", on_tool_start=on_start):
        tokens.append(t)

    assert any(tool[0] == "get_weather" for tool in tool_invocations)
    response = "".join(tokens)
    assert "Bangalore" in response or "degrees" in response

@pytest.mark.asyncio
async def test_agent_follow_up_context():
    """Test conversational context retention on follow-up questions."""
    await init_db()
    agent = VoicePilotAgent()
    
    # Turn 1
    async for _ in agent.process_turn("What's the weather in Bangalore?"):
        pass

    # Turn 2: Follow-up
    tokens2 = []
    async for t in agent.process_turn("What about tomorrow?"):
        tokens2.append(t)
        
    res2 = "".join(tokens2)
    assert "tomorrow" in res2.lower()

@pytest.mark.asyncio
async def test_agent_cancellation():
    """Test stream stops immediately when cancelled."""
    agent = VoicePilotAgent()
    
    cancelled = True
    def is_cancelled():
        return cancelled

    tokens = []
    async for t in agent.process_turn("Tell me a story", is_cancelled=is_cancelled):
        tokens.append(t)

    assert len(tokens) == 0
