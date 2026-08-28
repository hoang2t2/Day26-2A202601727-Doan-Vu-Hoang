"""MCP CLIENT tương tác Real-time kết hợp OpenRouter LLM (meta-llama/llama-3.3-70b-instruct).

Chế độ hoạt động:
  - Chạy interactive chat thời gian thực (hỏi đáp liên tục, nhớ ngữ cảnh).
  - Hoặc truyền câu hỏi trực tiếp qua tham số dòng lệnh.

Cách chạy:
    python weather_llm_client.py
    # Hoặc:
    python weather_llm_client.py "Thời tiết Đà Lạt và Sài Gòn thế nào?"
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi encoding
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

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI


async def process_turn(
    user_query: str,
    messages: list[dict],
    openai_tools: list[dict],
    openai_client: OpenAI,
    session: ClientSession,
) -> str:
    """Xử lý một lượt hỏi đáp: Gửi prompt -> LLM gọi MCP Tool -> Tổng hợp trả lời."""
    messages.append({"role": "user", "content": user_query})

    # 1. Gửi tới OpenRouter LLM
    resp = openai_client.chat.completions.create(
        model=OPEN_ROUTER_MODEL,
        messages=messages,
        tools=openai_tools,
        tool_choice="auto",
    )

    msg = resp.choices[0].message

    # 2. Vòng lặp Function Calling qua MCP Server nếu có yêu cầu
    while msg.tool_calls:
        messages.append(msg)
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            print(f"  ⚡ [LLM gọi MCP Tool] {fn_name}({fn_args})")

            # Gọi tool thực tế trên MCP Server
            result = await session.call_tool(fn_name, fn_args)
            result_text = result.content[0].text
            print(f"  📥 [MCP Server trả về] -> {result_text}")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": fn_name,
                    "content": result_text,
                }
            )

        # Gửi kết quả lại cho LLM
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
    print("🌤️  MCP WEATHER AGENT (Real-time Interactive Client)")
    print("=" * 65)
    print(f"🤖 Model: {OPEN_ROUTER_MODEL}")
    print(f"🌐 Endpoint: {OPEN_ROUTER_URL}\n")

    # Khởi động MCP Server qua stdio
    server_path = Path(__file__).parent / "weather_server.py"
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_path)],
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. Khám phá dynamic tools từ MCP Server
            mcp_tools = await session.list_tools()
            print("📦 Tools khám phá từ MCP Server:")
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
            print("=" * 65)

            system_instruction = {
                "role": "system",
                "content": (
                    "Bạn là trợ lý thời tiết thông minh kết nối với MCP Server. "
                    "Hãy trả lời bằng tiếng Việt tự nhiên, thân thiện, dùng emoji sinh động (🌦️ 💨 ☔). "
                    "Nếu người dùng hỏi về thời tiết của địa điểm nào, hãy dùng tool get_weather để lấy dữ liệu chính xác."
                ),
            }

            messages: list[dict] = [system_instruction]

            # Kiểm tra nếu người dùng truyền câu hỏi trực tiếp qua CLI argument
            if len(sys.argv) > 1:
                single_query = " ".join(sys.argv[1:])
                print(f"\n👤 Câu hỏi: {single_query}\n")
                ans = await process_turn(
                    single_query, messages, openai_tools, openai_client, session
                )
                print(f"\n💬 Trả lời:\n{ans}\n")
                return

            # Chế độ tương tác Real-time (Chat REPL)
            print("\n💡 Chế độ Real-time Chat đã sẵn sàng!")
            print("   - Nhập câu hỏi bất kỳ (VD: 'Thời tiết Cần Thơ và Đà Lạt hôm nay ra sao?')")
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

                print("\n⏳ Đang xử lý câu hỏi...")
                try:
                    answer = await process_turn(
                        user_input, messages, openai_tools, openai_client, session
                    )
                    print(f"\n💬 Trợ lý:\n{answer}\n")
                    print("-" * 65)
                except Exception as e:
                    print(f"❌ Có lỗi xảy ra: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
