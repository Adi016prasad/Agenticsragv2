from crewai_agents.config import build_llm
llm = build_llm("openai/openai.gpt-oss-safeguard-120b")
print(llm.call("who are you ?"))