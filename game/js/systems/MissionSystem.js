class MissionSystem {
    constructor(scene, missionPack) {
        this.scene = scene;
        this.missions = missionPack.missions || [];
        this.currentMissionIndex = -1;
        this.currentMission = null;
        this.currentStepIndex = 0;
        this.completed = false;
    }

    startNextMission() {
        this.currentMissionIndex++;
        if (this.currentMissionIndex >= this.missions.length) {
            this.completed = true;
            this.scene.events.emit('game:complete');
            return false;
        }
        this.currentMission = this.missions[this.currentMissionIndex];
        this.currentStepIndex = 0;
        this.scene.events.emit('mission:start', this.currentMission);
        return true;
    }

    getCurrentStep() {
        if (!this.currentMission) return null;
        return this.currentMission.steps[this.currentStepIndex] || null;
    }

    getTargetObjectName() {
        const step = this.getCurrentStep();
        return step ? step.target_object : null;
    }

    handleInteraction(objectName) {
        if (!this.currentMission || this.completed) return false;

        const step = this.getCurrentStep();
        if (!step) return false;

        // Check if the interacted object matches the current target
        const target = step.target_object?.toLowerCase() || '';
        const interacted = objectName.toLowerCase();

        if (interacted.includes(target) || target.includes(interacted) || target === interacted) {
            // Step complete
            this.scene.events.emit('mission:step_complete', step);

            this.currentStepIndex++;
            if (this.currentStepIndex >= this.currentMission.steps.length) {
                // Mission complete
                this.scene.events.emit('mission:complete', this.currentMission);

                // Auto-start next mission after delay
                this.scene.time.delayedCall(3000, () => {
                    this.startNextMission();
                });
                return true;
            }

            // Show next step
            this.scene.events.emit('mission:next_step', this.getCurrentStep());
            return true;
        }

        return false;
    }
}
