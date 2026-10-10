import asyncio
import os
from conversation_engine.langgraph_dialogue import DialogueManager, DialogueState
from langchain_core.messages import HumanMessage, AIMessage

class MockRAG:
    async def get_rebuttal(self, text): return ""

class MockLLM:
    async def generate(self, msgs):
        print("\n=== LLM CALLED WITH ===")
        for m in msgs:
            print(f"[{m['role'].upper()}]\n{m['content']}\n")
        return "Stub Response"

dm = DialogueManager(MockLLM(), None, None)
dm.rag_service = MockRAG()

async def run():
    state = DialogueState(
        messages=[
            AIMessage(content="Hi, this is Angela. I'm calling from Debt Relief Services. We're actually reaching out because we might have some really good news for you. It looks like you could qualify for a program that significantly reduces what you currently owe. Just to see if you qualify... do you happen to have more than seven thousand dollars in unsecured debt, like credit cards, medical bills, utilities, or personal loans?"),
            HumanMessage(content="Yes.")
        ],
        script_step="1",
        fsm_state="",
        qualification_answers={},
        objection_count=0,
        dnc_count=0,
        intent="qualification",
        lead_first_name="",
        nlu_response=None,
        sentiment="neutral"
    )
    result = await dm._step_1_node(state)
    print("Result:", result)

if __name__ == "__main__":
    asyncio.run(run())
