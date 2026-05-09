import asyncio
import uuid
from typing import Dict, Any, List, Callable, Optional
from utils.ollama_client import client

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
                             repeat_penalty: float = 1.1,
                             system_prompt: str = "",
                             tool_funcs_map: Dict[str, Callable] = None,
                             log_requests: bool = False,
                             persist_callback: Callable[[List[Dict]], Any] = None,
                             listener: Callable = None,
                             keep_alive: str = "5m"
                             ):
        
        if self.is_streaming(stream_id):
            return

        self.stop_flags[stream_id] = False
        self.stream_contexts[stream_id] = messages
        
        task = asyncio.create_task(self._process_stream(
            stream_id, messages, model, temperature, top_p, repeat_penalty, system_prompt, 
            tool_funcs_map, log_requests, persist_callback, listener, keep_alive
        ))
        self.active_tasks[stream_id] = task
        
        def cleanup(t):
            self.active_tasks.pop(stream_id, None)
            self.stop_flags.pop(stream_id, None)
            pass
            
        task.add_done_callback(cleanup)
        return task

    async def _process_stream(self, stream_id, messages, model, temperature, top_p, repeat_penalty, system_prompt, tool_funcs_map, log_requests, persist_callback, listener=None, keep_alive="5m"):
        try:
            import time
            from datetime import datetime
            
            # Prepare API messages
            api_messages = []
            sys_content = system_prompt or "You are a helpful assistant."
            
            tz = time.tzname[time.daylight]
            current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sys_content += f"\n\nCurrent System Date and Time: {current_time_str} {tz}"
            
            if tool_funcs_map:
                 sys_content += "\n\nIMPORTANT: When generating tool calls, ensure strictly valid JSON. Do not use invalid escape sequences like '\\?' inside strings. Only escape backslashes and double quotes. Note that the tool content/result is NOT displayed to the user, so you must interpret the tool content and provide the user a response based on it."
            
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
                list_tools = list(tool_funcs_map.values()) if tool_funcs_map else None
                
                try:
                    stream = await client.chat(
                        model=model,
                        messages=api_messages,
                        stream=True,
                        options={
                            'temperature': temperature,
                            'top_p': top_p,
                            'repeat_penalty': repeat_penalty
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
                        if part: response_content += part
                        
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
                    
                except Exception as e:
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
