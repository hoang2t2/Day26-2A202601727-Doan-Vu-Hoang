#!/usr/bin/env python3
"""
Verification script for Weather Agent setup
Checks if all components are configured correctly
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi encoding
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def check_environment():
    """Check if .env file exists and is configured"""
    print("🔍 Checking environment configuration...")
    
    env_file = Path(".env")
    if not env_file.exists():
        env_file = Path(__file__).parent.parent.parent / ".env"

    if not env_file.exists():
        print("❌ .env file not found")
        print("   Run: cp .env.example .env (and configure your keys)")
        return False
    
    load_dotenv(dotenv_path=env_file)
    
    openrouter_key = os.getenv("OPEN_ROUTER_API_KEY")
    openrouter_model = os.getenv("OPEN_ROUTER_MODEL", os.getenv("OPEN_ROUTER_ANSWER_MODEL"))
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    has_valid_config = False

    if openrouter_key and not openrouter_key.startswith("your_"):
        print(f"✅ OPEN_ROUTER_API_KEY configured ({openrouter_key[:10]}...)")
        print(f"   Model: {openrouter_model or 'meta-llama/llama-3.3-70b-instruct'}")
        has_valid_config = True

    if google_key and not google_key.startswith("your_"):
        print(f"✅ GOOGLE_API_KEY configured ({google_key[:10]}...)")
        has_valid_config = True

    if not has_valid_config:
        print("❌ Neither OPEN_ROUTER_API_KEY nor GOOGLE_API_KEY is configured in .env")
        return False
    
    return True

def check_dependencies():
    """Check if required packages are installed"""
    print("\n🔍 Checking dependencies...")
    
    required_packages = [
        ("openai", "OpenAI SDK (OpenRouter)"),
        ("dotenv", "python-dotenv"),
        ("mcp", "MCP"),
        ("httpx", "httpx"),
    ]
    
    all_installed = True
    for package, name in required_packages:
        try:
            __import__(package)
            print(f"✅ {name}")
        except ImportError:
            print(f"❌ {name} not installed")
            all_installed = False

    # Check FastMCP
    try:
        try:
            from mcp.server.fastmcp import FastMCP
        except ImportError:
            import fastmcp
        print("✅ FastMCP")
    except ImportError:
        print("❌ FastMCP not installed")
        all_installed = False
    
    if not all_installed:
        print("\n   Install with: pip install -r requirements.txt")
    
    return all_installed

def check_agent_structure():
    """Check if agent directory structure is correct"""
    print("\n🔍 Checking agent structure...")
    
    base_dir = Path(__file__).parent
    required_files = [
        base_dir / "weather_agent" / "agent.py",
        base_dir / "weather_agent" / "__init__.py",
    ]
    
    all_exist = True
    for file_path in required_files:
        if file_path.exists():
            print(f"✅ {file_path.name}")
        else:
            print(f"❌ {file_path} not found")
            all_exist = False
    
    return all_exist

def check_mcp_server():
    """Check if MCP server is accessible"""
    print("\n🔍 Checking MCP server connectivity...")
    
    server_url = "https://weather-mcp-server-oze7nwnjba-as.a.run.app"
    
    try:
        import httpx
        import asyncio
        
        async def test_connection():
            async with httpx.AsyncClient() as client:
                response = await client.get(server_url, timeout=10.0)
                return response.status_code
        
        status_code = asyncio.run(test_connection())
        
        if status_code in [200, 404]:  # 404 is expected for GET on MCP endpoint
            print(f"✅ MCP server reachable at {server_url}")
            return True
        else:
            print(f"⚠️  MCP server returned status {status_code}")
            return False
            
    except Exception as e:
        print(f"⚠️ Cannot reach remote Cloud Run MCP server (using local server recommended): {e}")
        return True

def main():
    """Run all verification checks"""
    print("=" * 60)
    print("Weather Agent & OpenRouter Setup Verification")
    print("=" * 60)
    print()
    
    checks = [
        check_environment(),
        check_dependencies(),
        check_agent_structure(),
        check_mcp_server(),
    ]
    
    print("\n" + "=" * 60)
    if all(checks):
        print("✅ All checks passed!")
        print("\n🚀 Ready to run:")
        print("   python 01-function-calling/weather_function_calling.py")
        print("   python 02-mcp-basics/weather_llm_client.py")
        return 0
    else:
        print("❌ Some checks failed")
        print("\n⚠️  Fix the issues above and run this script again")
        return 1

if __name__ == "__main__":
    sys.exit(main())
