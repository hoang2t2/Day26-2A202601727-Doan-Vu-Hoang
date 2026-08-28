# 03 — Production (Auth, Tool Registry, Versioning)

`02-mcp-basics` chạy tốt trên máy cá nhân. Đưa vào production cần giải quyết thêm 3 vấn đề:

| Vấn đề | Demo | Production |
|---|---|---|
| **Auth** | stdio, cùng máy, ai cũng gọi | HTTP + Bearer token / OAuth |
| **Discovery** | Hard-code tool/server | Tool Registry — agent tìm tool theo task |
| **Versioning** | 1 tool duy nhất | v1 + v2 song song, deprecation notice |

## Files

| File | Vấn đề | Mô tả |
|---|---|---|
| `auth_server.py` | Auth | MCP server qua Streamable HTTP + `TokenVerifier` kiểm tra bearer token |
| `auth_client.py` | Auth | Client gửi token qua `httpx.AsyncClient` |
| `registry.json` | Discovery | Tool Registry — danh mục tool-centric, agent tìm theo tag/keyword |
| `registry_client.py` | Discovery | Agent tra cứu registry theo logic thuần, chọn best match, tự kết nối |
| `registry_llm_client.py` | Discovery + LLM | **OpenRouter LLM (`meta-llama/llama-3.3-70b-instruct`)** tự đọc registry, chọn tool và gọi server phù hợp |
| `versioned_server.py` | Versioning | Server v2: giữ tool v1 (deprecated) + thêm v2 + resource metadata |
| `versioned_client.py` | Versioning | Client test gọi tool v1, v2 và đọc `server://info` metadata |

---

## 3a. Authentication

Server chạy qua **Streamable HTTP** thay vì stdio, kèm bearer token verification.

```bash
# Terminal 1 — khởi động server
python auth_server.py
# Server lắng nghe tại http://localhost:8000/mcp

# Terminal 2 — client kết nối kèm token
python auth_client.py
```

Luồng:

```
Client                                Server
  │                                      │
  │── POST /mcp ──────────────────────▶  │
  │   Authorization: Bearer <token>      │
  │                                      │── TokenVerifier.verify_token()
  │                                      │   token hợp lệ → AccessToken
  │◀── 200 OK (tools, results) ────────  │
  │                                      │
  │── POST /mcp (token sai) ──────────▶  │
  │◀── 401 Unauthorized ───────────────  │
```

- Token hợp lệ (`dev-token-abc123`) → truy cập tool bình thường
- Thiếu token → `401 Unauthorized`
- Token sai → `403 Forbidden`
- Logic tool không biết gì về auth — SDK xử lý ở tầng transport

---

## 3b. Tool Registry & Discovery

### 1. Khám phá Tool thuần (Programmatic):
Agent hỏi Tool Registry theo yêu cầu tag/keyword:
```bash
python registry_client.py
```

### 2. Khám phá Tool thông minh với OpenRouter LLM:
Người dùng đặt câu hỏi tự nhiên → LLM tự chọn tool tối ưu trong `registry.json` và kết nối tới đúng MCP server:
```bash
python registry_llm_client.py "Dự báo thời tiết chi tiết tại Đà Nẵng 2 ngày tới ra sao?"
```

Luồng:

```
User hỏi
   │
   ▼
LLM (meta-llama/llama-3.3-70b-instruct) đọc tool schemas từ registry.json
   │
   ▼
LLM quyết định gọi get_weather_v2(city="Đà Nẵng", include_forecast=True)
   │
   ▼
Client tra cứu registry.json: tool 'get_weather_v2' thuộc server 'weather-v2' (stdio)
   │
   ▼
Kết nối tới weather-v2 qua MCP, thực thi tool và trả kết quả cho LLM tổng hợp
```

---

## 3c. Versioning & Backward Compatibility

Server v2 dùng 3 kỹ thuật để thêm tính năng mà không break client cũ:

```bash
python versioned_client.py
```

| Kỹ thuật | Mô tả |
|---|---|
| **Tool mới song song** | `get_weather_v2` tồn tại bên cạnh `get_weather` — không xoá tool cũ |
| **Tham số optional** | `include_forecast`, `units` có default → client cũ gọi `get_weather_v2(city="Hanoi")` vẫn đúng |
| **Server metadata** | Resource `server://info` công bố version, deprecated tools, migration guide |

```
Server v2
├── get_weather(city)              ← v1, deprecated nhưng vẫn hoạt động
├── get_weather_v2(city, ...)      ← v2, thêm forecast + units
└── resource server://info         ← version + migration guide cho client
```
