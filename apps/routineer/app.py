import os
import json
import uuid
from datetime import datetime, timedelta
from nicegui import ui
from apps.utils import load_app_data, save_app_data, set_app_badge

DEFAULT_DATA = {
    "routines": [
        {
            "id": str(uuid.uuid4()),
            "name": "Drink Water",
            "description": "Drink at least 8 glasses of water",
            "frequency": "daily",
            "created_at": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Walk",
            "description": "30 minutes brisk walk",
            "frequency": "daily",
            "created_at": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Stretch",
            "description": "10 minutes of stretching",
            "frequency": "daily",
            "created_at": datetime.now().strftime("%Y-%m-%d")
        }
    ],
    "history": []
}

def load_data():
    return load_app_data('routineer', 'routineer.json', DEFAULT_DATA)

def save_data(data):
    save_app_data('routineer', 'routineer.json', data)

def is_due_today(routine, today_str):
    freq = routine.get('frequency', 'daily')
    created_at_str = routine.get('created_at', today_str)
    try:
        created_at = datetime.strptime(created_at_str, "%Y-%m-%d")
        today = datetime.strptime(today_str, "%Y-%m-%d")
    except ValueError:
        return True
        
    days_diff = (today - created_at).days
    if days_diff < 0:
        return False
        
    if freq == 'daily':
        return True
    elif freq == 'weekly':
        return days_diff % 7 == 0
    elif freq == 'monthly':
        return today.day == created_at.day
    return False

def render():
    data = load_data()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    with ui.column().classes('w-full max-w-5xl mx-auto gap-8'):
        
        with ui.row().classes('w-full justify-between items-center'):
            ui.label('Routineer').classes('text-4xl font-extrabold text-indigo-400 tracking-tight')
            ui.button('Add Routine', icon='add', on_click=lambda: open_add_dialog()).classes('bg-indigo-600 text-white rounded-full px-4 py-2 hover:bg-indigo-700 transition').props('no-caps')
                
        # Main content row
        with ui.row().classes('w-full gap-6 flex-wrap items-start'):
            
            # Left Column
            with ui.column().classes('flex-1 min-w-[300px] gap-6'):
                # Today's Routines
                with ui.card().classes('w-full rounded-2xl border border-white/10 glass-panel shadow-lg p-6 bg-slate-900/50'):
                    ui.label("Today's Routines").classes('text-2xl font-bold mb-4 text-white')
                    today_container = ui.column().classes('w-full gap-3')
                    
            # Right Column
            with ui.column().classes('flex-1 min-w-[300px] gap-6'):
                # Stats (Calendar)
                with ui.card().classes('w-full rounded-2xl border border-white/10 glass-panel shadow-lg p-6 bg-slate-900/50'):
                    ui.label('Stats (Last 7 Days)').classes('text-2xl font-bold mb-4 text-white')
                    stats_container = ui.column().classes('w-full')
                    
                # All Routines Management
                with ui.card().classes('w-full rounded-2xl border border-white/10 glass-panel shadow-lg p-6 bg-slate-900/50'):
                    ui.label('Manage Routines').classes('text-2xl font-bold mb-4 text-white')
                    routines_container = ui.column().classes('w-full gap-3')

    # DIALOGS AND FUNCTIONS
    dialog = ui.dialog()
    with dialog, ui.card().classes('p-6 min-w-[400px] rounded-2xl bg-slate-800 border border-white/10'):
        dialog_title = ui.label('Add New Routine').classes('text-2xl font-bold mb-4 text-indigo-300')
        name_input = ui.input('Name').classes('w-full mb-2').props('outlined')
        desc_input = ui.textarea('Description').classes('w-full mb-2').props('outlined')
        freq_select = ui.select(['daily', 'weekly', 'monthly'], value='daily', label='Frequency').classes('w-full mb-4').props('outlined')
        edit_id = {'id': None}
        
        def save_routine():
            if not name_input.value:
                ui.notify('Name is required', type='negative')
                return
            if edit_id['id']:
                # Edit
                for r in data['routines']:
                    if r['id'] == edit_id['id']:
                        r['name'] = name_input.value
                        r['description'] = desc_input.value
                        r['frequency'] = freq_select.value
                        break
            else:
                # Add
                data['routines'].append({
                    "id": str(uuid.uuid4()),
                    "name": name_input.value,
                    "description": desc_input.value,
                    "frequency": freq_select.value,
                    "created_at": datetime.now().strftime("%Y-%m-%d")
                })
            save_data(data)
            dialog.close()
            refresh_ui()
            ui.notify('Routine saved successfully!', type='positive')
            
        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Cancel', on_click=dialog.close).classes('text-gray-400').props('flat')
            ui.button('Save', on_click=save_routine).classes('bg-indigo-600 text-white rounded')

    def open_add_dialog():
        dialog_title.set_text('Add New Routine')
        name_input.value = ''
        desc_input.value = ''
        freq_select.value = 'daily'
        edit_id['id'] = None
        dialog.open()
        
    def open_edit_dialog(routine):
        dialog_title.set_text('Edit Routine')
        name_input.value = routine.get('name', '')
        desc_input.value = routine.get('description', '')
        freq_select.value = routine.get('frequency', 'daily')
        edit_id['id'] = routine['id']
        dialog.open()

    def delete_routine(routine_id):
        data['routines'] = [r for r in data['routines'] if r['id'] != routine_id]
        data['history'] = [h for h in data['history'] if h['routine_id'] != routine_id]
        save_data(data)
        refresh_ui()
        ui.notify('Routine deleted', type='info')

    def toggle_today(routine_id, checked):
        data['history'] = [h for h in data['history'] if not (h['routine_id'] == routine_id and h['date'] == today_str)]
        if checked:
            data['history'].append({
                "routine_id": routine_id,
                "date": today_str,
                "status": "done"
            })
        save_data(data)
        refresh_stats()
        
        # Update badge
        due_routines = [r for r in data['routines'] if is_due_today(r, today_str)]
        left_count = sum(1 for r in due_routines if not any(h['routine_id'] == r['id'] and h['date'] == today_str and h['status'] == 'done' for h in data['history']))
        set_app_badge('routineer', left_count)

    def refresh_ui():
        today_container.clear()
        routines_container.clear()
        
        due_routines = [r for r in data['routines'] if is_due_today(r, today_str)]
        
        left_count = sum(1 for r in due_routines if not any(h['routine_id'] == r['id'] and h['date'] == today_str and h['status'] == 'done' for h in data['history']))
        set_app_badge('routineer', left_count)
        
        with today_container:
            if not due_routines:
                ui.label("No routines due today! Enjoy your day!").classes('text-gray-400 italic')
            else:
                for r in due_routines:
                    is_done = any(h['routine_id'] == r['id'] and h['date'] == today_str and h['status'] == 'done' for h in data['history'])
                    with ui.row().classes('w-full flex-nowrap items-center justify-between p-3 rounded-xl bg-white/5 hover:bg-white/10 transition'):
                        with ui.column().classes('gap-0 flex-1 min-w-0 pr-4'):
                            ui.label(r['name']).classes(f'text-lg font-semibold {"line-through text-gray-500" if is_done else "text-white"}')
                            if r.get('description'):
                                ui.label(r['description']).classes('text-sm text-gray-400')
                        ui.checkbox(value=is_done, on_change=lambda e, rid=r['id']: toggle_today(rid, e.value)).classes('scale-125 ml-4')

        with routines_container:
            if not data['routines']:
                ui.label("No routines added yet.").classes('text-gray-400 italic')
            else:
                for r in data['routines']:
                    with ui.row().classes('w-full items-center justify-between p-3 rounded-xl bg-white/5 group'):
                        with ui.column().classes('gap-0 flex-1'):
                            ui.label(r['name']).classes('font-medium text-white')
                            ui.label(f"{r.get('frequency', 'daily').capitalize()}").classes('text-xs text-indigo-300')
                        with ui.row().classes('gap-2 opacity-0 group-hover:opacity-100 transition'):
                            ui.button(icon='edit', on_click=lambda r=r: open_edit_dialog(r)).classes('text-blue-400').props('flat round size=sm')
                            ui.button(icon='delete', on_click=lambda rid=r['id']: delete_routine(rid)).classes('text-red-400').props('flat round size=sm')

        refresh_stats()
        
    def refresh_stats():
        stats_container.clear()
        days = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
        days_names = [(datetime.now() - timedelta(days=i)).strftime("%a") for i in range(6, -1, -1)]
        
        with stats_container:
            with ui.grid(columns=7).classes('w-full gap-2 text-center'):
                for name in days_names:
                    ui.label(name).classes('text-xs text-gray-400 font-medium')
                
                for d in days:
                    due_count = sum(1 for r in data['routines'] if is_due_today(r, d))
                    done_count = sum(1 for h in data['history'] if h['date'] == d and h['status'] == 'done')
                    
                    if due_count == 0:
                        color_class = 'bg-gray-800 border-gray-700'
                    elif done_count == 0:
                        color_class = 'bg-red-900/50 border-red-800'
                    elif done_count < due_count:
                        color_class = 'bg-yellow-900/50 border-yellow-800'
                    else:
                        color_class = 'bg-green-600 border-green-500 shadow-[0_0_10px_rgba(34,197,94,0.3)]'
                        
                    is_today = (d == today_str)
                    border = 'border-2 border-indigo-400' if is_today else 'border'
                    
                    with ui.column().classes(f'aspect-square rounded-lg {color_class} {border} items-center justify-center p-1 relative group cursor-help transition hover:scale-105'):
                        if due_count > 0:
                            ui.label(f"{done_count}/{due_count}").classes('text-xs font-bold text-white')
                        else:
                            ui.label("-").classes('text-xs text-gray-500')
                            
                        with ui.tooltip().classes('bg-slate-800 text-white p-2 rounded text-xs whitespace-nowrap'):
                            ui.label(f"Date: {d}")
                            if due_count > 0:
                                ui.label(f"Completed: {done_count} of {due_count} routines")
                            else:
                                ui.label("No routines due")
                                
    refresh_ui()
