import asyncio
import sys
import os

# Add backend to path so we can import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ai.rag_service import RAGService
from services.ai.llm_engine import CloudLLMEngine
from core.logging import get_logger

logger = get_logger("RAG_Evaluator")

# Small test suite covering a variety of scenarios
TEST_DATASET = [
    {"user_query": "What is the name of this program?", "expected_id": "1"},
    {"user_query": "Why did you call me today?", "expected_id": "2"},
    {"user_query": "What company is this?", "expected_id": "3"},
    {"user_query": "Please put me on the Do Not Call list.", "expected_id": "6"},
    {"user_query": "Are you calling from India?", "expected_id": "8"},
    {"user_query": "Is this a scam?", "expected_id": "17"},
    {"user_query": "How will this affect my credit score?", "expected_id": "20"},
    {"user_query": "Can you email this information to me?", "expected_id": "21"},
    {"user_query": "I have been sued by my creditor.", "expected_id": "24"}
]

EVAL_SYSTEM_PROMPT = """You are an expert AI evaluator.
Your job is to evaluate the quality of an AI agent's response in a debt relief call center setting.
You will answer with a single word: "YES" or "NO"."""

async def evaluate_faithfulness(llm, retrieved_rebuttal, generated_response):
    prompt = f"""
    Retrieved Ground Truth Rebuttal: "{retrieved_rebuttal}"
    AI Generated Response: "{generated_response}"
    
    Question: Did the AI Generated Response stick strictly to the facts provided in the Ground Truth Rebuttal? 
    (It is allowed to add conversational filler like 'I understand', but it must NOT invent new numbers, company policies, or promises).
    Answer YES or NO.
    """
    messages = [
        {"role": "system", "content": EVAL_SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]
    result = await llm.generate(messages)
    return "YES" in result.upper()

async def evaluate_answer_relevancy(llm, user_query, generated_response):
    prompt = f"""
    User Asked: "{user_query}"
    AI Generated Response: "{generated_response}"
    
    Question: Does the AI Generated Response directly address or answer the User's question/statement?
    Answer YES or NO.
    """
    messages = [
        {"role": "system", "content": EVAL_SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]
    result = await llm.generate(messages)
    return "YES" in result.upper()

async def simulate_dialogue_generation(llm, user_query, rebuttal):
    prompt = f"""
    You are Angela from Debt Relief Service. 
    The user just said: "{user_query}"
    You must respond using EXACTLY the information in this rebuttal, but you may weave it into natural conversation.
    Rebuttal to use: "{rebuttal}"
    """
    messages = [
        {"role": "user", "content": prompt}
    ]
    return await llm.generate(messages)

async def main():
    print("Initializing RAG Service and LLM Engine...")
    rag = RAGService()
    llm = CloudLLMEngine()
    
    total = len(TEST_DATASET)
    context_relevance_score = 0
    faithfulness_score = 0
    answer_relevancy_score = 0
    
    print(f"Starting evaluation of {total} test cases...\n")
    
    for i, test in enumerate(TEST_DATASET):
        query = test["user_query"]
        expected_id = test["expected_id"]
        
        print(f"--- Test {i+1}/{total} ---")
        print(f"User Query: {query}")
        
        # 1. Test Context Relevance (Retrieval)
        from services.ai.rag_service import REBUTTALS
        query_vector = rag.model.encode(query).tolist()
        results = rag.client.query_points(
            collection_name=rag.collection_name,
            query=query_vector,
            limit=1
        ).points
        
        retrieved_text = results[0].payload["rebuttal"] if results else ""
        retrieved_key = next((k for k, v in REBUTTALS.items() if v == retrieved_text), None)
        confidence = results[0].score if results else 0.0
        
        is_context_relevant = (retrieved_key == expected_id)
        if is_context_relevant:
            context_relevance_score += 1
            print(f"[PASS] Context Relevance: Matched expected ID {expected_id} (Confidence: {confidence:.2f})")
        else:
            print(f"[FAIL] Context Relevance: Failed. Expected ID {expected_id}, Got ID {retrieved_key} (Confidence: {confidence:.2f})")
            
        # If retrieval failed, we still test the generation based on what it DID retrieve to see if the LLM is faithful
        
        # 2. Simulate AI Generation
        generated_response = await simulate_dialogue_generation(llm, query, retrieved_text)
        print(f"AI Response: {generated_response}")
        
        # 3. Test Faithfulness
        is_faithful = await evaluate_faithfulness(llm, retrieved_text, generated_response)
        if is_faithful:
            faithfulness_score += 1
            print("[PASS] Faithfulness: Passed")
        else:
            print("[FAIL] Faithfulness: Failed (Hallucination detected)")
            
        # 4. Test Answer Relevancy
        is_relevant = await evaluate_answer_relevancy(llm, query, generated_response)
        if is_relevant:
            answer_relevancy_score += 1
            print("[PASS] Answer Relevancy: Passed")
        else:
            print("[FAIL] Answer Relevancy: Failed")
            
        print("-" * 40 + "\n")
        
    print("=== FINAL EVALUATION REPORT ===")
    print(f"Context Relevance (Retrieval Accuracy): {context_relevance_score}/{total} ({(context_relevance_score/total)*100:.1f}%)")
    print(f"Faithfulness (No Hallucinations):       {faithfulness_score}/{total} ({(faithfulness_score/total)*100:.1f}%)")
    print(f"Answer Relevancy (Addresses Question):  {answer_relevancy_score}/{total} ({(answer_relevancy_score/total)*100:.1f}%)")

if __name__ == "__main__":
    asyncio.run(main())
