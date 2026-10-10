import re

def handle_ssml(text: str):
    text = re.sub(r',(?=\s|$)\s*', ' <break time="500ms"/> ', text)
    text = re.sub(r'\.{2,}\s*', ' <break time="800ms"/> ', text)
    break_pattern = re.compile(r'(<break\s+time=["\']?\d+(?:\.\d+)?(?:s|ms)["\']?\s*/?>)')
    parts = break_pattern.split(text)
    
    for i, part in enumerate(parts):
        print(f"Part {i}: {repr(part)}")
        if part.strip().startswith('<break'):
            time_match = re.search(r'time=["\']?(\d+(?:\.\d+)?)(s|ms)["\']?', part)
            if time_match:
                print(f"  -> BREAK MATCH: {time_match.group(1)} {time_match.group(2)}")
            else:
                print(f"  -> BREAK FAILED TO PARSE TIME")
        else:
            clean_text = re.sub(r'<[^>]+>', '', part).strip()
            print(f"  -> TEXT MATCH: {repr(clean_text)}")

text = "That's great to hear, umm <break time=\"500ms\"/> you're doing a fantastic job"
handle_ssml(text)
