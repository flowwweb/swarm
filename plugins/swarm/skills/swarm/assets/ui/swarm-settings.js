// Embedded Settings uses the existing MCP client and canonical text editor supplied by HQ.
export function mountSettings(root, {app, scope = {type: 'global'}, scopes = [], hostModels = [], modelOrder = [], editText}) {
  const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const valueAt = (value, key) => key.split('.').reduce((part, name) => part?.[name], value);
  let projection, draft = {}, busy = false, generation = 0, retry = null;
  root.classList.add('swarm-settings');
  root.innerHTML = '<header><h1>Settings</h1><p>Choose how SWARM works.</p></header><label class="settings-scope">Apply to<select aria-label="Settings scope"></select></label><form><fieldset disabled><legend>Essentials</legend><div data-fields></div></fieldset><section><h2>Jev</h2><p>Unconfigured. No credentials requested.</p></section><section><h2>Blocker options</h2><p>Experimental actions are off.</p></section><footer><p role="status" aria-live="polite"></p><div><button type="button" data-reload>Reload</button><button type="button" data-revert>Revert</button><button type="submit">Save changes</button></div></footer></form>';
  const form = root.querySelector('form'), fields = root.querySelector('[data-fields]');
  const status = root.querySelector('[role=status]'), picker = root.querySelector('select');
  const choices = [{label: 'Global defaults', scope: {type: 'global'}}, ...scopes];
  if (!choices.some(choice => equal(choice.scope, scope))) choices.push({label: 'Current project', scope});
  choices.forEach((choice, index) => picker.add(new Option(choice.label, String(index))));
  picker.value = String(choices.findIndex(choice => equal(choice.scope, scope)));
  function controls() {
    const dirty = Object.keys(draft).length > 0;
    picker.disabled = busy || dirty;
    root.querySelector('fieldset').disabled = busy || projection?.state !== 'KNOWN';
    form.querySelector('[type=submit]').disabled = busy || !dirty || projection?.available !== true || projection?.write_contract?.method !== 'POST' || retry?.exhausted === true;
    form.querySelector('[data-revert]').disabled = busy || !dirty || !!retry;
    form.querySelector('[data-reload]').disabled = busy;
    form.querySelector('[type=submit]').textContent = busy ? 'Saving…' : retry ? 'Retry save' : 'Save changes';
  }
  async function call(name, args) {
    const result = await app.callServerTool({name, arguments: args});
    if (result?.isError || !result?.structuredContent) throw new Error('Settings could not be confirmed. Your changes are preserved.');
    return result.structuredContent;
  }
  function render() {
    fields.replaceChildren();
    const settings = projection?.effective_settings || {};
    const profile = settings.execution?.usage_profile;
    const policyEnabled = projection?.descriptors?.some(row => row.key === 'execution.model_order' && row.editable);
    const defaultKey = policyEnabled ? 'execution.default_model' : `models.${profile}.task_model`;
    const selectedModel = (draft[defaultKey] ?? valueAt(settings, defaultKey)) || settings.models?.[profile]?.task_model;
    // Configured capability declarations are not evidence of host availability.
    const models = hostModels.length ? hostModels : Object.entries(settings.model_capabilities || {}).map(([id, capability]) => ({id, reasoning: capability.reasoning || []}));
    const order = draft['execution.model_order'] ?? settings.execution?.model_order ?? modelOrder;
    const rows = [
      ['Fast', 'execution.fast_mode', 'boolean', 'Request Fast service when available.'],
      ['Usage Saver', 'execution.usage_saver', 'boolean', 'Reduce avoidable coordination work.'],
      ...(policyEnabled ? [['Model order', 'execution.model_order', 'order', 'Lowest to highest, comma-separated configured model IDs. This is your routing preference, not a claim of host availability.']] : []),
      ['Default model', defaultKey, 'model', 'Default for new tasks. Explicit role and task choices remain unchanged.'],
      ['Minimum model', 'execution.min_model', 'model', 'Lower routing bound.'],
      ['Maximum model', 'execution.max_model', 'model', 'Upper routing bound.'],
      ['Reasoning', `models.${profile}.task_reasoning`, 'reasoning', 'Default for new tasks; current conversations are unchanged.'],
    ];
    for (const [label, key, kind, help] of rows) {
      const descriptor = projection?.descriptors?.find(row => row.key === key);
      const current = Object.hasOwn(draft, key) ? draft[key] : valueAt(settings, key);
      const row = document.createElement('div'); row.className = 'settings-row';
      const labelNode = document.createElement('label'); labelNode.textContent = label;
      const hint = document.createElement('small'); hint.textContent = help;
      const control = document.createElement(kind === 'boolean' || kind === 'order' ? 'input' : 'select');
      control.id = `setting-${key}`; labelNode.htmlFor = control.id; control.dataset.key = key;
      if (kind === 'boolean') { control.type = 'checkbox'; control.checked = current === true; }
      else if (kind === 'order') { control.type = 'text'; control.value = order.join(', '); control.placeholder = 'Enter model IDs in your preferred order'; }
      else {
        const values = kind === 'model' ? models.map(model => model.id) : models.find(model => model.id === selectedModel)?.reasoning || [];
        if (current != null && !values.includes(current)) control.add(new Option(current === '' ? 'Use existing profile' : `${current} (unavailable)`, current));
        if (current == null) control.add(new Option('Not configured', ''));
        values.forEach(value => control.add(new Option(value, value)));
        control.value = current ?? '';
      }
      const bounded = key === 'execution.min_model' || key === 'execution.max_model';
      control.disabled = !descriptor?.editable || ['model', 'reasoning'].includes(kind) && !models.length || bounded && !policyEnabled && !modelOrder.length;
      if (control.disabled) hint.textContent = bounded ? 'Routing bounds are unavailable until a supported policy is provided.' : 'Unavailable from the current settings or host capability.';
      control.addEventListener('change', () => {
        const value = kind === 'boolean' ? control.checked : kind === 'order' ? control.value.split(',').map(value => value.trim()).filter(Boolean) : control.value;
        if (equal(value, valueAt(settings, key))) delete draft[key]; else draft[key] = value;
        // Uncertain writes must be reconciled before a different operation is submitted.
        status.textContent = retry ? 'Reload to reconcile the previous save before changing this request.' : 'Unsaved changes';
        controls();
        if (key === defaultKey) { render(); root.querySelector(`[data-key="${key}"]`).focus(); }
      });
      row.append(labelNode, hint, control); fields.append(row);
    }
    controls();
  }
  async function load() {
    const token = ++generation, requestedScope = structuredClone(scope);
    // A failed read revokes the old write authority, never the user's draft.
    projection = null;
    busy = true; controls(); status.textContent = 'Loading settings…';
    try {
      const next = await call('swarm_settings_read', {scope: requestedScope});
      if (token !== generation) return;
      if (next.state !== 'KNOWN' || next.available !== true || !equal(next.scope, requestedScope) || !/^[a-f0-9]{64}$/.test(next.revision) || typeof next.editable_text !== 'string') throw new Error('Settings scope or revision could not be verified.');
      projection = next;
      // This confirms current state, not authorship or a missing operation receipt.
      // No POST, new operation identity or retry-budget reset is used to reconcile.
      const reconciled = retry && equal(next.scope, retry.payload.scope)
        && next.revision !== retry.payload.expected_revision
        && next.editable_text === retry.payload.text
        && Object.entries(draft).every(([key, value]) => equal(valueAt(next.effective_settings, key), value));
      if (reconciled) { retry = null; draft = {}; }
      status.textContent = reconciled ? 'Current settings match your requested changes. No save was repeated.' : retry ? 'Previous save remains uncertain. Your draft is preserved.' : Object.keys(draft).length ? 'Reloaded. Your unsaved changes are preserved.' : 'Preferences loaded. Current execution is unchanged.';
      render();
    } catch (error) { if (token === generation) status.textContent = error.message; }
    finally { if (token === generation) { busy = false; controls(); } }
  }
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (busy || projection?.state !== 'KNOWN' || !Object.keys(draft).length || retry?.exhausted) return;
    let request;
    try {
      const settings = projection.effective_settings, profile = settings.execution.usage_profile;
      const hasPolicy = projection.descriptors?.some(row => row.key === 'execution.model_order' && row.editable);
      const modelKeys = ['execution.min_model', hasPolicy ? 'execution.default_model' : `models.${profile}.task_model`, 'execution.max_model'];
      const models = modelKeys.map(key => draft[key] ?? valueAt(settings, key));
      const order = draft['execution.model_order'] ?? settings.execution?.model_order ?? modelOrder;
      if (models[0] || models[2] || hasPolicy && (models[1] || order.length)) {
        const ranks = models.map(model => order.indexOf(model));
        if (ranks.some(rank => rank < 0) || ranks[0] > ranks[1] || ranks[1] > ranks[2]) throw new Error('Choose a default model within the supported minimum and maximum.');
      }
      const text = editText(projection.editable_text, draft);
      if (retry && text !== retry.payload.text) throw new Error('Reload to reconcile the previous save before changing this request.');
      request = retry || {payload: {scope: structuredClone(scope), expected_revision: projection.revision, acknowledge: true, text, operation_id: crypto.randomUUID()}, attempts: 0};
      request.attempts++; busy = true; controls(); status.textContent = 'Saving…';
      const result = await call('swarm_settings_save', request.payload), receipt = result.mutation_receipt;
      if (result.state !== 'KNOWN' || !equal(result.scope, request.payload.scope) || !equal(receipt?.scope, request.payload.scope) || receipt?.action !== 'config_update' || receipt?.accepted !== true || receipt?.acknowledged !== true || typeof receipt?.replayed !== 'boolean' || receipt?.operation_id !== request.payload.operation_id || receipt?.expected_revision !== request.payload.expected_revision || result.revision !== receipt?.new_revision || !/^[a-f0-9]{64}$/.test(result.revision) || !Object.entries(draft).every(([key, value]) => equal(valueAt(result.effective_settings, key), value))) throw new Error('Save receipt did not match. Your changes are preserved.');
      projection = result; draft = {}; retry = null; render(); status.textContent = 'Saved. New work uses these preferences; current execution is unchanged.';
    } catch (error) {
      if (request) retry = {...request, exhausted: request.attempts >= 2};
      status.textContent = error.message + (retry?.exhausted ? ' Reload to reconcile before another save.' : '');
    } finally { busy = false; controls(); }
  });
  form.querySelector('[data-revert]').addEventListener('click', () => { if (busy || retry) return; draft = {}; render(); status.textContent = 'Unsaved changes reverted.'; });
  form.querySelector('[data-reload]').addEventListener('click', load);
  picker.addEventListener('change', () => { if (busy || Object.keys(draft).length) return; scope = structuredClone(choices[Number(picker.value)].scope); projection = null; load(); });
  return {ready: load()};
}
