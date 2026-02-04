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
        self.get_ratings = get_ratings
        self.available_tags = available_tags
        self.show_avatars = show_avatars
        
        # Track components for streaming updates
        self._msg_elements: Dict[str, Dict[str, Any]] = {}

    def clear(self):
        self.container.clear()
        self._msg_elements.clear()

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

                    # Message Body
                    if msg.get('editing', False):
                        self._render_edit_mode(msg)
                    else:
                        self._render_view_mode(msg)

    def _render_controls(self, msg: Dict):
        if not (self.on_edit or self.on_delete):
            return
            
        with ui.row().classes('opacity-0 group-hover:opacity-100 transition-opacity gap-1'):
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
        # Always create label, hidden if empty
        thinking_label = ui.label(thinking).classes('text-xs text-gray-400 font-mono bg-white/5 p-3 rounded-md border-l-2 border-indigo-500 whitespace-pre-wrap w-full')
        if not thinking:
            thinking_label.classes('hidden')
        
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
        content_markdown = None
        
        if role == 'tool':
            ui.label(f"Tool Output: {msg.get('name', 'unknown')}").classes('text-xs text-gray-500 font-bold')
            ui.label(content).classes('text-xs font-mono bg-white/5 p-2 rounded text-gray-300 whitespace-pre-wrap')
        elif role == 'assistant':
            # Always use markdown for assistant to ensure streaming updates work correctly with correct styling
            # Escaping < to prevent HTML injection (style/script) while keeping markdown functional
            safe_content = content.replace('<', '&lt;')
            content_markdown = ui.markdown(safe_content).classes('w-full prose dark:prose-invert text-gray-100 min-h-[1.5em] break-words')
        else:
            if not content and not thinking and not tool_calls:
                 # Init placeholder
                 content_markdown = ui.label('...').classes('text-gray-500 italic')
            else:
                # Regular content styling
                if role == 'user':
                    ui.label(content).classes('text-base px-5 py-3 rounded-2xl bg-[#27272a] text-white max-w-full break-words whitespace-pre-wrap')
                else:
                    # Fallback
                    safe_content = content.replace('<', '&lt;')
                    content_markdown = ui.markdown(safe_content).classes('w-full prose dark:prose-invert text-gray-100')

        # 4. Ratings (Assistant only)
        if role == 'assistant' and self.get_ratings:
            self._render_ratings(msg)

        # Store references for streaming updates
        self._msg_elements[msg_id] = {
            'thinking': thinking_label,
            'tools': tool_container,
            'content': content_markdown
        }

    def _render_tool_call(self, tc: Dict):
        fname = tc.get('function', {}).get('name', 'unknown')
        try:
             args = tc.get('function', {}).get('arguments', '')
        except:
             args = '...'
        ui.label(f"🔧 Call: {fname}").classes('text-xs font-mono text-orange-300 font-bold')
        ui.label(str(args)).classes('text-xs font-mono text-orange-200/70 truncate pl-4')

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

    async def update_message(self, msg_id: str, content: str, thinking: str, tool_calls: List[Dict]):
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
            if elements['thinking']:
                 elements['thinking'].text = thinking
                 elements['thinking'].classes(remove='hidden')
                 elements['thinking'].update()
        
        # Update Tools
        if tool_calls and elements['tools']:
             elements['tools'].classes(remove='hidden')
             elements['tools'].clear()
             with elements['tools']:
                 for tc in tool_calls:
                     self._render_tool_call(tc)
             elements['tools'].update()

