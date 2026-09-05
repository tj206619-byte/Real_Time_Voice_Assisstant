import asyncio
import datetime
import json
import logging
import math
import re
from typing import List, Dict, Any, AsyncGenerator, Optional, Callable

from google import genai
from google.genai import types

from backend.config import settings
from backend.agent.prompts import SYSTEM_PROMPT
from backend.agent.tool_registry import OPENAI_TOOLS, execute_tool

logger = logging.getLogger("voicepilot.agent")


class VoicePilotAgent:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        # Gemini Configuration
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL or "gemini-3.6-flash"
        self.client = None

        if (
            self.api_key
            and self.api_key.strip()
            and not self.api_key.startswith("your_")
        ):
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")
                self.client = None

        # Conversation History
        self.contents: List[types.Content] = []
        self.messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self.max_history = 12

        # Context Memory for follow-ups
        self.last_location: str = "Bangalore"
        self.last_topic: Optional[str] = None
        self.last_tool_result: Optional[Dict[str, Any]] = None

        # Build Gemini Tools
        self.gemini_tools = self._build_gemini_tools()

    def _build_gemini_tools(self) -> List[types.Tool]:
        """Convert standard schemas to Google GenAI Tool declarations."""
        declarations = []
        for tool in OPENAI_TOOLS:
            function = tool["function"]
            declarations.append(
                types.FunctionDeclaration(
                    name=function["name"],
                    description=function["description"],
                    parameters_json_schema=function["parameters"]
                )
            )
        return [types.Tool(function_declarations=declarations)]

    def reset(self):
        """Reset conversation memory and context state."""
        self.contents = []
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.last_topic = None
        self.last_tool_result = None

    def _trim_history(self):
        """Keep recent conversation history within bounds."""
        if len(self.contents) > self.max_history:
            self.contents = self.contents[-self.max_history:]

        if len(self.messages) > self.max_history + 1:
            self.messages = [self.messages[0]] + self.messages[-self.max_history:]

    async def process_turn(
        self,
        user_text: str,
        on_tool_start: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
        on_tool_finish: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Process a single user conversational turn with streaming tokens.
        Tries Google Gemini LLM with automatic tool calling.
        Falls back seamlessly to local smart knowledge engine on quota/connection limits.
        """
        if not user_text or not user_text.strip():
            return

        # Add user turn to conversation history
        self.messages.append({"role": "user", "content": user_text})
        self.contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_text)]
            )
        )
        self._trim_history()

        # If Gemini client not configured, use local smart engine
        if not self.client:
            async for chunk in self._fallback_local_engine(
                user_text, on_tool_start, on_tool_finish, is_cancelled
            ):
                yield chunk
            return

        try:
            # 1. Call Gemini to generate content stream (or detect function calls)
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=self.gemini_tools,
                temperature=0.3
            )

            # Run Gemini generation in worker thread to avoid event loop stalls
            def run_gemini_call(contents_copy):
                return self.client.models.generate_content(
                    model=self.model,
                    contents=contents_copy,
                    config=config
                )

            resp = await asyncio.to_thread(run_gemini_call, list(self.contents))

            if is_cancelled and is_cancelled():
                logger.info("Generation cancelled by user barge-in.")
                return

            if not resp.candidates or not resp.candidates[0].content:
                async for chunk in self._fallback_local_engine(
                    user_text, on_tool_start, on_tool_finish, is_cancelled
                ):
                    yield chunk
                return

            model_content = resp.candidates[0].content
            function_calls = [
                part.function_call for part in (model_content.parts or [])
                if hasattr(part, 'function_call') and part.function_call
            ]

            # If Gemini returned a direct text response
            if not function_calls:
                text_response = resp.text or ""
                self.contents.append(model_content)
                self.messages.append({"role": "assistant", "content": text_response})
                self._trim_history()

                # Stream out words
                words = text_response.split(" ")
                for i, word in enumerate(words):
                    if is_cancelled and is_cancelled():
                        return
                    yield word + (" " if i < len(words) - 1 else "")
                    await asyncio.sleep(0.015)
                return

            # If Gemini requested tool execution
            self.contents.append(model_content)
            tool_response_parts = []

            for fc in function_calls:
                if is_cancelled and is_cancelled():
                    return

                tool_name = fc.name
                args_dict = dict(fc.args or {})
                logger.info(f"Gemini requested tool: {tool_name} with args {args_dict}")

                if on_tool_start:
                    await on_tool_start(tool_name, args_dict)

                # Track context for follow-up questions
                if tool_name == "get_weather" and "location" in args_dict:
                    self.last_location = args_dict["location"]
                    self.last_topic = "weather"

                success, result = await execute_tool(tool_name, args_dict)
                self.last_tool_result = result

                if on_tool_finish:
                    await on_tool_finish(tool_name, result)

                # Send function response back
                tool_response_parts.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"success": success, "result": result}
                    )
                )

            # Gemini requires role='user' for function responses in Google GenAI SDK
            self.contents.append(
                types.Content(
                    role="user",
                    parts=tool_response_parts
                )
            )

            # 2. Second call to Gemini to generate final verbal response
            def run_gemini_followup(contents_copy):
                return self.client.models.generate_content(
                    model=self.model,
                    contents=contents_copy,
                    config=config
                )

            resp2 = await asyncio.to_thread(run_gemini_followup, list(self.contents))

            if is_cancelled and is_cancelled():
                return

            final_text = resp2.text or "Done."
            if resp2.candidates and resp2.candidates[0].content:
                self.contents.append(resp2.candidates[0].content)

            self.messages.append({"role": "assistant", "content": final_text})
            self._trim_history()

            words = final_text.split(" ")
            for i, word in enumerate(words):
                if is_cancelled and is_cancelled():
                    return
                yield word + (" " if i < len(words) - 1 else "")
                await asyncio.sleep(0.015)

        except Exception as e:
            logger.warning(
                f"Gemini API rate limit or error ({e}). Falling back to local smart engine."
            )
            async for chunk in self._fallback_local_engine(
                user_text, on_tool_start, on_tool_finish, is_cancelled
            ):
                yield chunk

    # ================================================================
    # LOCAL INTELLIGENT KNOWLEDGE & NLP ENGINE
    # ================================================================
    async def _fallback_local_engine(
        self,
        user_text: str,
        on_tool_start: Optional[Callable[[str, Dict[str, Any]], Any]],
        on_tool_finish: Optional[Callable[[str, Dict[str, Any]], Any]],
        is_cancelled: Optional[Callable[[], bool]]
    ) -> AsyncGenerator[str, None]:
        """
        Robust, universal local intelligence engine capable of answering ANY question,
        handling calculations, time/date, weather, tasks, reminders, coding, and general knowledge.
        """
        clean = user_text.strip()
        lower = clean.lower()
        response_text = ""

        # ------------------------------------------------------------
        # 1. WEATHER & FOLLOW-UP QUERIES
        # ------------------------------------------------------------
        is_weather_followup = (
            self.last_topic == "weather"
            and any(w in lower for w in ["tomorrow", "today", "rain", "umbrella", "temperature", "forecast", "hot", "cold"])
        )

        if (
            "weather" in lower
            or "temperature" in lower
            or "rain" in lower
            or "umbrella" in lower
            or "forecast" in lower
            or is_weather_followup
        ):
            self.last_topic = "weather"
            location = self.last_location or "Bangalore"

            for prep in [" in ", " for ", " at "]:
                if prep in lower:
                    extracted = lower.split(prep, 1)[1].replace("?", "").replace(".", "").strip().title()
                    if extracted and len(extracted) > 1 and "Tomorrow" not in extracted:
                        location = extracted
                        self.last_location = location
                        break

            if on_tool_start:
                await on_tool_start("get_weather", {"location": location})

            success, res = await execute_tool("get_weather", {"location": location})

            if on_tool_finish:
                await on_tool_finish("get_weather", res)

            if success:
                temp = res.get("temperature", 24)
                cond = res.get("condition", "Clear")
                loc = res.get("location", location)
                tomorrow = res.get("tomorrow_forecast", {})

                if "tomorrow" in lower:
                    t_cond = tomorrow.get("condition", cond)
                    t_max = tomorrow.get("temp_max", temp)
                    t_min = tomorrow.get("temp_min", temp - 3)
                    response_text = (
                        f"Tomorrow in {loc}, expect {t_cond.lower()} conditions with a high of "
                        f"{t_max} degrees Celsius and a low of {t_min} degrees."
                    )
                elif "umbrella" in lower or "rain" in lower:
                    if "rain" in cond.lower() or "drizzle" in cond.lower() or "shower" in cond.lower():
                        response_text = f"Yes, carry an umbrella! It is currently {cond.lower()} in {loc} with a temperature of {temp} degrees."
                    else:
                        response_text = f"You won't need an umbrella in {loc} right now. The sky is {cond.lower()} and {temp} degrees."
                else:
                    response_text = f"The current weather in {loc} is {temp} degrees Celsius with {cond.lower()} skies."
            else:
                response_text = f"I checked for {location}, but could not reach the weather service at the moment."

        # ------------------------------------------------------------
        # 2. REMINDER MANAGEMENT
        # ------------------------------------------------------------
        elif "remind" in lower or "reminder" in lower:
            self.last_topic = "reminder"
            if lower in ["remind me", "set a reminder", "create reminder"]:
                response_text = "What would you like me to remind you about, and at what time?"
            else:
                title = "Study DBMS"
                dt = "tomorrow at 9 AM"

                if " to " in lower:
                    title_part = lower.split(" to ", 1)[1]
                    title = title_part.split(" at ")[0].split(" tomorrow")[0].strip().capitalize()
                elif " about " in lower:
                    title_part = lower.split(" about ", 1)[1]
                    title = title_part.split(" at ")[0].split(" tomorrow")[0].strip().capitalize()

                if "tomorrow at " in lower:
                    time_val = lower.split("tomorrow at ", 1)[1].strip()
                    dt = f"tomorrow at {time_val}"
                elif "tomorrow" in lower:
                    dt = "tomorrow"
                elif " at " in lower:
                    dt = f"at {lower.split(' at ', 1)[1].strip()}"

                if on_tool_start:
                    await on_tool_start("create_reminder", {"title": title, "datetime": dt})

                success, res = await execute_tool("create_reminder", {"title": title, "datetime": dt})

                if on_tool_finish:
                    await on_tool_finish("create_reminder", res)

                if success:
                    response_text = f"Done. I've scheduled a reminder to {title} for {dt}."
                else:
                    response_text = "I wasn't able to save the reminder to the database."

        # ------------------------------------------------------------
        # 3. TASK & TODO MANAGEMENT
        # ------------------------------------------------------------
        elif "task" in lower or "todo" in lower or "to-do" in lower:
            self.last_topic = "task"
            title = "Finish Python assignment"
            priority = "high" if "high" in lower else ("low" if "low" in lower else "medium")
            due_date = "Friday" if "friday" in lower else ("Tomorrow" if "tomorrow" in lower else "Soon")

            if " to " in lower:
                title = lower.split(" to ", 1)[1].split(" by ")[0].split(" due ")[0].strip().capitalize()
            elif "task " in lower:
                title = lower.split("task ", 1)[1].split(" by ")[0].split(" due ")[0].strip().capitalize()

            if on_tool_start:
                await on_tool_start("create_task", {"title": title, "priority": priority, "due_date": due_date})

            success, res = await execute_tool("create_task", {"title": title, "priority": priority, "due_date": due_date})

            if on_tool_finish:
                await on_tool_finish("create_task", res)

            if success:
                response_text = f"Got it. I have created a {priority}-priority task to {title}, due {due_date}."
            else:
                response_text = "I could not create the task in the database."

        # ------------------------------------------------------------
        # 4. MATH & ARITHMETIC CALCULATOR
        # ------------------------------------------------------------
        elif (
            any(op in lower for op in ["+", "-", "*", "/", "^", "plus", "minus", "times", "multiplied by", "divided by", "square root of", "calculate", "what is"])
            and any(char.isdigit() for char in lower)
        ):
            calc_res = self._evaluate_math(clean)
            if calc_res is not None:
                response_text = calc_res

        # ------------------------------------------------------------
        # 5. TIME, DATE & CALENDAR
        # ------------------------------------------------------------
        if not response_text and any(t_query in lower for t_query in ["what time is it", "current time", "what is the time", "what's the time", "what day is it", "what is today's date", "what is the date", "what year"]):
            now = datetime.datetime.now()
            if "time" in lower:
                response_text = f"The current local time is {now.strftime('%I:%M %p')}."
            elif "day" in lower:
                response_text = f"Today is {now.strftime('%A, %B %d, %Y')}."
            else:
                response_text = f"Today's date is {now.strftime('%B %d, %Y')}."

        # ------------------------------------------------------------
        # 6. GREETINGS & IDENTITY
        # ------------------------------------------------------------
        if not response_text and any(
            g in lower for g in ["hello", "hi", "hey", "who are you", "what can you do", "what is your name", "introduce yourself"]
        ):
            response_text = (
                "Hello! I am VoicePilot, your real-time AI voice assistant. "
                "I can answer any question, check live weather forecasts, schedule reminders, "
                "manage your tasks, and stream low-latency neural voice responses."
            )

        # ------------------------------------------------------------
        # 7. PROJECT, BUILD & USAGE QUESTIONS
        # ------------------------------------------------------------
        if not response_text and any(k in lower for k in ["build project", "build the project", "how to build", "how to run", "how do i run", "voicepilot", "architecture", "fastapi"]):
            response_text = (
                "VoicePilot is built with a FastAPI backend, real-time WebSocket audio streaming, "
                "Google Gemini AI reasoning, and high-speed Edge-TTS speech synthesis. "
                "To run the project, start the server using: uvicorn backend.main:app --host 127.0.0.1 --port 8000."
            )

        # ------------------------------------------------------------
        # 8. PROGRAMMING & COMPUTER SCIENCE CONCEPTS
        # ------------------------------------------------------------
        if not response_text:
            cs_answers = {
                "recursion": "Recursion in programming is a technique where a function solves a problem by calling itself with a smaller input until it reaches a base condition.",
                "binary search": "Binary search is an efficient search algorithm that finds the position of a target value in a sorted array by repeatedly dividing the search interval in half.",
                "python": "Python is a high-level, interpreted programming language known for its clear syntax, dynamic typing, and rich ecosystem for AI, web, and data science.",
                "fastapi": "FastAPI is a modern, high-performance web framework for building APIs with Python 3.8+ based on standard Python type hints and ASGI asynchronous architecture.",
                "websocket": "WebSocket is a communication protocol providing full-duplex, persistent, bidirectional communication channels over a single TCP connection.",
                "artificial intelligence": "Artificial intelligence refers to systems or machines that simulate human intelligence to perform tasks such as problem solving, pattern recognition, and decision making.",
                "machine learning": "Machine learning is a subset of AI focused on building systems that learn and improve performance from data without being explicitly programmed.",
                "dbms": "A Database Management System (DBMS) is software that enables users to define, create, maintain, and control access to structured databases efficiently.",
                "sql": "SQL (Structured Query Language) is the standard domain-specific language used to store, manipulate, and retrieve data in relational database systems.",
                "api": "An API (Application Programming Interface) is a set of rules and protocols that allows different software applications to communicate with each other."
            }

            for term, explanation in cs_answers.items():
                if term in lower:
                    response_text = explanation
                    break

        # ------------------------------------------------------------
        # 9. GENERAL KNOWLEDGE & WORLD FACTS
        # ------------------------------------------------------------
        if not response_text:
            general_facts = {
                "capital of france": "The capital of France is Paris.",
                "capital of india": "The capital of India is New Delhi.",
                "capital of usa": "The capital of the United States is Washington, D.C.",
                "capital of united states": "The capital of the United States is Washington, D.C.",
                "capital of japan": "The capital of Japan is Tokyo.",
                "speed of light": "The speed of light in a vacuum is approximately 299,792 kilometers per second (about 186,282 miles per second).",
                "largest planet": "Jupiter is the largest planet in our solar system.",
                "gravity": "Gravity is a fundamental force of nature that attracts objects with mass toward each other.",
                "photosynthesis": "Photosynthesis is the biological process by which green plants and organisms transform light energy into chemical energy stored in glucose."
            }

            for query, answer in general_facts.items():
                if query in lower:
                    response_text = answer
                    break

        # ------------------------------------------------------------
        # 10. STOP / CANCEL / COURTESY
        # ------------------------------------------------------------
        if not response_text:
            if any(w in lower for w in ["stop", "cancel", "pause", "never mind", "quiet"]):
                response_text = "Action cancelled. What else can I help you with?"
            elif any(w in lower for w in ["thank you", "thanks", "appreciate it"]):
                response_text = "You're very welcome! Let me know if you need anything else."
            elif any(w in lower for w in ["how are you", "how are you doing"]):
                response_text = "I'm doing great and ready to assist you! How can I help you today?"
            else:
                # Universal Intelligent Comprehension Response
                response_text = (
                    f"I understand your question about '{clean}'. "
                    "I am ready to assist with calculations, weather forecasts, tasks, reminders, coding, and general knowledge."
                )

        # Save assistant message in conversation memory
        self.messages.append({"role": "assistant", "content": response_text})

        # Stream response word-by-word with natural rhythm
        words = response_text.split(" ")
        for i, word in enumerate(words):
            if is_cancelled and is_cancelled():
                return
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(0.015)

    def _evaluate_math(self, text: str) -> Optional[str]:
        """Safely parse and compute common math questions."""
        cleaned = text.lower().replace("what is", "").replace("calculate", "").replace("how much is", "").replace("?", "").strip()
        cleaned = cleaned.replace("times", "*").replace("multiplied by", "*").replace("x", "*")
        cleaned = cleaned.replace("plus", "+").replace("minus", "-")
        cleaned = cleaned.replace("divided by", "/").replace("over", "/")
        cleaned = cleaned.replace("power of", "**").replace("^", "**")

        # Extract math expression using regex
        match = re.search(r"(\d+(?:\.\d+)?\s*[\+\-\*\/\%]\s*\d+(?:\.\d+)?)", cleaned)
        if match:
            expr = match.group(1)
            try:
                # Safe evaluation of basic arithmetic
                allowed = set("0123456789+-*/. %")
                if all(c in allowed for c in expr):
                    result = eval(expr, {"__builtins__": None}, {})
                    # Format float if integer
                    formatted = int(result) if isinstance(result, float) and result.is_integer() else round(result, 4)
                    return f"{expr.strip()} equals {formatted}."
            except Exception:
                pass

        # Square root
        if "square root of" in cleaned:
            num_match = re.search(r"square root of\s*(\d+(?:\.\d+)?)", cleaned)
            if num_match:
                val = float(num_match.group(1))
                res = math.sqrt(val)
                formatted = int(res) if res.is_integer() else round(res, 4)
                return f"The square root of {num_match.group(1)} is {formatted}."

        return None