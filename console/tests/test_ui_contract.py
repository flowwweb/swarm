"""Focused Settings projection contracts; no server or browser writes."""
import pathlib
import subprocess
import unittest


class SettingsAuthorityTests(unittest.TestCase):
    def test_settings_summary_tracks_current_scope_authority(self):
        app = pathlib.Path(__file__).resolve().parents[1] / "static" / "app.js"
        script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const app = fs.readFileSync(process.argv[1], 'utf8');
const state = { projectId: 'all', ctrlId: '', configStatus: 'current', settingsDraft: new Map() };
const grid = {};
const context = vm.createContext({ state, structuredClone, $: () => grid,
  selectedSettingsCtrl: () => null, settingsContextPresentation: () => ({title:'Scope',note:''}),
  settingsDraftValue: (_, value) => value, settingsThemeMarkup: () => '', settingsScopeOptions: () => '',
  settingsSwitch: () => '', descriptorBooleanSwitch: () => '', settingsSpeedMarkup: () => '', settingsTaskLifeMarkup: () => '',
  escapeHTML: value => String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;') });
for (const [start, end] of [
  ['function configWriteScope(', 'function configTomlLiteral('],
  ['function currentSettingsScope(', 'function settingsScopeOptions('],
  ['function settingsConfigSummary(', 'function renderSettings('],
  ['function renderSettings(', 'function renderAllViews('],
]) { const a=app.indexOf(start), b=app.indexOf(end,a); if(a>=0) vm.runInContext(app.slice(a,b),context); }
const projection = () => ({state:'KNOWN',available:true,scope:{type:'global'},revision:'a'.repeat(64),
  editable_text:'[automation]\nmode = "manual"',read_only:false,write_contract:{available:true}});
const render = () => { vm.runInContext('renderSettings()',context); return grid.innerHTML; };
state.config = projection();
assert.match(render(), /Global configuration · revision a{12} · Config text available/);
for(const status of ['stale','unavailable','loading']) {
  state.configStatus=status;
  assert.doesNotMatch(render(), /revision a{12}|Config text available/);
}
state.configStatus='current';
state.projectId='p1';
assert.match(render(), /Project configuration unavailable for this scope/);
state.config.scope={type:'project',project_id:'p1',accepted_cursor:{sequence:3}};
assert.match(render(), /Project configuration · revision a{12} · Config text available/);
delete state.config.scope.accepted_cursor;
assert.match(render(), /Project configuration unavailable for this scope/);
state.config.scope.accepted_cursor={sequence:3};
state.config.scope.project_id='p2';
assert.match(render(), /Project configuration unavailable for this scope/);
state.ctrlId='ctrl1';
assert.match(render(), /CTRL configuration unavailable for this scope/);
state.projectId='all'; state.ctrlId=''; state.config=projection();
state.config.read_only=true;
assert.match(render(), /Read-only/);
delete state.config.editable_text;
assert.match(render(), /Config text unavailable/);
for (const change of [{state:'UNKNOWN'}, {available:false}, {revision:null}]) {
  state.config={...projection(),...change};
  assert.doesNotMatch(render(), /revision a{12}|Config text available/);
}
state.config=projection(); state.settingsScopeType='project';state.settingsScopeId='p1';
assert.match(render(), /Project configuration unavailable for this scope/);
console.log('Settings authority: current, stale, unavailable, global/project/CTRL mismatch PASS');
'''
        result = subprocess.run(["node", "-e", script.replace("\n", " "), str(app)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Settings authority:", result.stdout)


if __name__ == "__main__":
    unittest.main()
