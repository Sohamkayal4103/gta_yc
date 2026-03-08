class BootScene extends Phaser.Scene {
    constructor() {
        super({ key: 'BootScene' });
    }

    preload() {
        // Loading bar
        const width = this.cameras.main.width;
        const height = this.cameras.main.height;

        const progressBar = this.add.graphics();
        const progressBox = this.add.graphics();
        progressBox.fillStyle(0x222222, 0.8);
        progressBox.fillRect(width / 2 - 160, height / 2 - 15, 320, 30);

        const loadingText = this.add.text(width / 2, height / 2 - 40, 'Loading Universe...', {
            fontSize: '18px',
            fill: '#ffffff',
        }).setOrigin(0.5);

        this.load.on('progress', (value) => {
            progressBar.clear();
            progressBar.fillStyle(0x7b2ff7, 1);
            progressBar.fillRect(width / 2 - 155, height / 2 - 10, 310 * value, 20);
        });

        this.load.on('complete', () => {
            progressBar.destroy();
            progressBox.destroy();
            loadingText.destroy();
        });

        // Load manifest
        this.load.json('manifest', `/api/game/${window.SESSION_ID}/manifest.json`);
    }

    create() {
        const manifest = this.cache.json.get('manifest');
        if (!manifest) {
            this.add.text(400, 300, 'Failed to load game data', {
                fontSize: '20px', fill: '#ff0000'
            }).setOrigin(0.5);
            return;
        }

        this.registry.set('manifest', manifest);

        // Load game assets referenced in manifest
        const base = `/static/games/${window.SESSION_ID}`;

        this.load.image('map', `${base}/${manifest.assets.map}`);
        this.load.image('player', `${base}/${manifest.assets.player}`);

        // Load NPC sprites
        if (manifest.assets.npcs) {
            manifest.assets.npcs.forEach((npc, i) => {
                this.load.image(`npc_${i}`, `${base}/${npc}`);
            });
        }

        // Load audio (with error handling for missing files)
        if (manifest.audio?.soundtrack) {
            this.load.audio('bgm', `${base}/${manifest.audio.soundtrack}`);
        }
        if (manifest.audio?.sfx) {
            Object.entries(manifest.audio.sfx).forEach(([name, file]) => {
                this.load.audio(`sfx_${name}`, `${base}/${file}`);
            });
        }

        this.load.once('complete', () => {
            this.scene.start('MenuScene');
        });

        // Handle load errors gracefully
        this.load.on('loaderror', (file) => {
            console.warn('Failed to load:', file.key);
        });

        this.load.start();
    }
}
