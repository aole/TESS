import ollama
from typing import List, Dict, Any, AsyncGenerator
import json
import os
from datetime import datetime
from utils.base_llm_client import BaseLLMClient

class OllamaClient(BaseLLMClient):
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

    async def create_model(self, model: str, from_: str = None, system: str = None, template: str = None, parameters: Dict[str, Any] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Create a model from components using the Ollama python client."""
        try:
            self._log('create_request', {'model': model, 'from': from_, 'system': system, 'parameters': parameters}, model)
            
            # Construct arguments for client.create
            create_args = {'model': model, 'stream': True}
            
            if from_:
                create_args['from_'] = from_
            if system:
                create_args['system'] = system
            if template: 
                create_args['template'] = template
            if parameters: 
                create_args['parameters'] = parameters

            # Use the python client directly
            # stream=True yields progress updates
            resp = await self.client.create(**create_args)
            async for chunk in resp:
                 data = (chunk.model_dump() if hasattr(chunk, 'model_dump') else (chunk.dict() if hasattr(chunk, 'dict') else dict(chunk)))
                 yield data
                
        except Exception as e:
            self._log('create_error', str(e), model)
            yield {'status': 'error', 'error': str(e)}

    async def generate(self, model: str, prompt: str, system: str = None, template: str = None, context: List[int] = None, stream: bool = True, options: Dict[str, Any] = None, log_requests: bool = True):
        """Generate a response for a given prompt."""
        if log_requests:
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
                        if log_requests:
                            self._log('generate_response', full_response, model)
                    except Exception as e:
                        if log_requests:
                            self._log('generate_error', str(e), model)
                        yield {'response': f"Error: {str(e)}"}
                return generator()
            else:
                data = (response.model_dump() if hasattr(response, 'model_dump') else (response.dict() if hasattr(response, 'dict') else dict(response)))
                if log_requests:
                    self._log('generate_response', data.get('response'), model)
                return data
        except Exception as e:
            error_message = str(e)
            if log_requests:
                self._log('generate_error', error_message, model)
            print(f"Error generating response: {error_message}")
            if stream:
                async def error_gen():
                    yield {'response': f"Error: {error_message}"}
                return error_gen()
            return {'response': f"Error: {error_message}"}

    async def chat(self, model: str, messages: List[Dict[str, str]], stream: bool = True, options: Dict[str, Any] = None, tools: List[Any] = None, keep_alive: Any = None, log_requests: bool = True):
        """Chat with a model."""
        if log_requests:
            self._log('chat_request', {'messages': messages, 'options': options, 'tools': str(tools) if tools else None, 'keep_alive': keep_alive}, model)
        try:
            chat_args = {
                'model': model,
                'messages': messages,
                'stream': stream,
                'options': options,
                'tools': tools
            }
            if keep_alive is not None:
                chat_args['keep_alive'] = keep_alive

            response = await self.client.chat(**chat_args)
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
                        if log_requests:
                            self._log('chat_response', log_content, model)
                    
                    except Exception as e:
                        if log_requests:
                            self._log('chat_error', str(e), model)
                        yield {'message': {'content': f"Error: {str(e)}"}}

                return generator()
            else:
                data = (response.model_dump() if hasattr(response, 'model_dump') else (response.dict() if hasattr(response, 'dict') else dict(response)))
                if log_requests:
                    self._log('chat_response', data.get('message'), model)
                return data
        except Exception as e:
            error_message = str(e)
            if log_requests:
                self._log('chat_error', error_message, model)
            print(f"Error chatting with model: {error_message}")
            if stream:
                async def error_gen():
                    yield {'message': {'content': f"Error: {error_message}"}}
                return error_gen()
            return {'message': {'content': f"Error: {error_message}"}}

    async def get_model_parameters(self, model_name: str) -> Dict[str, Any]:
        """Get default parameters and system prompt for a model."""
        try:
            info = await self.show_model(model_name)
            params = {}
            
            # Get system prompt
            if 'system' in info and info['system']:
                params['system'] = info['system']
            elif 'modelfile' in info:
                # Fallback: parse Modelfile for SYSTEM command
                # This is a simple parser and might not catch all edge cases (like multiline with triple quotes if not handled by API)
                for line in info['modelfile'].split('\n'):
                    if line.strip().upper().startswith('SYSTEM '):
                        # Extract content after SYSTEM
                        # Typically: SYSTEM "content" or SYSTEM content
                        content = line.strip()[6:].strip()
                        
                        # Remove quotes if present
                        if (content.startswith('"') and content.endswith('"')) or \
                           (content.startswith("'") and content.endswith("'")):
                            content = content[1:-1]
                        
                        # Handle triple quotes if simple one-liner
                        if (content.startswith('"""') and content.endswith('"""')):
                             content = content[3:-3]
                        
                        params['system'] = content
                        break
            
            # Parse parameters blob
            params_text = info.get('parameters', '')
            if params_text:
                for line in params_text.split('\n'):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        key = parts[0]
                        value = parts[1]
                        try:
                            if key == 'temperature' or key == 'temp':
                                params['temperature'] = float(value)
                            elif key == 'top_p':
                                params['top_p'] = float(value)
                            elif key == 'repeat_penalty':
                                params['repeat_penalty'] = float(value)
                            # Add more parsers as needed
                        except ValueError:
                            pass
            return params
        except Exception as e:
            print(f"Error getting parameters for {model_name}: {e}")
            return {}

    async def unload_all_models(self) -> bool:
        """Unload all currently loaded models from memory."""
        try:
            ps_res = await self.client.ps()
            models = ps_res.get('models', [])
            for m in models:
                model_name = m.get('name') or m.get('model')
                if model_name:
                    print(f"Unloading LLM: {model_name}")
                    self._log('unload_model', f"Unloading {model_name}", model_name)
                    await self.client.generate(model=model_name, keep_alive=0)
            return True
        except Exception as e:
            print(f"Error unloading models: {e}")
            self._log('unload_error', str(e))
            return False

# Removed singleton instance to utils/llm_client.py
