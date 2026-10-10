import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import get_settings
from conversation_engine.langgraph_dialogue import DialogueManager, DialogueState
from services.ai.llm_engine import LLMEngine
from langchain_core.messages import HumanMessage

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TestWorkflow")

async def test_full_workflow():
    logger.info("Initializing LLM Engine...")
    llm = LLMEngine()
    manager = DialogueManager(llm_engine=llm)
    
    state: DialogueState = {
        "messages": [],
        "fsm_state": "QUALIFICATION",
        "script_step": 0
    }
    
    test_inputs = [
        "hello",
        "yes I pay them on time",
        "yes i am the decision maker",
        "about 20000 dollars, no medical",
        "i have 4 cards",
        "no i want to keep one for emergencies",
        "i pay 200 a month",
        "ok i can afford 300",
        "i am employed full time"
    ]
    
    for i, user_msg in enumerate(test_inputs):
        logger.info("=" * 60)
        logger.info(f"TURN {i}: USER SAYS -> '{user_msg}'")
        logger.info("=" * 60)
        
        state["messages"].append(HumanMessage(content=user_msg))
        
        logger.info(f"PRE-RUN: script_step={state.get('script_step')}, fsm_state={state.get('fsm_state')}")
        
        state = await manager.generate_reply(state)
        
        ai_reply = state["messages"][-1].content
        logger.info(f"AI OUTPUT: {ai_reply}")
        logger.info(f"POST-RUN: script_step={state.get('script_step')}, fsm_state={state.get('fsm_state')}\n")

if __name__ == "__main__":
    asyncio.run(test_full_workflow())
