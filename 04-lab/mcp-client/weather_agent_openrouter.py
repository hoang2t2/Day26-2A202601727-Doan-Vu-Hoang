"""Weather Agent Client (Lab 04) kết hợp Remote MCP Server + OpenRouter LLM.

Kiến trúc:
  [User / Terminal] <---> [OpenRouter LLM: meta-llama/llama-3.3-70b-instruct]
                                      │
                              (Streamable HTTP)
                                      ▼
                        [Remote MCP Server: localhost:8085/mcp]
                                      │
                            (Live Real-time API)
                                      ▼
                                [Weather API]

Cách chạy:
  1. Khởi động MCP Server (ở terminal 1):
     python ../mcp-server/weather.py

  2. Khởi động Agent Client (ở terminal 2):
     python weather_agent_openrouter.py
     # Hoặc hỏi nhanh:
     python weather_agent_openrouter.py "Dự báo thời tiết 3 ngày tới ở Đà Nẵng"
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
    env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

OPEN_ROUTER_API_KEY = os.getenv("OPEN_ROUTER_API_KEY")
OPEN_ROUTER_URL = os.getenv("OPEN_ROUTER_URL", "https://openrouter.ai/api/v1")
OPEN_ROUTER_MODEL = os.getenv(
    "OPEN_ROUTER_MODEL",
    os.getenv("OPEN_ROUTER_ANSWER_MODEL", "meta-llama/llama-3.3-70b-instruct"),
)

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8085/mcp")

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from openai import OpenAI


async def process_turn(
    user_query: str,
    messages: list[dict],
    openai_tools: list[dict],
    openai_client: OpenAI,
    session: ClientSession,
) -> str:
    """Xử lý 1 lượt hội thoại giữa User -> LLM -> Remote MCP Server -> LLM."""
    messages.append({"role": "user", "content": user_query})

    # 1. Gửi tới OpenRouter LLM
    resp = openai_client.chat.completions.create(
        model=OPEN_ROUTER_MODEL,
        messages=messages,
        tools=openai_tools,
        tool_choice="auto",
    )

    msg = resp.choices[0].message

    # 2. Xử lý Function Calling nếu LLM yêu cầu gọi Remote MCP tool
    while msg.tool_calls:
        messages.append(msg)

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            print(f"  ⚡ [LLM gọi Remote MCP Tool]: {fn_name}({fn_args})")

            # Gọi tool qua giao thức Streamable HTTP tới MCP Server
            result = await session.call_tool(fn_name, fn_args)
            result_text = result.content[0].text if result.content else ""
            print(f"  📥 [MCP Server 8085 phản hồi]:\n{result_text.strip()}\n")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": fn_name,
                    "content": result_text,
                }
            )

        # Gửi kết quả lại cho LLM để tổng hợp
        follow_up = openai_client.chat.completions.create(
            model=OPEN_ROUTER_MODEL,
            messages=messages,
            tools=openai_tools,
        )
        msg = follow_up.choices[0].message

    answer = msg.content or ""
    messages.append({"role": "assistant", "content": answer})
    return answer


async def main() -> None:
    if not OPEN_ROUTER_API_KEY:
        print("❌ Lỗi: Chưa cấu hình OPEN_ROUTER_API_KEY trong file .env")
        return

    openai_client = OpenAI(
        base_url=OPEN_ROUTER_URL,
        api_key=OPEN_ROUTER_API_KEY,
    )

    print("=" * 65)
    print("🌤️  LAB 04 — REMOTE MCP WEATHER AGENT (OpenRouter)")
    print("=" * 65)
    print(f"🤖 LLM Model: {OPEN_ROUTER_MODEL}")
    print(f"📡 Remote MCP Server: {MCP_SERVER_URL}\n")

    print(f"🔌 Đang kết nối tới MCP Server qua Streamable HTTP ({MCP_SERVER_URL})...")

    try:
        async with httpx.AsyncClient() as http_client:
            async with streamable_http_client(MCP_SERVER_URL, http_client=http_client) as (
                read, write, _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # 1. Khám phá dynamic tools từ MCP Server
                    mcp_tools = await session.list_tools()
                    print("\n📦 Remote MCP Tools khám phá được:")
                    openai_tools = []
                    for t in mcp_tools.tools:
                        print(f"   • {t.name}: {t.description}")
                        openai_tools.append(
                            {
                                "type": "function",
                                "function": {
                                    "name": t.name,
                                    "description": t.description or "",
                                    "parameters": t.inputSchema
                                    or {"type": "object", "properties": {}},
                                },
                            }
                        )
                    print("=" * 65 + "\n")

                    system_instruction = {
                        "role": "system",
                        "content": (
                            "Bạn là Weather Agent thông minh kết nối với Remote MCP Server. "
                            "Hãy trả lời bằng tiếng Việt tự nhiên, thân thiện và giàu thông tin, dùng emoji sinh động. "
                            "Dùng get_current_weather cho thời tiết hiện tại và get_forecast cho dự báo các ngày tới."
                        ),
                    }

                    messages = [system_instruction]

                    # 2. Xử lý CLI Argument nếu có
                    if len(sys.argv) > 1:
                        query = " ".join(sys.argv[1:])
                        print(f"👤 Câu hỏi: {query}\n")
                        ans = await process_turn(
                            query, messages, openai_tools, openai_client, session
                        )
                        print(f"💬 Trả lời:\n{ans}\n")
                        return

                    # 3. Chế độ Real-time Chat
                    print("💡 Chế độ Real-time Interactive Chat đã sẵn sàng!")
                    print("   - Nhập câu hỏi bất kỳ (VD: 'Dự báo thời tiết 3 ngày tới ở Đà Lạt')")
                    print("   - Nhập 'clear' để xoá lịch sử hội thoại")
                    print("   - Nhập 'exit', 'quit' hoặc 'q' để thoát\n")

                    while True:
                        try:
                            user_input = input("👤 Bạn: ").strip()
                        except (EOFError, KeyboardInterrupt):
                            print("\n👋 Tạm biệt!")
                            break

                        if not user_input:
                            continue

                        if user_input.lower() in ["exit", "quit", "q"]:
                            print("\n👋 Tạm biệt!")
                            break

                        if user_input.lower() == "clear":
                            messages = [system_instruction]
                            print("🧹 Đã làm mới lịch sử hội thoại.\n")
                            continue

                        print("\n⏳ Đang gửi yêu cầu tới Remote MCP Server...")
                        try:
                            answer = await process_turn(
                                user_input, messages, openai_tools, openai_client, session
                            )
                            print(f"\n💬 Trợ lý:\n{answer}\n")
                            print("-" * 65)
                        except Exception as e:
                            print(f"❌ Có lỗi xảy ra: {e}\n")

    except Exception as e:
        print(f"\n❌ Không thể kết nối tới MCP Server tại {MCP_SERVER_URL}: {e}")
        print("👉 Vui lòng đảm bảo MCP Server đang chạy ở terminal khác bằng lệnh:")
        print("   cd 04-lab/mcp-server && python weather.py\n")


if __name__ == "__main__":
    asyncio.run(main())
