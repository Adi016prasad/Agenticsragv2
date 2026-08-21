from openai import OpenAI
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel
import os
from dotenv import load_dotenv

load_dotenv()


class BedrockResponse(BaseModel):
    answer: str
    confidence: float


# LangChain handles the structure
parser = PydanticOutputParser(pydantic_object=BedrockResponse)

client = OpenAI(
    base_url="https://bedrock-mantle.ap-south-1.api.aws/v1",
    api_key=os.getenv("APIKEYFORBEDROCK"),
    default_headers={"OpenAI-Project": "default"},
)

response = client.chat.completions.create(
    model="deepseek.v3.1",
    messages=[
        {
            "role": "system",
            "content": (
                "Return the response according to this format:\n"
                + parser.get_format_instructions()
            ),
        },
        {
            "role": "user",
            "content": "What is Amazon Bedrock?",
        },
    ]
)

print(response)

result = parser.parse(
    response.choices[0].message.content
)

print(result)
print(result.answer)
print(result.confidence)