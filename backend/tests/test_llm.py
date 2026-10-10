import asyncio
from dotenv import load_dotenv
load_dotenv()
from services.ai.rag_service import RAGService

async def test():
    rag = RAGService()
    sys_prompt = f"""You are an expert intent classifier for a debt relief call center. 
Your job is to match the user's message to the most relevant category from the list below.

CATEGORIES:
{rag.categories_text}

INSTRUCTIONS:
1. Find the category that best matches the user's intent.
2. Output ONLY the number of the matching category (e.g., '4' or '8'). Do not output any other words, punctuation, or explanation.
3. If the user's message is completely unrelated to ANY category, output '0'."""
    
    import httpx
    import os
    headers = {'Authorization': f'Bearer {os.getenv("GROQ_API_KEY")}', 'Content-Type': 'application/json'}
    payload = {
        "model": "llama3-8b-8192",
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": 'where is your company situated'}
        ],
        "temperature": 0.0,
        "max_tokens": 10
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post('https://api.groq.com/openai/v1/chat/completions', headers=headers, json=payload, timeout=10.0)
        print('RESPONSE STATUS:', resp.status_code)
        if resp.status_code == 200:
             print('LLM OUTPUT:', resp.json()['choices'][0]['message']['content'])
        else:
             print('ERROR:', resp.text)

asyncio.run(test())
