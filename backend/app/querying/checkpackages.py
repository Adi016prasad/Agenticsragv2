import importlib.metadata as metadata

packages = [
    "langgraph",
    "langchain-aws",
    "langchain-core",
    "fastapi",
    "python-dotenv",
    "uvicorn",
    "langchain-openai",
    "openai",
    "anthropic",
    "langchain-anthropic",
    "google-cloud-firestore",
    "qdrant-client",
    "langsmith",
    "crewai",
    "apscheduler",
    "redis",
    "pandas",
    "prometheus-client",
    "datasets",
    "tiktoken",
    "langchain-google-vertexai",
    "rouge-score",
    "sacrebleu",
    "google-adk",
]

for package in packages:
    try:
        version = metadata.version(package)
        print(f"✅ {package}: {version}")
    except metadata.PackageNotFoundError:
        print(f"❌ {package}: NOT INSTALLED")