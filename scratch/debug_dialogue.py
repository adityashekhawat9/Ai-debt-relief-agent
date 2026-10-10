import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/backend'))

from langchain_core.messages import HumanMessage
from conversation_engine.langgraph_dialogue import DialogueManager
from services.ai.llm_engine import LLMEngine

async def main():
    llm = LLMEngine()
    manager = DialogueManager(llm_engine=llm)
    
    state = {
        "messages": [],
        "fsm_state": "QUALIFICATION",
        "qualification_answers": {},
        "objection_count": 0,
        "intent": None,
        "script_step": 0,
        "lead_first_name": "John"
    }
    
    print("--- CALL STARTED ---")
    
    # 1. AI initial greeting
    state = await manager.generate_reply(state)
    print(f"\n[Step {state['script_step']}] AI: {state['messages'][-1].content}")
    
    # 2. User says hello (interrupting or greeting back)
    print("\nUSER SAYS: 'hello'")
    state["messages"] = list(state["messages"]) + [HumanMessage(content="hello")]
    state = await manager.generate_reply(state)
    print(f"\n[Step {state['script_step']}] AI: {state['messages'][-1].content}")

    # 3. User asks a question
    print("\nUSER SAYS: 'what is this about?'")
    state["messages"] = list(state["messages"]) + [HumanMessage(content="what is this about?")]
    state = await manager.generate_reply(state)
    print(f"\n[Step {state['script_step']}] AI: {state['messages'][-1].content}")

    # 4. User says yes
    print("\nUSER SAYS: 'yes'")
    state["messages"] = list(state["messages"]) + [HumanMessage(content="yes")]
    state = await manager.generate_reply(state)
    print(f"\n[Step {state['script_step']}] AI: {state['messages'][-1].content}")

if __name__ == "__main__":
    asyncio.run(main())
