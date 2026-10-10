from enum import Enum
from core.logging import get_logger
from conversation_engine.session_manager import CallSession, SessionManager

logger = get_logger(__name__)

class CallState(str, Enum):
    WAIT_FOR_ANSWER = "WAIT_FOR_ANSWER"
    INTRO = "INTRO"
    DISCLOSURE = "DISCLOSURE"
    QUALIFICATION = "QUALIFICATION"
    OBJECTION_HANDLING = "OBJECTION_HANDLING"
    TRANSFER_ROUTING = "TRANSFER_ROUTING"
    POLITE_CLOSE = "POLITE_CLOSE"
    ENDED = "ENDED"

class CallFSM:
    """
    Finite State Machine for the call.
    Uses SessionManager to persist current state.
    """
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    async def advance_state(self, call_id: str, trigger: str, context: dict) -> CallState:
        """
        Calculates next state based on trigger and current state.
        Updates session in Redis.
        """
        session = await self.session_manager.get_session(call_id)
        if not session:
            logger.error(f"Session not found for call_id: {call_id}")
            raise ValueError(f"Session not found for call_id: {call_id}")
            
        current_state_str = getattr(session, 'state', CallState.WAIT_FOR_ANSWER.value)
        try:
            current_state = CallState(current_state_str)
        except ValueError:
            logger.warning(f"Invalid state {current_state_str}, defaulting to WAIT_FOR_ANSWER")
            current_state = CallState.WAIT_FOR_ANSWER

        next_state = current_state

        if trigger == "opt_out":
            if current_state != CallState.POLITE_CLOSE:
                next_state = CallState.POLITE_CLOSE
            else:
                next_state = CallState.ENDED
        elif trigger == "hangup":
            next_state = CallState.ENDED
        elif current_state == CallState.WAIT_FOR_ANSWER:
            if trigger == "answered":
                next_state = CallState.INTRO
        elif current_state == CallState.INTRO:
            if trigger == "objection":
                context["return_state"] = current_state.value
                next_state = CallState.OBJECTION_HANDLING
            elif trigger == "continue":
                next_state = CallState.DISCLOSURE
        elif current_state == CallState.DISCLOSURE:
            if trigger == "objection":
                context["return_state"] = current_state.value
                next_state = CallState.OBJECTION_HANDLING
            elif trigger == "continue":
                next_state = CallState.QUALIFICATION
        elif current_state == CallState.QUALIFICATION:
            if trigger == "objection":
                context["return_state"] = current_state.value
                next_state = CallState.OBJECTION_HANDLING
            elif trigger == "qualified":
                next_state = CallState.TRANSFER_ROUTING
            elif trigger == "not_qualified":
                next_state = CallState.POLITE_CLOSE
        elif current_state == CallState.OBJECTION_HANDLING:
            if trigger == "resolved":
                return_state_str = context.get("return_state", CallState.QUALIFICATION.value)
                try:
                    next_state = CallState(return_state_str)
                except ValueError:
                    next_state = CallState.QUALIFICATION
            elif trigger == "unresolved":
                next_state = CallState.POLITE_CLOSE
        elif current_state == CallState.TRANSFER_ROUTING:
            if trigger == "transferred":
                next_state = CallState.ENDED
        elif current_state == CallState.POLITE_CLOSE:
            if trigger == "continue":
                next_state = CallState.ENDED

        session.state = next_state.value
        await self.session_manager.save_session(session)
        logger.info(f"FSM transitioned call {call_id}: {current_state.value} -> {next_state.value} on trigger '{trigger}'")
        return next_state
