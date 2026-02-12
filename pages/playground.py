from nicegui import ui
import urllib.parse

# Constants
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Canvas Game Environment</title>
    <style>
        /* Ensure the body and html take up 100% height and remove margins */
        body, html {
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            overflow: hidden; /* Prevents scrollbars during gameplay */
            background-color: #000; /* Standard game backdrop */
        }

        /* Make the canvas behave as a block element to avoid whitespace issues */
        canvas {
            display: block;
        }
    </style>
</head>
<body>

    <canvas id="gameCanvas"></canvas>

    <script>
        /** @type {HTMLCanvasElement} */
        const canvas = document.getElementById('gameCanvas');
        const ctx = canvas.getContext('2d');

        // Function to scale canvas to the current window size
        function resizeCanvas() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            
            // Re-render or notify game engine of resize here if necessary
        }

        // Initialize size and listen for window resizing
        window.addEventListener('resize', resizeCanvas);
        resizeCanvas();

        // --- USER CUSTOM JS CODE START ---
        {user_js}
        // --- USER CUSTOM JS CODE END ---
    </script>
</body>
</html>
"""

DEFAULT_JS = """
const GRID_SIZE = 50;
const TEAM = ['#2222AA', '#AA2222']
const PLAYER_SIZE = 20;

let players = [[], []]; 

// 2. Use Math.floor to ensure we stay within the grid bounds
const GRID_MAX_X = Math.floor(canvas.width / GRID_SIZE);
const GRID_MAX_Y = Math.floor(canvas.height / GRID_SIZE);

// 3. Helper for random integers
const randomInt = (max) => Math.floor(Math.random() * max);

// 4. Spawn logic
for (let t = 0; t < 2; t++) {
    for (let i = 0; i < 3; i++) {
        players[t][i] = {
            x: randomInt(GRID_MAX_X), 
            y: randomInt(GRID_MAX_Y)
        };
    }
}

let grid_x = -1;
let grid_y = -1;

function drawGrid() {
    ctx.beginPath();
    ctx.strokeStyle = '#AAA'; // Subtle dark grey for grid lines
    ctx.lineWidth = 1;

    // Draw vertical lines
    for (let x = 0; x <= canvas.width; x += GRID_SIZE) {
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvas.height);
    }

    // Draw horizontal lines
    for (let y = 0; y <= canvas.height; y += GRID_SIZE) {
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
    }

    ctx.stroke();
}

function drawPlayers() {
    for (let t = 0; t < 2; t++) {
        ctx.fillStyle = TEAM[t];
        for (let i = 0; i < 3; i++){
            let x = players[t][i].x * GRID_SIZE + GRID_SIZE/2;
            let y = players[t][i].y * GRID_SIZE + GRID_SIZE/2;
            ctx.beginPath();
            ctx.arc(x, y, PLAYER_SIZE/2, 0, Math.PI * 2);
            ctx.fill();
        }
    }
}

function animate() {
    // 1. Clear the screen
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // 2. Draw the background grid
    drawGrid();
    drawPlayers();

    // 3. User Game Logic (Example: Mouse Follower)
    drawUserExample();

    requestAnimationFrame(animate);
}

// --- Example Interaction Logic ---
let mouse = { x: 0, y: 0 };
window.addEventListener('mousemove', (e) => {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
    grid_x = Math.floor(mouse.x / GRID_SIZE);
    grid_y = Math.floor(mouse.y / GRID_SIZE);
});

window.addEventListener('mousedown', (e) => {
    let found = false;
    let t, i;
    for (t = 0; t < 2; t++) {
        for (i = 0; i < 3; i++) {
            if (grid_x==players[t][i].x && grid_y==players[t][i].y) {
                found = true;
                break;
            }
        }
        if (found) break;
    }
    if (found) {
        console.log('found: '+t+','+i);
    }
});

function drawUserExample() {
    const snapX = grid_x * GRID_SIZE;
    const snapY = grid_y * GRID_SIZE;
    
    ctx.fillStyle = '#55555577';
    ctx.fillRect(snapX, snapY, GRID_SIZE, GRID_SIZE);
}

animate();
"""

# State - JS content persists across navigation
js_code = DEFAULT_JS

def create_page():
    
    # Logic
    def update_preview(e):
        global js_code
        js_code = e.value
        full_html = HTML_TEMPLATE.replace("{user_js}", js_code)
        preview.run_method('setAttribute', 'srcdoc', full_html)

    # Layout
    with ui.column().classes('w-full h-[calc(100vh-4rem)] pt-4 px-4 max-w-[100%] mx-auto'):

        with ui.grid(columns=2).classes('w-full h-full gap-4'):
            # Left Column: Code Editor
            with ui.card().classes('w-full h-full glass-panel flex flex-col p-0 overflow-hidden'):

                editor = ui.codemirror(value=js_code, on_change=update_preview, language='JavaScript').classes('w-full flex-grow font-mono text-sm')
                editor.props('theme=dracula')

                # Helper functions for toolbar
                async def handle_upload(e):
                    try:
                        # e.file is the file object, read() is async and returns bytes
                        bytes_content = await e.file.read()
                        
                        # Try to decode as utf-8, fallback to latin-1
                        try:
                            content = bytes_content.decode('utf-8')
                        except UnicodeDecodeError:
                            content = bytes_content.decode('latin-1')
                        
                        # Update global state
                        global js_code
                        js_code = content
                        
                        # Update Editor and Preview
                        editor.value = content # Direct property update is more reliable
                        update_preview(type("Event", (), {"value": content})) 
                        
                        open_dialog.close()
                        ui.notify('File loaded successfully', type='success')
                    except Exception as err:
                        ui.notify(f'Failed to open file: {str(err)}', type='negative')

                def save_file():
                    # Get current content from global or editor
                    current_content = js_code
                    ui.download(current_content.encode('utf-8'), 'game.js')

                def run_tab():
                    # Use JS to open new window and write content to avoid data: URL restrictions
                    full_html = HTML_TEMPLATE.replace("{user_js}", js_code)
                    encoded = urllib.parse.quote(full_html)
                    ui.run_javascript(f'''
                        const win = window.open("", "_blank");
                        win.document.write(decodeURIComponent("{encoded}"));
                        win.document.close();
                    ''')

                # Open File Dialog
                with ui.dialog() as open_dialog, ui.card().classes('glass-panel p-6 w-96'):
                    ui.label('Select JS File').classes('text-lg font-bold mb-4 text-center w-full')
                    # Use a cleaner upload appearance
                    ui.upload(on_upload=handle_upload, auto_upload=True, label='Choose File').props('accept=.js,.txt max-files=1 color=primary flat').classes('w-full')
                    ui.button('Cancel', on_click=open_dialog.close).props('flat color=grey').classes('w-full mt-2')

                # Toolbar
                with ui.row().classes('w-full p-2 gap-2 bg-white/5 border-t border-white/10 items-center justify-between'):
                    with ui.row().classes('gap-2 items-center flex-grow'):
                         ui.button(icon='folder_open', on_click=open_dialog.open).props('flat dense color=primary').tooltip('Open File')
                         ui.button(icon='save', on_click=save_file).props('flat dense color=primary').tooltip('Save File')
                         
                         ui.separator().props('vertical').classes('mx-2 h-8')
                         
                         prompt_input = ui.input(placeholder='Ask AI to edit...').classes('flex-grow').props('dense outlined rounded input-class=text-white')
                         ui.button(icon='send').props('flat dense color=secondary').tooltip('Submit Request')

                    ui.button(icon='open_in_new', on_click=run_tab).props('flat dense color=secondary').tooltip('Run in New Tab')

            # Right Column: Preview
            with ui.card().classes('w-full h-full glass-panel flex flex-col p-0 overflow-hidden bg-black'):

                # Use a specific container for the HTML preview to control its environment slightly better if needed
                with ui.element('div').classes('w-full h-full p-0 overflow-hidden bg-black') as preview_container:
                     preview = ui.element('iframe').classes('w-full h-full border-none')
                     # Set initial content safely
                     initial_html = HTML_TEMPLATE.replace("{user_js}", js_code)
                     ui.timer(0.1, lambda: preview.run_method('setAttribute', 'srcdoc', initial_html), once=True)
