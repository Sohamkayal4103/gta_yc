class HUDScene extends Phaser.Scene {
    constructor() {
        super({ key: 'HUDScene' });
    }

    create() {
        const manifest = this.registry.get('manifest');
        const theme = GENRE_THEMES[manifest.genre] || GENRE_THEMES.fantasy;

        // Mission title (top-left)
        this.missionTitle = this.add.text(16, 16, '', {
            fontSize: '18px',
            fontStyle: 'bold',
            fill: theme.accent,
            stroke: '#000000',
            strokeThickness: 3,
        });

        // Mission description (below title)
        this.missionDesc = this.add.text(16, 40, '', {
            fontSize: '13px',
            fill: theme.text,
            stroke: '#000000',
            strokeThickness: 2,
            wordWrap: { width: 350 },
        });

        // Current step indicator
        this.stepText = this.add.text(16, 80, '', {
            fontSize: '14px',
            fill: theme.interact,
            stroke: '#000000',
            strokeThickness: 2,
            wordWrap: { width: 350 },
        });

        // Dialogue box (bottom center, hidden initially)
        this.dialogueBg = this.add.rectangle(400, 530, 700, 80, 0x000000, 0.85)
            .setStrokeStyle(2, Phaser.Display.Color.HexStringToColor(theme.accent).color)
            .setVisible(false);

        this.dialogueSpeaker = this.add.text(70, 500, '', {
            fontSize: '14px',
            fontStyle: 'bold',
            fill: theme.accent,
        }).setVisible(false);

        this.dialogueText = this.add.text(70, 520, '', {
            fontSize: '13px',
            fill: '#ffffff',
            wordWrap: { width: 620 },
        }).setVisible(false);

        // Notification text (center, for mission complete etc.)
        this.notification = this.add.text(400, 200, '', {
            fontSize: '28px',
            fontStyle: 'bold',
            fill: theme.highlight,
            stroke: '#000000',
            strokeThickness: 4,
            align: 'center',
        }).setOrigin(0.5).setAlpha(0);

        // Genre badge (top-right)
        const genreLabels = { fantasy: 'Fantasy RPG', cyberpunk: 'Cyberpunk', horror: 'Horror Survival' };
        this.add.text(784, 16, genreLabels[manifest.genre] || manifest.genre, {
            fontSize: '12px',
            fill: theme.accent,
            backgroundColor: '#00000088',
            padding: { x: 6, y: 3 },
        }).setOrigin(1, 0);

        // Listen for game scene events
        const gameScene = this.scene.get('GameScene');

        gameScene.events.on('mission:start', (mission) => {
            this.missionTitle.setText(mission.title);
            this.missionDesc.setText(mission.description);
            const step = mission.steps[0];
            if (step) {
                this.stepText.setText(`> ${step.instruction}`);
            }
            this.showNotification(`Mission: ${mission.title}`);
        });

        gameScene.events.on('mission:step_complete', (step) => {
            if (step.dialogue) {
                this.showDialogue('System', step.dialogue);
            }
        });

        gameScene.events.on('mission:next_step', (step) => {
            this.stepText.setText(`> ${step.instruction}`);
        });

        gameScene.events.on('mission:complete', (mission) => {
            this.showNotification(`Mission Complete!\n${mission.reward_text}`);
            this.stepText.setText('');
            // Play complete SFX
            if (this.cache?.audio?.exists('sfx_complete')) {
                this.sound.play('sfx_complete', { volume: 0.6 });
            }
        });

        gameScene.events.on('game:complete', () => {
            this.showNotification('All Missions Complete!\nYou conquered this universe!');
            this.missionTitle.setText('ALL MISSIONS COMPLETE');
            this.missionDesc.setText('You have conquered this universe.');
            this.stepText.setText('');
        });

        gameScene.events.on('dialogue:show', ({ speaker, text }) => {
            this.showDialogue(speaker, text);
        });
    }

    showNotification(text) {
        this.notification.setText(text);
        this.notification.setAlpha(1);
        this.tweens.add({
            targets: this.notification,
            alpha: 0,
            duration: 3000,
            ease: 'Power2',
        });
    }

    showDialogue(speaker, text) {
        this.dialogueBg.setVisible(true);
        this.dialogueSpeaker.setText(speaker).setVisible(true);
        this.dialogueText.setText(text).setVisible(true);

        // Auto-hide after 4 seconds
        this.time.delayedCall(4000, () => {
            this.dialogueBg.setVisible(false);
            this.dialogueSpeaker.setVisible(false);
            this.dialogueText.setVisible(false);
        });
    }
}
