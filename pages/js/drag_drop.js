(function() {
    // Check if style already injected
    if (!document.getElementById('visual-drag-style')) {
        const style = document.createElement('style');
        style.id = 'visual-drag-style';
        style.innerHTML = `
            @keyframes visual-spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
            }
            .visual-spin {
                animation: visual-spin 1s linear infinite;
            }
        `;
        document.head.appendChild(style);
    }

    const container = document.getElementById('visual-image-container');
    if (!container) return;

    // Remove old overlay if it exists
    const oldOverlay = document.getElementById('visual-drag-overlay');
    if (oldOverlay) {
        oldOverlay.remove();
    }

    // Create a beautiful drag and drop overlay inside the container
    const overlay = document.createElement('div');
    overlay.id = 'visual-drag-overlay';
    overlay.className = 'hidden absolute inset-0 flex flex-col items-center justify-center rounded-lg z-[9999] transition-all duration-300';
    overlay.style.backgroundColor = 'rgba(15, 23, 42, 0.85)'; 
    overlay.style.backdropFilter = 'blur(8px)';
    overlay.style.border = '2px dashed rgba(139, 92, 246, 0.6)'; 
    overlay.style.margin = '4px';

    const icon = document.createElement('span');
    icon.className = 'material-icons text-purple-400 mb-2';
    icon.style.fontSize = '48px';
    icon.innerText = 'cloud_upload';

    const text = document.createElement('p');
    text.className = 'text-white text-base font-semibold';
    text.innerText = 'Drop images to upload to grid';

    overlay.appendChild(icon);
    overlay.appendChild(text);
    container.appendChild(overlay);

    let dragCounter = 0;

    container.addEventListener('dragenter', (e) => {
        e.preventDefault();
        dragCounter++;
        if (dragCounter === 1) {
            overlay.classList.remove('hidden');
        }
    });

    container.addEventListener('dragover', (e) => {
        e.preventDefault();
    });

    container.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dragCounter--;
        if (dragCounter === 0) {
            overlay.classList.add('hidden');
        }
    });

    container.addEventListener('drop', async (e) => {
        e.preventDefault();
        dragCounter = 0;
        overlay.classList.add('hidden');

        const files = e.dataTransfer.files;
        if (!files || files.length === 0) return;

        // Filter for images
        const imageFiles = Array.from(files).filter(file => {
            const ext = file.name.split('.').pop().toLowerCase();
            return ['png', 'jpg', 'jpeg', 'webp'].includes(ext);
        });

        if (imageFiles.length === 0) return;

        // Show uploading state
        overlay.querySelector('p').innerText = 'Uploading ' + imageFiles.length + ' file(s)...';
        overlay.querySelector('span').innerText = 'sync';
        overlay.querySelector('span').classList.add('visual-spin');
        overlay.classList.remove('hidden');

        let uploadedCount = 0;
        for (const file of imageFiles) {
            const formData = new FormData();
            formData.append('file', file);

            try {
                const response = await fetch('/upload_visual_image', {
                    method: 'POST',
                    body: formData
                });
                if (response.ok) {
                    uploadedCount++;
                }
            } catch (err) {
                console.error('Upload failed:', err);
            }
        }

        // Hide overlay, restore text/icon
        overlay.classList.add('hidden');
        overlay.querySelector('p').innerText = 'Drop images to upload to grid';
        overlay.querySelector('span').innerText = 'cloud_upload';
        overlay.querySelector('span').classList.remove('visual-spin');

        if (uploadedCount > 0) {
            // Trigger Python side refresh
            const refreshBtn = document.getElementById('visual-refresh-btn');
            if (refreshBtn) {
                refreshBtn.click();
            }
        }
    });
})();
