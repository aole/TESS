import ollama
import asyncio

async def test_raw_output():
    print("Starting raw output test...")
    full_response = ""
    try:
        # We use the options template hack to ensure we get raw content if possible, 
        # or just standard chat if that's what's working now.
        # But specifically we want to see if <think> tags appear in the content.
        
        # Note: We need to use a model that actually exists and is the one causing issues.
        # The user mentioned "ServiceNow-AI_Apriel-1.6-15b-Think:Q6_K_L"
        model = 'ServiceNow-AI_Apriel-1.6-15b-Think:Q6_K_L'
        
        print(f"Chatting with {model}...")
        stream = await ollama.AsyncClient().chat(
            model=model,
            messages=[{'role': 'user', 'content': 'Why is sky blue? Answer briefly.'}],
            stream=True
        )
        
        async for chunk in stream:
            content = chunk.get('message', {}).get('content', '')
            print(f"CHUNK: {repr(content)}")
            full_response += content

        print(f"\n--- FULL RESPONSE ---\n{full_response}\n---------------------")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    asyncio.run(test_raw_output())
