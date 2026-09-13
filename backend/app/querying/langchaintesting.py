from fastapi import middleware
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

from langchain.agents.middleware import PIIMiddleware, ToolCallLimitMiddleware, ContentFilterMiddleware

agent1 = create_agent(
    model = "openai:gpt-4o-mini",
    system_prompt = "You are a helpful assistant that can create users in the system. Use the provided tools to perform actions",
    tools = toolsrequired,
    middleware = [PIIMiddleware("email", strategy = "mask", apply_to_input = True, apply_to_output = True),
                  ToolCallLimitMiddleware(
                      run_limit = 3,
                      thread_limit = 3,
                      tool_name = "createUser"
                  ),
                ContentFilterMiddleware(banned_keywords=["hack", "exploit"])]   
)

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

docs = [
    "Artificial intelligence (AI) is a branch of computer science that aims to create machines that",
    "Helpful in performing tasks that typically require human intelligence. AI can be categorized into narrow AI, which is designed for specific tasks, and general AI, which has the potential to perform any intellectual task that a human can do.",
    "Machine learning (ML) is a subset of AI that focuses on the development of algorithms that allow computers to learn from and make predictions or decisions based on data. ML algorithms can be classified"]

embedding = OpenAIEmbeddings(
    model = "text-embedding-3-large",
    max_retries = 10,
    timeout = 120,
    api_key = "",
    base_url = "https://api.openai.com/v1",
    headers = {"Custom-Header": "Value"},
    chunk_size = 3000
)

vectors = embedding.embed_documents(docs)


from langchain_core.runnables import RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
class retrievingthedocuments :
    def __init__(self, vectors) :
        self.vectors = vectors

    def retrieve(self, query : str) :
        return self.vectors[0]

retriever = retrievingthedocuments(vectors)

prompt = ChatPromptTemplate.from_template(
    "You are a helpful assistant. Answer the question based on the provided documents.\n\nQuestion: {question}\n\nDocuments: {answers}"
)
rag_input ={
    "question" : RunnablePassthrough(),
    "answers" : retriever
}

chain = rag_input | prompt | model | StrOutputParser()

chain.invoke({"question" : "What is AI and how does it relate to machine learning?"})

import logging
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda

logger = logging.getLogger("llm_pipeline")

# --- Models -----------------------------------------------------------

# Primary: retried on transient errors, capped attempts + backoff
primary_model = ChatOpenAI(
    model="gpt-4o",
    timeout=15,
    max_retries=0,  # disable provider's own retry, we control it via .with_retry
).with_retry(
    retry_if_exception_type=(TimeoutError, ConnectionError),
    wait_exponential_jitter=True,
    stop_after_attempt=3,
)

# Backup: cheaper/faster model, also retried but with fewer attempts
backup_model = ChatOpenAI(
    model="gpt-4o-mini",
    timeout=10,
    max_retries=0,
).with_retry(
    retry_if_exception_type=(TimeoutError, ConnectionError),
    wait_exponential_jitter=True,
    stop_after_attempt=2,
)

# Last resort: different provider entirely, in case OpenAI is down
last_resort_model = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    timeout=10,
).with_retry(
    stop_after_attempt=2,
)

modelforinput = primary_model.with_fallbacks(
    fallbacks = [backup_model, last_resort_model],
    exceptions_to_handle = (TimeoutError, ConnectionError)
)

chain = prompt | modelforinput | StrOutputParser()


from langchain_core.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder

documents = []

prompt1 = PromptTemplate.from_template(
    f"You are a helpful assistant. Answer the question based on the provided documents.\n\nQuestion: {{question}}\n\nDocuments: {{answers}}"
)

prompt2 = ChatPromptTemplate.from_template(
    ("system", "You are a helpful assistant. Answer the question based on the provided documents"),
    MessagesPlaceholder("history"),
    ("user", "Question: {question}\n\nDocuments: {documents}"),
)


result = prompt2.invoke(
    {
        "history": [
            ("user", "What is AI?"),
            ("assistant", "AI is a branch of computer science that aims to create machines that can perform tasks that typically require human intelligence."),
        ],
        "question": "How does it relate to machine learning?",
        "documents": documents
    }
)