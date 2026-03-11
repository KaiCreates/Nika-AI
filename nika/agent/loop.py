"""ReAct agent loop — core of Nika AI."""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, Callable

from loguru import logger

from nika.agent.auto_memory import auto_save
from nika.agent.context_builder import build_context
from nika.agent.planner import create_plan, needs_planning
from nika.agent.response_parser import ParseResult, parse_response
from nika.agent.safety import classify_tool_call, is_allowed
from nika.config import NikaConfig
from nika.llm.client import OllamaClient
from nika.logging.audit_logger import AuditLogger
from nika.logging.event_bus import EventBus, EventType
from nika.tools.registry import ToolRegistry


@dataclass
class AgentEvent:
    type: str                        # thinking | tool_start | tool_end | llm_chunk | final | error | plan | safety
    content: str = ""
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: str = ""
    risk: str = ""
    plan_steps: list[str] = field(default_factory=list)
    step_index: int = 0


# Sentinel: caller injects this to pause for confirmation on DANGEROUS ops
ConfirmCallback = Callable[[str, str, dict], "asyncio.Future[bool]"]


class AgentLoop:
    def __init__(
        self,
        config: NikaConfig,
        llm_client: OllamaClient,
        tool_registry: ToolRegistry,
        memory_manager: Any,
        audit_logger: AuditLogger,
        event_bus: EventBus,
        session_id: str | None = None,
        confirm_callback: ConfirmCallback | None = None,
    ) -> None:
        self.config = config
        self.llm = llm_client
        self.tools = tool_registry
        self.memory = memory_manager
        self.audit = audit_logger
        self.bus = event_bus
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.confirm_callback = confirm_callback

        # Inject current loop for memory/history tools
        from nika.tools.memory_tools import SummarizeSessionTool
        SummarizeSessionTool.current_loop = self

        self.messages: list[dict[str, str]] = []
        self._interrupt = False
        self._recent_calls: list[tuple[str, str]] = []  # (tool, args_str) for loop detection

    def interrupt(self) -> None:
        """Signal the loop to stop after the current tool."""
        self._interrupt = True

    async def run(self, task: str) -> AsyncGenerator[AgentEvent, None]:
        """Run the ReAct loop for a task, yielding AgentEvents."""
        self._interrupt = False
        task_id = str(uuid.uuid4())[:8]

        await self.audit.log("task_start", {"task_id": task_id, "task": task, "session_id": self.session_id})

        # Phase 0: Query memory
        memories = []
        episodes = []
        if self.memory:
            try:
                memories = await self.memory.recall(query=task, top_k=self.config.memory.semantic_top_k)
                episodes = await self.memory.recent_episodes(n=self.config.memory.episodic_load_count)
            except Exception as e:
                logger.warning(f"Memory query failed: {e}")

        # Phase 1: Plan if needed
        plan_steps: list[str] = []
        if needs_planning(task):
            try:
                plan_steps = await create_plan(task, self.llm, self.config.active_model)
                yield AgentEvent(type="plan", plan_steps=plan_steps)
                await self.bus.publish(EventType.PLAN_CREATED, {"steps": plan_steps})
            except Exception as e:
                logger.warning(f"Planning failed: {e}")

        # Auto-extract and persist any personal facts in the user message
        if self.memory:
            saved = await auto_save(task, self.memory)
            if saved:
                yield AgentEvent(type="memory_saved", content=f"Auto-saved {len(saved)} fact(s) from your message.")

        self.messages.append({"role": "user", "content": task})

        step = 0
        max_steps = self.config.agent.max_steps

        while step < max_steps and not self._interrupt:
            step += 1
            logger.debug(f"Agent loop step {step}/{max_steps}")

            # Build context
            ctx_messages = build_context(
                messages=self.messages,
                tool_manifest=self.tools.manifest(),
                memories=memories,
                episodes=episodes,
                token_limit=self.config.agent.context_limit,
            )

            # Phase 2: Stream LLM response — filter out <tool_call>, <thinking>, <final_answer> tags
            full_response = ""
            await self.bus.publish(EventType.LLM_STARTED, {"step": step})
            try:
                _buf = ""          # partial-tag lookahead buffer
                _state = "normal"  # normal | in_tool_call | in_thinking | in_final_answer
                _CLOSE = {"in_tool_call": "</tool_call>", "in_thinking": "</thinking>", "in_final_answer": "</final_answer>"}
                _OPEN  = {"<tool_call>": "in_tool_call", "<thinking>": "in_thinking", "<final_answer>": "in_final_answer"}

                async for chunk in self.llm.chat_stream(
                    model=self.config.active_model,
                    messages=ctx_messages,
                ):
                    full_response += chunk
                    # Don't publish raw chunks here, the AgentEvent llm_chunk handles the filtered output
                    _buf += chunk

                    # State-machine: emit only visible text, hide tool_call/thinking blocks
                    while _buf:
                        if _state == "normal":
                            # Find earliest opening tag
                            earliest, earliest_tag = len(_buf), None
                            for tag in _OPEN:
                                idx = _buf.find(tag)
                                if 0 <= idx < earliest:
                                    earliest, earliest_tag = idx, tag
                            
                            # Check for partial tag boundary (e.g. "<think" at the end of buffer)
                            partial_idx = _buf.rfind("<")
                            # If we see a "<" but haven't found a full tag yet, and it's near the end
                            if earliest_tag is None and partial_idx >= 0 and partial_idx > len(_buf) - 20:
                                # Yield everything up to the "<" and keep the rest in buffer
                                if partial_idx > 0:
                                    yield AgentEvent(type="llm_chunk", content=_buf[:partial_idx])
                                    _buf = _buf[partial_idx:]
                                break # wait for next chunk
                            
                            # If a full tag was found
                            if earliest_tag:
                                # Yield text before the tag
                                if earliest > 0:
                                    yield AgentEvent(type="llm_chunk", content=_buf[:earliest])
                                # Enter new state and consume the tag from buffer
                                _state = _OPEN[earliest_tag]
                                _buf = _buf[earliest + len(earliest_tag):]
                            else:
                                # No tag or partial tag found, yield all and empty buffer
                                yield AgentEvent(type="llm_chunk", content=_buf)
                                _buf = ""
                                break
                        else:
                            close_tag = _CLOSE[_state]
                            end = _buf.find(close_tag)
                            if end >= 0:
                                # For final_answer, emit its content as it arrives
                                if _state == "in_final_answer" and end > 0:
                                    yield AgentEvent(type="llm_chunk", content=_buf[:end])
                                # Move back to normal and consume the closing tag
                                _buf = _buf[end + len(close_tag):]
                                _state = "normal"
                            else:
                                # Closing tag not complete yet
                                tail = len(close_tag) - 1
                                # Special case for final_answer: yield what we have minus the tail
                                if _state == "in_final_answer":
                                    safe = max(0, len(_buf) - tail)
                                    if safe > 0:
                                        yield AgentEvent(type="llm_chunk", content=_buf[:safe])
                                        _buf = _buf[safe:]
                                else:
                                    # For other blocks, discard body but keep potential closing-tag prefix
                                    if len(_buf) > tail:
                                        _buf = _buf[-tail:]
                                break # wait for next chunk

                # Emit any leftover normal text
                if _buf.strip() and _state == "normal":
                    yield AgentEvent(type="llm_chunk", content=_buf)
                _buf = ""
            except Exception as e:
                err = f"LLM error: {e}"
                yield AgentEvent(type="error", content=err)
                await self.audit.log("llm_error", {"error": str(e), "step": step})
                break

            await self.bus.publish(EventType.LLM_DONE, {"response": full_response})

            # Phase 3: Parse
            parsed: ParseResult = parse_response(full_response)

            if parsed.thinking and parsed.tool_calls:
                yield AgentEvent(type="thinking", content=parsed.thinking)

            # Phase 7 early-exit: final answer
            if parsed.final_answer and not parsed.tool_calls:
                self.messages.append({"role": "assistant", "content": full_response})
                yield AgentEvent(type="final", content=parsed.final_answer)
                await self.audit.log("task_complete", {
                    "task_id": task_id, "steps": step, "answer": parsed.final_answer[:200]
                })
                await self._auto_save_episode(parsed.final_answer)
                return

            if not parsed.tool_calls:
                # No tool calls and no final answer — treat whole response as final
                # but STRIP any raw <thinking> tags if the state-machine missed them
                import re
                clean_final = re.sub(r"<thinking>.*?</thinking>", "", full_response, flags=re.DOTALL | re.IGNORECASE).strip()
                # Also strip any other tags
                clean_final = re.sub(r"<(tool_call|final_answer)>.*?</\1>", "", clean_final, flags=re.DOTALL | re.IGNORECASE).strip()
                
                if not clean_final and parsed.thinking:
                   clean_final = "I've planned it out, Boss! (Wait, I thought about it but forgot to actually do the tool call. Let me try again if you want me to!)"

                self.messages.append({"role": "assistant", "content": full_response})
                yield AgentEvent(type="final", content=clean_final)
                await self.audit.log("task_complete", {"task_id": task_id, "steps": step})
                await self._auto_save_episode(clean_final)
                return

            # Phase 4–6: Execute tools in parallel
            tool_results: list[str] = []
            tool_tasks = []
            
            async def execute_tool_task(tc):
                # Phase 4: Safety gate
                risk = classify_tool_call(tc.tool, tc.args)
                safety_mode = self.config.active_safety

                yield_event = AgentEvent(type="safety", tool_name=tc.tool, tool_args=tc.args, risk=risk)
                # Note: We can't yield from inside a task easily if we gather, 
                # so we'll handle the events carefully.
                
                if not is_allowed(risk, safety_mode):
                    if self.confirm_callback and risk == "DANGEROUS":
                        try:
                            confirmed = await self.confirm_callback(tc.tool, risk, tc.args)
                        except Exception:
                            confirmed = False
                        if not confirmed:
                            return f"Tool '{tc.tool}' result:\n[Blocked by user] Dangerous operation was not confirmed."
                    elif risk == "DANGEROUS":
                        return f"Tool '{tc.tool}' result:\n[Blocked] classified as DANGEROUS (mode={safety_mode})."
                    else:
                        return f"Tool '{tc.tool}' result:\n[Blocked] Not allowed in {safety_mode} mode."

                # Phase 5: Execute
                await self.audit.log("tool_start", {"tool": tc.tool, "args": tc.args, "risk": risk, "step": step})
                # We still want to show progress in the UI
                # (For simplicity in this turn, we'll run them in parallel but we might want a list of starts)
                
                # Special case: save_memory can be backgrounded if we don't need the ID immediately
                if tc.tool == "save_memory":
                    asyncio.create_task(self.tools.execute(tc.tool, tc.args))
                    return f"Tool '{tc.tool}' result:\n[Backgrounded] Memory is being saved, dear."

                result = await self.tools.execute(tc.tool, tc.args)

                # Self-healing
                if result.startswith("[Error]") and self.config.agent.auto_recovery:
                    recovery_result = await self._attempt_recovery(tc.tool, tc.args, result, ctx_messages)
                    if recovery_result and not recovery_result.startswith("[Error]"):
                        result = f"[Recovered] {recovery_result}"

                return f"Tool '{tc.tool}' result:\n{result}"

            # To keep the UI reactive, we'll still emit 'start' events for all tools
            for tc in parsed.tool_calls:
                risk = classify_tool_call(tc.tool, tc.args)
                yield AgentEvent(type="tool_start", tool_name=tc.tool, tool_args=tc.args, risk=risk)
                tool_tasks.append(execute_tool_task(tc))

            if tool_tasks:
                results = await asyncio.gather(*tool_tasks)
                tool_results.extend(results)
                # Emit end events for UI
                for i, tc in enumerate(parsed.tool_calls):
                    yield AgentEvent(type="tool_end", tool_name=tc.tool, tool_result=results[i])

            if tool_results:
                observation = "\n\n".join(tool_results)
                self.messages.append({"role": "assistant", "content": full_response})
                self.messages.append({"role": "user", "content": f"[Tool Results]\n{observation}"})

            # Check for final answer in this response even with tool calls
            if parsed.final_answer:
                yield AgentEvent(type="final", content=parsed.final_answer)
                await self.audit.log("task_complete", {
                    "task_id": task_id, "steps": step, "answer": parsed.final_answer[:200]
                })
                await self._auto_save_episode(parsed.final_answer)
                return

        # Fell through max steps
        if step >= max_steps:
            msg = f"Reached maximum steps ({max_steps}). Stopping."
            yield AgentEvent(type="error", content=msg)
            await self.audit.log("max_steps_reached", {"task_id": task_id, "steps": step})
            await self._auto_save_episode("Reached max steps limit.")

    async def _auto_save_episode(self, summary_fragment: str) -> None:
        """Automatically save current chat progress to episodic history."""
        if not self.memory:
            return
        try:
            # Use user's first message as summary title
            user_msg = next((m["content"] for m in self.messages if m["role"] == "user"), "Conversation")
            summary = f"{user_msg[:50]}..."
            await self.memory.save_episode(
                summary=summary,
                messages=self.messages
            )
        except Exception as e:
            logger.error(f"Auto-save episode failed: {e}")

    async def _attempt_recovery(
        self,
        tool: str,
        args: dict,
        error: str,
        ctx_messages: list[dict],
    ) -> str:
        """Ask LLM for an alternative approach and try it once."""
        try:
            recovery_prompt = (
                f"The tool '{tool}' with args {args} failed with error: {error}\n"
                f"Suggest and execute one alternative approach using available tools."
            )
            messages = ctx_messages + [{"role": "user", "content": recovery_prompt}]
            response = await self.llm.chat(
                model=self.config.active_model,
                messages=messages,
                temperature=0.3,
            )
            parsed = parse_response(response)
            if parsed.tool_calls:
                tc = parsed.tool_calls[0]
                return await self.tools.execute(tc.tool, tc.args)
        except Exception as e:
            logger.debug(f"Recovery attempt failed: {e}")
        return ""
