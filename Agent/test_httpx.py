"""
Test httpx connectivity to Agent servers
"""
import asyncio
import httpx

async def test_connection():
    print("Testing httpx connection to Agent servers...")
    
    # Test with same configuration as AgentBridge
    timeout = httpx.Timeout(30.0)
    client = httpx.AsyncClient(timeout=timeout)
    
    try:
        print("\n1. Testing Calculator Agent (port 9001)...")
        response = await client.post("http://127.0.0.1:9001/handshake")
        print(f"   Status: {response.status_code}")
        print(f"   Data: {response.json()}")
    except Exception as e:
        print(f"   ERROR: {type(e).__name__}: {e}")
    
    try:
        print("\n2. Testing Data Generator Agent (port 9002)...")
        response = await client.post("http://127.0.0.1:9002/handshake")
        print(f"   Status: {response.status_code}")
        print(f"   Data: {response.json()}")
    except Exception as e:
        print(f"   ERROR: {type(e).__name__}: {e}")
    
    await client.aclose()
    print("\n✅ Test complete")

if __name__ == "__main__":
    asyncio.run(test_connection())
