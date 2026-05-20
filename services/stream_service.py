import asyncio
import uuid
from typing import Dict, Any, List, Callable, Optional
from utils.llm_client import client

class StreamService:
    def __init__(self):
        # active streams: id -> asyncio.Task
        self.active_tasks: Dict[str, asyncio.Task] = {}
        # listeners: id -> callback
        self.listeners: Dict[str, Callable] = {}
        # cancellation flags: id -> bool
        self.stop_flags: Dict[str, bool] = {}
        # active context storage: id -> list of messages
        # This allows new listeners to retrieve the current state of a stream
        self.stream_contexts: Dict[str, List[Dict]] = {}
        
    def is_streaming(self, stream_id: str) -> bool:
        return stream_id in self.active_tasks and not self.active_tasks[stream_id].done()

    def any_active(self) -> bool:
        return any(not t.done() for t in self.active_tasks.values())

    def get_context(self, stream_id: str) -> Optional[List[Dict]]:
        return self.stream_contexts.get(stream_id)

    def stop_generation(self, stream_id: str):
        self.stop_flags[stream_id] = True
        if stream_id in self.active_tasks:
            self.active_tasks[stream_id].cancel()

    def stop_all(self):
        for sid in list(self.active_tasks.keys()):
            self.stop_flags[sid] = True
            if sid in self.active_tasks:
                self.active_tasks[sid].cancel()

    def register_listener(self, stream_id: str, callback: Callable):
        self.listeners[stream_id] = callback

    def unregister_listener(self, stream_id: str):
        if stream_id in self.listeners:
            del self.listeners[stream_id]

    async def start_generation(self, 
                             stream_id: str, 
                             messages: List[Dict],
                             model: str, 
                             temperature: float = 0.7,
                             top_p: float = 0.9,
                             min_p: float = 0.0,
                             repeat_penalty: float = 1.1,
                             top_k: int = 40,
                             system_prompt: str = "",
                             tool_funcs_map: Dict[str, Callable] = None,
                             log_requests: bool = False,
                             persist_callback: Callable[[List[Dict]], Any] = None,
                             listener: Callable = None,
                             keep_alive: str = "5m",
                             memory_enabled: bool = False,
                             has_attachments: bool = False
                             ):
        
        if self.is_streaming(stream_id):
            return

        self.stop_flags[stream_id] = False
        self.stream_contexts[stream_id] = messages
        
        # Ensure visual pipeline is unloaded to free VRAM for LLM
        try:
            from services.visual_service import unload_pipeline
            unload_pipeline()
        except Exception as e:
            print(f"Failed to unload visual pipeline: {e}")
        
        task = asyncio.create_task(self._process_stream(
            stream_id, messages, model, temperature, top_p, min_p, repeat_penalty, top_k, system_prompt, 
            tool_funcs_map, log_requests, persist_callback, listener, keep_alive,
            memory_enabled, has_attachments
        ))
        self.active_tasks[stream_id] = task
        
        def cleanup(t):
            self.active_tasks.pop(stream_id, None)
            self.stop_flags.pop(stream_id, None)
            pass
            
        task.add_done_callback(cleanup)
        return task

    async def _process_stream(self, stream_id, messages, model, temperature, top_p, min_p, repeat_penalty, top_k, system_prompt, tool_funcs_map, log_requests, persist_callback, listener=None, keep_alive="5m", memory_enabled=False, has_attachments=False):
        try:
            import time
            from datetime import datetime
            from nicegui import app
            
            try:
                if 'models_without_tools' not in app.storage.general:
                    app.storage.general['models_without_tools'] = []
                if model in app.storage.general['models_without_tools']:
                    tool_funcs_map = None
                    memory_enabled = False
            except Exception: pass

            # Prepare API messages
            api_messages = []
            from services.system_message_service import system_message_service
            sys_content = system_message_service.compile_message(
                base_prompt=system_prompt,
                memory_enabled=memory_enabled,
                has_attachments=has_attachments,
                tool_funcs_map=tool_funcs_map
            )

            api_messages.append({'role': 'system', 'content': sys_content})
            
            for msg in messages:
                if msg['role'] in ['user', 'assistant', 'tool']:
                    clean_msg = {k:v for k,v in msg.items() if k in ['role', 'content', 'images', 'tool_calls']}
                    api_messages.append(clean_msg)
            
            # Helper for tool execution
            async def execute_tool_call(tool_call):
                try:
                    fname = tool_call.get('function', {}).get('name')
                    args = tool_call.get('function', {}).get('arguments', {})
                    if tool_funcs_map and fname in tool_funcs_map:
                        func = tool_funcs_map[fname]
                        if asyncio.iscoroutinefunction(func):
                            res = await func(**args)
                        else:
                            res = func(**args)
                        return str(res)
                    else:
                        return f"Error: Tool {fname} not found"
                except Exception as e:
                    return f"Error executing tool: {e}"

            # Loop for conversation (turns)
            while True:
                if self.stop_flags.get(stream_id): break

                # New Assistant Message
                msg_id = str(uuid.uuid4())
                assistant_msg = {
                    'role': 'assistant', 
                    'content': '', 
                    'thinking': '', 
                    'model': model,
                    'id': msg_id
                }
                messages.append(assistant_msg)
                
                # Notify Listener: New Message
                try:
                    if listener:
                         await listener('new_message', assistant_msg)
                    if stream_id in self.listeners:
                         await self.listeners[stream_id]('new_message', assistant_msg)
                except: pass
                
                # Setup stream
                while True:
                    list_tools = list(tool_funcs_map.values()) if tool_funcs_map else None
                    
                    try:
                        stream = await client.chat(
                            model=model,
                            messages=api_messages,
                            stream=True,
                            options={
                                'temperature': temperature,
                                'top_p': top_p,
                                'min_p': min_p,
                                'repeat_penalty': repeat_penalty,
                                'top_k': top_k
                            },
                            keep_alive=keep_alive,
                            tools=list_tools,
                            log_requests=log_requests
                        )
                        
                        response_content = ""
                        full_thinking = ""
                        tool_calls = []

                        async for chunk in stream:
                            if self.stop_flags.get(stream_id):
                                if not response_content and not full_thinking:
                                    response_content = '_Stopped by user_'
                                    assistant_msg['content'] = response_content
                                break
                                
                            msg_chunk = chunk.get('message', {})
                            part = msg_chunk.get('content') or ''
                            thinking_part = msg_chunk.get('thinking', '')
                            tc_part = msg_chunk.get('tool_calls', [])
                            
                            if thinking_part: full_thinking += thinking_part
                            if tc_part: tool_calls.extend(tc_part)
                            if part: 
                                if part.startswith("Error:") and "does not support tools" in part.lower():
                                    raise Exception(part)
                                response_content += part
                            if chunk.get("error"):
                                raise Exception(chunk["error"])
                            
                            # Update local msg
                            assistant_msg['content'] = response_content
                            assistant_msg['thinking'] = full_thinking
                            if tool_calls: assistant_msg['tool_calls'] = tool_calls
                            
                            # Notify Listener: Update
                            try:
                                if listener:
                                    await listener('update_message', msg_id, response_content, full_thinking, tool_calls)
                                if stream_id in self.listeners:
                                   await self.listeners[stream_id]('update_message', msg_id, response_content, full_thinking, tool_calls)
                            except: pass
                        break
                    except Exception as e:
                        error_msg = str(e).lower()
                        if "does not support tools" in error_msg and list_tools:
                            print(f"Model {model} does not support tools. Retrying without tools.")
                            from nicegui import app
                            try:
                                if 'models_without_tools' not in app.storage.general:
                                    app.storage.general['models_without_tools'] = []
                                if model not in app.storage.general['models_without_tools']:
                                    app.storage.general['models_without_tools'].append(model)
                            except Exception: pass
                            tool_funcs_map = None
                            continue

                        assistant_msg['content'] += f"\n[Error: {e}]"
                        print(f"Streaming Exception: {e}")
                        if listener:
                             try: await listener('error', str(e))
                             except: pass
                                 
                        if stream_id in self.listeners:
                             try: await self.listeners[stream_id]('error', str(e))
                             except: pass
                        # Save before breaking
                        if persist_callback:
                            if asyncio.iscoroutinefunction(persist_callback):
                                await persist_callback(messages)
                            else:
                                persist_callback(messages)
                        break

                # End of stream (or stop)
                assistant_msg['content'] = response_content
                assistant_msg['thinking'] = full_thinking
                if tool_calls: assistant_msg['tool_calls'] = tool_calls
                
                # Update API messages
                clean_assist = {k:v for k,v in assistant_msg.items() if k in ['role', 'content', 'tool_calls']}
                api_messages.append(clean_assist)
                
                # Save
                if persist_callback:
                    if asyncio.iscoroutinefunction(persist_callback):
                        await persist_callback(messages)
                    else:
                        persist_callback(messages)
                
                if self.stop_flags.get(stream_id): break
                
                if tool_calls:
                    for tc in tool_calls:
                        res = await execute_tool_call(tc)
                        tool_msg = {
                            'role': 'tool',
                            'content': res,
                            'name': tc.get('function', {}).get('name'),
                            'id': str(uuid.uuid4())
                        }
                        messages.append(tool_msg)
                        api_messages.append({'role': 'tool', 'content': res})
                        
                        try:
                            if listener: await listener('new_message', tool_msg)
                            if stream_id in self.listeners: await self.listeners[stream_id]('new_message', tool_msg)
                        except: pass
                    
                    if persist_callback:
                        if asyncio.iscoroutinefunction(persist_callback):
                            await persist_callback(messages)
                        else:
                            persist_callback(messages)
                else:
                    break 
        
        except asyncio.CancelledError:
             # Handle cancellation by saving partial state if possible
            if 'assistant_msg' in locals():
                if not assistant_msg['content'] and not assistant_msg['thinking']:
                     assistant_msg['content'] = "_Stopped_"
                
                try:
                    if listener:
                        await listener('update_message', assistant_msg['id'], assistant_msg['content'], assistant_msg['thinking'], assistant_msg.get('tool_calls', []))
                    if stream_id in self.listeners:
                        await self.listeners[stream_id]('update_message', assistant_msg['id'], assistant_msg['content'], assistant_msg['thinking'], assistant_msg.get('tool_calls', []))
                except: pass
                
                # Save
                if persist_callback:
                    if asyncio.iscoroutinefunction(persist_callback):
                        await persist_callback(messages)
                    else:
                        persist_callback(messages)
            # We treat cancellation as a stop
            pass

        except Exception as e:
            print(f"Outer Streaming process error: {e}")
        finally:
             try:
                 if listener: await listener('done')
                 if stream_id in self.listeners: await self.listeners[stream_id]('done')
             except: pass

stream_service = StreamService()
