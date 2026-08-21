# ============================================================
# prompt.py
# ============================================================
from abc import ABC, abstractmethod


class Prompt(ABC):
    @abstractmethod
    def systemprompt(self) -> str :
        pass

    @abstractmethod
    def filteringsystemprompt(self, parenttext : list[str]) -> str:
        pass

class DefaultPrompt(Prompt):
    def systemprompt(self) -> str:
        return (
            """You are a helpful assistant. Provide concise, accurate responses. Never return an empty response.
            You must respond ONLY with a valid JSON object matching the requested schema.
            If for any policy related query comes to you, output tool_needed = true and keep rewrittenQueryforVectorsearch as rewritten user query to a standalone, self-contained rewrite of the user's latest question. This rewrite must include any missing context (such as the product name or topic) drawn from the conversation history
            But if you can answer the policy specific user query from conversation history or any general query not related to your context or policy, then answer it simply and keep (tool_needed = false and rewrittenQueryforVectorsearch = "")"""
        )

    def filteringsystemprompt(self, parenttext : list[str]) -> str:
            return (
                f"""You are a query vs document analyzer. You will have the retrieved result in "retrievedresult" and the query in "query".
                Your task is to analyze the retrieved result carefully against the asked query, ignore unused and noisy text, and extract only the relevant information that answers the query.
                Set isAnswerFound to true and put the relevant extracted information in output, only if the retrieved result actually contains information relevant to the query.
                If the retrieved result does not contain any information relevant to the query, set isAnswerFound to false and set output to what you found out in the result in short and also ask the user to clarify their question.
                Here is the retrieved documents from RAG
                retrievedresult = {parenttext}"""
            )

class PromptFactory:
    _registry: dict[str, type[Prompt]] = {
        "default": DefaultPrompt,
    }

    @classmethod
    def create(cls, name: str) -> Prompt:
        try:
            prompt_cls = cls._registry[name]
        except KeyError:
            raise ValueError(f"Unknown prompt provider: {name}")
        return prompt_cls()

    @classmethod
    def register(cls, name: str, prompt_cls: type[Prompt]) -> None:
        cls._registry[name] = prompt_cls