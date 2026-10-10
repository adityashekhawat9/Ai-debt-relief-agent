import re

class OptOutDetector:
    """
    Fast regex-based opt-out detection to run on STT transcripts before LLM processing.
    """
    OPT_OUT_PATTERNS = [
        r"\b(do not call)\b",
        r"\b(take me off your list)\b",
        r"\b(stop calling)\b",
        r"\b(not interested)\b",
        r"\b(wrong number)\b",
        r"\b(fuck off)\b",
        r"\b(lose my number)\b",
    ]
    
    def __init__(self):
        self.compiled = [re.compile(p, re.IGNORECASE) for p in self.OPT_OUT_PATTERNS]
        
    def is_opt_out(self, text: str) -> bool:
        """Returns True if text matches any opt-out pattern."""
        for pattern in self.compiled:
            if pattern.search(text):
                return True
        return False
