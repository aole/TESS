import ollama
from typing import List, Dict, Any, AsyncGenerator
import json
import os
from datetime import datetime

class OllamaClient:
    def __init__(self):
        self.client = ollama.AsyncClient()
        self.log_path = os.path.join(os.getcwd(), 'logs', 'llm_debug.log')
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

    def _log(self, type: str, content: Any, model: str = None):
        try:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': type,
                'model': model,
                'content': content
            }
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, indent=2, default=str) + "\n" + "="*80 + "\n")
        except Exception as e:
            print(f"Failed to log: {e}")

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

    async def create_model(self, model: str, modelfile: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Create a model from a Modelfile using CLI."""
        import tempfile
        import asyncio
        
        # Create temp file
        # Windows requires file to be closed before another process uses it
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as tmp:
                tmp.write(modelfile)
                tmp_path = tmp.name
            
            self._log('create_request', {'modelfile': modelfile}, model)
            
            process = await asyncio.create_subprocess_exec(
                'ollama', 'create', model, '-f', tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            
            # Read stdout
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                line_str = line.decode().strip()
                if line_str:
                    yield {'status': line_str}
            
            await process.wait()
            
            if process.returncode != 0:
                raise Exception(f"Process exited with code {process.returncode}")
                
        except Exception as e:
            self._log('create_error', str(e), model)
            yield {'status': 'error', 'error': str(e)}
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass

    async def generate(self, model: str, prompt: str, system: str = None, template: str = None, context: List[int] = None, stream: bool = True, options: Dict[str, Any] = None):
        """Generate a response for a given prompt."""
        self._log('generate_request', {'prompt': prompt, 'system': system, 'options': options}, model)
        try:
            response = await self.client.generate(model=model, prompt=prompt, system=system, template=template, context=context, stream=stream, options=options)
            if stream:
                async def generator():
                    full_response = ""
                    try:
                        async for chunk in response:
                            data = (chunk.model_dump() if hasattr(chunk, 'model_dump') else (chunk.dict() if hasattr(chunk, 'dict') else dict(chunk)))
                            full_response += data.get('response', '')
                            yield data
                        self._log('generate_response', full_response, model)
                    except Exception as e:
                        self._log('generate_error', str(e), model)
                        yield {'response': f"Error: {str(e)}"}
                return generator()
            else:
                data = (response.model_dump() if hasattr(response, 'model_dump') else (response.dict() if hasattr(response, 'dict') else dict(response)))
                self._log('generate_response', data.get('response'), model)
                return data
        except Exception as e:
            self._log('generate_error', str(e), model)
            print(f"Error generating response: {e}")
            if stream:
                async def error_gen():
                    yield {'response': f"Error: {str(e)}"}
                return error_gen()
            return {'response': f"Error: {str(e)}"}

    async def chat(self, model: str, messages: List[Dict[str, str]], stream: bool = True, options: Dict[str, Any] = None, tools: List[Any] = None):
        """Chat with a model."""
        self._log('chat_request', {'messages': messages, 'options': options, 'tools': str(tools) if tools else None}, model)
        try:
            response = await self.client.chat(model=model, messages=messages, stream=stream, options=options, tools=tools)
            if stream:
                async def generator():
                    accumulated_content = ""
                    accumulated_tool_calls = []
                    accumulated_thinking = ""
                    try:
                        async for chunk in response:
                            data = (chunk.model_dump() if hasattr(chunk, 'model_dump') else (chunk.dict() if hasattr(chunk, 'dict') else dict(chunk)))
                            msg = data.get('message', {})
                            accumulated_content += msg.get('content', '') or ''
                            accumulated_thinking += msg.get('thinking', '') or ''
                            if 'tool_calls' in msg and msg['tool_calls']:
                                accumulated_tool_calls.extend(msg['tool_calls'])
                            yield data
                        
                        log_content = {'content': accumulated_content}
                        if accumulated_thinking:
                            log_content['thinking'] = accumulated_thinking
                        if accumulated_tool_calls:
                            log_content['tool_calls'] = accumulated_tool_calls
                        self._log('chat_response', log_content, model)
                    
                    except Exception as e:
                        self._log('chat_error', str(e), model)
                        yield {'message': {'content': f"Error: {str(e)}"}}

                return generator()
            else:
                data = (response.model_dump() if hasattr(response, 'model_dump') else (response.dict() if hasattr(response, 'dict') else dict(response)))
                self._log('chat_response', data.get('message'), model)
                return data
        except Exception as e:
            self._log('chat_error', str(e), model)
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
