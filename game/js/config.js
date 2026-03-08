const GENRE_THEMES = {
    fantasy: {
        bg: '#1a1408',
        text: '#f4e4bc',
        accent: '#c9a04e',
        highlight: '#7b2ff7',
        interact: '#4ade80',
    },
    cyberpunk: {
        bg: '#050510',
        text: '#00ffff',
        accent: '#ff00ff',
        highlight: '#00ffff',
        interact: '#ff00ff',
    },
    horror: {
        bg: '#0a0505',
        text: '#cc3333',
        accent: '#884444',
        highlight: '#ff3333',
        interact: '#44ff44',
    },
};

const gameConfig = {
    type: Phaser.AUTO,
    parent: 'game-container',
    width: 800,
    height: 600,
    backgroundColor: GENRE_THEMES[window.GENRE]?.bg || '#000000',
    physics: {
        default: 'arcade',
        arcade: {
            gravity: { y: 0 },
            debug: false,
        },
    },
    scene: [BootScene, MenuScene, GameScene, HUDScene],
    pixelArt: true,
    scale: {
        mode: Phaser.Scale.FIT,
        autoCenter: Phaser.Scale.CENTER_BOTH,
    },
};
