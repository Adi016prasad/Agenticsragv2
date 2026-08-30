import os
import sys

# Add parent directory (querying/) to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from crewai_agents.config import build_llm

# Note: Add "openai/" prefix so LiteLLM routes it through your OpenAI-compatible Bedrock Mantle
model_name = "openai/google.gemma-3-4b-it"
llm = build_llm(model_name)

print("\n🤖 Calling Bedrock Mantle with model:", model_name)
response = llm.call([{"role": "user", "content": "who are you ?"}])
print("\n📊 Response:\n", response)