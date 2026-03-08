class MenuScene extends Phaser.Scene {
    constructor() {
        super({ key: 'MenuScene' });
    }

    create() {
        const manifest = this.registry.get('manifest');
        const theme = GENRE_THEMES[manifest.genre] || GENRE_THEMES.fantasy;
        const cx = this.cameras.main.centerX;
        const cy = this.cameras.main.centerY;

        // Title
        this.add.text(cx, cy - 100, 'REALMCAST', {
            fontSize: '48px',
            fontStyle: 'bold',
            fill: theme.accent,
        }).setOrigin(0.5);

        // Genre subtitle
        const genreLabels = {
            fantasy: 'Fantasy RPG',
            cyberpunk: 'Cyberpunk',
            horror: 'Horror Survival',
        };
        this.add.text(cx, cy - 50, genreLabels[manifest.genre] || manifest.genre, {
            fontSize: '24px',
            fill: theme.text,
        }).setOrigin(0.5);

        // Room description
        if (manifest.room_layout?.room_description) {
            this.add.text(cx, cy + 10, manifest.room_layout.room_description, {
                fontSize: '14px',
                fill: '#888888',
                wordWrap: { width: 500 },
                align: 'center',
            }).setOrigin(0.5);
        }

        // First mission preview
        if (manifest.missions?.missions?.[0]) {
            const firstMission = manifest.missions.missions[0];
            this.add.text(cx, cy + 60, `First Mission: ${firstMission.title}`, {
                fontSize: '16px',
                fill: theme.highlight,
            }).setOrigin(0.5);
        }

        // Start prompt (blinking)
        const startText = this.add.text(cx, cy + 120, 'Press ENTER to begin', {
            fontSize: '20px',
            fill: '#ffffff',
        }).setOrigin(0.5);

        this.tweens.add({
            targets: startText,
            alpha: 0.3,
            duration: 800,
            yoyo: true,
            repeat: -1,
        });

        // Controls info
        this.add.text(cx, cy + 170, 'WASD to move  |  E to interact', {
            fontSize: '13px',
            fill: '#666666',
        }).setOrigin(0.5);

        // Start on ENTER
        this.input.keyboard.once('keydown-ENTER', () => {
            this.scene.start('GameScene');
        });

        // Also start on click/tap
        this.input.once('pointerdown', () => {
            this.scene.start('GameScene');
        });
    }
}
