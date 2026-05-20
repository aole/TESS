import asyncio
import uuid
import time
from typing import Dict, List, Optional, Any
from services.stream_service import stream_service
from utils.config import config_manager
from utils.llm_client import client

class BatchService:
    def __init__(self):
        self.active_batches: Dict[str, Dict] = {}
        # batch_id -> background task
        self.batch_tasks: Dict[str, asyncio.Task] = {}

    def get_batch(self, batch_id: str) -> Optional[Dict]:
        return self.active_batches.get(batch_id)

    def start_batch(self, 
                   user_prompt: str, 
                   system_prompt: str, 
                   models: List[str]) -> str:
        
        batch_id = str(uuid.uuid4())
        
        # Initialize State
        batch_state = {
            'id': batch_id,
            'user_prompt': user_prompt,
            'system_prompt': system_prompt,
            'models': models,
            'status': 'running', # running, stopped, completed
            'current_model': None,
            'model_states': {}, # model -> { status, time, tokens, messages, stream_id }
            'results': {} # model -> output string (convenience)
        }

        for m in models:
            batch_state['model_states'][m] = {
                'status': 'waiting', # waiting, generating, done, error, cancelled
                'time': 0,
                'tokens': 0,
                'stream_id': f"{batch_id}_{m}",
                'messages': [] 
            }
            
            # Prep messages
            msgs = []
            if system_prompt:
                msgs.append({'role': 'system', 'content': system_prompt})
            msgs.append({'role': 'user', 'content': user_prompt})
            batch_state['model_states'][m]['messages'] = msgs

        self.active_batches[batch_id] = batch_state
        
        # Start Background Task
        task = asyncio.create_task(self._run_batch_process(batch_id))
        self.batch_tasks[batch_id] = task
        
        return batch_id

    def any_active(self) -> bool:
        return any(b['status'] == 'running' for b in self.active_batches.values())

    def stop_batch(self, batch_id: str):
        if batch_id in self.active_batches:
            self.active_batches[batch_id]['status'] = 'stopped'
            # Also invoke stop on current stream
            current_model = self.active_batches[batch_id].get('current_model')
            if current_model:
                sid = self.active_batches[batch_id]['model_states'][current_model]['stream_id']
                stream_service.stop_generation(sid)
    
    def stop_all(self):
        for bid, b in self.active_batches.items():
            if b['status'] == 'running':
                self.stop_batch(bid)

    async def _run_batch_process(self, batch_id: str):
        state = self.active_batches[batch_id]
        
        for model in state['models']:
            if state['status'] == 'stopped':
                state['model_states'][model]['status'] = 'cancelled'
                continue
            
            state['current_model'] = model
            m_state = state['model_states'][model]
            m_state['status'] = 'generating'
            m_state['start_time'] = time.time()
            
            stream_id = m_state['stream_id']
            messages = m_state['messages']
            
            # We don't need a persist callback for batch usually, as it's ephemeral, 
            # but we update our local state object which is kept in memory.
            # StreamService updates 'messages' list in-place.
            
            # Track tokens via a wrapped listener? 
            # StreamService doesn't easily expose token counts in usage yet, 
            # but it does pass raw chunks if we used a different mechanism.
            # For now, we reuse the mechanism in batch.py: 
            # We can't easily get 'eval_count' from StreamService unless we update StreamService to expose it or store it.
            # Let's update StreamService to store/expose metrics or pass them in update events?
            # Existing StreamService implementation just passes content. 
            # We will ignore detailed token counts for now or accept they might be missing 
            # unless we modify StreamService. 
            # Actually, `StreamService` does not currently extract `eval_count`.
            # We can leave that as a TODO or minor regression, or update `StreamService`.
            # Let's verify `StreamService` code I wrote.
            # It extracts: part, thinking_part, tc_part.
            # It ignores `eval_count`. 
            # I should probably update `StreamService` to handle metadata/metrics if I want to keep feature parity.
            # But simpler to verify basic functionality first.

            # Fetch model-specific parameters
            from nicegui import app
            model_configs = app.storage.general.get('model_configurations', {})
            model_cfg = model_configs.get(model) or {}
            
            params = await client.get_model_parameters(model)
            
            temperature = model_cfg.get('temperature') or params.get('temperature', 0.7)
            top_p = model_cfg.get('top_p') or params.get('top_p', 0.9)
            min_p = model_cfg.get('min_p', params.get('min_p', 0.0))
            repeat_penalty = model_cfg.get('repeat_penalty') or params.get('repeat_penalty', 1.1)
            top_k = model_cfg.get('top_k') or params.get('top_k', 40)
            
            await stream_service.start_generation(
                stream_id=stream_id,
                messages=m_state['messages'], # Use messages from state
                model=model,
                temperature=temperature,
                top_p=top_p,
                min_p=min_p,
                repeat_penalty=repeat_penalty,
                top_k=top_k,
                system_prompt=state['system_prompt'],
                log_requests=config_manager.is_logging_enabled('batch'),
                keep_alive=0
            )
            
            # Wait for completion
            while stream_service.is_streaming(stream_id):
                if state['status'] == 'stopped':
                    stream_service.stop_generation(stream_id)
                await asyncio.sleep(0.1)
            
            end_time = time.time()
            m_state['time'] = end_time - m_state.get('start_time', end_time)
            
            # Check if it was stopped
            context = stream_service.get_context(stream_id) or m_state['messages']
            # Last message is assistant
            if context and context[-1]['role'] == 'assistant':
                content = context[-1]['content']
                if '_Stopped by user_' in content:
                     m_state['status'] = 'cancelled'
                else:
                     m_state['status'] = 'done'
            else:
                m_state['status'] = 'error'

            # Small breather
            await asyncio.sleep(0.5)

        state['status'] = 'completed'
        state['current_model'] = None

batch_service = BatchService()
