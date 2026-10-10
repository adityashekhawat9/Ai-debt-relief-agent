import re
import unittest

class SentenceChunker:
    def __init__(self):
        self.buffer = ""
        self.delimiter_regex = re.compile(r'([.!?,:;—]\s+)')

    def add_token(self, token: str) -> list[str]:
        self.buffer += token
        chunks = []
        while True:
            # First strip any complete tags so delimiters inside them (e.g. colon in [DISPOSITION: ...]) are never split
            self.buffer = re.sub(r'<<[^>]*>>|\[[^\]]*\]|<[^>]+>', '', self.buffer)

            # Avoid splitting if buffer currently ends in an unclosed tag like <<... or [...
            open_double = self.buffer.find("<<")
            if open_double != -1 and self.buffer.find(">>") == -1:
                break
                
            open_bracket = self.buffer.find("[")
            if open_bracket != -1 and self.buffer.find("]") == -1:
                break

            match = self.delimiter_regex.search(self.buffer)
            if not match:
                break
            end_pos = match.end()
            clause = self.buffer[:end_pos]
            self.buffer = self.buffer[end_pos:]
            cleaned = self.clean_text(clause)
            if cleaned:
                chunks.append(cleaned)
        return chunks

    def flush(self) -> list[str]:
        cleaned = self.clean_text(self.buffer)
        self.buffer = ""
        return [cleaned] if cleaned else []

    @staticmethod
    def clean_text(text: str) -> str:
        text = re.sub(r'<<[^>]*>>', '', text)
        text = re.sub(r'\[[^\]]*\]', '', text)
        text = re.sub(r'<[^>]*>', '', text)
        text = re.sub(r'[<>]', '', text)
        return re.sub(r'\s+', ' ', text).strip()


class TestSentenceChunker(unittest.TestCase):
    def test_clause_splitting(self):
        chunker = SentenceChunker()
        tokens = ["Right, ", "that ", "makes ", "sense. ", "How ", "much ", "do ", "you ", "owe?"]
        received = []
        for t in tokens:
            received.extend(chunker.add_token(t))
        received.extend(chunker.flush())
        
        self.assertEqual(received, ["Right,", "that makes sense.", "How much do you owe?"])

    def test_tag_stripping(self):
        chunker = SentenceChunker()
        text = "Hold on a moment. <<TRANSFER>> [DISPOSITION: QUALIFIED]"
        chunks = chunker.add_token(text)
        chunks.extend(chunker.flush())
        self.assertEqual(chunks, ["Hold on a moment."])

    def test_unclosed_tag_buffering(self):
        chunker = SentenceChunker()
        self.assertEqual(chunker.add_token("Perfect. "), ["Perfect."])
        self.assertEqual(chunker.add_token("Let me get someone, "), ["Let me get someone,"])
        self.assertEqual(chunker.add_token("<<TRANS"), [])
        self.assertEqual(chunker.add_token("FER>>"), [])
        self.assertEqual(chunker.flush(), [])


if __name__ == "__main__":
    unittest.main()
