# Lab 04 — Weather Agent with Remote MCP Server

A full-stack weather agent connecting to a remote MCP server via **Streamable HTTP** transport, powered by **OpenRouter LLM (`meta-llama/llama-3.3-70b-instruct`)** or Google ADK.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  👤 User (Terminal / Interactive Chat / Web)                    │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  🤖 OpenRouter LLM (meta-llama/llama-3.3-70b-instruct)          │
│  - Phân tích câu hỏi người dùng                                │
│  - Tự động quyết định gọi tool nào và bao nhiêu lần             │
└────────────────────────────────┬────────────────────────────────┘
                                 │ Streamable HTTP (POST/GET/DELETE)
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  📡 Remote FastMCP Server (localhost:8085/mcp)                  │
│  - `get_current_weather(city)`                                  │
│  - `get_forecast(city, days)`                                   │
│  - `health_check()`                                             │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  🌐 Weather Data Source                                         │
│  - WeatherAPI.com (nếu có WEATHERAPI_KEY)                       │
│  - Live Real-Time Weather API fallback (không cần API key)      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tools

| Tool | Description |
|---|---|
| `get_current_weather(city)` | Lấy nhiệt độ, cảm nhận, độ ẩm, gió thực tế của thành phố |
| `get_forecast(city, days)` | Dự báo thời tiết từ 1 đến 3 ngày tới |
| `health_check()` | Kiểm tra trạng thái hoạt động của server |

---

## Hướng dẫn chạy Lab 04

### Bước 1: Khởi động MCP Server (Terminal 1)

```powershell
cd 04-lab/mcp-server
python weather.py
```
> Server sẽ khởi động trên `http://0.0.0.0:8085/mcp` và sẵn sàng nhận kết nối Streamable HTTP.

---

### Bước 2: Chạy Weather Agent Client với OpenRouter LLM (Terminal 2)

```powershell
cd 04-lab/mcp-client
python weather_agent_openrouter.py
```

**Hoặc hỏi nhanh 1 câu trực tiếp từ dòng lệnh:**
```powershell
python weather_agent_openrouter.py "Dự báo thời tiết 3 ngày tới ở Đà Nẵng và Đà Lạt"
```

---

## Cấu hình môi trường (`.env`)

| Biến | Vị trí | Mô tả |
|---|---|---|
| `OPEN_ROUTER_API_KEY` | `.env` | API key OpenRouter |
| `OPEN_ROUTER_MODEL` | `.env` | `meta-llama/llama-3.3-70b-instruct` |
| `WEATHERAPI_KEY` | `.env` | API key weatherapi.com (tuỳ chọn) |
| `PORT` | env | Cổng chạy server (mặc định: `8085`) |
