class GameScene extends Phaser.Scene {
    constructor() {
        super({ key: 'GameScene' });
        this.nearbyInteractable = null;
    }

    create() {
        const manifest = this.registry.get('manifest');
        const theme = GENRE_THEMES[manifest.genre] || GENRE_THEMES.fantasy;

        // 1. Add the generated map as background
        if (this.textures.exists('map')) {
            this.mapImage = this.add.image(0, 0, 'map').setOrigin(0, 0);
            this.mapImage.setDisplaySize(manifest.map_width, manifest.map_height);
        } else {
            // Fallback: draw a colored rectangle
            const bg = this.add.rectangle(
                manifest.map_width / 2, manifest.map_height / 2,
                manifest.map_width, manifest.map_height,
                Phaser.Display.Color.HexStringToColor(theme.bg).color
            );
        }

        // 2. Set world bounds
        this.physics.world.setBounds(0, 0, manifest.map_width, manifest.map_height);

        // 3. Create collision bodies
        this.collisionGroup = this.physics.add.staticGroup();
        manifest.collision_rects.forEach(rect => {
            const body = this.add.rectangle(
                rect.x + rect.w / 2, rect.y + rect.h / 2,
                rect.w, rect.h,
                0x000000, 0 // Invisible
            );
            this.physics.add.existing(body, true);
            this.collisionGroup.add(body);
        });

        // 4. Create interactable zones with visual indicators
        this.interactableZones = [];
        manifest.interactables.forEach(obj => {
            // Glowing indicator
            const glow = this.add.rectangle(
                obj.x, obj.y, obj.w + 8, obj.h + 8,
                Phaser.Display.Color.HexStringToColor(theme.interact).color, 0.15
            );
            glow.setStrokeStyle(2,
                Phaser.Display.Color.HexStringToColor(theme.interact).color, 0.6
            );

            // Pulse animation
            this.tweens.add({
                targets: glow,
                alpha: 0.05,
                scaleX: 1.05,
                scaleY: 1.05,
                duration: 1200,
                yoyo: true,
                repeat: -1,
            });

            // Label
            const label = this.add.text(obj.x, obj.y - obj.h / 2 - 12, obj.game_name, {
                fontSize: '11px',
                fill: theme.interact,
                backgroundColor: '#00000088',
                padding: { x: 4, y: 2 },
            }).setOrigin(0.5, 1);

            this.interactableZones.push({
                zone: glow,
                label: label,
                data: obj,
            });
        });

        // 5. Create NPCs
        this.npcs = [];
        const npcData = manifest.missions?.npcs || [];
        npcData.forEach((npc, i) => {
            const npcX = (npc.x_percent || 0.3) * manifest.map_width;
            const npcY = (npc.y_percent || 0.3) * manifest.map_height;

            let npcSprite;
            if (this.textures.exists(`npc_${i}`)) {
                npcSprite = this.physics.add.sprite(npcX, npcY, `npc_${i}`);
                npcSprite.setDisplaySize(48, 48);
            } else {
                npcSprite = this.add.circle(npcX, npcY, 16,
                    Phaser.Display.Color.HexStringToColor(theme.accent).color
                );
                this.physics.add.existing(npcSprite, true);
            }

            const npcLabel = this.add.text(npcX, npcY - 28, npc.name, {
                fontSize: '11px',
                fill: theme.accent,
                backgroundColor: '#00000088',
                padding: { x: 3, y: 1 },
            }).setOrigin(0.5);

            this.npcs.push({ sprite: npcSprite, label: npcLabel, data: npc });
        });

        // 6. Create player
        const spawnX = manifest.spawn_point.x;
        const spawnY = manifest.spawn_point.y;

        if (this.textures.exists('player')) {
            this.player = this.physics.add.sprite(spawnX, spawnY, 'player');
            this.player.setDisplaySize(40, 40);
        } else {
            // Fallback: colored circle
            this.player = this.add.circle(spawnX, spawnY, 16,
                Phaser.Display.Color.HexStringToColor(theme.highlight).color
            );
            this.physics.add.existing(this.player);
        }

        this.player.setCollideWorldBounds(true);
        if (this.player.body) {
            this.player.body.setSize(24, 24);
        }

        // 7. Collisions
        this.physics.add.collider(this.player, this.collisionGroup);

        // 8. Camera
        this.cameras.main.startFollow(this.player, true, 0.08, 0.08);
        this.cameras.main.setBounds(0, 0, manifest.map_width, manifest.map_height);
        this.cameras.main.setZoom(1);

        // 9. Input
        this.cursors = this.input.keyboard.addKeys({
            up: 'W', down: 'S', left: 'A', right: 'D',
            interact: 'E',
        });
        this.arrowKeys = this.input.keyboard.createCursorKeys();

        // 10. Interact prompt (hidden initially)
        this.interactPrompt = this.add.text(0, 0, '[E] Interact', {
            fontSize: '14px',
            fill: '#ffffff',
            backgroundColor: theme.highlight + 'cc',
            padding: { x: 8, y: 4 },
        }).setOrigin(0.5).setVisible(false).setDepth(100);

        // 11. Music
        if (this.sound.get('bgm') || this.cache.audio.exists('bgm')) {
            try {
                this.bgm = this.sound.add('bgm', { loop: true, volume: 0.3 });
                this.bgm.play();
            } catch (e) {
                console.warn('BGM playback failed:', e);
            }
        }

        // 12. Mission system
        this.missionSystem = new MissionSystem(this, manifest.missions);
        this.missionSystem.startNextMission();

        // 13. Launch HUD
        this.scene.launch('HUDScene');
    }

    update() {
        if (!this.player || !this.player.body) return;

        const speed = 200;
        this.player.body.setVelocity(0);

        // Movement
        const left = this.cursors.left.isDown || this.arrowKeys.left.isDown;
        const right = this.cursors.right.isDown || this.arrowKeys.right.isDown;
        const up = this.cursors.up.isDown || this.arrowKeys.up.isDown;
        const down = this.cursors.down.isDown || this.arrowKeys.down.isDown;

        if (left) this.player.body.setVelocityX(-speed);
        else if (right) this.player.body.setVelocityX(speed);
        if (up) this.player.body.setVelocityY(-speed);
        else if (down) this.player.body.setVelocityY(speed);

        // Normalize diagonal speed
        if ((left || right) && (up || down)) {
            this.player.body.velocity.normalize().scale(speed);
        }

        // Check proximity to interactables
        this.nearbyInteractable = null;
        let closestDist = 80;

        this.interactableZones.forEach(iz => {
            const dist = Phaser.Math.Distance.Between(
                this.player.x, this.player.y,
                iz.data.x, iz.data.y
            );
            if (dist < closestDist) {
                closestDist = dist;
                this.nearbyInteractable = iz;
            }
        });

        // Also check NPCs
        this.npcs.forEach(npc => {
            const dist = Phaser.Math.Distance.Between(
                this.player.x, this.player.y,
                npc.sprite.x, npc.sprite.y
            );
            if (dist < closestDist) {
                closestDist = dist;
                this.nearbyInteractable = {
                    data: { name: npc.data.name, game_name: npc.data.name },
                    isNPC: true,
                    npcData: npc.data,
                };
            }
        });

        // Show/hide interact prompt
        if (this.nearbyInteractable) {
            const target = this.nearbyInteractable.data;
            this.interactPrompt.setPosition(
                target.x || this.player.x,
                (target.y || this.player.y) - 40
            );
            this.interactPrompt.setText(`[E] ${target.game_name || target.name}`);
            this.interactPrompt.setVisible(true);

            // Handle interaction
            if (Phaser.Input.Keyboard.JustDown(this.cursors.interact)) {
                this.handleInteraction(this.nearbyInteractable);
            }
        } else {
            this.interactPrompt.setVisible(false);
        }
    }

    handleInteraction(interactable) {
        const objectName = interactable.data.name;

        // Play SFX
        if (this.cache.audio.exists('sfx_interact')) {
            this.sound.play('sfx_interact', { volume: 0.5 });
        }

        // Check if NPC
        if (interactable.isNPC && interactable.npcData) {
            const lines = interactable.npcData.dialogue_lines || ['...'];
            const line = lines[Math.floor(Math.random() * lines.length)];
            this.events.emit('dialogue:show', {
                speaker: interactable.npcData.name,
                text: line,
            });
        }

        // Try mission interaction
        const handled = this.missionSystem.handleInteraction(objectName);
        if (handled && this.cache.audio.exists('sfx_complete')) {
            this.sound.play('sfx_complete', { volume: 0.6 });
        }
    }
}
