import { App } from '@swarm/sdk';
import { mountSettings } from './swarm-settings.js';
import { configTextWithChanges } from '@swarm/config-editor';
import {mountProjects} from './swarm-projects-bootstrap.mjs';
if (document.querySelector('#all-projects')) { await mountProjects(); } else {

// One official client. The source snapshot remains immutable and explicitly not live.
const root = document.documentElement;
const baseline = document.querySelector('.space-baseline');
if (baseline) baseline.append(' · Saved snapshot, not live');
const app = new App({name: 'SWARM HQ', version: '1.0.0'}, {}, {autoResize: false});
root.dataset.swarmHost = 'connecting';
const opener = document.createElement('button');
opener.type = 'button'; opener.textContent = 'Settings'; opener.disabled = true;
opener.dataset.swarmSettings = '';
const dialog = document.createElement('dialog'); dialog.className = 'swarm-settings-dialog';
dialog.setAttribute('aria-label', 'SWARM Settings');
const close = document.createElement('button'); close.type = 'button'; close.textContent = 'Close settings';
const panel = document.createElement('section'); dialog.append(close, panel);
document.body.append(opener, dialog);
let mounted = false;
opener.addEventListener('click', async () => {
  dialog.showModal();
  if (!mounted) {
    mounted = true;
    let scopes = [];
    try {
      const result = await app.callServerTool({name: 'swarm_projects', arguments: {}});
      const roster = result?.structuredContent;
      if (!result.isError && roster?.available === true && roster.cursor && typeof roster.cursor === 'object' && !Array.isArray(roster.cursor)) {
        scopes = (roster.projects || []).filter(row => typeof row.id === 'string').map(row => ({
          label: row.name || row.id, scope: {type: 'project', project_id: row.id, accepted_cursor: roster.cursor},
        }));
      }
    } catch { /* Global settings remain available; no inferred project binding. */ }
    // No model catalogue/rank is fabricated from config or model names.
    mountSettings(panel, {app, scopes, editText: configTextWithChanges});
  }
});
close.addEventListener('click', () => dialog.close());
dialog.addEventListener('close', () => opener.focus());
app.onteardown = async () => { root.dataset.swarmHost = 'closed'; opener.disabled = true; if (dialog.open) dialog.close(); return {}; };
try {
  await app.connect(undefined, {timeout: 5000});
  root.dataset.swarmHost = 'initialized'; opener.disabled = !app.getHostCapabilities()?.serverTools;
} catch {
  root.dataset.swarmHost = 'unavailable';
  if (baseline) baseline.append(' · Host connection unavailable');
}
}
