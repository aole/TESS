from nicegui import ui
import urllib.parse
import os

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

BOILERPLATE_JS = """/* 
    Welcome to the Canvas Playground!
    
    Available assignments:
    - canvas: HTMLCanvasElement (id="gameCanvas")
    - ctx: CanvasRenderingContext2D
    - resizeCanvas(): Call to reset canvas to full window size
    
    Your code is automatically saved to data/playground/canvas.js
*/

// Example: Bouncing Box
let x = 100, y = 100;
let dx = 4, dy = 4;
const size = 50;

function animate() {
    // Clear with slight fade effect
    ctx.fillStyle = 'rgba(0,0,0,0.1)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Update
    x += dx;
    y += dy;
    
    if(x + size > canvas.width || x < 0) dx = -dx;
    if(y + size > canvas.height || y < 0) dy = -dy;
    
    // Draw
    ctx.fillStyle = '#00ff00';
    ctx.fillRect(x, y, size, size);
    
    requestAnimationFrame(animate);
}

animate();
"""

CANVAS_FILE = 'data/playground/canvas.js'

def load_js_code():
    if not os.path.exists(CANVAS_FILE):
        try:
            os.makedirs(os.path.dirname(CANVAS_FILE), exist_ok=True)
            with open(CANVAS_FILE, 'w', encoding='utf-8') as f:
                f.write(BOILERPLATE_JS)
            return BOILERPLATE_JS
        except Exception as e:
            print(f"Error creating default canvas file: {e}")
            return BOILERPLATE_JS

    try:
        with open(CANVAS_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return BOILERPLATE_JS

js_code = load_js_code()

def create_page():
    
    # Logic
    def update_preview(e):
        global js_code
        js_code = e.value
        
        # Save to file
        with open(CANVAS_FILE, 'w', encoding='utf-8') as f:
            f.write(js_code)
            
        full_html = HTML_TEMPLATE.replace("{user_js}", js_code)
        preview.run_method('setAttribute', 'srcdoc', full_html)

    # Layout
    with ui.column().classes('w-full h-[calc(100vh-4rem)] pt-4 px-4 max-w-[100%] mx-auto'):

        with ui.grid(columns=2).classes('w-full h-full gap-4'):
            # Left Column: Code Editor
            with ui.card().classes('w-full h-full glass-panel flex flex-col p-0 overflow-hidden'):

                editor = ui.codemirror(value=js_code, on_change=update_preview, language='JavaScript').classes('w-full flex-grow font-mono text-sm')
                editor.props('theme=dracula')

                def run_tab():
                    # Use JS to open new window and write content to avoid data: URL restrictions
                    full_html = HTML_TEMPLATE.replace("{user_js}", js_code)
                    encoded = urllib.parse.quote(full_html)
                    ui.run_javascript(f'''
                        const win = window.open("", "_blank");
                        win.document.write(decodeURIComponent("{encoded}"));
                        win.document.close();
                    ''')

                # Toolbar
                with ui.row().classes('w-full p-2 gap-2 bg-white/5 border-t border-white/10 items-center justify-between'):
                    with ui.row().classes('gap-2 items-center flex-grow'):
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
