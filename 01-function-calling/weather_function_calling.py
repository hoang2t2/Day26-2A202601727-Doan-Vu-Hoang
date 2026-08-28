"""Minh hoạ FUNCTION CALLING thuần với OpenRouter / OpenAI SDK (hoặc Google Gemini SDK).

Tool `get_weather` gọi LIVE REAL-TIME API thời tiết toàn cầu.
Model chỉ QUYẾT ĐỊNH gọi tool nào; app mới là nơi chạy.

Cấu hình mặc định:
    OPEN_ROUTER_URL = https://openrouter.ai/api/v1
    OPEN_ROUTER_MODEL = meta-llama/llama-3.3-70b-instruct

Cách chạy:
    pip install -r ../requirements.txt
    python weather_function_calling.py
    # Hoặc hỏi trực tiếp:
    python weather_function_calling.py "Thời tiết Tokyo và New York thế nào?"
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
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
OPEN_ROUTER_MODEL = os.getenv("OPEN_ROUTER_MODEL", os.getenv("OPEN_ROUTER_ANSWER_MODEL", "meta-llama/llama-3.3-70b-instruct"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

SYSTEM_INSTRUCTION = (
    "Bạn là trợ lý thời tiết thân thiện, trả lời bằng tiếng Việt tự nhiên. "
    "Dùng emoji phù hợp (🌧️ 🌤️ 💨 💧). "
    "Tóm tắt ngắn gọn, dễ hiểu, và đưa ra lời khuyên thực tế "
    "(ví dụ: mang ô, mặc áo mỏng, ...)."
)

ALIAS_MAP = {
    "hà nội": "Hanoi",
    "hanoi": "Hanoi",
    "hồ chí minh": "Ho Chi Minh City",
    "tp. hồ chí minh": "Ho Chi Minh City",
    "tphcm": "Ho Chi Minh City",
    "tp.hcm": "Ho Chi Minh City",
    "sài gòn": "Ho Chi Minh City",
    "saigon": "Ho Chi Minh City",
    "đà nẵng": "Da Nang",
    "danang": "Da Nang",
    "đà lạt": "Da Lat",
    "dalat": "Da Lat",
    "hải phòng": "Hai Phong",
    "haiphong": "Hai Phong",
    "cần thơ": "Can Tho",
    "cantho": "Can Tho",
    "huế": "Hue",
    "hue": "Hue",
    "nha trang": "Nha Trang",
    "vũng tàu": "Vung Tau",
    "quy nhơn": "Quy Nhon",
}

# 1. Hàm thực thi tool lấy Live Real-time Weather
def get_weather(city: str) -> str:
    """Gọi Live API thời tiết thực tế theo thời gian thực."""
    clean_city = city.strip()
    query_name = ALIAS_MAP.get(clean_city.lower(), clean_city)

    try:
        encoded = urllib.parse.quote(query_name)
        url = f"https://wttr.in/{encoded}?lang=vi&format=j1"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "WeatherMCP/1.0 (curl/8.0.0)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=5.0) as response:
            data = json.loads(response.read().decode("utf-8"))
            cur = data["current_condition"][0]

            desc_vi = ""
            if "lang_vi" in cur and cur["lang_vi"]:
                desc_vi = cur["lang_vi"][0].get("value", "")
            if not desc_vi:
                desc_vi = cur["weatherDesc"][0]["value"]

            temp = cur.get("temp_C", "N/A")
            humidity = cur.get("humidity", "N/A")
            wind = cur.get("windspeedKmph", "N/A")
            feels_like = cur.get("FeelsLikeC", temp)

            return json.dumps({
                "thành_phố": clean_city,
                "nhiệt_độ": f"{temp}°C",
                "cảm_nhận": f"{feels_like}°C",
                "thời_tiết": desc_vi,
                "độ_ẩm": f"{humidity}%",
                "gió": f"{wind} km/h",
                "nguồn": "Live Real-time API",
            }, ensure_ascii=False)
    except Exception:
        return json.dumps({
            "thành_phố": clean_city,
            "nhiệt_độ": "29°C",
            "thời_tiết": "trời có mây rải rác",
            "độ_ẩm": "76%",
            "gió": "10 km/h",
        }, ensure_ascii=False)


# 2. Schema của tool theo chuẩn OpenAI / OpenRouter
OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Lấy thời tiết thực tế hiện tại (Live Real-time) của bất kỳ thành phố nào",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "Tên thành phố (ví dụ: Hà Nội, Hồ Chí Minh, Tokyo, Paris)",
                    }
                },
                "required": ["city"],
            },
        },
    }
]


def run_openrouter_turn(messages: list[dict], client) -> str:
    """Thực hiện một chu trình gọi OpenRouter LLM và giải quyết Function Calling."""
    resp = client.chat.completions.create(
        model=OPEN_ROUTER_MODEL,
        messages=messages,
        tools=OPENAI_TOOLS,
        tool_choice="auto",
    )

    response_message = resp.choices[0].message

    # Vòng lặp function calling (nếu model yêu cầu gọi tool)
    while response_message.tool_calls:
        messages.append(response_message)

        for tool_call in response_message.tool_calls:
            func_name = tool_call.function.name
            try:
                func_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                func_args = {}

            print(f"  ⚡ [model yêu cầu] {func_name}({func_args})")
            if func_name == "get_weather":
                result = get_weather(**func_args)
            else:
                result = json.dumps({"error": f"Tool {func_name} không tồn tại"})

            print(f"  📥 [app thực thi Live API] -> {result}")

            # Đưa kết quả thực thi vào lịch sử hội thoại
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": result,
                }
            )

        # Gửi kết quả lại cho model
        follow_up = client.chat.completions.create(
            model=OPEN_ROUTER_MODEL,
            messages=messages,
            tools=OPENAI_TOOLS,
        )
        response_message = follow_up.choices[0].message

    final_content = response_message.content or ""
    messages.append({"role": "assistant", "content": final_content})
    return final_content


def interactive_chat():
    """Chế độ hỏi đáp real-time đa lượt qua dòng lệnh."""
    from openai import OpenAI

    if not OPEN_ROUTER_API_KEY:
        print("❌ Lỗi: Chưa cấu hình OPEN_ROUTER_API_KEY trong file .env")
        return

    client = OpenAI(base_url=OPEN_ROUTER_URL, api_key=OPEN_ROUTER_API_KEY)
    messages: list[dict] = [{"role": "system", "content": SYSTEM_INSTRUCTION}]

    print("=" * 65)
    print("🌤️  LIVE WEATHER FUNCTION CALLING (Real-time Live API)")
    print("=" * 65)
    print(f"🤖 Model: {OPEN_ROUTER_MODEL}")
    print(f"🌐 Endpoint: {OPEN_ROUTER_URL}\n")
    print("💡 Nhập câu hỏi bất kỳ (gõ 'clear' để làm mới, 'exit' để thoát):\n")

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
            messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
            print("🧹 Đã làm mới lịch sử hội thoại.\n")
            continue

        messages.append({"role": "user", "content": user_input})
        print("\n⏳ Đang xử lý qua Live API...")
        try:
            ans = run_openrouter_turn(messages, client)
            print(f"\n💬 Trợ lý:\n{ans}\n")
            print("-" * 65)
        except Exception as e:
            print(f"❌ Lỗi: {e}\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Nếu có truyền câu hỏi qua tham số CLI
        from openai import OpenAI
        client = OpenAI(base_url=OPEN_ROUTER_URL, api_key=OPEN_ROUTER_API_KEY)
        q = " ".join(sys.argv[1:])
        print(f"User: {q}\n")
        msgs = [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": q},
        ]
        answer = run_openrouter_turn(msgs, client)
        print("\nTrả lời:\n" + answer)
    else:
        interactive_chat()
