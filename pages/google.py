from nicegui import ui, run
from services.google_service import google_service
import asyncio

def create_page():
    # Helper to refresh the entire dashboard content
    def refresh_dashboard():
        content_container.clear()
        with content_container:
            render_dashboard_content()
        update_account_selector()

    # Helper to switch account
    def switch_account(acc_id):
        google_service.set_current_account(acc_id)
        refresh_dashboard()

    # Helper to add account with async offload
    async def add_new_account():
        # Clean current container and show loading state
        # But we can't easily overlay unless we use a dialog. 
        # Using a spinner notification.
        n = ui.notification('Waiting for Google Login...', timeout=None, spinner=True)
        try:
            # Run blocking flow in executor to not freeze UI
            # Note: run_local_server opens browser on server side (local machine)
            new_acc = await run.io_bound(google_service.add_account)
            n.dismiss()
            if new_acc:
                ui.notify(f"Added {new_acc['email']}", type='positive')
                refresh_dashboard()
            else:
                ui.notify("Login failed or cancelled", type='warning')
        except Exception as e:
            n.dismiss()
            ui.notify(f"Error: {e}", type='negative')

    # Email Dialog
    async def open_email_dialog(message_id):
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-3xl h-[80vh] p-0 bg-[#1e1f20] border border-white/10 flex flex-col'):
            content_area = ui.column().classes('w-full h-full p-6 flex flex-col')
            with content_area:
                 ui.spinner('dots', size='lg').classes('self-center my-auto text-primary')
        dialog.open()

        # Fetch details in background
        details = await run.io_bound(google_service.get_email_details, message_id)
        
        content_area.clear()
        with content_area:
            if details:
                 with ui.row().classes('w-full justify-between items-start mb-4'):
                     with ui.column().classes('gap-1'):
                         ui.label(details['subject']).classes('text-xl font-bold text-gray-200 list-disc')
                         ui.label(f"From: {details['sender']}").classes('text-sm text-gray-400')
                         ui.label(details['date']).classes('text-xs text-gray-500')
                     ui.button(icon='close', on_click=dialog.close).props('flat round dense color=grey')
                 
                 ui.separator().classes('bg-white/10 mb-4')
                 
                 with ui.scroll_area().classes('flex-1 w-full'):
                     if details.get('is_html'):
                         # Wrap in a white container because most emails assume a white background
                         # and add padding for readability.
                         with ui.element('div').classes('w-full bg-white text-black p-4 rounded'):
                             ui.html(details['body'], sanitize=False)
                     else:
                         ui.label(details['body']).classes('text-gray-300 whitespace-pre-wrap font-sans')
            else:
                 with ui.column().classes('w-full h-full items-center justify-center'):
                    ui.icon('error', size='lg').classes('text-red-400 mb-2')
                    ui.label('Failed to load email details.').classes('text-red-400')
                    ui.button('Close', on_click=dialog.close).classes('mt-4')

    # Account Selector Component
    def update_account_selector():
        account_row.clear()
        current = google_service.get_current_account()
        accounts = google_service.get_accounts()
        
        with account_row:
            if not current and not accounts:
                ui.button('Sign in with Google', on_click=add_new_account).props('icon=login color=secondary')
                return

            if not current and accounts:
                # Should set current if existing, but handled in service usually.
                pass

            # Current Account Display
            if current:
                with ui.row().classes('items-center gap-2 cursor-pointer bg-white/5 px-3 py-1 rounded-full hover:bg-white/10 transition-colors'):
                    # Avatar handling
                    if current['avatar'].startswith('http'):
                        ui.image(current['avatar']).classes('w-6 h-6 rounded-full')
                    else:
                        ui.icon(current['avatar'], size='sm').classes('text-gray-300')
                    
                    ui.label(current['email']).classes('text-sm text-gray-300')
                    ui.icon('arrow_drop_down', size='sm').classes('text-gray-400')
                    
                    with ui.menu().classes('bg-[#1e1f20] border border-white/10'):
                        for acc in accounts:
                            ui.menu_item(acc['name'], on_click=lambda _, i=acc['id']: switch_account(i))
                        ui.separator()
                        ui.menu_item('Add another account', on_click=add_new_account).props('icon=add')

    # Main Layout
    with ui.column().classes('w-full h-[calc(100vh-4rem)] p-6 gap-6'):
        
        # Header Row
        with ui.row().classes('w-full justify-between items-center'):
            ui.label('Google Dashboard').classes('text-3xl font-bold text-gray-200')
            account_row = ui.row().classes('items-center')
            update_account_selector()

        # Content Area (3 Columns)
        content_container = ui.row().classes('w-full h-full gap-6 items-start')
        
        def render_dashboard_content():
            current = google_service.get_current_account()
            if not current:
                with ui.column().classes('w-full h-full items-center justify-center'):
                    ui.icon('lock', size='48px').classes('text-gray-600 mb-4')
                    ui.label('Sign in to view your dashboard').classes('text-xl text-gray-500')
                    ui.button('Sign in', on_click=add_new_account).classes('mt-4')
                return

            # 1. Gmail Column
            with ui.column().classes('flex-1 h-full bg-[#1e1f20] border border-white/10 rounded-xl overflow-hidden flex flex-col'):
                # Header
                with ui.row().classes('w-full p-4 border-b border-white/10 items-center justify-between'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('mail', size='sm').classes('text-red-400')
                        ui.label('Gmail').classes('text-lg font-semibold')
                    ui.button(icon='refresh', on_click=refresh_dashboard).props('flat round dense size=sm color=grey')
                
                # List
                with ui.scroll_area().classes('flex-1 w-full p-2'):
                    emails = google_service.get_gmail_data()
                    if not emails:
                         ui.label('No emails found').classes('text-gray-500 p-4 w-full text-center')

                    for email in emails:
                        with ui.column().classes('w-full p-2 hover:bg-white/5 rounded-lg transition-colors gap-0 cursor-pointer mb-1').on('click', lambda _, i=email['id']: open_email_dialog(i)):
                            with ui.row().classes('w-full justify-between items-center'):
                                ui.label(email['sender']).classes('text-xs text-gray-400 truncate pr-2')
                                ui.label(email['time']).classes('text-xs text-gray-500 flex-shrink-0')
                            ui.label(email['subject']).classes('text-sm font-bold text-gray-200 truncate w-full')

            # 2. YouTube Column
            with ui.column().classes('flex-1 h-full bg-[#1e1f20] border border-white/10 rounded-xl overflow-hidden flex flex-col'):
                # Header
                with ui.row().classes('w-full p-4 border-b border-white/10 items-center gap-2'):
                    ui.icon('smart_display', size='sm').classes('text-red-500')
                    ui.label('YouTube').classes('text-lg font-semibold')
                
                # List
                with ui.scroll_area().classes('flex-1 w-full p-2'):
                    videos = google_service.get_youtube_data()
                    if not videos:
                         ui.label('No recent videos').classes('text-gray-500 p-4 w-full text-center')

                    for video in videos:
                        with ui.row().classes('w-full p-2 hover:bg-white/5 rounded-lg transition-colors gap-3 cursor-pointer mb-1 items-start'):
                            # Thumbnail
                            if video.get('thumbnail'):
                                ui.image(video['thumbnail']).classes('w-24 h-auto rounded flex-shrink-0')
                            else:
                                ui.element('div').classes(f'w-24 h-14 rounded {video.get("color", "bg-gray-700")} flex-shrink-0')
                            
                            with ui.column().classes('gap-0 flex-1 min-w-0'):
                                ui.label(video['title']).classes('text-sm font-medium text-gray-200 leading-tight mb-1 line-clamp-2')
                                ui.label(video['channel']).classes('text-xs text-gray-400')
                                ui.label(video.get('views', '')).classes('text-xs text-gray-500')

            # 3. Drive Column
            with ui.column().classes('flex-1 h-full bg-[#1e1f20] border border-white/10 rounded-xl overflow-hidden flex flex-col'):
                # Header
                with ui.row().classes('w-full p-4 border-b border-white/10 items-center gap-2'):
                    ui.icon('add_to_drive', size='sm').classes('text-blue-400')
                    ui.label('Drive').classes('text-lg font-semibold')
                
                # List
                with ui.scroll_area().classes('flex-1 w-full p-2'):
                    files = google_service.get_drive_data()
                    if not files:
                         ui.label('No files found').classes('text-gray-500 p-4 w-full text-center')

                    with ui.grid().classes('grid-cols-1 w-full gap-2'):
                        for file in files:
                            with ui.row().classes('w-full p-3 hover:bg-white/5 rounded-lg transition-colors items-center gap-3 cursor-pointer'):
                                with ui.element('div').classes('p-2 bg-white/5 rounded-full'):
                                    ui.icon(file['icon']).classes(f'{file["color"]}')
                                
                                with ui.column().classes('gap-0 flex-1'):
                                    ui.label(file['name']).classes('text-sm text-gray-200')
                                    ui.label(f"Modified {file['modified']}").classes('text-xs text-gray-500')
                                    
                                ui.button(icon='more_vert').props('flat round dense size=sm color=grey')

        # Initial Render
        with content_container:
            render_dashboard_content()
