import { SceneObject, ScenePerson, Mission, MissionObjective, InteractionType } from './api';

function flattenObjects(objects: SceneObject[]): SceneObject[] {
  const result: SceneObject[] = [];
  for (const obj of objects) {
    result.push(obj);
    if (obj.children) result.push(...flattenObjects(obj.children));
  }
  return result;
}

function guessInteraction(name: string | null | undefined): InteractionType {
  const n = String(name ?? '').toLowerCase();
  if (/chair|couch|sofa|bench|stool|seat/.test(n)) return 'sit';
  if (/whiteboard|blackboard|chalkboard|board/.test(n)) return 'write';
  if (/laptop|monitor|computer|tv|television|microwave|printer|phone|coffee|machine|screen/.test(n)) return 'use';
  if (/door|cabinet|drawer|fridge|closet|cupboard|suitcase/.test(n)) return 'open';
  if (/lamp|light|switch|fan/.test(n)) return 'toggle';
  return 'none';
}

export function generateMissions(objects: SceneObject[], people: ScenePerson[]): Mission[] {
  const flat = flattenObjects(objects);
  const categorized: Record<string, SceneObject[]> = {
    sit: [], use: [], open: [], toggle: [], write: [],
  };

  for (const obj of flat) {
    const interaction = obj.interaction && obj.interaction !== 'none'
      ? obj.interaction
      : guessInteraction(obj.name);
    if (interaction !== 'none') {
      categorized[interaction].push(obj);
    }
  }

  const missions: Mission[] = [];
  let missionId = 0;

  // Meet & Greet
  if (people.length >= 1) {
    missions.push({
      id: `m${missionId++}`,
      type: 'greet',
      title: 'Meet & Greet',
      description: 'Greet every person in the room',
      objectives: people.map((p, i) => ({
        id: `obj${i}`,
        description: `Greet ${p.name.replace(/_/g, ' ')}`,
        targetName: p.name,
        targetInteraction: 'greet' as const,
        completed: false,
      })),
      completed: false,
    });
  }

  // Explorer — doors & containers
  const openables = categorized.open;
  if (openables.length >= 1) {
    missions.push({
      id: `m${missionId++}`,
      type: 'open',
      title: 'Explorer',
      description: 'Open every door and container',
      objectives: openables.map((o, i) => ({
        id: `obj${i}`,
        description: `Open ${o.name.replace(/_/g, ' ')}`,
        targetName: o.name,
        targetInteraction: 'open' as InteractionType,
        completed: false,
      })),
      completed: false,
    });
  }

  // Take a Seat
  if (categorized.sit.length >= 1) {
    missions.push({
      id: `m${missionId++}`,
      type: 'sit',
      title: 'Take a Seat',
      description: 'Sit on each chair',
      objectives: categorized.sit.map((o, i) => ({
        id: `obj${i}`,
        description: `Sit on ${o.name.replace(/_/g, ' ')}`,
        targetName: o.name,
        targetInteraction: 'sit' as InteractionType,
        completed: false,
      })),
      completed: false,
    });
  }

  // Tech Check
  if (categorized.use.length >= 1) {
    missions.push({
      id: `m${missionId++}`,
      type: 'use',
      title: 'Tech Check',
      description: 'Use every device',
      objectives: categorized.use.map((o, i) => ({
        id: `obj${i}`,
        description: `Use ${o.name.replace(/_/g, ' ')}`,
        targetName: o.name,
        targetInteraction: 'use' as InteractionType,
        completed: false,
      })),
      completed: false,
    });
  }

  // Light It Up
  if (categorized.toggle.length >= 1) {
    missions.push({
      id: `m${missionId++}`,
      type: 'toggle',
      title: 'Light It Up',
      description: 'Toggle every light and switch',
      objectives: categorized.toggle.map((o, i) => ({
        id: `obj${i}`,
        description: `Toggle ${o.name.replace(/_/g, ' ')}`,
        targetName: o.name,
        targetInteraction: 'toggle' as InteractionType,
        completed: false,
      })),
      completed: false,
    });
  }

  // Room Tour — always available
  const corners = ['front-left', 'front-right', 'back-left', 'back-right'];
  missions.push({
    id: `m${missionId++}`,
    type: 'corner',
    title: 'Room Tour',
    description: 'Visit all 4 corners of the room',
    objectives: corners.map((c, i) => ({
      id: `obj${i}`,
      description: `Visit the ${c} corner`,
      targetName: c,
      targetInteraction: 'corner' as const,
      completed: false,
    })),
    completed: false,
  });

  // Return top 4 (prioritize ones with objectives, Room Tour always last)
  return missions.slice(0, 4);
}
