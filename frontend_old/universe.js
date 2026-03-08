(function () {
    const DIRECTIONS = ['front', 'back', 'left', 'right', 'up', 'down'];

    const inputs = {};
    DIRECTIONS.forEach((dir) => {
        inputs[dir] = document.getElementById(`video-${dir}`);
    });

    const generateBtn = document.getElementById('generate-btn');
    const uploadStatus = document.getElementById('upload-status');
    const uploadCount = document.getElementById('upload-count');

    function getUploadedDirections() {
        return DIRECTIONS.filter((dir) => inputs[dir] && inputs[dir].files && inputs[dir].files.length > 0);
    }

    function updateState() {
        const uploaded = getUploadedDirections();
        uploadCount.textContent = uploaded.length;

        if (uploaded.length === 0) {
            generateBtn.disabled = true;
            uploadStatus.textContent = 'Upload at least one direction to get started. All 6 for best results.';
        } else if (uploaded.length < 6) {
            generateBtn.disabled = false;
            const missing = DIRECTIONS.filter((d) => !uploaded.includes(d));
            uploadStatus.textContent = `${uploaded.length}/6 uploaded. Missing: ${missing.join(', ')}. You can generate now or add more.`;
        } else {
            generateBtn.disabled = false;
            uploadStatus.textContent = 'All 6 directions uploaded. Ready to build your universe!';
        }
    }

    // Bind file inputs
    DIRECTIONS.forEach((dir) => {
        const input = inputs[dir];
        if (!input) return;

        input.addEventListener('change', (e) => {
            const file = e.target.files && e.target.files[0];
            const card = e.target.closest('.upload-card');
            const fname = document.getElementById(`fname-${dir}`);
            const checkmark = card.querySelector('.checkmark');

            if (fname) fname.textContent = file ? file.name : '';
            if (card) {
                if (file) card.classList.add('has-file');
                else card.classList.remove('has-file');
            }
            if (checkmark) {
                if (file) checkmark.classList.remove('hidden');
                else checkmark.classList.add('hidden');
            }

            updateState();
        });
    });

    // Generate button
    if (generateBtn) {
        generateBtn.addEventListener('click', startGeneration);
    }

    async function startGeneration() {
        const uploaded = getUploadedDirections();
        if (uploaded.length === 0) {
            alert('Please upload at least one directional video.');
            return;
        }

        const formData = new FormData();
        uploaded.forEach((dir) => {
            formData.append(`room_${dir}_video`, inputs[dir].files[0]);
        });

        // Switch to loading UI
        document.getElementById('upload-section').classList.add('hidden');
        document.getElementById('loading-section').classList.remove('hidden');

        try {
            const res = await fetch('/api/generate-3d', {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();

            if (!res.ok) throw new Error(data.detail || 'Generation failed');

            pollStatus(data.session_id);
        } catch (err) {
            alert('Error: ' + err.message);
            document.getElementById('upload-section').classList.remove('hidden');
            document.getElementById('loading-section').classList.add('hidden');
        }
    }

    const STAGE_LABELS = {
        initializing: 'Initializing spatial analysis...',
        spatial_analysis: 'Analyzing room videos with AI...',
        generating_universe: 'Generating 3D A-Frame universe...',
        complete: 'Your universe is ready!',
    };

    function pollStatus(sessionId) {
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`/api/status/${sessionId}`);
                const data = await res.json();

                const stageEl = document.getElementById('loading-stage');
                const fillEl = document.getElementById('progress-fill');
                const textEl = document.getElementById('progress-text');

                stageEl.textContent = STAGE_LABELS[data.stage] || data.message;
                fillEl.style.width = data.progress + '%';
                textEl.textContent = data.progress + '%';

                if (data.status === 'complete') {
                    clearInterval(interval);
                    showReady(sessionId);
                } else if (data.status === 'error') {
                    clearInterval(interval);
                    alert('Generation failed: ' + data.message);
                    document.getElementById('upload-section').classList.remove('hidden');
                    document.getElementById('loading-section').classList.add('hidden');
                }
            } catch (err) {
                console.error('Poll error:', err);
            }
        }, 2000);
    }

    function showReady(sessionId) {
        document.getElementById('loading-section').classList.add('hidden');
        document.getElementById('ready-section').classList.remove('hidden');

        const universeUrl = `${window.location.origin}/universe/${sessionId}`;
        document.getElementById('universe-link').value = universeUrl;
        document.getElementById('enter-btn').href = universeUrl;

        const copyBtn = document.getElementById('copy-btn');
        copyBtn.addEventListener('click', () => {
            navigator.clipboard.writeText(universeUrl);
            copyBtn.textContent = 'Copied!';
            setTimeout(() => { copyBtn.textContent = 'Copy'; }, 2000);
        });
    }

    updateState();
})();
