import operator
import json
import re
from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from core.logging import get_logger
from services.ai.rag_service import RAGService
from .checkpointer import CheckpointerFactory

logger = get_logger(__name__)

from .config_prompts import (
    UNIVERSAL_BEHAVIOR_PROMPT, SCRIPT_TEXTS, REDIRECT_QUESTIONS,
    PROMPT_INJECTION_PHRASES, HOSTILE_PHRASES, OBJECTION_PHRASES,
    DNC_PHRASES, BUSY_PHRASES, VOICEMAIL_PHRASES, CONTINUITY_PHRASES,
    LANGUAGE_BARRIER_PHRASES, AFFIRM_WORDS, DENY_WORDS, GREETING_WORDS, WORD_TO_NUM
)






class DialogueState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    fsm_state: str
    qualification_answers: dict
    objection_count: int
    dnc_count: int
    intent: str | None
    script_step: str | int
    lead_first_name: str | None
    nlu_response: str | None
    sentiment: str

class DialogueManager:
    def __init__(self, llm_engine, qdrant_service=None, embedder_service=None):
        self.llm_engine = llm_engine
        self.qdrant_service = qdrant_service
        self.embedder_service = embedder_service
        self.rag_service = RAGService()
        self.checkpointer = CheckpointerFactory.get_checkpointer()
        self.graph = self._build_graph()
        
    def _build_graph(self):
        workflow = StateGraph(DialogueState)
        
        workflow.add_node("router", self._router_node)
        
        workflow.add_node("step_1", self._step_1_node)
        workflow.add_node("step_2", self._step_2_node)
        workflow.add_node("step_3", self._step_3_node)
        workflow.add_node("step_4", self._step_4_node)
        workflow.add_node("step_5", self._step_5_node)
        workflow.add_node("step_6", self._step_6_node)
        
        workflow.add_node("objection", self._objection_node)
        workflow.add_node("knowledge_retrieval", self._knowledge_node)
        workflow.add_node("fast_nlu", self._fast_nlu_node)
        workflow.add_node("hostile", self._hostile_node)
        workflow.add_node("clarify", self._clarify_node)
        workflow.add_node("dnc", self._dnc_node)
        workflow.add_node("busy", self._busy_node)
        workflow.add_node("voicemail", self._voicemail_node)
        workflow.add_node("continuity", self._continuity_node)
        workflow.add_node("language_barrier", self._language_barrier_node)
        
        workflow.set_entry_point("router")
        
        workflow.add_conditional_edges(
            "router",
            self._route_intent,
            {
                "step_1": "step_1",
                "step_2": "step_2",
                "step_3": "step_3",
                "step_4": "step_4",
                "step_5": "step_5",
                "step_6": "step_6",
                "objection": "objection",
                "knowledge_retrieval": "knowledge_retrieval",
                "fast_nlu": "fast_nlu",
                "hostile": "hostile",
                "clarify": "clarify",
                "dnc": "dnc",
                "continuity": "continuity",
                "language_barrier": "language_barrier"
            }
        )
        
        workflow.add_edge("step_1", END)
        workflow.add_edge("step_2", END)
        workflow.add_edge("step_3", END)
        workflow.add_edge("step_4", END)
        workflow.add_edge("step_5", END)
        workflow.add_edge("step_6", END)
        workflow.add_edge("objection", END)
        workflow.add_edge("knowledge_retrieval", END)
        workflow.add_edge("fast_nlu", END)
        workflow.add_edge("hostile", END)
        workflow.add_edge("dnc", END)
        workflow.add_edge("busy", END)
        workflow.add_edge("voicemail", END)
        workflow.add_edge("continuity", END)
        workflow.add_edge("language_barrier", END)
        
        return workflow.compile(checkpointer=self.checkpointer)
        


    async def _router_node(self, state: DialogueState) -> dict:
        intent = "qualification"
        nlu_response = None
        
        if state["messages"] and isinstance(state["messages"][-1], HumanMessage):
            last_msg = state["messages"][-1].content
            clean_msg = last_msg.strip().lower()
            
            # --- 0. PYTHON KEYWORD FAST-PATH for hostile/objection ---
            for phrase in VOICEMAIL_PHRASES:
                if phrase in clean_msg:
                    logger.info(f"[KEYWORD] Voicemail phrase detected: '{phrase}'")
                    return {"intent": "voicemail", "nlu_response": None, "sentiment": state.get("sentiment", "neutral")}
            
            # --- 0.5. CONTINUITY CHECK ("hello?", "are you there?") mid-conversation ---
            current_step = state.get("script_step", 1)
            if str(current_step) != "1":
                clean_check = clean_msg.rstrip("?.! ")
                if clean_check in CONTINUITY_PHRASES:
                    logger.info(f"[KEYWORD] Continuity check detected: '{clean_msg}' at step {current_step}")
                    return {"intent": "continuity", "nlu_response": None, "sentiment": state.get("sentiment", "neutral")}
                    
            for phrase in DNC_PHRASES:
                if phrase in clean_msg:
                    logger.info(f"[KEYWORD] DNC phrase detected: '{phrase}'")
                    return {"intent": "dnc", "nlu_response": None, "sentiment": state.get("sentiment", "neutral")}
                    
            for phrase in BUSY_PHRASES:
                if phrase in clean_msg:
                    logger.info(f"[KEYWORD] Busy phrase detected: '{phrase}'")
                    return {"intent": "busy", "nlu_response": None, "sentiment": state.get("sentiment", "neutral")}
                    
            for phrase in PROMPT_INJECTION_PHRASES:
                if phrase in clean_msg:
                    logger.info(f"[KEYWORD] Prompt Injection phrase detected: '{phrase}'")
                    return {"intent": "hostile", "nlu_response": None, "sentiment": state.get("sentiment", "neutral")}
            
            for phrase in HOSTILE_PHRASES:
                if re.search(rf'\b{phrase}\b', clean_msg):
                    logger.info(f"[KEYWORD] Hostile phrase detected: '{phrase}'")
                    return {"intent": "hostile", "nlu_response": None, "sentiment": state.get("sentiment", "neutral")}
            
            for phrase in OBJECTION_PHRASES:
                if re.search(rf'\b{phrase}\b', clean_msg):
                    logger.info(f"[KEYWORD] Objection phrase detected: '{phrase}'")
                    return {"intent": "objection", "nlu_response": None, "sentiment": state.get("sentiment", "neutral")}
                    
            for phrase in LANGUAGE_BARRIER_PHRASES:
                if phrase in clean_msg:
                    logger.info(f"[KEYWORD] Language Barrier phrase detected: '{phrase}'")
                    return {"intent": "language_barrier", "nlu_response": None, "sentiment": state.get("sentiment", "neutral")}
            
            # --- 1. PRIMARY NLU FAST-PATH (Zero LLM Generation) ---
            if self.embedder_service and self.qdrant_service:
                try:
                    query_embedding = await self.embedder_service.embed_query(last_msg)
                    results = await self.qdrant_service.search(query_embedding, limit=1)
                    
                    # Check for a high-confidence match
                    if results and getattr(results[0], 'score', 0) > 0.85:
                        payload = getattr(results[0], 'payload', {})
                        matched_intent = payload.get("intent", "").lower()
                        
                        logger.info(f"[RAG MATCH] Found highly confident intent: {matched_intent} (Score: {results[0].score})")
                        
                        if matched_intent.startswith("advance_"):
                            intent = "fast_nlu"
                            nlu_response = payload.get("text", "")
                            return {"intent": intent, "nlu_response": nlu_response}
                        elif matched_intent in ["objection", "lawsuit_threat", "not_interested", "scam_doubt", "bankruptcy"]:
                            intent = "objection"
                            return {"intent": intent}
                except Exception as e:
                    logger.error(f"RAG classification failed: {e}")
            # --- 1.5. FAST-PATH for simple YES/NO/NUMBER answers ---
            words = clean_msg.split()
            is_simple = len(words) <= 15 and not any(q in clean_msg for q in ["?", "what", "who", "how", "why", "but", "scam", "question", "ask", "wondering"])
            
            fast_path_matched = (
                self._is_affirmative(clean_msg) or 
                self._is_negative(clean_msg) or 
                self._extract_number(clean_msg) is not None or
                self._extract_employment(clean_msg) is not None or
                self._extract_bill_handling(clean_msg) is not None
            )
            
            if is_simple and fast_path_matched:
                logger.info("[FAST PATH] Simple yes/no/number/enum detected, routing to qualification.")
                return {"intent": "qualification", "nlu_response": None}
                
            # --- 2. FALLBACK LLM PATH (If RAG score is low or DB is empty) ---
            logger.info("[LOW CONFIDENCE] Falling back to fast LLM intent classification.")
            clean_intent = await self._classify_enum(
                state,
                "classify the user's LAST message into exactly ONE of these categories: OBJECTION, QUESTION, QUALIFICATION, HOSTILE, CLARIFY",
                ["OBJECTION", "QUESTION", "QUALIFICATION", "HOSTILE", "CLARIFY"]
            )
            
            clean_intent = clean_intent.strip().upper()
            if "HOSTILE" in clean_intent:
                intent = "hostile"
            elif "OBJECTION" in clean_intent:
                intent = "objection"
            elif "QUESTION" in clean_intent:
                intent = "question"
            elif "CLARIFY" in clean_intent:
                intent = "clarify"
            else:
                intent = "qualification"
                
        return {"intent": intent, "nlu_response": nlu_response}
        
    def _route_intent(self, state: DialogueState) -> str:
        intent = state.get("intent", "qualification")
        if intent == "hostile":
            return "hostile"
        elif intent == "clarify":
            return "clarify"
        elif intent == "dnc":
            return "dnc"
        elif intent == "voicemail":
            return "voicemail"
        elif intent == "continuity":
            return "continuity"
        elif intent == "objection":
            return "objection"
        elif intent == "language_barrier":
            return "language_barrier"
        elif intent == "question":
            return "knowledge_retrieval"
        elif intent == "fast_nlu":
            return "fast_nlu"
        
        current_step = state.get("script_step", 1)
        return f"step_{str(current_step).lower()}"

    async def _call_llm(self, sys_prompt: str, state: DialogueState, few_shot_msgs: list = None, allow_streaming: bool = True) -> str:
        universal_rule = "CRITICAL RULE: NEVER use the word 'balance'. Always refer to it as 'debt' or 'amount owed'.\n\n" + UNIVERSAL_BEHAVIOR_PROMPT
        
        qa = state.get("qualification_answers", {})
        context_str = ""
        if qa:
            context_str = "\n\nUSER PROFILE SO FAR:\n"
            if "total_debt" in qa: context_str += f"- Total Debt: ${qa['total_debt']}\n"
            if "card_count" in qa: context_str += f"- Number of Cards: {qa['card_count']}\n"
            if "monthly_payment" in qa: context_str += f"- Monthly Payment: ${qa['monthly_payment']}\n"
            context_str += "Use this context to naturally personalize your response and confirm their details if helpful."
        
        # --- ANTI-REPETITION: Extract recent AI phrases so the LLM avoids reusing them ---
        recent_ai_phrases = []
        for msg in state.get("messages", [])[-10:]:
            if isinstance(msg, AIMessage) and msg.content:
                # Extract the first ~60 chars (the appreciation/opener part)
                opener = msg.content[:80].split("?")[0].split("!")[0]
                if opener.strip():
                    recent_ai_phrases.append(opener.strip())
        
        anti_repeat_str = ""
        if recent_ai_phrases:
            anti_repeat_str = "\n\n=== PHRASES YOU ALREADY USED (NEVER REPEAT THESE — USE COMPLETELY DIFFERENT WORDS) ===\n"
            for phrase in recent_ai_phrases[-5:]:
                anti_repeat_str += f'- "{phrase}"\n'
            anti_repeat_str += "You MUST use a COMPLETELY DIFFERENT opener, filler pattern, and appreciation phrase than any listed above.\n"
            
        # 1. System Prompt stays 100% byte-static across all turns (GUARANTEED Prompt Cache Hit)
        messages = [SystemMessage(content=universal_rule)]
        if few_shot_msgs:
            messages.extend(few_shot_msgs)

        # 2. Ephemeral directives (turn instructions, anti-repeat, profile) injected into conversation window
        turn_directives = []
        if context_str:
            turn_directives.append(context_str.strip())
        if anti_repeat_str:
            turn_directives.append(anti_repeat_str.strip())
        if sys_prompt:
            turn_directives.append(f"=== CURRENT TASK ===\n{sys_prompt.strip()}")
        
        directive_block = "\n\n".join(turn_directives)

        history = list(state.get("messages", [])[-6:])
        clean_history = []
        for m in history[:-1]:
            if isinstance(m, HumanMessage):
                clean_content = re.sub(r'\[TURN GUIDANCE:[\s\S]*?\]\n\nCustomer:\s*', '', m.content).strip()
                clean_history.append(HumanMessage(content=clean_content))
            else:
                clean_history.append(m)

        if history:
            last_msg = history[-1]
            if isinstance(last_msg, HumanMessage):
                annotated_content = f"[TURN GUIDANCE:\n{directive_block}]\n\nCustomer: {last_msg.content}"
                messages.extend(clean_history)
                messages.append(HumanMessage(content=annotated_content))
            else:
                messages.extend(clean_history)
                messages.append(HumanMessage(content=f"[TURN GUIDANCE:\n{directive_block}]"))
        else:
            messages.append(HumanMessage(content=f"[TURN GUIDANCE:\n{directive_block}]"))
        
        if self.llm_engine:
            dict_msgs = [{"role": "system" if getattr(m, "type", "") == "system" else "user" if getattr(m, "type", "") == "human" else "assistant", "content": m.content} for m in messages]
            
            stream_cb = getattr(self, "_current_stream_callback", None) if allow_streaming else None
            if stream_cb:
                response_parts = []
                async for chunk in self.llm_engine.generate_stream(dict_msgs):
                    response_parts.append(chunk)
                    await stream_cb(chunk)
                response = "".join(response_parts)
            else:
                response = await self.llm_engine.generate(dict_msgs)
            
            # Hallucination Checker (FTC Compliance)
            blocked_words = [
                "guarantee", "promise", "upfront fee", "charge you", "fee", "cost", 
                "pay upfront", "100%", "settle for pennies", "wipe out", "erase"
            ]
            lower_resp = response.lower()
            for bw in blocked_words:
                if bw in lower_resp:
                    logger.warning(f"Hallucination Checker blocked response containing '{bw}'. Response was: {response}")
                    current_step = str(state.get("script_step", 1)).upper()
                    redirect = REDIRECT_QUESTIONS.get(current_step, "Let's stay focused on your account details.")
                    return f"I apologize, I cannot make any specific guarantees or discuss fees right now, as our senior counselors handle that. {redirect}"
                    
        return response
        
    async def _classify_enum(self, state: DialogueState, prompt: str, valid_enums: list[str]) -> str:
        """Uses the LLM to perform ultra-fast 1-token intent classification."""
        sys_prompt = f"""Based on the conversation context, {prompt}
You must respond with EXACTLY ONE WORD from this list: {", ".join(valid_enums)}. Do not add any punctuation."""
        
        # Only pass the last few messages for classification context
        temp_state = {"messages": list(state["messages"][-5:])}
        
        messages = [SystemMessage(content=sys_prompt)]
        messages.extend(temp_state["messages"])
        
        if self.llm_engine:
            dict_msgs = [{"role": "system" if getattr(m, "type", "") == "system" else "user" if getattr(m, "type", "") == "human" else "assistant", "content": m.content} for m in messages]
            try:
                # Bypass universal behavior prompt and streaming
                response = await self.llm_engine.generate(dict_msgs)
                clean_resp = response.strip().upper().translate(str.maketrans('', '', '.,!?'))
                for e in valid_enums:
                    if e == clean_resp or e in clean_resp.split():
                        return e
            except Exception as e:
                logger.error(f"Enum classification failed: {e}")
                
        return "UNKNOWN"

    # =========================================================================
    # DETERMINISTIC KEYWORD CLASSIFIERS (Python-level, no LLM needed)
    # These run BEFORE the LLM to handle obvious yes/no/number answers.
    # The LLM is ONLY called for ambiguous or conversational cases.
    # =========================================================================
    

    
    def _is_affirmative(self, text: str) -> bool:
        """Check if user text is an affirmative/yes response."""
        clean = text.strip().lower()
        for word in AFFIRM_WORDS:
            if re.search(rf'\b{word}\b', clean):
                return True
        return False
    
    def _is_negative(self, text: str) -> bool:
        """Check if user text is a negative/no response."""
        clean = text.strip().lower()
        for word in DENY_WORDS:
            if re.search(rf'\b{word}\b', clean):
                return True
        return False
    
    def _is_greeting(self, text: str) -> bool:
        """Check if user text is just a greeting."""
        clean = text.strip().lower().rstrip(".!?,")
        return clean in GREETING_WORDS
        
    def _extract_employment(self, text: str) -> str | None:
        """Extract employment status from text."""
        clean = text.strip().lower()
        if "unemployed" in clean or "not working" in clean:
            return "UNEMPLOYED"
        if "self" in clean and "employed" in clean:
            return "SELF_EMPLOYED"
        if "employed" in clean or "work" in clean or "job" in clean:
            return "EMPLOYED"
        if "retired" in clean or "pension" in clean:
            return "RETIRED"
        return None

    def _extract_bill_handling(self, text: str) -> str | None:
        """Extract who handles bills from text."""
        clean = text.strip().lower()
        if "my husband" in clean or "my wife" in clean or "my spouse" in clean or "someone else" in clean:
            return "NO"
        if "we both" in clean or "we share" in clean or "together" in clean or "shared" in clean or "both of us" in clean:
            return "SHARED"
        # Affirmative is handled after this check in the step node, or we can check me/I do here
        if "me" in clean.split() or "i do" in clean or "mostly me" in clean or "i handle" in clean:
            return "YES"
        return None
        
    def _is_answering_script_question(self, state: DialogueState, step: str) -> bool:
        """Determines if the user is answering the main script question vs an off-script clarification."""
        if len(state["messages"]) < 2:
            return True
        last_ai_msg = state["messages"][-2].content.lower()
        
        keywords = {
            "1": ["debt", "seven thousand", "7000", "7,000", "unsecured", "qualify", "owe", "dollars"],
            "2": ["handling", "bills", "accounts", "take care", "responsible", "managing"],
            "3": ["employed", "retired", "working", "job", "income"],
            "4": ["pay", "month", "monthly", "payment"],
            "5": ["right", "correct", "got all of that", "accurate", "good"]
        }
        
        step_keywords = keywords.get(str(step), [])
        for kw in step_keywords:
            if kw in last_ai_msg:
                return True
        return False
    


    def _extract_number(self, text: str) -> int | None:
        """Extract a dollar amount or number from text. Returns value in dollars. Averages ranges."""
        # STT often translates "four fifty" as "4.50". Removing decimal points makes it "450".
        clean = text.strip().lower().replace(",", "").replace("$", "").replace(".", "")
        
        # Check for negations
        negation_phrases = ["don't have", "do not have", "don't owe", "do not owe", "not even close", "less than", "under"]
        for np in negation_phrases:
            if np in clean:
                return None

        # Check for range: e.g. "300 to 500", "between 30 and 40 thousand"
        m_range = re.search(r'(\d+)\s*(thousand|k|grand)?\s*(?:to|and|-|thru|through)\s*(\d+)\s*(thousand|k|grand)?', clean)
        if m_range:
            val1 = int(m_range.group(1))
            val2 = int(m_range.group(3))
            
            mult1 = 1000 if m_range.group(2) else 1
            mult2 = 1000 if m_range.group(4) else 1
            
            # If they say "10 to 20k", val1 is 10, val2 is 20k. We should make val1 10k.
            if mult2 == 1000 and mult1 == 1:
                mult1 = 1000
                
            # If they say "12 to 13000", val1 is 12, val2 is 13000. We should make val1 12k.
            if mult1 == 1 and mult2 == 1 and val2 >= 1000 and val1 < 100:
                mult1 = 1000
            
            return ((val1 * mult1) + (val2 * mult2)) // 2

        # Match patterns like "20 thousand", "20k", "20,000", "20000"
        m = re.search(r'(\d+)\s*(thousand|k|grand)', clean)
        if m:
            return int(m.group(1)) * 1000
        # Plain number
        m = re.search(r'(\d+)', clean)
        if m:
            val = int(m.group(1))
            # If someone says just "20" or "55" in debt context, assume thousands
            if 0 < val < 100:
                val = val * 1000
            return val
            
        # Fallback to word numbers
        for word, val in WORD_TO_NUM.items():
            if re.search(rf'\b{word}\b', clean):
                return val
                
        return None


    def _get_redirect_question(self, state, current_step: str) -> str:
        if str(current_step).upper() == "5":
            qa = state.get("qualification_answers", {})
            total = qa.get("total_debt", "more than seven thousand")
            payment = qa.get("monthly_payment", "your current")
            job = qa.get("employment_status", "employed")
            return f"Just to make sure I have everything perfectly correct... you have {total} dollars in total debt, you handle the bills, you're currently {job}, and you're paying around {payment} monthly. Did I get all of that right?"
        return REDIRECT_QUESTIONS.get(str(current_step).upper(), "Where were we?")

    async def _dynamic_advance(self, state: DialogueState, prefix_intent: str, next_step: str, context: str = "") -> dict:
        target_question = SCRIPT_TEXTS.get(next_step, "")
        
        if next_step == "5":
            qa = state.get("qualification_answers", {})
            total = qa.get("total_debt", "more than seven thousand")
            payment = qa.get("monthly_payment", "your current")
            job = qa.get("employment_status", "employed")
            target_question = f"Okay, thank you for sharing that with me. Based on what you're telling me, I really think we can help you lower those payments. Just to make sure my notes are perfect before I grab my senior counselor... you've got {total} dollars in debt, you handle the accounts, you're currently {job}, and paying about {payment} a month. Does that all sound correct?"
            return {"messages": [AIMessage(content=target_question)], "script_step": next_step}

        # If it's step 6, we don't need dynamic empathy, we just say the line and transfer
        if next_step == "6":
            return {"messages": [AIMessage(content=target_question)], "script_step": next_step}
            
        # Check for emotional distress indicators from the user
        last_msg = state["messages"][-1].content.lower() if state.get("messages") else ""
        distress_indicators = ["stress", "drown", "struggl", "scared", "worried", "terrif", "depress", "overwhelm", "can't afford", "help me"]
        has_distress = any(w in last_msg for w in distress_indicators)

        # Fast-Path: for standard non-distress responses, advance with 0ms LLM latency
        fast_acknowledgments = {
            "2": ["Makes sense, ", "Perfect, ", "Gotcha, ", "Okay, good to know, ", "Right, "],
            "3": ["Okay, excellent, ", "Got it, that helps, ", "Great, ", "Understood, ", "Awesome, "],
            "4": ["I hear you, ", "Right, that's very common, ", "Okay, got it, ", "Makes sense, "],
        }

        if not has_distress and next_step in fast_acknowledgments:
            import random
            ack = random.choice(fast_acknowledgments[next_step])
            full_response = f"{ack}{target_question}"
            logger.info(f"[FAST-PATH ADVANCE] Step {next_step} generated with 0ms LLM delay: '{ack}'")
            return {"messages": [AIMessage(content=full_response)], "script_step": next_step}
            
        sys_prompt = f"""You are Angela, a warm, empathetic, and naturally human debt relief agent on a real phone call.
Context: {context}

Your ONLY job right now is TWO things in ONE short response:
1. Acknowledge what they just said with a brief, natural reaction (e.g., "{prefix_intent}", "That makes sense...", "Oh, wow, okay..."). If they expressed stress about their debt or payments, show brief empathy (e.g., "I know that can be stressful...").
2. Immediately ask the next question EXACTLY as written: "{target_question}"

CRITICAL RULES:
- Your ENTIRE response must be exactly 1 to 2 sentences ONLY. Never more.
- NEVER make up your own questions or ask for extra details (like how many cards, specific amounts, etc).
- The ONLY question you are allowed to ask is the EXACT target question provided above. Do not add anything else to it.
- Do NOT use unprofessional fillers (um, uh, like).
- Use exactly one ellipsis (...) to create a natural pause between your reaction and the question.
- Do NOT rephrase or add extra conversational filler to the question itself.
- Do NOT repeat the user's answer back verbatim.
- Do NOT use markdown, asterisks, or action tags.
- NEVER start your response with "Got it" or "I understand". Mix up your affirmations!
- Sound like a real, warm, and confident professional on the phone — NOT a scripted robot.
- Write numbers as words (e.g. 'seven thousand dollars').
- ALWAYS use contractions: I'm, you're, we've, don't.
"""
        ai_response = await self._call_llm(sys_prompt, state)
        return {"messages": [AIMessage(content=ai_response)], "script_step": next_step}

    def _handle_advance(self, response: str) -> dict:
        """Parses <<ADVANCE_X>> tags and appends next script text dynamically."""
        match = re.search(r"<<ADVANCE_([A-Z0-9_]+)>>|\[ADVANCE_([A-Z0-9_]+)\]|\bADVANCE_([A-Z0-9_]+)\b", response)
        if match:
            next_step = str(match.group(1) or match.group(2) or match.group(3))
            clean_response = re.sub(r"<<ADVANCE_[A-Z0-9_]+>>|\[ADVANCE_[A-Z0-9_]+\]|\bADVANCE_[A-Z0-9_]+\b", "", response).strip()
            return {"messages": [AIMessage(content=clean_response)], "script_step": next_step}
        return {"messages": [AIMessage(content=response)]}

    # =========================================================================
    # STEP NODES - Each uses Python keywords first, LLM only as fallback
    # =========================================================================

    async def _step_1_node(self, state: DialogueState) -> dict:
        first_name = state.get("lead_first_name")
        greeting_name = first_name if first_name else ""
        last_msg = state["messages"][-1].content if state["messages"] else ""

        if not last_msg:
            greeting = SCRIPT_TEXTS["1"]
            return {"messages": [AIMessage(content=greeting)]}
        
        if self._is_greeting(last_msg):
            name_part = f" {greeting_name}" if greeting_name else ""
            return {"messages": [AIMessage(content=f"Oh, hi{name_part}! I'm Angela from Debt Relief Service, and I'm calling with some potentially really great news for you. It looks like you may qualify for a debt relief program that could significantly reduce what you owe. Do you currently have more than seven thousand dollars in unsecured debt, like credit cards, medical bills, utilities, or personal loans?")]}
        
        num = self._extract_number(last_msg)
        is_script_q = self._is_answering_script_question(state, "1")
        
        if (self._is_affirmative(last_msg) and is_script_q) or (num is not None and num >= 7000):
            qa = state.get("qualification_answers", {})
            qa["total_debt"] = num if num and num >= 7000 else "more than seven thousand"
            state["qualification_answers"] = qa
            return await self._dynamic_advance(state, "Great!", "2", "User confirmed they owe >$7000 in unsecured debt.")
        
        if state.get("asked_under_7k_confirmation"):
            if self._is_affirmative(last_msg):
                qa = state.get("qualification_answers", {})
                qa["total_debt"] = "less than seven thousand"
                return {"messages": [AIMessage(content="I understand. Unfortunately, our program requires a minimum of $7,000 in unsecured debt to qualify, so we won't be able to assist you at this time. Thank you so much for your time, and have a wonderful day. <<END_CALL:NQ>>")], "qualification_answers": qa}
            else:
                return {"messages": [AIMessage(content="Gotcha, I must have misheard you! So roughly how much would you say you owe in total?")], "asked_under_7k_confirmation": False}
                
        if (self._is_negative(last_msg) and is_script_q):
            qa = state.get("qualification_answers", {})
            qa["total_debt"] = "less than seven thousand"
            return {"messages": [AIMessage(content="I understand. Unfortunately, our program requires a minimum of $7,000 in unsecured debt to qualify, so we won't be able to assist you at this time. Thank you so much for your time, and have a wonderful day. <<END_CALL:NQ>>")], "qualification_answers": qa}
            
        if num is not None and num < 7000:
            return {"messages": [AIMessage(content="Okay, just to make sure I heard you right—did you say your total unsecured debt is under seven thousand dollars?")], "asked_under_7k_confirmation": True}
        
        knowledge = await self.rag_service.get_rebuttal(last_msg) if last_msg else ""
        sys_prompt = f"""You are Angela, a warm, confident, and professional debt relief specialist on a phone call.
The customer said something unclear or asked an off-topic question.

STEP 1 - Address their interruption/question:
- If KNOWLEDGE is provided below, use it to answer warmly in 1 sentence.
- If KNOWLEDGE is empty, warmly acknowledge what they said or say you don't have that info handy. Do NOT ignore their interruption!
- NEVER hallucinate or make up facts.

STEP 2 - Redirect warmly back to EXACTLY this question (do not rephrase):
"Just to clarify, do you currently have more than seven thousand dollars in unsecured debt, like credit cards, medical bills, utilities, or personal loans?"

RULES: Max 2 sentences total. Use contractions. Sound warm and human. No markdown.

KNOWLEDGE: "{knowledge}"
"""
        ai_response = await self._call_llm(sys_prompt, state)
        return {"messages": [AIMessage(content=ai_response)]}

    async def _step_2_node(self, state: DialogueState) -> dict:
        last_msg = state["messages"][-1].content if state["messages"] else ""
        lower_msg = last_msg.lower()
        is_script_q = self._is_answering_script_question(state, "2")
        
        # 1. Fast-path Intent Classification via Python Keyword Extraction
        intent = self._extract_bill_handling(last_msg)
        
        # 2. Fallback to LLM if Python extraction fails
        if not intent:
            prompt = "Did the user say they handle the bills (YES), that they share responsibility for the bills with someone else like a spouse (SHARED), or that they do not handle the bills (NO)? If they asked a question or their answer is unclear, output UNKNOWN."
            intent = await self._classify_enum(state, prompt, ["YES", "NO", "SHARED", "UNKNOWN"])
        
        if intent in ["YES", "SHARED"] or (self._is_affirmative(last_msg) and is_script_q):
            qa = state.get("qualification_answers", {})
            qa["handles_bills"] = "yes (shared)" if intent == "SHARED" else "yes"
            state["qualification_answers"] = qa
            return await self._dynamic_advance(state, "Perfect.", "3", "User confirmed they handle or share responsibility for the bills.")
        
        if intent == "NO" or (self._is_negative(last_msg) and is_script_q):
            # If they say they don't handle it, we politely close without a confusing question.
            return {"messages": [AIMessage(content="I understand. Since we require the primary account manager to proceed, we won't be able to move forward right now. Thank you for your time and have a wonderful day. <<END_CALL:NQ>>")]}
        
        knowledge = await self.rag_service.get_rebuttal(last_msg) if last_msg else ""
        sys_prompt = f"""You are Angela, a warm, confident, and professional debt relief specialist on a phone call.
The customer didn't give a clear answer about who manages their accounts.

STEP 1 - Address their interruption/question:
- If KNOWLEDGE is provided below, use it to answer warmly in 1 sentence.
- If KNOWLEDGE is empty, warmly acknowledge what they said or say you don't have that info handy. Do NOT ignore their interruption!
- NEVER hallucinate or make up facts.

STEP 2 - Redirect warmly back to EXACTLY this question (do not rephrase):
"I just want to confirm real quick - are you the one handling the bills and taking care of these accounts?"

RULES: Max 2 sentences total. Use contractions. Sound warm and human. No markdown.

KNOWLEDGE: "{knowledge}"
"""
        ai_response = await self._call_llm(sys_prompt, state)
        return {"messages": [AIMessage(content=ai_response)]}

    async def _step_3_node(self, state: DialogueState) -> dict:
        last_msg = state["messages"][-1].content if state["messages"] else ""
        lower_msg = last_msg.lower()
        is_script_q = self._is_answering_script_question(state, "3")
        
        # 1. Fast-path Intent Classification via Python Keyword Extraction
        intent = self._extract_employment(last_msg)
        
        # 2. Fallback to LLM if Python extraction fails
        if not intent:
            prompt = "Did the user say they are employed (EMPLOYED), self-employed (SELF_EMPLOYED), retired (RETIRED), or unemployed/not working (UNEMPLOYED)? If they asked a question or their answer is unclear, output UNKNOWN."
            intent = await self._classify_enum(state, prompt, ["EMPLOYED", "SELF_EMPLOYED", "RETIRED", "UNEMPLOYED", "UNKNOWN"])
        
        if intent in ["EMPLOYED", "SELF_EMPLOYED", "RETIRED"] or (self._is_affirmative(last_msg) and is_script_q):
            qa = state.get("qualification_answers", {})
            qa["employment_status"] = intent.lower()
            state["qualification_answers"] = qa
            return await self._dynamic_advance(state, "Excellent.", "4", "User confirmed they are employed or retired.")
            
        if intent == "UNEMPLOYED" or (self._is_negative(last_msg) and is_script_q):
            return {"messages": [AIMessage(content="I understand. Unfortunately, our program requires a source of income, so we won't be able to assist you at this time. Have a wonderful day. <<END_CALL:NQ>>")]}
            
        knowledge = await self.rag_service.get_rebuttal(last_msg) if last_msg else ""
        sys_prompt = f"""You are Angela, a warm, confident, and professional debt relief specialist on a phone call.
The customer didn't give a clear answer about their employment status.

STEP 1 - Address their interruption/question:
- If KNOWLEDGE is provided below, use it to answer warmly in 1 sentence.
- If KNOWLEDGE is empty, warmly acknowledge what they said or say you don't have that info handy. Do NOT ignore their interruption!
- NEVER hallucinate or make up facts.

STEP 2 - Redirect warmly back to EXACTLY this question (do not rephrase):
"Just so I have everything I need - are you currently employed, self-employed, or retired?"

RULES: Max 2 sentences total. Use contractions. Sound warm and human. No markdown.

KNOWLEDGE: "{knowledge}"
"""
        ai_response = await self._call_llm(sys_prompt, state)
        return {"messages": [AIMessage(content=ai_response)]}

    async def _step_4_node(self, state: DialogueState) -> dict:
        last_msg = state["messages"][-1].content if state["messages"] else ""
        qa = state.get("qualification_answers", {})
        
        # --- Handle confirmation of under-$250 disqualification ---
        if state.get("asked_under_250_confirmation"):
            if self._is_affirmative(last_msg):
                return {
                    "messages": [AIMessage(content="I understand, and I appreciate you sharing that with me. Unfortunately, our program requires a minimum monthly payment of two hundred and fifty dollars to qualify, so we won't be able to assist you at this time. Thank you so much for your time and I hope things get easier for you. Have a wonderful day. <<END_CALL:NQ>>")],
                    "qualification_answers": qa,
                    "asked_under_250_confirmation": False
                }
            else:
                return {
                    "messages": [AIMessage(content="Gotcha, I may have misheard you! So roughly how much would you say you pay each month toward your debt?")],
                    "asked_under_250_confirmation": False
                }

        num = self._extract_number(last_msg)
        if num is not None:
            qa["monthly_payment"] = num
            state["qualification_answers"] = qa
            
            # Disqualification: monthly payment under $250
            if num < 250:
                return {
                    "messages": [AIMessage(content=f"Okay, just to make sure I heard you right, did you say you're paying around {num} dollars a month toward your debt?")],
                    "qualification_answers": qa,
                    "asked_under_250_confirmation": True
                }
            
            return await self._dynamic_advance(state, "Got it.", "5", "User provided their monthly payment.")
            
        knowledge = await self.rag_service.get_rebuttal(last_msg) if last_msg else ""
        sys_prompt = f"""You are Angela, a warm, confident, and professional debt relief specialist on a phone call.
The customer didn't give a clear monthly payment amount.

STEP 1 - Address their interruption/question:
- If KNOWLEDGE is provided below, use it to answer warmly in 1 sentence.
- If KNOWLEDGE is empty, warmly acknowledge what they said or say you don't have that info handy. Do NOT ignore their interruption!
- NEVER hallucinate or make up facts.

STEP 2 - Redirect warmly back to EXACTLY this question (do not rephrase):
"I really want to help you figure this out - roughly how much do you pay per month on your debt right now?"

RULES: Max 2 sentences total. Use contractions. Sound warm and human. No markdown.

KNOWLEDGE: "{knowledge}"
"""
        ai_response = await self._call_llm(sys_prompt, state)
        return {"messages": [AIMessage(content=ai_response)]}

    async def _step_5_node(self, state: DialogueState) -> dict:
        last_msg = state["messages"][-1].content if state["messages"] else ""
        is_script_q = self._is_answering_script_question(state, "5")
        
        # Fast-path Intent Classification via LLM
        prompt = "Did the user confirm that their details are correct (CONFIRMED), or did they say something was wrong/incorrect (DENIED)? If they asked a question or their answer is unclear, output UNKNOWN."
        intent = await self._classify_enum(state, prompt, ["CONFIRMED", "DENIED", "UNKNOWN"])
        
        if intent == "CONFIRMED" or (self._is_affirmative(last_msg) and is_script_q and intent != "DENIED"):
            return await self._dynamic_advance(state, "Perfect.", "6", "User confirmed all their details are correct.")
        
        sys_prompt = f"""You are Angela, a warm, empathetic, and professional debt relief specialist. You just read back the customer's details and they said something was wrong.
Your job: Apologize with genuine warmth (e.g. 'I'm so sorry about that!'), then in the same breath ask what needs to be corrected (e.g. 'What should I update for you?').
RULES: Max 2 sentences. Sound genuinely caring and human. No markdown.
"""
        ai_response = await self._call_llm(sys_prompt, state)
        return {"messages": [AIMessage(content=ai_response)]}

    async def _step_6_node(self, state: DialogueState) -> dict:
        return {"messages": [AIMessage(content="Please hold the line for a moment, let me get my senior counselor on the line. <<TRANSFER:XFER>>", additional_kwargs={"use_tts_cache": True})], "fsm_state": "CLOSED_SALE"}

    async def _objection_node(self, state: DialogueState) -> dict:
        count = state.get("objection_count", 0) + 1
        
        if count >= 3:
            tag = "NIBP" if int(state.get("script_step", 1)) <= 2 else "NIAP"
            return {
                "messages": [AIMessage(content=f"I understand. Since you are not interested, I will go ahead and remove you from our list. Have a great day. <<END_CALL:{tag}>>")],
                "objection_count": count
            }
        
        last_msg = state["messages"][-1].content if state["messages"] else ""
        knowledge = await self.rag_service.get_rebuttal(last_msg)
        
        current_step = str(state.get("script_step", 1)).upper()
        redirect = self._get_redirect_question(state, current_step)
        
        # Fast-path for verified knowledge rebuttals: zero LLM delay!
        if knowledge and "I understand you might have concerns, but my main objective" not in knowledge:
            full_response = f"{knowledge} {redirect}"
            logger.info(f"[FAST-PATH REBUTTAL] Returning verified rebuttal with 0ms LLM delay.")
            return {"messages": [AIMessage(content=full_response)], "objection_count": count}
        
        sys_prompt = f"""You are Angela, a warm, empathetic, and professional debt relief specialist. The customer raised an objection or concern.
Respond like a caring human who genuinely wants to help.

STEP 1 - Validate with deep empathy:
Use warm, natural transitions: 'I completely understand...', 'I hear you...', 'That makes total sense...'

STEP 2 - Address their concern or interruption:
- If KNOWLEDGE is provided below, use it to answer warmly in 1 sentence.
- If KNOWLEDGE is empty, warmly acknowledge what they said. Do NOT ignore their interruption!
- NEVER hallucinate or make up facts.

STEP 3 - Redirect warmly back:
End by warmly asking: "{redirect}"

RULES: Max 2-3 sentences total. Use contractions. Sound like a real caring person on the phone. No markdown.

KNOWLEDGE: "{knowledge}"
"""
        ai_response = await self._call_llm(sys_prompt, state)
        return {"messages": [AIMessage(content=ai_response)], "objection_count": count}
        
    async def _knowledge_node(self, state: DialogueState) -> dict:
        last_msg = state["messages"][-1].content if state["messages"] else ""
        knowledge = await self.rag_service.get_rebuttal(last_msg)
        
        current_step = str(state.get("script_step", 1)).upper()
        redirect = self._get_redirect_question(state, current_step)
        
        # Fast-path for verified knowledge answers: zero LLM delay!
        if knowledge and "I understand you might have concerns, but my main objective" not in knowledge:
            full_response = f"{knowledge} {redirect}"
            logger.info(f"[FAST-PATH KNOWLEDGE] Returning verified answer with 0ms LLM delay.")
            return {"messages": [AIMessage(content=full_response)]}
        
        sys_prompt = f"""You are Angela, a warm, confident, and professional debt relief specialist. The customer asked a question.
Respond like a real, helpful human who genuinely cares about answering properly.

STEP 1 - Answer their question or acknowledge the interruption:
- If KNOWLEDGE is provided below, use it to answer warmly in 1 sentence.
- If KNOWLEDGE is empty, warmly acknowledge what they said (e.g., "I understand", "That makes sense") or say you don't have that info handy. Do NOT ignore their interruption!
- NEVER hallucinate or make up facts.

STEP 2 - Redirect warmly back to EXACTLY this question (do not rephrase):
"{redirect}"

RULES: Max 2 sentences total. Use contractions. Sound like a real caring person on the phone. No markdown.

KNOWLEDGE: "{knowledge}"
"""
        ai_response = await self._call_llm(sys_prompt, state)
        return {"messages": [AIMessage(content=ai_response)]}
        
    async def _fast_nlu_node(self, state: DialogueState) -> dict:
        """Bypasses the LLM entirely and uses the hardcoded RAG response."""
        nlu_text = state.get("nlu_response", "")
        return self._handle_advance(nlu_text)
        

    async def _voicemail_node(self, state: DialogueState) -> dict:
        return {"messages": [AIMessage(content="<<END_CALL:A>>")], "fsm_state": "VOICEMAIL"}
        
    async def _dnc_node(self, state: DialogueState) -> dict:
        count = state.get("dnc_count", 0) + 1
        
        if count >= 2:
            return {
                "messages": [AIMessage(content="I completely understand. I'll go ahead and remove you from our list right away. Have a great day. <<END_CALL:DNC>>")],
                "fsm_state": "DNC",
                "dnc_count": count
            }
            
        last_msg = state["messages"][-1].content if state["messages"] else ""
        knowledge = await self.rag_service.get_rebuttal(last_msg)
        current_step = str(state.get("script_step", 1)).upper()
        redirect = self._get_redirect_question(state, current_step)
        
        sys_prompt = f"""You are Angela, a warm, empathetic debt relief specialist. The customer said they are not interested or asked to be removed.
Respond like a caring human.

STEP 1 - Validate with deep empathy:
"I completely understand where you're coming from..."

STEP 2 - Address their concern:
- If KNOWLEDGE is provided below, use it to answer warmly in 1 sentence.
- If KNOWLEDGE is empty, warmly acknowledge their hesitation.

STEP 3 - Redirect warmly back:
End by warmly asking: "{redirect}"

RULES: Max 2-3 sentences. Sound caring. No markdown.

KNOWLEDGE: "{knowledge}"
"""
        ai_response = await self._call_llm(sys_prompt, state)
        return {"messages": [AIMessage(content=ai_response)], "dnc_count": count}

    async def _busy_node(self, state: DialogueState) -> dict:
        return {"messages": [AIMessage(content="I completely understand! I'll let you go for now and we can try back another time. Have a great rest of your day! <<END_CALL:CB>>")], "fsm_state": "BUSY"}

    async def _hostile_node(self, state: DialogueState) -> dict:
        # Deterministic - no LLM needed. Just apologize and end call.
        return {
            "messages": [AIMessage(content="I'm really sorry about that, I didn't mean to bother you. I'll go ahead and remove you from our list right away. Have a great day. <<END_CALL:DNC>>")]
        }
        
    async def _clarify_node(self, state: DialogueState) -> dict:
        """Handles garbled/misheard speech by asking the user to clarify based on context."""
        last_msg = state["messages"][-1].content if state["messages"] else ""
        current_step = str(state.get("script_step", 1)).upper()
        redirect = self._get_redirect_question(state, current_step)
        
        sys_prompt = f"""You are Angela, a warm, confident debt relief specialist. 
The speech recognition misheard the user, or they mumbled something confusing (they said: '{last_msg}').

STEP 1: Acknowledge that you didn't quite catch that, or that the connection broke up for a second.
STEP 2: Based on the conversation context, guess what they were trying to say and ask them to confirm, or just warmly repeat your question.
For example, if you asked if they are employed/retired, and they said 'retred', you should ask: "Sorry, did you mean you're retired?"

If you cannot guess, just warmly repeat the question: "{redirect}"

RULES: Max 2 sentences. Be very human and apologetic about missing it. No markdown."""
        
        ai_response = await self._call_llm(sys_prompt, state)
        return {"messages": [AIMessage(content=ai_response)]}
        
    async def _continuity_node(self, state: DialogueState) -> dict:
        """Handles mid-conversation continuity checks like 'hello?', 'are you there?'"""
        import random
        
        current_step = str(state.get("script_step", 1)).upper()
        redirect = self._get_redirect_question(state, current_step)
        
        # Randomized warm continuity responses so it doesn't sound scripted
        continuity_openers = [
            f"I'm still here, sorry about that! So I was just asking, {redirect.lower()}",
            f"Yes, I'm still here! Sorry, so like I was saying, {redirect.lower()}",
            f"I'm right here! So... {redirect.lower()}",
            f"I'm here, sorry! So... {redirect.lower()}",
            f"I'm still here, don't worry! So... {redirect.lower()}",
        ]
        
        response = random.choice(continuity_openers)
        logger.info(f"[CONTINUITY] Responding to check-in at step {current_step}")
        return {"messages": [AIMessage(content=response)]}

    async def _language_barrier_node(self, state: DialogueState) -> dict:
        """Handles non-English speakers by ending the call."""
        return {
            "messages": [AIMessage(content="I apologize, but we only have English-speaking representatives available at this time. Thank you and have a great day. <<END_CALL:LB>>")],
            "fsm_state": "LANGUAGE_BARRIER"
        }

    async def generate_reply(self, state: DialogueState, session_id: str = "default_session", stream_callback=None) -> dict:
        if "script_step" not in state:
            state["script_step"] = 1
        self._current_stream_callback = stream_callback
        try:
            config = {"configurable": {"thread_id": session_id}}
            return await self.graph.ainvoke(state, config=config)
        finally:
            self._current_stream_callback = None
