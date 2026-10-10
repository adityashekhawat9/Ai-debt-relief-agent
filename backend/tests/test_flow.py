import asyncio
import sys

# Mock get_logger before importing FSM
class MockLogger:
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass
    def debug(self, *args, **kwargs): pass

class MockCoreLogging:
    @staticmethod
    def get_logger(name): return MockLogger()

import sys
from types import ModuleType
core_logging = ModuleType('core.logging')
core_logging.get_logger = MockCoreLogging.get_logger
sys.modules['core.logging'] = core_logging

# Mock Redis
redis = ModuleType('redis')
redis.asyncio = ModuleType('redis.asyncio')
sys.modules['redis'] = redis
sys.modules['redis.asyncio'] = redis.asyncio

from conversation_engine.fsm import CallFSM, CallState
from conversation_engine.opt_out_detector import OptOutDetector


# Mock Session Manager for testing FSM without Redis
class MockSessionManager:
    def __init__(self):
        self.sessions = {}
        
    async def get_session(self, call_id):
        class MockSession:
            def __init__(self, state):
                self.state = state
                self.call_id = call_id
        return MockSession(self.sessions.get(call_id, CallState.WAIT_FOR_ANSWER.value))
        
    async def update_session(self, call_id, **kwargs):
        if "fsm_state" in kwargs:
            self.sessions[call_id] = kwargs["fsm_state"]

    async def save_session(self, session):
        self.sessions[session.call_id] = session.state

# Mock LLM Engine for testing LangGraph without llama.cpp
class MockLLMEngine:
    async def generate_stream(self, messages, max_tokens=150, temperature=0.3):
        yield "This "
        yield "is "
        yield "a "
        yield "mocked "
        yield "response."
        
    async def generate(self, messages):
        return "This is a mocked response."

async def test_flow():
    print("--- Testing Opt-Out Detector ---")
    detector = OptOutDetector()
    print("Test 'I am interested':", detector.is_opt_out("I am interested")) # False
    print("Test 'Please do not call me':", detector.is_opt_out("Please do not call me again")) # True
    print("Test 'Lose my number':", detector.is_opt_out("Hey, lose my number!")) # True
    print()

    print("--- Testing FSM Routing ---")
    mock_sm = MockSessionManager()
    fsm = CallFSM(mock_sm)
    call_id = "test-call-123"
    
    # Simulate Call Flow
    state = await fsm.advance_state(call_id, "answered", {})
    await mock_sm.update_session(call_id, fsm_state=state.value)
    print(f"Trigger: 'answered' -> State: {state.value}")
    
    state = await fsm.advance_state(call_id, "continue", {})
    await mock_sm.update_session(call_id, fsm_state=state.value)
    print(f"Trigger: 'continue'  -> State: {state.value}")
    
    state = await fsm.advance_state(call_id, "objection", {"return_state": state.value})
    await mock_sm.update_session(call_id, fsm_state=state.value)
    print(f"Trigger: 'objection' -> State: {state.value}")
    
    state = await fsm.advance_state(call_id, "opt_out", {})
    await mock_sm.update_session(call_id, fsm_state=state.value)
    print(f"Trigger: 'opt_out'   -> State: {state.value}")
    
    state = await fsm.advance_state(call_id, "opt_out", {})
    await mock_sm.update_session(call_id, fsm_state=state.value)
    print(f"Trigger: 'opt_out' (again) -> State: {state.value}")
    print()

if __name__ == "__main__":
    asyncio.run(test_flow())
