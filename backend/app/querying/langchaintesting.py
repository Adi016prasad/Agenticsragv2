from langchain.agents import create_agent
from langchain.tools import tool
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel
from langchain.tools import tool
from langchain.chat_models import init_chat_model
from langchain_anthropic import ChatAnthropic

@tool
def createUser(user : str) -> str :
    """
    Create a new user in the system.
    """
    # Here you would implement the logic to create a user in your system.
    # For demonstration purposes, we'll just return a success message.
    return f"User '{user}' has been successfully created"

toolsrequired = [createUser]

class Answer(BaseModel) :
    llm_responseLanggraph : str

class structuredoutput(BaseModel) :
    llm_responseLanggraph : str
    action : str
    user : str

agent = create_agent(
    model = "google_genai:gemini-3.6-flash",
    tools = toolsrequired,
    system_prompt = "You are a helpful assistant that can create users in the system. Use the provided tools to perform actions",
    response_format = Answer
)

stream = agent.stream_events(
    {"messages": [{"role": "user", "content": "Search for AI news and summarize the findings"}]},
    version="v3",
)

for chunk in stream.values :
    print(chunk.content, end = "", flush = True)

model = init_chat_model(
    "google_genai:gemini-3.6-flash",
    max_retries=10,
    timeout=120
)

modelwithtools = model.bind_tools(toolsrequired)

nonstreamresponse = model.invoke(
    {"messages": [{"role": "user", "content": "Create a new user named 'John Doe'"}]})

response = modelwithtools.stream_events(
    {"messages": [{"role": "user", "content": "Create a new user named 'John Doe'"}]},
    version="v3"
)

for chunk in response.values :
    print(chunk.content, end = "", flush = True)

structuredllm = model.with_structured_output(structuredoutput)

structuredresponse = structuredllm.invoke(
    {"messages": [{"role": "user", "content": "Create a new user named 'John Doe'"}]})

model = ChatAnthropic(model="claude-sonnet-4-6")
response = model.invoke(
    "Why do parrots have colorful feathers?",
    reasoning_effort="high"
)