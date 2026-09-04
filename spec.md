# VoicePilot — Advanced Real-Time Voice Assistant
## Advanced-Only Project Specification

### 1. Objective

Build an advanced, low-latency, real-time voice assistant that continuously handles spoken interaction, uses an LLM with function/tool calling to perform real actions, streams spoken responses back to the user, and supports natural user interruption (barge-in).

This project must demonstrate a genuine real-time voice-agent architecture rather than a simple voice chatbot.

---

## 2. Required Advanced Capabilities

The implementation MUST include all of the following:

1. **Streaming Speech-to-Text**
   - Capture microphone audio continuously.
   - Stream audio to an STT service while the user is speaking.
   - Display partial/final transcription.

2. **LLM with Function/Tool Calling**
   - The LLM must decide whether a tool is required.
   - Implement 3 real tools:
     - Weather
     - Reminder
     - Task/Notes
   - Tool execution must happen through backend functions.
   - Tool results must be returned to the LLM before the final response.

3. **Streaming Text-to-Speech**
   - Convert the assistant response to speech.
   - Stream audio to the browser rather than waiting for a complete audio file when the provider supports it.
   - Begin playback as early as practical to reduce perceived latency.

4. **Barge-In / Interruption Handling**
   - The user must be able to interrupt the assistant while it is speaking.
   - Detect new user speech while TTS playback is active.
   - Stop/cancel current audio playback.
   - Cancel the obsolete assistant response where possible.
   - Process the new request immediately.

5. **Low-Latency Real-Time Transport**
   - Use WebSockets for bidirectional real-time communication.
   - Avoid unnecessary request/response polling.
   - Maintain a persistent voice session.

6. **Conversation State**
   - Maintain conversation context during a session.
   - Allow follow-up requests such as:
     - User: "What's the weather in Bangalore?"
     - Assistant: answers
     - User: "What about tomorrow?"
   - The assistant should understand the context.

7. **Tool Result Confirmation**
   - After a successful action, the assistant must verbally confirm what happened.
   - Example:
     - User: "Remind me tomorrow at 9 AM to study DBMS."
     - Tool creates reminder.
     - Assistant: "Done. I've created a reminder for tomorrow at 9 AM to study DBMS."

---

# 3. Advanced User Experience

The interface should behave like a real voice agent.

### Main states

- IDLE
- LISTENING
- THINKING
- TOOL_CALLING
- SPEAKING
- INTERRUPTED
- ERROR

The current state must be visible in the UI.

Example:

```text
                VOICEPILOT
        Real-Time AI Voice Assistant

                 ●
            Listening...

     "What's the weather in Bangalore?"

        ─────────────────────

        AI is checking the weather...

        Tool: weather()

        ─────────────────────

        🔊 Speaking...
```

The user should not need to click a submit button after every sentence.

---

# 4. Advanced Voice Pipeline

The primary architecture must be:

```text
             MICROPHONE
                  |
                  v
        Audio Capture / Stream
                  |
                  v
       Streaming Speech-to-Text
                  |
                  v
          Partial Transcript
                  |
                  v
         Turn Detection / VAD
                  |
                  v
          LLM + Tool Calling
             /     |                  /      |                  v       v        v
       Weather  Reminder   Tasks
           \       |        /
            \      |       /
             v     v       v
              Tool Results
                   |
                   v
              LLM Response
                   |
                   v
          Streaming Text-to-Speech
                   |
                   v
             Audio Playback
                   |
                   v
                USER
```

The system must support the reverse path when the user interrupts:

```text
Assistant Speaking
       |
       v
User Starts Speaking
       |
       v
Barge-In Detection
       |
       +--> Stop TTS Playback
       |
       +--> Cancel Old Response
       |
       +--> Start New STT Turn
       |
       v
New LLM Response
```

---

# 5. Recommended Advanced Technology Stack

### Frontend

- HTML5
- CSS3
- Vanilla JavaScript
- Web Audio API
- MediaRecorder / AudioWorklet where appropriate

### Backend

- Python 3.11+
- FastAPI
- AsyncIO
- WebSockets

### Speech-to-Text

Preferred:
- Deepgram streaming STT

Alternative:
- Another genuinely streaming Whisper-compatible STT service.

### LLM

Preferred:
- OpenAI API with function/tool calling.

The assistant must use structured tool definitions rather than manually parsing every command with hard-coded if/else statements.

### Text-to-Speech

Preferred:
- ElevenLabs streaming TTS

Alternative:
- Another provider that supports streaming audio.

### Database

- SQLite
- SQLAlchemy optional

SQLite is sufficient for reminders/tasks in this prototype.

### External API

- Weather API such as Open-Meteo or another reliable weather provider.

---

# 6. Tool Definitions

Implement exactly these 3 tools.

## Tool 1 — get_weather

Purpose:
Retrieve weather information.

Schema:

```json
{
  "name": "get_weather",
  "description": "Get current weather for a location",
  "parameters": {
    "location": "string"
  }
}
```

Example:

User:
"What's the weather in Bangalore?"

LLM:
Calls `get_weather(location="Bangalore")`

Tool:
Returns weather data.

LLM:
Generates a natural spoken response.

---

## Tool 2 — create_reminder

Purpose:
Create a reminder.

Schema:

```json
{
  "name": "create_reminder",
  "description": "Create a reminder for the user",
  "parameters": {
    "title": "string",
    "datetime": "string"
  }
}
```

Example:

User:
"Remind me tomorrow at 9 AM to study DBMS."

Expected:

```text
create_reminder(
    title="Study DBMS",
    datetime="tomorrow 09:00"
)
```

Store the reminder in SQLite.

---

## Tool 3 — create_task

Purpose:
Create a task.

Schema:

```json
{
  "name": "create_task",
  "description": "Create a task for the user",
  "parameters": {
    "title": "string",
    "priority": "string",
    "due_date": "string"
  }
}
```

Example:

User:
"Create a high-priority task to finish my Python assignment by Friday."

Expected tool call:

```text
create_task(
    title="Finish Python assignment",
    priority="high",
    due_date="Friday"
)
```

---

# 7. Intelligent Tool Selection

Do not route every request to a tool.

The LLM should determine:

### Normal conversation

```text
User → "Hello"
LLM → Direct response
```

### Tool request

```text
User → "What's the weather?"
LLM → Weather tool
     → Tool result
     → Final response
```

### Ambiguous request

If required information is missing, the assistant should ask a short clarification.

Example:

User:
"Set a reminder."

Assistant:
"What would you like me to remind you about?"

---

# 8. Streaming STT Requirements

The STT implementation must:

- Open a streaming connection.
- Send audio chunks incrementally.
- Receive partial transcripts.
- Receive final transcripts.
- Update the UI with partial text.
- Detect the end of a user turn.

Example:

```text
User speaking:
"I want to know the weather..."

UI:
I want to know the weather...

User continues:
"...in Bangalore."

UI:
I want to know the weather in Bangalore.

Turn complete
        ↓
Send to LLM
```

---

# 9. Voice Activity Detection / Turn Detection

Implement practical turn detection.

The system should determine when:

- User started speaking.
- User is still speaking.
- User stopped speaking.

Preferred approach:
- Use provider-supported endpointing/VAD when available.
- Otherwise implement a simple audio-level/silence threshold.

Do not wait for an arbitrary long timeout after every sentence.

---

# 10. Streaming TTS Requirements

The assistant must not behave like:

```text
Generate entire response
        ↓
Generate entire audio file
        ↓
Play audio
```

Instead, where the selected TTS provider supports it:

```text
LLM response chunks
        ↓
TTS streaming
        ↓
Audio chunks
        ↓
Immediate playback
```

This reduces perceived response latency.

---

# 11. Barge-In Implementation

This is a mandatory Advanced feature.

Scenario:

```text
Assistant:
"The current weather in Bangalore is 27 degrees and—"

User:
"Stop. What about tomorrow?"
```

Required behavior:

```text
1. Detect user speech.
2. Stop current TTS playback immediately.
3. Cancel/ignore the old response.
4. Clear obsolete audio chunks.
5. Start processing the new utterance.
6. Return the new answer.
```

Use a response/session identifier so stale audio cannot continue playing after an interruption.

Example concept:

```text
response_id = 42

New user speech detected
        ↓
cancel response 42
        ↓
create response 43
        ↓
only play audio belonging to response 43
```

---

# 12. WebSocket Protocol

Use a persistent WebSocket between browser and backend.

Suggested message types:

### Client → Server

```json
{
  "type": "audio_chunk",
  "data": "..."
}
```

```json
{
  "type": "interrupt"
}
```

```json
{
  "type": "session_start"
}
```

### Server → Client

```json
{
  "type": "transcript_partial",
  "text": "What's the weather..."
}
```

```json
{
  "type": "transcript_final",
  "text": "What's the weather in Bangalore?"
}
```

```json
{
  "type": "state",
  "value": "tool_calling"
}
```

```json
{
  "type": "tool_result",
  "tool": "get_weather",
  "result": {}
}
```

```json
{
  "type": "audio_chunk",
  "data": "..."
}
```

```json
{
  "type": "error",
  "message": "..."
}
```

The exact protocol may be adapted to the selected providers.

---

# 13. Latency Requirements

Measure latency rather than claiming a number without testing.

Track:

```text
speech_end → transcript_final
transcript_final → LLM_start
LLM_start → tool_call
tool_call → tool_result
tool_result → first_response_token
first_response_token → first_audio
```

Display development metrics if practical:

```text
First Audio: 0.82s
Tool Latency: 0.31s
Total Response Start: 1.14s
```

### Stretch target

Attempt approximately:

**< 1.5 seconds round-trip latency**

but only after the mandatory features are stable.

---

# 14. Conversation Memory

Maintain a session history.

Example:

```text
User:
What's the weather in Bangalore?

Assistant:
It's currently...

User:
Will I need an umbrella?

Assistant:
Based on the forecast...
```

The assistant should understand that "Will I need an umbrella?" refers to the weather context.

Keep the conversation history bounded to avoid uncontrolled token growth.

---

# 15. Advanced Error Handling

The application must recover from:

- Microphone permission denial
- WebSocket disconnect
- STT timeout
- STT provider failure
- LLM timeout
- Invalid tool arguments
- Weather API failure
- Database failure
- TTS failure
- User interruption during tool execution
- Network failure

Example:

```text
Weather service unavailable.

I couldn't retrieve the weather right now.
Please try again.
```

Never expose raw stack traces or API keys to the user.

---

# 16. Security Requirements

Use environment variables:

```text
OPENAI_API_KEY=
DEEPGRAM_API_KEY=
ELEVENLABS_API_KEY=
WEATHER_API_KEY=
```

Never put secret keys in frontend JavaScript.

Include:

```text
.env
```

in `.gitignore`.

Provide:

```text
.env.example
```

with empty/placeholder values.

---

# 17. Recommended Project Structure

```text
voicepilot/
│
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── websocket/
│   │   └── voice_session.py
│   │
│   ├── agent/
│   │   ├── agent.py
│   │   ├── prompts.py
│   │   └── tool_registry.py
│   │
│   ├── services/
│   │   ├── stt.py
│   │   ├── tts.py
│   │   └── weather.py
│   │
│   ├── tools/
│   │   ├── weather_tool.py
│   │   ├── reminder_tool.py
│   │   └── task_tool.py
│   │
│   ├── database/
│   │   ├── db.py
│   │   └── models.py
│   │
│   └── requirements.txt
│
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
│
├── tests/
│   ├── test_tools.py
│   └── test_agent.py
│
├── .env.example
├── .gitignore
└── README.md
```

---

# 18. System Prompt Requirements

The assistant should be instructed to:

- Be concise because responses are spoken.
- Use tools when appropriate.
- Never claim an action was completed unless the tool succeeded.
- Ask for missing information.
- Preserve conversation context.
- Handle tool failures honestly.
- Avoid unnecessarily long responses.

Example behavior:

```text
You are VoicePilot, a concise real-time voice assistant.

You can:
1. Get weather.
2. Create reminders.
3. Create tasks.

Use tools when the user requests an action.
Never pretend a tool action succeeded if it failed.
Ask a short clarification question when required information is missing.
Keep spoken answers natural and concise.
```

---

# 19. Testing Requirements

Test at minimum:

### Test 1 — Normal conversation

"Hello, what can you do?"

Expected:
No tool call.

### Test 2 — Weather

"What's the weather in Bangalore?"

Expected:
`get_weather`

### Test 3 — Reminder

"Remind me tomorrow at 9 AM to study DBMS."

Expected:
`create_reminder`

### Test 4 — Task

"Create a high-priority task to finish my Python assignment."

Expected:
`create_task`

### Test 5 — Follow-up

"What's the weather in Bangalore?"
Then:
"What about tomorrow?"

Expected:
Conversation context is retained.

### Test 6 — Missing information

"Set a reminder."

Expected:
Assistant asks what to remind the user about.

### Test 7 — Barge-in

Interrupt the assistant while it is speaking.

Expected:
Current speech stops and the new request is processed.

### Test 8 — Tool failure

Simulate weather API failure.

Expected:
Friendly spoken error.

### Test 9 — Network failure

Disconnect WebSocket.

Expected:
UI returns to a recoverable state.

---

# 20. Advanced Demo Scenario

The final demo should demonstrate the complete system in approximately 2–3 minutes.

Recommended sequence:

### Demo 1

User:
"Hello VoicePilot."

Assistant responds by voice.

### Demo 2

User:
"What's the weather in Bangalore?"

Assistant:
Uses weather tool and speaks result.

### Demo 3

User:
"Remind me tomorrow at 9 AM to study DBMS."

Assistant:
Creates reminder and confirms by voice.

### Demo 4

User:
"Create a high priority task to finish my Python assignment."

Assistant:
Creates task and confirms.

### Demo 5 — Follow-up

User:
"What's the weather in Bangalore?"

Assistant answers.

User:
"And will I need an umbrella?"

Assistant uses conversation context.

### Demo 6 — Advanced Barge-In

Assistant starts a longer spoken response.

User interrupts:
"Stop. Create a task instead."

Assistant stops speaking and immediately processes the new request.

This final interaction is especially important because it visibly demonstrates the Advanced requirement.

---

# 21. Optional Stretch Goals

Only implement these after all mandatory features work.

### Stretch Goal A — Wake Word

Example:

"Hey VoicePilot"

Then begin active listening.

### Stretch Goal B — Latency Optimization

Target:

```text
< 1.5 seconds
```

Measure actual latency.

### Stretch Goal C — Voice Activity Visualization

Show a live microphone waveform/audio-level indicator.

### Stretch Goal D — Tool Activity Panel

Show:

```text
Thinking...
↓
Calling get_weather()
↓
Tool completed
↓
Speaking...
```

Do not sacrifice core reliability for stretch goals.

---

# 22. Evaluation Alignment

The project must clearly satisfy the six assessment categories.

## 1. End-to-End Functionality

Demonstrate:

```text
Voice
→ Streaming STT
→ LLM
→ Tool
→ Tool Result
→ LLM
→ Streaming TTS
→ Voice
```

## 2. Thoughtful LLM Use

The LLM performs actual tool selection and structured function calling.

## 3. Speech-Handling Quality

Demonstrate:
- streaming STT
- streaming TTS
- turn detection
- interruption/barge-in

## 4. Code Quality & Structure

Keep:
- agent logic
- tools
- STT
- TTS
- database
- WebSocket session
- frontend

separated into logical modules.

## 5. Documentation

README must explain:
- architecture
- setup
- environment variables
- API providers
- tool definitions
- real-time flow
- interruption strategy
- latency measurement
- assumptions
- trade-offs
- known limitations
- testing
- AI coding assistant usage

## 6. Creativity / Stretch Goals

Wake word, latency optimization, visual voice feedback, and tool activity visualization are optional enhancements.

---

# 23. GitHub Requirements

Commit incrementally.

Recommended commit sequence:

```text
Initial project setup
Add FastAPI WebSocket server
Add microphone audio streaming
Add streaming speech-to-text
Add LLM agent
Add tool calling framework
Add weather tool
Add reminder tool
Add task tool
Add SQLite persistence
Add streaming TTS
Add barge-in handling
Add conversation memory
Add latency metrics
Improve error handling
Add UI states
Add tests
Add README
Final submission cleanup
```

Do not make the project appear as one single final commit.

---

# 24. AI Coding Assistant Disclosure

If ChatGPT, GitHub Copilot, Claude, Gemini, Cursor, or another AI coding assistant is used, state this honestly in the README.

Example:

> AI Coding Assistant Usage: AI coding assistants were used for implementation guidance, debugging, API integration assistance, code review suggestions, and documentation support. The implementation was reviewed, tested, and integrated by the author.

Do not claim tools that were not actually used.

---

# 25. Definition of Done — Advanced

The project is complete only when ALL mandatory requirements below work:

[ ] Real-time microphone audio capture  
[ ] Streaming speech-to-text  
[ ] Partial/final transcript handling  
[ ] Turn detection/VAD  
[ ] LLM integration  
[ ] LLM function/tool calling  
[ ] Weather tool  
[ ] Reminder tool  
[ ] Task tool  
[ ] Real tool execution  
[ ] Tool result returned to LLM  
[ ] Streaming TTS  
[ ] Real-time audio playback  
[ ] Barge-in detection  
[ ] TTS cancellation on interruption  
[ ] New request processing after interruption  
[ ] WebSocket communication  
[ ] Session conversation context  
[ ] Error handling  
[ ] API key protection  
[ ] SQLite persistence  
[ ] Basic tests  
[ ] Incremental Git commits  
[ ] Complete README  
[ ] Working end-to-end demonstration  

Optional:

[ ] Wake word  
[ ] <1.5 second measured latency  
[ ] Voice waveform  
[ ] Tool activity visualization

---

## Final Principle

Build an **advanced real-time voice agent**, not a collection of disconnected features.

The evaluator should be able to see and hear this complete behavior:

**Speak → Understand while speaking → Reason → Choose a tool → Perform a real action → Respond quickly by voice → Get interrupted naturally → Continue with the new request.**

That end-to-end experience is the primary goal.
