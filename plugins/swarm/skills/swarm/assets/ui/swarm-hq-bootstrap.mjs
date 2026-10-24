import { App } from '@swarm/sdk';
import { mountSettings } from './swarm-settings.js';
import { configTextWithChanges } from '@swarm/config-editor';
import settingsCSS from './swarm-settings.css';
import {mountProjects} from './swarm-projects-bootstrap.mjs';
if (document.querySelector('#all-projects')) { await mountProjects(); } else {

// One official client. The source snapshot remains immutable and explicitly not live.
const root = document.documentElement;
const baseline = document.querySelector('.space-baseline');
if (baseline) baseline.append(' · Saved snapshot, not live');
const app = new App({name: 'SWARM HQ', version: '1.0.0'}, {}, {autoResize: false});
root.dataset.swarmHost = 'connecting';
const style = document.createElement('style');
style.textContent = settingsCSS + `
.swarm-settings-dialog{box-sizing:border-box;width:min(800px,calc(100vw - 24px));height:90dvh;max-height:90dvh;padding:12px;background:#07131d;color:#eef4f8;border:1px solid #456;border-radius:16px;overflow:hidden}
.swarm-settings-dialog[open]{display:grid;grid-template-rows:44px minmax(0,1fr);gap:8px}
.swarm-settings-dialog>button{justify-self:end;min-height:44px;padding:8px 16px;border:1px solid #385060;border-radius:8px;background:#13232e;color:inherit;font:15px system-ui}
.swarm-settings-dialog>.swarm-settings{width:100%;height:100%;min-height:0;overflow:auto;margin:0}
.swarm-settings-dialog::backdrop{background:#0009}
.swarm-settings-dialog :focus-visible{outline:2px solid #ff7a18;outline-offset:2px}
`;
document.head.append(style);
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
