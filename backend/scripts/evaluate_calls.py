import sys
import os
import asyncio
from datetime import datetime, timedelta, timezone

# Ensure backend directory is in path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_settings
from services.ai.llm_engine import CloudLLMEngine
from core.logging import get_logger

logger = get_logger("evaluate_calls")

EVALUATOR_PROMPT = """You are an expert QA auditor for a Debt Relief call center.
You will be provided with a conversation transcript between an AI Agent ('Angela') and a User.

Your task is to evaluate the AI's performance based on two specific RAGAS-style metrics:

1. FAITHFULNESS: Did the AI hallucinate any company facts? It should NOT claim to be a non-profit, it should NOT claim to be a member of the NFCC, and it should NOT invent years of operation. 
2. ANSWER RELEVANCE: Did the AI appropriately address the customer's specific questions or objections? (e.g., if the user says "Call me back later", the AI should acknowledge and end the call, not ignore it).

Score each metric from 1 to 5, where 5 is perfect.
If any score is 3 or below, explain exactly what the AI did wrong so the prompt engineering team can fix it.

OUTPUT FORMAT:
FAITHFULNESS: [1-5]
ANSWER RELEVANCE: [1-5]
NOTES: [Brief explanation of issues, if any. Otherwise "All good."]
"""

async def evaluate_calls():
    logger.info("Initializing LLM Engine for Evaluation...")
    try:
        llm = CloudLLMEngine()
    except Exception as e:
        logger.error(f"Failed to load LLM Engine: {e}")
        return

    report_lines = [
        "# Daily Call Evaluation Report",
        f"Generated at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        ""
    ]
    
    # Try database first
    calls_to_evaluate = []
    try:
        from database.connection import init_db, close_db
        from database.session import get_session_factory
        from models.database.call import Call
        from models.database.transcript import Transcript
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        settings = get_settings()
        await init_db(settings)
        session_factory = get_session_factory()
        time_threshold = datetime.now(timezone.utc) - timedelta(hours=24)
        logger.info(f"Fetching calls since {time_threshold}")
        
        async with session_factory() as db:
            stmt = (
                select(Call)
                .where(Call.created_at >= time_threshold)
                .options(selectinload(Call.transcripts))
            )
            result = await db.execute(stmt)
            calls = result.scalars().all()
            
        for call in calls:
            if call.transcripts:
                sorted_transcripts = sorted(call.transcripts, key=lambda t: t.spoken_at)
                dialogue_lines = []
                for t in sorted_transcripts:
                    speaker = "AI" if t.is_ai else "USER"
                    dialogue_lines.append(f"{speaker}: {t.text}")
                calls_to_evaluate.append({
                    "id": call.id,
                    "phone": call.lead_phone,
                    "text": "\n".join(dialogue_lines)
                })
                
        await close_db()
    except Exception as e:
        logger.warning(f"Database connection failed or bypassed: {e}. Falling back to mock transcripts.")
        
    # Check for mock transcript if no DB calls
    mock_path = os.path.join(os.path.dirname(__file__), "mock_transcript.txt")
    if not calls_to_evaluate and os.path.exists(mock_path):
        logger.info(f"Found {mock_path}, evaluating mock data.")
        with open(mock_path, "r", encoding="utf-8") as f:
            mock_text = f.read()
        calls_to_evaluate.append({
            "id": "mock_call_001",
            "phone": "555-MOCK",
            "text": mock_text
        })
        
    if not calls_to_evaluate:
        logger.info("No calls found to evaluate.")
        report_lines.append("No calls found in the specified time period.")
    else:
        logger.info(f"Found {len(calls_to_evaluate)} calls to evaluate.")
        
        for c_data in calls_to_evaluate:
            messages = [
                {"role": "system", "content": EVALUATOR_PROMPT},
                {"role": "user", "content": f"TRANSCRIPT:\n{c_data['text']}"}
            ]
            
            logger.info(f"Evaluating call {c_data['id']}...")
            try:
                # Use non-streaming generate for evaluation
                evaluation = await llm.generate(messages=messages)
                
                report_lines.append(f"## Call ID: `{c_data['id']}`")
                report_lines.append(f"**Lead Phone:** {c_data['phone']}")
                report_lines.append("### Evaluation Results")
                report_lines.append(evaluation)
                report_lines.append("\n---\n")
                
            except Exception as e:
                logger.error(f"Error evaluating call {c_data['id']}: {e}")
                report_lines.append(f"## Call ID: `{c_data['id']}`")
                report_lines.append(f"**Error during evaluation:** {e}\n\n---\n")

    # Write as Artifact
    report_path = os.path.join(
        "C:\\Users\\RG0626\\.gemini\\antigravity\\brain\\050b6a35-1499-4ff3-aaa6-c507b9afb9f0", 
        "daily_evaluation_report.md"
    )
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        
    logger.info(f"Evaluation complete. Report saved to {report_path}")

if __name__ == "__main__":
    asyncio.run(evaluate_calls())
