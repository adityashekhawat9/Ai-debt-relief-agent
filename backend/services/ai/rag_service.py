import os
import httpx
import re
from core.logging import get_logger

logger = get_logger(__name__)

REBUTTALS = {
    "1": "It's called the Debt Relief Program \u2014 also referred to as Debt Reduction or Debt Mitigation Program, designed to help you pay off your debts for less.",
    "2": "I'm calling to provide you with free information and guidance on how you can reduce your debt and pay it off in just 12-36 months \u2014 without any interest and without needing a loan.",
    "3": "We are Consumer Services, working in partnership with top-rated debt management companies. Our goal is to help individuals like you become debt-free in a short time \u2014 at no cost and with no obligation.",
    "4": "This is a no-cost, no-obligation call to provide free advice on how you can settle your debts for less and avoid years of interest payments. If you're not interested, I fully respect that.",
    "5": "Your information was provided through an opt-in consumer financial request. We're just reaching out because you may qualify to have your current credit card payments significantly reduced.",
    "6": "Understood. This was just a free informational call, and I wasn't asking you to make any decisions. I'll respect your request and remove your number from our list.",
    "7": "I sincerely apologize for the inconvenience. I will make sure you're not contacted again.",
    "8": "I'm calling locally, and our head office is based in Irvine, California.",
    "9": "I completely understand \u2014 this will only take a couple of minutes. I'll quickly explain how you could reduce your debt and interest to zero.",
    "10": "You may be receiving multiple calls because you're prequalified for a program that can significantly reduce your debt and interest. That's why you're a top priority.",
    "11": "We work with companies that have pre-negotiated agreements with most major creditors. Using proven debt negotiation strategies, we reduce your balances and interest down to zero.",
    "12": "There are no upfront fees and no enrollment charges. You pay nothing out-of-pocket to get started.",
    "13": "Our compensation comes from a portion of the savings we help you achieve \u2014 not from you directly.",
    "14": "Typically, around one-third of the savings we secure for you.",
    "15": "Absolutely \u2014 your privacy is respected. I'm simply here to offer free advice and guidance on how to cut your debt and interest rates.",
    "16": "I understand how it may sound that way, but I'm not selling anything. This is purely informational and meant to help you explore your options \u2014 at no cost or commitment.",
    "17": "That's a valid concern. That's why I'm not asking for personal details, money, or a commitment. This is simply a free consultation to explore a legitimate path to becoming debt-free.",
    "18": "That's great to hear. Still, it's often helpful to compare multiple programs. Ours is known for being among the most aggressive and effective in reducing total debt.",
    "19": "Some cards offer temporary promotional rates, but our program offers a guaranteed 0% interest while also reducing the principal you owe.",
    "20": "There may be a temporary and minimal impact early on, but once the program is completed, your credit score will recover and likely improve as your debts will be paid off. It varies for each individual, but most clients see steady improvement once they complete the program.",
    "21": "I'd be happy to \u2014 however, because this is a personalized solution, a quick conversation ensures we offer the right plan tailored to you. I'm also here to answer your questions live.",
    "22": "That's completely understandable. Many of our clients say the same at first, that's why we offer a free consultation with no pressure to enroll.",
    "23": "I may have outdated info, but I can still share helpful guidance with anyone interested in reducing their debt. It's a no-cost, no-obligation call.",
    "24": "Unfortunately, we can't help with accounts that are already in judgment. However, we can still assist you with any accounts that haven't reached that stage.",
    "25": "I'm referring to all of your credit cards \u2014 the total combined debt you're currently carrying."
}

# Questions mapping to the rebuttals so the vector space represents user queries
OBJECTION_QUERIES = {
    "1": "What is the name of the program? / What is the process called?",
    "2": "Why did you call me?",
    "3": "Who are you? / What is Consumer Services? / What company is this?",
    "4": "What do you guys do? / Not interested / Don't call me / Stop calling me.",
    "5": "How did you get my information? / I didn't fill out any survey.",
    "6": "Do not call me / Put me on the DNC list / Take me off your list.",
    "7": "I'm already on the Do Not Call list.",
    "8": "What's your address? / Are you calling from India / foreign country? / Where is your office?",
    "9": "I don't have time / I'm busy / Hurry up.",
    "10": "I've already been called / Why do you keep calling me?",
    "11": "How does this program work? / How do you reduce 40%? / How do you get 0% interest?",
    "12": "What is the cost of the program? / Do you charge fees? / How much does it cost?",
    "13": "How do you get paid then? / What's in it for you?",
    "14": "How much do you get paid from my savings? / What is your percentage?",
    "15": "None of your business / I won't tell you.",
    "16": "Sounds like a sales call / Are you trying to sell me something?",
    "17": "How do I know this isn't a scam? / Is this a scam?",
    "18": "I'm already enrolled in another program / It's being handled.",
    "19": "I'm already at 0% interest / My finances are in good shape.",
    "20": "Will this hurt my credit score? / How will this affect my score? / How many points will my score drop?",
    "21": "Can you send me this in writing? / Can you email me? / Mail it to me.",
    "22": "I've never heard of this before.",
    "23": "Wrong person / Not the right party / Wrong number.",
    "24": "Some of my accounts are in judgment / I've been sued / Legal action.",
    "25": "Which credit card are you referring to? / What account?"
}

class RAGService:
    def __init__(self):
        logger.info("Initializing LLM-based RAG Intent Classifier with Anthropic...")
        from core.config import get_settings
        settings = get_settings()
        self.api_key = settings.ANTHROPIC_API_KEY or ""
        self.categories_text = "\n".join([f"{k}. {v}" for k, v in OBJECTION_QUERIES.items()])
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=self.api_key)

    async def get_rebuttal(self, user_message: str) -> str:
        """Uses pattern matching + LLM to accurately extract intent from the user message, with 0ms fast-paths."""
        if not user_message or not user_message.strip():
            return ""

        msg_lower = user_message.lower().strip()
        
        # 0ms Pattern Fast-Path for high-frequency objections & questions
        if any(w in msg_lower for w in ["who are you", "who is this", "what company", "who're you", "what's your company"]):
            logger.info(f"[RAG Fast-Path] '{user_message}' -> Matched Category 3 (Who are you)")
            return REBUTTALS["3"]
        if any(w in msg_lower for w in ["how did you get my", "where did you get my", "how you get my", "got my information"]):
            logger.info(f"[RAG Fast-Path] '{user_message}' -> Matched Category 5 (How did you get my info)")
            return REBUTTALS["5"]
        if any(w in msg_lower for w in ["why are you calling", "why did you call"]):
            logger.info(f"[RAG Fast-Path] '{user_message}' -> Matched Category 2 (Why did you call)")
            return REBUTTALS["2"]
        if any(w in msg_lower for w in ["what do you do", "what is this program", "name of the program"]):
            logger.info(f"[RAG Fast-Path] '{user_message}' -> Matched Category 1 (Name of program)")
            return REBUTTALS["1"]
        if any(w in msg_lower for w in ["scam", "fraud", "legitimate", "is this real"]):
            logger.info(f"[RAG Fast-Path] '{user_message}' -> Matched Category 17 (Scam doubt)")
            return REBUTTALS["17"]
        if any(w in msg_lower for w in ["how much does it cost", "what is the cost", "what do you charge", "upfront fee"]):
            logger.info(f"[RAG Fast-Path] '{user_message}' -> Matched Category 12 (Cost/Fees)")
            return REBUTTALS["12"]
        if any(w in msg_lower for w in ["credit score", "hurt my score", "affect my credit"]):
            logger.info(f"[RAG Fast-Path] '{user_message}' -> Matched Category 20 (Credit score impact)")
            return REBUTTALS["20"]
        if any(w in msg_lower for w in ["send me an email", "in writing", "mail it"]):
            logger.info(f"[RAG Fast-Path] '{user_message}' -> Matched Category 21 (In writing/Email)")
            return REBUTTALS["21"]
        if any(w in msg_lower for w in ["don't have time", "i'm busy", "hurry up"]):
            logger.info(f"[RAG Fast-Path] '{user_message}' -> Matched Category 9 (Busy)")
            return REBUTTALS["9"]
            
        sys_prompt = f"""You are an expert intent classifier for a debt relief call center. 
Your job is to match the user's message to the most relevant category from the list below.

CATEGORIES:
{self.categories_text}

INSTRUCTIONS:
1. Find the category that best matches the user's intent. For example, "where are you located" maps to the category about addresses. "Not interested" maps to the don't call me category.
2. Output ONLY the number of the matching category (e.g., "4" or "8"). Do not output any other words, punctuation, or explanation.
3. If the user's message is completely unrelated to ANY category, output "0".
"""
        
        try:
            resp = await self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                system=sys_prompt,
                messages=[{"role": "user", "content": user_message}],
                max_tokens=10
            )
            result = resp.content[0].text.strip()
            m = re.search(r'\d+', result)
            if m:
                matched_id = m.group(0)
                if matched_id in REBUTTALS:
                    logger.info(f"[RAG Intent Classifier] '{user_message}' -> Matched Intent {matched_id}")
                    return REBUTTALS[matched_id]
        except Exception as e:
            logger.error(f"[RAG Intent Classifier] API Error: {e}")
            
        logger.info(f"[RAG Intent Classifier] '{user_message}' -> No match (0). Returning fallback.")
        return "I understand you might have concerns, but my main objective is to see if we can get your debts reduced."
