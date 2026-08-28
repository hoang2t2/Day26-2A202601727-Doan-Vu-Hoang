"""Tool Registry + OpenRouter LLM Client.

Quy trình:
  1. Agent nạp toàn bộ danh mục tools từ registry.json.
  2. Chuyển đổi định dạng sang OpenAI function calling schema.
  3. Gửi câu hỏi của User + danh sách tools tới OpenRouter (meta-llama/llama-3.3-70b-instruct).
  4. Khi LLM yêu cầu gọi tool, agent tự động tra cứu registry để tìm đúng MCP server (stdio hoặc HTTP kèm token).
  5. Kết nối tới server, thực thi tool và gửi kết quả về cho LLM tổng hợp.

Cách chạy:
    python registry_llm_client.py
    # Hoặc:
    python registry_llm_client.py "Dự báo thời tiết chi tiết ở Đà Nẵng 2 ngày tới ra sao?"
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Đảm bảo in tiếng Việt trên console Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Tìm và load file .env từ thư mục hiện tại hoặc thư mục cha
env_path = Path(__file__).parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

OPEN_ROUTER_API_KEY = os.getenv("OPEN_ROUTER_API_KEY")
OPEN_ROUTER_URL = os.getenv("OPEN_ROUTER_URL", "https://openrouter.ai/api/v1")
OPEN_ROUTER_MODEL = os.getenv(
    "OPEN_ROUTER_MODEL",
    os.getenv("OPEN_ROUTER_ANSWER_MODEL", "meta-llama/llama-3.3-70b-instruct"),
)

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from openai import OpenAI

from registry_client import ToolRegistry, connect_and_call, REGISTRY_PATH


def build_openai_tools(registry: ToolRegistry) -> list[dict]:
    """Chuyển đổi tools trong registry sang chuẩn OpenAI Function Calling schema."""
    openai_tools = []
    for tool_name, tool_cfg in registry.tools.items():
        if tool_cfg.get("deprecated", False):
            continue  # Ưu tiên bỏ qua tool deprecated nếu có tool mới

        properties = {}
        required = []
        for p_name, p_info in tool_cfg.get("parameters", {}).items():
            properties[p_name] = {
                "type": p_info.get("type", "string"),
                "description": f"Tham số {p_name}",
            }
            if p_info.get("required", False):
                required.append(p_name)

        openai_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_cfg.get("description", ""),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
        )
    return openai_tools


async def process_query(
    user_query: str,
    registry: ToolRegistry,
    openai_tools: list[dict],
    openai_client: OpenAI,
) -> str:
    """Xử lý câu hỏi qua LLM và kết nối động tới MCP server tương ứng."""
    messages = [
        {
            "role": "system",
            "content": (
                "Bạn là trợ lý AI thông minh tích hợp Tool Registry trung tâm. "
                "Hãy chọn tool phù hợp nhất từ danh mục để giải quyết yêu cầu của người dùng. "
                "Trả lời bằng tiếng Việt tự nhiên kèm emoji sinh động."
            ),
        },
        {"role": "user", "content": user_query},
    ]

    print(f"👤 Câu hỏi: {user_query}\n")

    resp = openai_client.chat.completions.create(
        model=OPEN_ROUTER_MODEL,
        messages=messages,
        tools=openai_tools,
        tool_choice="auto",
    )

    msg = resp.choices[0].message

    while msg.tool_calls:
        messages.append(msg)

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            print(f"  ⚡ [LLM yêu cầu gọi Tool]: {fn_name}({fn_args})")

            # Tra cứu server tương ứng trong registry
            tool_info = registry.tools.get(fn_name)
            if not tool_info:
                result_text = json.dumps({"error": f"Tool {fn_name} không có trong registry"})
            else:
                server_name = tool_info["server"]
                server_cfg = registry.servers.get(server_name, {})
                print(f"  🔍 [Tool Registry Match]: Tool '{fn_name}' nằm ở Server '{server_name}' (Transport: {server_cfg.get('transport')})")

                match_entry = {
                    "tool": fn_name,
                    "server": server_cfg,
                }
                result_text = await connect_and_call(match_entry, fn_args)

            print(f"  📥 [Server trả về]: {result_text}\n")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": fn_name,
                    "content": result_text,
                }
            )

        follow_up = openai_client.chat.completions.create(
            model=OPEN_ROUTER_MODEL,
            messages=messages,
            tools=openai_tools,
        )
        msg = follow_up.choices[0].message

    return msg.content or ""


async def main() -> None:
    if not OPEN_ROUTER_API_KEY:
        print("❌ Lỗi: Chưa cấu hình OPEN_ROUTER_API_KEY trong file .env")
        return

    openai_client = OpenAI(
        base_url=OPEN_ROUTER_URL,
        api_key=OPEN_ROUTER_API_KEY,
    )

    registry = ToolRegistry()
    openai_tools = build_openai_tools(registry)

    print("=" * 65)
    print("📋  TOOL REGISTRY + OPENROUTER LLM CLIENT")
    print("=" * 65)
    print(f"🤖 Model: {OPEN_ROUTER_MODEL}")
    print(f"📦 Số tools có trong Registry: {len(openai_tools)}")
    print("=" * 65 + "\n")

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        ans = await process_query(query, registry, openai_tools, openai_client)
        print(f"💬 Trả lời:\n{ans}\n")
    else:
        # Chế độ mặc định
        sample_query = "Dự báo thời tiết chi tiết tại Đà Nẵng 2 ngày tới bao gồm cả forecast như thế nào?"
        ans = await process_query(sample_query, registry, openai_tools, openai_client)
        print(f"💬 Trả lời:\n{ans}\n")


if __name__ == "__main__":
    asyncio.run(main())
