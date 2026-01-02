import ollama
from typing import List, Dict, Any, AsyncGenerator

class OllamaClient:
    def __init__(self):
        self.client = ollama.AsyncClient()

    async def list_models(self) -> List[Dict[str, Any]]:
        """List all available models."""
        try:
            response = await self.client.list()
            models = response.get('models', [])
            data = []
            for m in models:
                if hasattr(m, 'model_dump'):
                    data.append(m.model_dump())
                elif hasattr(m, 'dict'):
                    data.append(m.dict())
                else:
                    data.append(dict(m))
            return data
        except Exception as e:
            print(f"Error listing models: {e}")
            return []

    async def show_model(self, model_name: str) -> Dict[str, Any]:
        """Show details for a specific model."""
        try:
            info = await self.client.show(model_name)
            if hasattr(info, 'model_dump'):
                return info.model_dump()
            elif hasattr(info, 'dict'):
                return info.dict()
            return dict(info)
        except Exception as e:
            print(f"Error showing model {model_name}: {e}")
            return {}

    async def copy_model(self, source: str, destination: str) -> bool:
        """Copy a model."""
        try:
            await self.client.copy(source, destination)
            return True
        except Exception as e:
            print(f"Error copying model: {e}")
            return False

    async def delete_model(self, model_name: str) -> bool:
        """Delete a model."""
        try:
            await self.client.delete(model_name)
            return True
        except Exception as e:
            print(f"Error deleting model: {e}")
            return False

    async def pull_model(self, model_name: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Pull a model with streaming progress."""
        try:
            resp = await self.client.pull(model_name, stream=True)
            async for chunk in resp:
                yield (chunk.model_dump() if hasattr(chunk, 'model_dump') else (chunk.dict() if hasattr(chunk, 'dict') else dict(chunk)))
        except Exception as e:
            print(f"Error pulling model: {e}")
            yield {"status": "error", "error": str(e)}

    async def chat(self, model: str, messages: List[Dict[str, str]], stream: bool = True, options: Dict[str, Any] = None):
        """Chat with a model."""
        try:
            response = await self.client.chat(model=model, messages=messages, stream=stream, options=options)
            if stream:
                async def generator():
                    async for chunk in response:
                        yield (chunk.model_dump() if hasattr(chunk, 'model_dump') else (chunk.dict() if hasattr(chunk, 'dict') else dict(chunk)))
                return generator()
            else:
                if hasattr(response, 'model_dump'):
                    return response.model_dump()
                elif hasattr(response, 'dict'):
                    return response.dict()
                return dict(response)
        except Exception as e:
            print(f"Error chatting with model: {e}")
            if stream:
                async def error_gen():
                    yield {'message': {'content': f"Error: {str(e)}"}}
                return error_gen()
            return {'message': {'content': f"Error: {str(e)}"}}

    async def get_model_parameters(self, model_name: str) -> Dict[str, Any]:
        """Get default parameters for a model."""
        try:
            info = await self.show_model(model_name)
            params_text = info.get('parameters', '')
            if not params_text:
                return {}
            
            params = {}
            for line in params_text.split('\n'):
                parts = line.strip().split()
                if len(parts) >= 2:
                    key = parts[0]
                    value = parts[1]
                    try:
                        if key == 'temperature':
                            params['temperature'] = float(value)
                        elif key == 'top_p':
                            params['top_p'] = float(value)
                        # Add more parsers as needed
                    except ValueError:
                        pass
            return params
        except Exception as e:
            print(f"Error getting parameters for {model_name}: {e}")
            return {}

# Singleton instance
client = OllamaClient()
