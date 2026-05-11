from abc import ABC, abstractmethod
from typing import List, Dict, Any, AsyncGenerator

class BaseLLMClient(ABC):
    """
    Abstract base class for LLM clients.
    All backend implementations (e.g., Ollama, llama.cpp) should inherit from this.
    """

    @abstractmethod
    async def list_models(self) -> List[Dict[str, Any]]:
        raise NotImplementedError("Operation not supported.")

    @abstractmethod
    async def show_model(self, model_name: str) -> Dict[str, Any]:
        raise NotImplementedError("Operation not supported.")

    @abstractmethod
    async def copy_model(self, source: str, destination: str) -> bool:
        raise NotImplementedError("Operation not supported.")

    @abstractmethod
    async def delete_model(self, model_name: str) -> bool:
        raise NotImplementedError("Operation not supported.")

    @abstractmethod
    async def pull_model(self, model_name: str) -> AsyncGenerator[Dict[str, Any], None]:
        raise NotImplementedError("Operation not supported.")
        yield {} # Just to satisfy typing for generator

    @abstractmethod
    async def create_model(self, model: str, from_: str = None, system: str = None, template: str = None, parameters: Dict[str, Any] = None) -> AsyncGenerator[Dict[str, Any], None]:
        raise NotImplementedError("Operation not supported.")
        yield {} # Just to satisfy typing for generator

    @abstractmethod
    async def generate(self, model: str, prompt: str, system: str = None, template: str = None, context: List[int] = None, stream: bool = True, options: Dict[str, Any] = None, log_requests: bool = True):
        raise NotImplementedError("Operation not supported.")

    @abstractmethod
    async def chat(self, model: str, messages: List[Dict[str, str]], stream: bool = True, options: Dict[str, Any] = None, tools: List[Any] = None, keep_alive: Any = None, log_requests: bool = True):
        raise NotImplementedError("Operation not supported.")

    @abstractmethod
    async def get_model_parameters(self, model_name: str) -> Dict[str, Any]:
        raise NotImplementedError("Operation not supported.")

    @abstractmethod
    async def unload_all_models(self) -> bool:
        raise NotImplementedError("Operation not supported.")
