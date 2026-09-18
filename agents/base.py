import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def _load_env() -> None:
   """(Re)load the project .env so a key saved after startup is picked up without a restart."""
   try:
       from dotenv import load_dotenv

       load_dotenv(ENV_PATH, override=True)
   except ImportError:
       pass


_load_env()

DEFAULT_MODEL = "claude-sonnet-5"
MAX_TURNS = 8


def llm_available() -> bool:
   _load_env()
   return bool(os.getenv("ANTHROPIC_API_KEY"))


def run_tool_loop(
   system: str,
   user_message: str,
   tools: List[Dict[str, Any]],
   handlers: Dict[str, Callable[[Dict[str, Any]], Any]],
   terminal_tool: str,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
   """Run a Claude tool-use loop until `terminal_tool` is called or the turn limit is hit.

   Returns (trace, terminal_tool_input). The trace lists every tool call and the agent's text
   so the UI can show the swarm working.
   """
   import anthropic

   client = anthropic.Anthropic()
   model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
   messages: List[Dict[str, Any]] = [{"role": "user", "content": user_message}]
   trace: List[Dict[str, Any]] = []

   for _ in range(MAX_TURNS):
       response = client.messages.create(
           model=model,
           max_tokens=2048,
           system=system,
           tools=tools,
           messages=messages,
       )
       messages.append({"role": "assistant", "content": response.content})

       tool_results = []
       terminal_input = None
       for block in response.content:
           if block.type == "text" and block.text.strip():
               trace.append({"type": "thought", "text": block.text.strip()})
           elif block.type == "tool_use":
               try:
                   result = handlers[block.name](block.input)
               except Exception as exc:
                   result = {"error": str(exc)}
               trace.append({"type": "tool_call", "tool": block.name, "input": block.input, "result": result})
               if block.name == terminal_tool:
                   terminal_input = block.input
               tool_results.append({
                   "type": "tool_result",
                   "tool_use_id": block.id,
                   "content": json.dumps(result, default=str),
               })

       if terminal_input is not None:
           return trace, terminal_input
       if response.stop_reason != "tool_use":
           break
       messages.append({"role": "user", "content": tool_results})

   return trace, None
