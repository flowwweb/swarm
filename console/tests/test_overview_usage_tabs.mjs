import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../static/app.js', import.meta.url), 'utf8');
const start = source.indexOf('let overviewUsageView =');
const end = source.indexOf('function renderUsageCharts()', start);
assert.ok(start >= 0 && end > start);

const buttons = ['tokens', 'limits'].map(value => ({dataset: {overviewUsage: value}, setAttribute(name, value) { this[name] = value; }}));
let animations = 0;
const total = {textContent: '', animate() { animations += 1; }};
const note = {textContent: ''};
const graph = {hidden: false, setAttribute(name, value) { this[name] = value; }};
const host = {html: '', querySelector() { return this.html.includes('overview-usage-total') ? total : null; }, querySelectorAll() { return [{querySelector: () => total}]; }, set innerHTML(value) { this.html = value; }, get innerHTML() { return this.html; }};
const elements = {'#overview-usage-content': host, '#overview-usage-total': total, '#overview-usage-note': note, '#overview-usage-graph': graph};
const state = {usageStatus: 'current', usageScopeKey: 'scope', usageHistory: {ok: true, account_limits: {account_key: 'account'}, usage_now: {status: 'observed', source: 'persisted_local_token_deltas', tokens: 120}}, profile: {preferences: {reduced_motion: false}}};
const limit = {status: 'KNOWN', limit_id: 'main', window: 'primary', reset_at_ms: 9000, remaining_percent: 70};
const sandbox = {state, $: key => elements[key], $$: () => buttons, usageRequestKey: () => 'scope',
  compactMetricNumber: String, usageRangeLabel: () => 'last hour', usageHistorySeries: () => [20, 100],
  accountUsageDetails: () => '<section>Real account limits</section>', accountUsageDisplayWindows: () => [limit], drawLine: () => {},
  window: {matchMedia: () => ({matches: false})}};
vm.createContext(sandbox);
vm.runInContext(source.slice(start, end) + '\nglobalThis.setView = value => { overviewUsageView = value; }; globalThis.render = renderOverviewUsage;', sandbox);
sandbox.render();
assert.equal(total.textContent, '120');
assert.equal(note.textContent, 'Observed · last hour');
assert.equal(animations, 0);
state.usageHistory.usage_now.tokens = 230;
sandbox.render();
assert.equal(total.textContent, '230');
assert.equal(animations, 1, 'only a changed observed count animates');
state.profile.preferences.reduced_motion = true;
state.usageHistory.usage_now.tokens = 300;
sandbox.render();
assert.equal(total.textContent, '300');
assert.equal(animations, 1, 'reduced motion suppresses animation');
sandbox.setView('limits');
sandbox.render();
assert.equal(host.innerHTML, '<section>Real account limits</section>');
assert.equal(buttons[1]['aria-pressed'], 'true');
state.profile.preferences.reduced_motion = false;
limit.remaining_percent = 65;
sandbox.render();
assert.equal(animations, 2, 'only a changed observed limit animates');
sandbox.setView('tokens');
state.usageStatus = 'error';
sandbox.render();
assert.equal(total.textContent, '—');
assert.equal(note.textContent, 'Token usage is unavailable for this period.');
assert.equal(graph.hidden, true);

const graphStart = source.indexOf('function accountUsageGraph(');
const graphEnd = source.indexOf('function renderAccountUsage(', graphStart);
assert.ok(graphStart >= 0 && graphEnd > graphStart);
const graphSandbox = {};
vm.createContext(graphSandbox);
vm.runInContext(source.slice(graphStart, graphEnd), graphSandbox);
const windowRow = {reset_at_ms: 4000, history: [{sampled_at_ms: 1000, remaining_percent: 80}, {sampled_at_ms: 2000, remaining_percent: 40}], forecast: {status: 'ESTIMATED', exhaustion_at_ms: 3000}};
const plotted = graphSandbox.accountUsageGraph(windowRow);
assert.match(plotted, /0\.00,5\.60 80\.00,16\.80/, 'lower remaining values plot lower');
assert.match(plotted, /stroke-dasharray="3 3"/, 'eligible forecast is dashed');
windowRow.forecast.exhaustion_at_ms = 5000;
assert.doesNotMatch(graphSandbox.accountUsageGraph(windowRow), /stroke-dasharray/, 'do not forecast past reset');
assert.equal(graphSandbox.accountUsageGraph({history: [windowRow.history[0]]}), '', 'one observation does not invent a trend');
const gapped = {reset_at_ms: 900000, history: [
  {sampled_at_ms: 1000, remaining_percent: 80}, {sampled_at_ms: 2000, remaining_percent: 75},
  {sampled_at_ms: 302000, remaining_percent: 55}, {sampled_at_ms: 303000, remaining_percent: 50},
], forecast: {status: 'ESTIMATED', exhaustion_at_ms: 600000}};
const separated = graphSandbox.accountUsageGraph(gapped);
assert.equal((separated.match(/<polyline /g) || []).length, 2, 'a gap separates observed lines');
assert.match(separated, /0\.00,5\.60 0\.53,7\.00/);
assert.match(separated, /159\.47,12\.60 160\.00,14\.00/);
assert.doesNotMatch(separated, /stroke-dasharray/, 'a gap withholds the forecast');
const sparse = graphSandbox.accountUsageGraph({...gapped, history: [gapped.history[0], gapped.history[2]]});
assert.equal((sparse.match(/<circle /g) || []).length, 2, 'isolated downsampled observations remain visible');
assert.doesNotMatch(sparse, /<polyline|stroke-dasharray/, 'do not connect across gaps or forecast');
console.log('PASS overview usage tabs, observed counts, unavailable state and reduced motion');
