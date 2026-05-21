from nicegui import ui
from typing import List, Dict, Optional, Callable, Any
import uuid

class ConversationRenderer:
    def __init__(self, 
                 container: ui.element, 
                 on_edit: Optional[Callable[[Dict], Any]] = None,
                 on_save_edit: Optional[Callable[[Dict, str], Any]] = None,
                 on_cancel_edit: Optional[Callable[[Dict], Any]] = None,
                 on_delete: Optional[Callable[[Dict], Any]] = None,
                 on_rate: Optional[Callable[[Dict, int, str], Any]] = None,
                 on_delete_rating: Optional[Callable[[Dict, str], Any]] = None,
                 on_save_and_respond: Optional[Callable[[Dict, str], Any]] = None,
                 on_play_tts: Optional[Callable[[Dict], Any]] = None,
                 get_playing_tts_id: Optional[Callable[[], str]] = None,
                 get_ratings: Optional[Callable[[str], List[Any]]] = None,
                 available_tags: List[str] = ["General", "Coding", "Tools", "Writing"],
                 show_avatars: bool = True):
        
        self.container = container
        self.on_edit = on_edit
        self.on_save_edit = on_save_edit
        self.on_cancel_edit = on_cancel_edit
        self.on_delete = on_delete
        self.on_rate = on_rate
        self.on_delete_rating = on_delete_rating
        self.on_save_and_respond = on_save_and_respond
        self.on_play_tts = on_play_tts
        self.get_playing_tts_id = get_playing_tts_id
        self.get_ratings = get_ratings
        self.available_tags = available_tags
        self.show_avatars = show_avatars
        
        # Track components for streaming updates
        self._msg_elements: Dict[str, Dict[str, Any]] = {}

    def clear(self):
        self.container.clear()
        self._msg_elements.clear()

    @staticmethod
    def get_turn_indices(messages: List[Dict], msg: Dict) -> set:
        """
        Calculates the indices of all messages belonging to the same interaction turn
        as the given message.
        - For user messages: Includes the user message and all subsequent non-user messages.
        - For assistant/tool messages: Includes all messages between the preceding user message
          and the next user message (the entire assistant turn).
        """
        if msg not in messages:
            return set()
        
        idx = messages.index(msg)
        
        if msg.get('role') == 'user':
            indices = {idx}
            j = idx + 1
            while j < len(messages) and messages[j].get('role') != 'user':
                indices.add(j)
                j += 1
            return indices
        else:
            # Find the start of this block (after previous user message or start of list)
            start = idx
            while start > 0 and messages[start-1].get('role') != 'user':
                start -= 1
            
            # Find the end of this block (before next user message or end of list)
            end = idx
            while end + 1 < len(messages) and messages[end+1].get('role') != 'user':
                end += 1
            
            return set(range(start, end + 1))

    def render_messages(self, messages: List[Dict]):
        self.clear()
        with self.container:
            for msg in messages:
                self.render_message(msg)

    def render_message(self, msg: Dict):
        # Skip system messages - they are not meant to be shown in the UI
        if msg.get('role') == 'system':
            return

        # Ensure ID
        if 'id' not in msg:
            msg['id'] = str(uuid.uuid4())
        
        msg_id = msg['id']
        role = msg.get('role', 'unknown')
        
        # Ensure we render into the container
        with self.container:
            # Wrapper Row
            with ui.row().classes('w-full items-start gap-4 mb-4 group') as row:
                # Avatar
                if self.show_avatars:
                    with ui.avatar(color='transparent', square=True).classes('size-8 shrink-0 mt-1'):
                        if role == 'user':
                            ui.icon('person', size='24px').classes('text-gray-400')
                        elif role == 'assistant':
                            ui.icon('smart_toy', size='24px').classes('text-indigo-400')
                        elif role == 'tool':
                            ui.icon('output', size='20px').classes('text-gray-500')
                        else:
                            ui.icon('help', size='20px').classes('text-gray-500')

                # Content Column
                with ui.column().classes('flex-grow min-w-0 gap-2'):
                    
                    # Header (Assistant Name / Model) & Controls
                    if role == 'assistant':
                        with ui.row().classes('w-full justify-between items-center'):
                            model_name = msg.get('model', 'Unknown Model')
                            ui.label(model_name).classes('text-xs text-gray-400 font-bold')
                            
                            # Controls
                            self._render_controls(msg)
                    elif role == 'user':
                        with ui.row().classes('w-full justify-end items-center mb-1'):
                            self._render_controls(msg)
                    elif role == 'tool':
                        with ui.row().classes('w-full justify-between items-center mb-1'):
                            tool_name = msg.get('name', 'unknown')
                            ui.label(f"Tool Output: {tool_name}").classes('text-xs text-gray-500 italic font-medium')
                            self._render_controls(msg)

                    # Message Body
                    if msg.get('editing', False):
                        self._render_edit_mode(msg)
                    else:
                        self._render_view_mode(msg)

    def _render_controls(self, msg: Dict):
        if not (self.on_edit or self.on_delete or self.on_play_tts):
            return
            
        with ui.row().classes('opacity-0 group-hover:opacity-100 transition-opacity gap-1'):
            if self.on_play_tts:
                is_playing = self.get_playing_tts_id and self.get_playing_tts_id() == msg.get('id')
                icon = 'stop' if is_playing else 'play_arrow'
                color = 'primary' if is_playing else 'grey'
                ui.button(icon=icon, on_click=lambda m=msg: self.on_play_tts(m)).props(f'flat round dense size=sm color={color}')
            if self.on_edit:
                ui.button(icon='edit', on_click=lambda m=msg: self.on_edit(m)).props('flat round dense size=sm color=grey')
            if self.on_delete:
                ui.button(icon='delete', on_click=lambda m=msg: self.on_delete(m)).props('flat round dense size=sm color=negative')

    def _render_edit_mode(self, msg: Dict):
        with ui.column().classes('w-full items-end gap-2'):
            edit_input = ui.textarea(value=msg.get('content', '')).classes('w-full').props('autogrow rows=2')
            with ui.row().classes('gap-1'):
                if self.on_cancel_edit:
                    ui.button('Cancel', on_click=lambda m=msg: self.on_cancel_edit(m)).props('flat dense color=grey')
                
                if self.on_save_edit:
                    ui.button('Save', on_click=lambda m=msg, inp=edit_input: self.on_save_edit(m, inp.value)).props('flat dense color=primary')
                
                if self.on_save_and_respond:
                    ui.button('Respond', on_click=lambda m=msg, inp=edit_input: self.on_save_and_respond(m, inp.value)).props('flat dense color=secondary')
 
    def _render_view_mode(self, msg: Dict):
        msg_id = msg.get('id')
        role = msg.get('role')
        
        # 1. Thinking
        thinking = msg.get('thinking', '')
        
        # Use an expansion panel for thinking output
        thinking_container = ui.expansion().classes('w-full bg-white/5 rounded-md border-l-2 border-indigo-500 mb-2')
        with thinking_container:
            with thinking_container.add_slot('header'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('psychology', size='20px').classes('text-indigo-400')
                    ui.label('Thought Process').classes('text-[11px] font-bold text-gray-300 uppercase tracking-wider')
            
            thinking_label = ui.label(thinking).classes('text-xs text-gray-400 font-mono whitespace-pre-wrap w-full p-2')
        
        if not thinking:
            thinking_container.classes('hidden')
        
        # 2. Tool Calls
        tool_calls = msg.get('tool_calls', [])
        # Create container always, hidden if empty
        tool_container = ui.column().classes('gap-1 w-full my-2 bg-orange-900/10 p-2 rounded border border-orange-500/20')
        if not tool_calls:
            tool_container.classes('hidden')
        else:
            with tool_container:
                for tc in tool_calls:
                    self._render_tool_call(tc)

        # 3. Content
        content = msg.get('content', '')
        display_content = content
        attachments = msg.get('attachments', [])
        
        # If there are attachments, we want to show them in a collapsible section
        if attachments:
            import re
            # Pattern matches from "### Available Documents:" to the last "</FILE_XX>" block
            pattern = r'^### Available Documents:.*<\/FILE_\d+>\n*'
            display_content = re.sub(pattern, '', content, flags=re.DOTALL).strip()
            
            # Collapsible section for attachments
            with ui.expansion().classes('w-full bg-white/5 rounded-md border border-white/10 mb-2 group/exp') as exp:
                # Custom header with badges
                with exp.add_slot('header'):
                    with ui.row().classes('items-center gap-2 flex-grow'):
                        ui.icon('attachment', size='20px').classes('text-blue-400')
                        ui.label(f"{len(attachments)} Files Attached").classes('text-[11px] font-bold text-gray-300 uppercase tracking-wider')
                        ui.space()
                        with ui.row().classes('gap-1'):
                            for att in attachments:
                                name = att['name'] if isinstance(att, dict) else str(att)
                                ui.badge(name, color='blue-6').props('outline').classes('text-[10px] px-2 py-0.5')
                
                # Content area showing file contents
                with ui.column().classes('w-full p-2 gap-2 bg-black/20'):
                    for att in attachments:
                        if isinstance(att, dict) and 'content' in att:
                            with ui.expansion(att['name'], icon='description').classes('w-full bg-white/5 rounded border border-white/5').props('dense'):
                                with ui.scroll_area().classes('h-48 w-full bg-black/40 rounded p-2'):
                                    ui.label(att['content']).classes('text-xs font-mono text-gray-300 whitespace-pre-wrap')
                        else:
                            # Fallback for old messages with only names
                            ui.label(f"Content for {att} is embedded in message context.").classes('text-xs italic text-gray-500 p-2')

        content_markdown = None
        
        if role == 'tool':
            with ui.expansion().classes('w-full bg-white/5 rounded-md border-l-2 border-gray-500 mb-2') as exp:
                with exp.add_slot('header'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('storage', size='20px').classes('text-gray-400')
                        ui.label('View Raw Output').classes('text-[11px] font-bold text-gray-300 uppercase tracking-wider')
                ui.label(display_content).classes('text-xs font-mono p-2 text-gray-300 whitespace-pre-wrap w-full break-words')
        elif role == 'assistant':
            # Always use markdown for assistant
            safe_content = display_content.replace('<', '&lt;')
            content_markdown = ui.markdown(safe_content).classes('w-full prose dark:prose-invert text-gray-100 min-h-[1.5em] break-words')
        else:
            if not display_content and not thinking and not tool_calls:
                 # Init placeholder
                 content_markdown = ui.label('...').classes('text-gray-500 italic')
            else:
                # Regular content styling
                if role == 'user':
                    ui.label(display_content).classes('text-base px-5 py-3 rounded-2xl bg-[#27272a] text-white max-w-full break-words whitespace-pre-wrap')
                else:
                    # Fallback
                    safe_content = display_content.replace('<', '&lt;')
                    content_markdown = ui.markdown(safe_content).classes('w-full prose dark:prose-invert text-gray-100')

        # 3.5 Stats (Assistant only)
        stats_container = None
        if role == 'assistant':
            stats_container = ui.row().classes('w-full items-center gap-3 text-[10px] text-gray-500 font-mono mt-1 border-t border-white/5 pt-1.5 opacity-60 hover:opacity-100 transition-opacity')
            self._render_stats_content(stats_container, msg.get('stats'))
            if not msg.get('stats'):
                stats_container.classes('hidden')

        # 4. Ratings (Assistant only)
        if role == 'assistant' and self.get_ratings:
            self._render_ratings(msg)

        # Store references for streaming updates
        self._msg_elements[msg_id] = {
            'thinking_container': thinking_container,
            'thinking_label': thinking_label,
            'tools': tool_container,
            'content': content_markdown,
            'stats_container': stats_container
        }

    def _render_tool_call(self, tc: Dict):
        fname = tc.get('function', {}).get('name', 'unknown')
        try:
             args = tc.get('function', {}).get('arguments', '')
        except:
             args = '...'
        ui.label(f"🔧 Call: {fname}").classes('text-xs font-mono text-orange-300 font-bold')
        ui.label(str(args)).classes('text-xs font-mono text-orange-200/70 pl-4 whitespace-pre-wrap break-all')

    def _render_ratings(self, msg: Dict):
        ratings = self.get_ratings(msg['id'])
        if ratings:
            with ui.row().classes('gap-2 mt-2'):
                for r in ratings:
                    with ui.row().classes('items-center gap-1 bg-yellow-400/10 px-2 py-1 rounded border border-yellow-400/20'):
                         ui.label(f"{r.tag}: {r.rating}★").classes('text-xs font-bold text-yellow-400')
                         if self.on_delete_rating:
                             ui.icon('close', size='xs').classes('text-yellow-400/50 cursor-pointer hover:text-red-400').on('click', lambda _, m=msg, t=r.tag: self.on_delete_rating(m, t))
        
        if self.on_rate:
             with ui.row().classes('items-center gap-2 mt-2 opacity-50 hover:opacity-100 transition-opacity'):
                 # Tag Selector
                 tag_select = ui.select(self.available_tags, value=self.available_tags[0], label='Tag').props('dense options-dense borderless behavior=menu').classes('w-24 text-xs')
                 
                 # Stars
                 for i in range(1, 6):
                     ui.icon('star_border').classes('cursor-pointer hover:text-yellow-400').on('click', lambda _, r=i, m=msg, t=tag_select: self.on_rate(m, r, t.value))

    def _render_stats_content(self, container: ui.element, stats: Optional[Dict]):
        if not stats:
            return
            
        total_duration_ns = stats.get('total_duration', 0)
        load_duration_ns = stats.get('load_duration', 0)
        prompt_eval_count = stats.get('prompt_eval_count', 0)
        prompt_eval_duration_ns = stats.get('prompt_eval_duration', 0)
        eval_count = stats.get('eval_count', 0)
        eval_duration_ns = stats.get('eval_duration', 0)
        
        # Convert nanoseconds to seconds
        total_sec = total_duration_ns / 1e9 if total_duration_ns else 0
        load_sec = load_duration_ns / 1e9 if load_duration_ns else 0
        prompt_sec = prompt_eval_duration_ns / 1e9 if prompt_eval_duration_ns else 0
        eval_sec = eval_duration_ns / 1e9 if eval_duration_ns else 0
        
        # Compute rates
        eval_tps = eval_count / eval_sec if (eval_count and eval_sec) else 0
        prompt_tps = prompt_eval_count / prompt_sec if (prompt_eval_count and prompt_sec) else 0
        
        with container:
            def stats_item(icon_name, text, tooltip_text, icon_color_class='text-indigo-400'):
                with ui.row().classes('items-center gap-1 bg-white/5 px-2 py-0.5 rounded border border-white/10 hover:bg-white/10 transition-colors') as item:
                    ui.icon(icon_name, size='14px').classes(icon_color_class)
                    ui.label(text).classes('text-[10px] text-gray-300 font-medium')
                    if tooltip_text:
                        item.tooltip(tooltip_text)

            # 1. Total Time
            if total_sec > 0:
                stats_item(
                    icon_name='schedule',
                    text=f"{total_sec:.2f}s",
                    tooltip_text=f"Total time. Model load: {load_sec:.2f}s, Prompt eval: {prompt_sec:.2f}s, Response gen: {eval_sec:.2f}s",
                    icon_color_class='text-amber-400'
                )
            
            # 2. Token generation speed (t/s)
            if eval_tps > 0:
                stats_item(
                    icon_name='speed',
                    text=f"{eval_tps:.1f} t/s",
                    tooltip_text=f"Response generation speed: {eval_count} tokens generated in {eval_sec:.2f}s",
                    icon_color_class='text-emerald-400'
                )
                
            # 3. Token counts (prompt + response)
            if prompt_eval_count > 0 or eval_count > 0:
                total_tokens = prompt_eval_count + eval_count
                stats_item(
                    icon_name='toll',
                    text=f"{total_tokens} tkn",
                    tooltip_text=f"Tokens - Prompt: {prompt_eval_count} ({prompt_tps:.1f} t/s), Response: {eval_count}",
                    icon_color_class='text-blue-400'
                )

    async def update_message(self, msg_id: str, content: str, thinking: str, tool_calls: List[Dict], stats: Optional[Dict] = None):
        """
        Updates the displayed content of a message.
        Expected to be used during streaming.
        """
        elements = self._msg_elements.get(msg_id)
        if not elements:
            return 

        # Update Content
        if elements['content']:
            if isinstance(elements['content'], ui.markdown):
                # Escaping < to prevent HTML injection
                elements['content'].content = content.replace('<', '&lt;')
                elements['content'].update()
            elif isinstance(elements['content'], ui.label):
                elements['content'].text = content
                elements['content'].update()
            
        # Update Thinking
        if thinking:
            if elements.get('thinking_container'):
                 elements['thinking_container'].classes(remove='hidden')
                 # NiceGUI Expansion handles visibility
            if elements.get('thinking_label'):
                 elements['thinking_label'].text = thinking
                 elements['thinking_label'].update()
        
        # Update Tools
        if tool_calls and elements['tools']:
             elements['tools'].classes(remove='hidden')
             elements['tools'].clear()
             with elements['tools']:
                 for tc in tool_calls:
                     self._render_tool_call(tc)
             elements['tools'].update()

        # Update Stats
        if stats and elements.get('stats_container'):
             elements['stats_container'].classes(remove='hidden')
             elements['stats_container'].clear()
             with elements['stats_container']:
                 self._render_stats_content(elements['stats_container'], stats)
             elements['stats_container'].update()

