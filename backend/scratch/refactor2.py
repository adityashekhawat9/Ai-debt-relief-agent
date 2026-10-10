import re

file_path = "C:/Users/RG0626/Desktop/Debt-relief-ai/ai-voice-platform/backend/conversation_engine/langgraph_dialogue.py"
with open(file_path, "r") as f:
    content = f.read()

# Replace all [ADVANCE_X] with <<ADVANCE_X>>
content = re.sub(r"\[ADVANCE_([A-Z0-9_]+)\]", r"<<ADVANCE_\1>>", content)
# Replace [END_CALL] with <<END_CALL>>
content = content.replace("[END_CALL]", "<<END_CALL>>")

# Update the regex in _handle_advance to look for <<ADVANCE_X>>
content = content.replace(
    r'match = re.search(r"\[ADVANCE_([A-Z0-9_]+)\]|\bADVANCE_([A-Z0-9_]+)\b", response)',
    r'match = re.search(r"<<ADVANCE_([A-Z0-9_]+)>>|\[ADVANCE_([A-Z0-9_]+)\]|\bADVANCE_([A-Z0-9_]+)\b", response)'
)
content = content.replace(
    r'clean_response = re.sub(r"\[ADVANCE_[A-Z0-9_]+\]|\bADVANCE_[A-Z0-9_]+\b", "", response).strip()',
    r'clean_response = re.sub(r"<<ADVANCE_[A-Z0-9_]+>>|\[ADVANCE_[A-Z0-9_]+\]|\bADVANCE_[A-Z0-9_]+\b", "", response).strip()'
)

with open(file_path, "w") as f:
    f.write(content)
print("Updated tags to use << >>")
