import asyncio
import os
from langchain_core.messages import HumanMessage
from conversation_engine.langgraph_dialogue import DialogueManager
from services.ai.llm_engine import CloudLLMEngine
from core.config import get_settings

async def main():
    os.environ["USE_CLOUD_LLM"] = "True"
    llm = CloudLLMEngine()
    dm = DialogueManager(llm_engine=llm)

    # Test 1: Step 0 - user says "Yes"
    state0 = {
        "messages": [HumanMessage(content="Yes.")],
        "fsm_state": "QUALIFICATION",
        "qualification_answers": {},
        "objection_count": 0,
        "intent": "qualification",
        "script_step": 0,
        "lead_first_name": "John"
    }
    res0 = await dm._step_0_node(state0)
    print("=" * 60)
    print("TEST 1: Step 0, User says 'Yes.'")
    print(f"  script_step => {res0.get('script_step')}")
    print(f"  Response starts with: {res0['messages'][-1].content[:60]}...")
    assert res0.get("script_step") == "0_B", "FAIL: Should advance to 0_B"
    print("  PASS!")

    # Test 2: Step 0_B - user says "Yes"
    state0b = {
        "messages": [HumanMessage(content="Yes.")],
        "fsm_state": "QUALIFICATION",
        "qualification_answers": {},
        "objection_count": 0,
        "intent": "qualification",
        "script_step": "0_B",
        "lead_first_name": "John"
    }
    res0b = await dm._step_0_b_node(state0b)
    print("=" * 60)
    print("TEST 2: Step 0_B, User says 'Yes.'")
    print(f"  script_step => {res0b.get('script_step')}")
    print(f"  Response starts with: {res0b['messages'][-1].content[:60]}...")
    assert res0b.get("script_step") == "1", "FAIL: Should advance to 1"
    print("  PASS!")

    # Test 3: Step 0_B - user says "Yeah I do"
    state0b2 = {
        "messages": [HumanMessage(content="Yeah I do.")],
        "fsm_state": "QUALIFICATION",
        "qualification_answers": {},
        "objection_count": 0,
        "intent": "qualification",
        "script_step": "0_B",
        "lead_first_name": "John"
    }
    res0b2 = await dm._step_0_b_node(state0b2)
    print("=" * 60)
    print("TEST 3: Step 0_B, User says 'Yeah I do.'")
    print(f"  script_step => {res0b2.get('script_step')}")
    assert res0b2.get("script_step") == "1", "FAIL: Should advance to 1"
    print("  PASS!")

    # Test 4: Step 1 - user says "20 thousand"
    state1 = {
        "messages": [HumanMessage(content="20 thousand")],
        "fsm_state": "QUALIFICATION",
        "qualification_answers": {},
        "objection_count": 0,
        "intent": "qualification",
        "script_step": "1",
        "lead_first_name": "John"
    }
    res1 = await dm._step_1_node(state1)
    print("=" * 60)
    print("TEST 4: Step 1, User says '20 thousand'")
    print(f"  script_step => {res1.get('script_step')}")
    assert res1.get("script_step") == "2", "FAIL: Should advance to 2"
    print("  PASS!")

    # Test 5: Step 1 - user says "4000" (under 7k)
    state1b = {
        "messages": [HumanMessage(content="4000")],
        "fsm_state": "QUALIFICATION",
        "qualification_answers": {},
        "objection_count": 0,
        "intent": "qualification",
        "script_step": "1",
        "lead_first_name": "John"
    }
    res1b = await dm._step_1_node(state1b)
    print("=" * 60)
    print("TEST 5: Step 1, User says '4000' (under $7k)")
    print(f"  script_step => {res1b.get('script_step')}")
    print(f"  Response: {res1b['messages'][-1].content[:80]}...")
    assert res1b.get("script_step") is None, "FAIL: Should NOT advance (under 7k)"
    print("  PASS!")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(main())
