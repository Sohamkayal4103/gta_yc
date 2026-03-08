(function () {
    const legacyRoomInput = document.getElementById('room-video-legacy');
    const selfieInput = document.getElementById('selfie-video');
    const generateBtn = document.getElementById('generate-btn');
    const genreCards = document.querySelectorAll('.genre-card');
    const uploadStatus = document.getElementById('upload-status');

    const roomDirectionInputs = {
        front: document.getElementById('room-front-video'),
        back: document.getElementById('room-back-video'),
        left: document.getElementById('room-left-video'),
        right: document.getElementById('room-right-video'),
        up: document.getElementById('room-up-video'),
        down: document.getElementById('room-down-video'),
    };

    const uiEvents = [];
    let selectedGenre = null;
    let lastPolledStage = null;

    function logUI(event, details = {}) {
        const entry = {
            ts: new Date().toISOString(),
            event,
            ...details,
        };
        uiEvents.push(entry);
        console.log('[UPLOAD_UI]', entry);
    }

    function fileMeta(file) {
        if (!file) return null;
        return {
            name: file.name,
            size: file.size,
            type: file.type,
            last_modified: file.lastModified,
        };
    }

    function hasDirectionalRoomUpload() {
        return Object.values(roomDirectionInputs).some((input) => input && input.files && input.files.length > 0);
    }

    function selectedDirections() {
        return Object.entries(roomDirectionInputs)
            .filter(([, input]) => input && input.files && input.files.length > 0)
            .map(([direction]) => direction);
    }

    function updateUploadStatus(reason) {
        if (!uploadStatus) return;

        const hasDirectional = hasDirectionalRoomUpload();
        const hasLegacy = !!(legacyRoomInput && legacyRoomInput.files && legacyRoomInput.files.length > 0);
        const hasRoom = hasDirectional || hasLegacy;
        const hasSelfie = !!(selfieInput && selfieInput.files && selfieInput.files.length > 0);
        const hasGenre = !!selectedGenre;

        const missing = [];
        if (!hasRoom) missing.push('room video (at least one direction)');
        if (!hasSelfie) missing.push('selfie video');
        if (!hasGenre) missing.push('genre');

        if (missing.length === 0) {
            const dirs = selectedDirections();
            const dirsLabel = dirs.length > 0 ? dirs.join(', ') : 'legacy room video';
            uploadStatus.textContent = `Ready to generate. Room views: ${dirsLabel}.`;
        } else {
            uploadStatus.textContent = `Missing: ${missing.join(', ')}.`;
        }

        if (reason) {
            logUI('upload_status_updated', {
                reason,
                status_text: uploadStatus.textContent,
                selected_genre: selectedGenre,
                directions: selectedDirections(),
                has_legacy_room: hasLegacy,
                has_selfie: hasSelfie,
            });
        }
    }

    function checkReady(reason) {
        const hasRoomDirectional = hasDirectionalRoomUpload();
        const hasRoomLegacy = !!(legacyRoomInput && legacyRoomInput.files && legacyRoomInput.files.length > 0);
        const hasRoom = hasRoomDirectional || hasRoomLegacy;
        const hasSelfie = !!(selfieInput && selfieInput.files && selfieInput.files.length > 0);
        const enabled = !!(hasRoom && hasSelfie && selectedGenre && generateBtn);

        if (generateBtn) {
            generateBtn.disabled = !enabled;
        }

        updateUploadStatus(reason || 'check_ready');

        logUI('check_ready', {
            reason: reason || 'unknown',
            has_room_directional: hasRoomDirectional,
            has_room_legacy: hasRoomLegacy,
            has_selfie: hasSelfie,
            selected_genre: selectedGenre,
            generate_enabled: enabled,
        });
    }

    function bindFileInput(input, filenameId, fieldName) {
        if (!input) {
            logUI('file_input_missing', { field: fieldName, filename_id: filenameId });
            return;
        }

        input.addEventListener('change', (e) => {
            const file = e.target.files && e.target.files[0] ? e.target.files[0] : null;
            const card = e.target.closest('.upload-card');
            const filename = document.getElementById(filenameId);

            if (filename) {
                filename.textContent = file ? file.name : '';
            }

            if (card) {
                if (file) card.classList.add('has-file');
                else card.classList.remove('has-file');
            }

            logUI('file_selected', {
                field: fieldName,
                file: fileMeta(file),
            });

            checkReady(`file_change:${fieldName}`);
        });
    }

    Object.entries(roomDirectionInputs).forEach(([direction, input]) => {
        bindFileInput(input, `room-${direction}-filename`, `room_${direction}_video`);
    });

    bindFileInput(legacyRoomInput, 'room-legacy-filename', 'room_video_legacy');
    bindFileInput(selfieInput, 'selfie-filename', 'selfie_video');

    if (genreCards && genreCards.length > 0) {
        genreCards.forEach((card) => {
            card.addEventListener('click', () => {
                genreCards.forEach((c) => c.classList.remove('selected'));
                card.classList.add('selected');
                selectedGenre = card.dataset.genre;

                logUI('genre_selected', { genre: selectedGenre });
                checkReady('genre_selected');
            });
        });
    } else {
        logUI('genre_cards_missing', {});
    }

    async function startGeneration() {
        if (!generateBtn) {
            logUI('generate_button_missing', {});
            return;
        }

        const formData = new FormData();

        if (legacyRoomInput && legacyRoomInput.files && legacyRoomInput.files[0]) {
            formData.append('room_video', legacyRoomInput.files[0]);
        }

        const directionFieldNames = {
            front: 'room_front_video',
            back: 'room_back_video',
            left: 'room_left_video',
            right: 'room_right_video',
            up: 'room_up_video',
            down: 'room_down_video',
        };

        Object.entries(roomDirectionInputs).forEach(([direction, input]) => {
            if (input && input.files && input.files[0]) {
                formData.append(directionFieldNames[direction], input.files[0]);
            }
        });

        if (!selfieInput || !selfieInput.files || !selfieInput.files[0]) {
            logUI('generate_click_blocked', { reason: 'missing_selfie' });
            alert('Please select a selfie video.');
            checkReady('generate_click_blocked');
            return;
        }

        if (!selectedGenre) {
            logUI('generate_click_blocked', { reason: 'missing_genre' });
            alert('Please select a genre.');
            checkReady('generate_click_blocked');
            return;
        }

        formData.append('selfie_video', selfieInput.files[0]);
        formData.append('genre', selectedGenre);

        logUI('generate_clicked', {
            selected_genre: selectedGenre,
            room_directions: selectedDirections(),
            has_legacy_room: !!(legacyRoomInput && legacyRoomInput.files && legacyRoomInput.files[0]),
            selfie: fileMeta(selfieInput.files[0]),
        });

        // Include a full UI interaction trace in the request body so backend can persist it.
        formData.append('ui_debug_log', JSON.stringify(uiEvents));

        document.getElementById('upload-section').classList.add('hidden');
        document.getElementById('loading-section').classList.remove('hidden');

        try {
            const res = await fetch('/api/generate', { method: 'POST', body: formData });
            const data = await res.json();

            logUI('generate_response', {
                status: res.status,
                ok: res.ok,
                response: data,
            });

            if (!res.ok) throw new Error(data.detail || 'Upload failed');
            pollStatus(data.session_id);
        } catch (err) {
            logUI('generate_error', { message: String(err && err.message ? err.message : err) });
            alert('Error: ' + err.message);
            document.getElementById('upload-section').classList.remove('hidden');
            document.getElementById('loading-section').classList.add('hidden');
        }
    }

    if (generateBtn) {
        generateBtn.addEventListener('click', startGeneration);
    } else {
        logUI('generate_button_missing', {});
    }

    const STAGE_LABELS = {
        initializing: 'Initializing agents...',
        spatial_analysis: 'Analyzing multi-view room uploads...',
        missions: 'Generating GTA-style missions...',
        art: 'Creating your game world and character...',
        audio: 'Composing soundtrack and sound effects...',
        assembly: 'Assembling your universe...',
        complete: 'Your universe is ready!',
    };

    function pollStatus(sessionId) {
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`/api/status/${sessionId}`);
                const data = await res.json();

                document.getElementById('loading-stage').textContent =
                    STAGE_LABELS[data.stage] || data.message;
                document.getElementById('progress-fill').style.width = data.progress + '%';
                document.getElementById('progress-text').textContent = data.progress + '%';

                if (data.stage !== lastPolledStage) {
                    lastPolledStage = data.stage;
                    logUI('status_stage_changed', {
                        session_id: sessionId,
                        stage: data.stage,
                        progress: data.progress,
                        message: data.message,
                    });
                }

                if (data.status === 'complete') {
                    clearInterval(interval);
                    showReady(sessionId);
                } else if (data.status === 'error') {
                    clearInterval(interval);
                    logUI('status_error', { session_id: sessionId, message: data.message });
                    alert('Generation failed: ' + data.message);
                    document.getElementById('upload-section').classList.remove('hidden');
                    document.getElementById('loading-section').classList.add('hidden');
                }
            } catch (err) {
                logUI('status_poll_error', {
                    session_id: sessionId,
                    message: String(err && err.message ? err.message : err),
                });
                console.error('Poll error:', err);
            }
        }, 2000);
    }

    function showReady(sessionId) {
        document.getElementById('loading-section').classList.add('hidden');
        document.getElementById('ready-section').classList.remove('hidden');

        const gameUrl = `${window.location.origin}/play/${sessionId}`;
        document.getElementById('game-link').value = gameUrl;
        document.getElementById('play-btn').href = gameUrl;

        logUI('generation_ready', { session_id: sessionId, game_url: gameUrl });

        const copyBtn = document.getElementById('copy-btn');
        copyBtn.addEventListener('click', () => {
            navigator.clipboard.writeText(gameUrl);
            copyBtn.textContent = 'Copied!';
            setTimeout(() => {
                copyBtn.textContent = 'Copy';
            }, 2000);
        });
    }

    logUI('page_initialized', {
        found_inputs: {
            legacy_room: !!legacyRoomInput,
            selfie: !!selfieInput,
            directions: Object.fromEntries(
                Object.entries(roomDirectionInputs).map(([k, v]) => [k, !!v])
            ),
            generate_button: !!generateBtn,
            upload_status: !!uploadStatus,
            genre_cards: genreCards ? genreCards.length : 0,
        },
    });

    checkReady('page_init');
})();
