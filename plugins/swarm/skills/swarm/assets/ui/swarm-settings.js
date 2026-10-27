// Illustrative only: backend resolve_task_presentation remains the validation authority.
// Keep this bounded preview in parity with the canonical formatter's golden cases.
export function namingExample(template, values, emoji, enabled) {
  const invalid = value => typeof value !== 'string' || [...value].length > 160 || /[\p{C}\p{Zl}\p{Zp}]/u.test(value.replaceAll('\u200d',''));
  if (invalid(template) || !template.trim() || Object.values(values).some(invalid) || invalid(emoji)) throw new Error('Use a single-line template, up to 160 characters.');
  const title = template.replace(/{{|}}|{([^{}]*)}|[{}]/g, (match, field) => {
    if (match === '{{') return '{'; if (match === '}}') return '}';
    if (field === 'created:MMM D') return 'Oct 27'; // Explicit example creation date: 2026-10-27.
    const key = field?.replace(/:$/, '');
    if (!['project','unit','role','responsibility'].includes(key)) throw new Error('Choose one of the available variables.');
    return values[key].trim();
  }).split('·').map(part => part.trim()).filter(Boolean).join(' · ');
  if (!title) throw new Error('The example title cannot be empty.');
  const hasIcon = /^\p{So}/u.test(title) || /^[#*0-9]\ufe0f?\u20e3/u.test(title);
  const result = enabled && emoji && !title.startsWith(emoji) && !hasIcon ? `${emoji} ${title}` : title;
  if ([...result].length > 160) throw new Error('The example title exceeds 160 characters.');
  return result;
}

// Embedded Settings uses the existing MCP client and canonical text editor supplied by HQ.
export function mountSettings(root, {app, scope = {type: 'global'}, scopes = [], hostModels = [], modelOrder = [], editText}) {
  const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const valueAt = (value, key) => key.split('.').reduce((part, name) => part?.[name], value);
  let projection, draft = {}, busy = false, generation = 0, retry = null;
  root.classList.add('swarm-settings');
  root.innerHTML = `<header><div><h1>Settings</h1><p>Choose how SWARM works.</p></div><label class="settings-scope">Apply to<select aria-label="Settings scope"></select></label></header>
    <label class="settings-search">Search settings<input type="search" placeholder="Search all settings, including Advanced" aria-label="Search settings"></label>
    <form><div class="settings-layout"><nav aria-label="Settings sections"><button type="button" data-section="essentials" aria-pressed="true">Essentials</button><button type="button" data-section="advanced" aria-pressed="false">Advanced</button></nav>
    <div class="settings-content"><fieldset data-section="essentials" disabled><legend>Essentials</legend><div data-fields></div></fieldset>
    <fieldset data-section="advanced" hidden disabled><legend>Task naming &amp; pinning</legend><p id="naming-availability">Task naming and Auto-pin are unavailable until host support is verified.</p>
    <p class="naming-variables">Available variables: <code>{project}</code> <code>{unit}</code> <code>{role}</code> <code>{responsibility}</code> <code>{created:MMM D}</code></p>
    <p class="quiet" data-emoji-note></p><div data-naming></div><p class="naming-help">Examples use an imaginary project created Oct 27, 2026.</p></fieldset>
    <p data-search-empty hidden>No settings match. Try a category, variable or setting name.</p></div></div>
    <footer><p role="status" aria-live="polite"></p><div><button type="button" data-reload>Reload</button><button type="button" data-revert>Revert</button><button type="submit">Save changes</button></div></footer></form>`;
  const form = root.querySelector('form'), fields = root.querySelector('[data-fields]');
  const status = root.querySelector('[role=status]'), picker = root.querySelector('select');
  const search = root.querySelector('[type=search]');
  const choices = [{label: 'Global defaults', scope: {type: 'global'}}, ...scopes];
  if (!choices.some(choice => equal(choice.scope, scope))) choices.push({label: 'Current project', scope});
  choices.forEach((choice, index) => picker.add(new Option(choice.label, String(index))));
  picker.value = String(choices.findIndex(choice => equal(choice.scope, scope)));
  function controls() {
    const dirty = Object.keys(draft).length > 0;
    picker.disabled = busy || dirty;
    form.querySelectorAll('fieldset').forEach(fieldset => { fieldset.disabled = busy || projection?.state !== 'KNOWN'; });
    form.querySelector('[type=submit]').disabled = busy || !dirty || projection?.available !== true || projection?.write_contract?.method !== 'POST' || retry?.exhausted === true || !!form.querySelector('input:invalid');
    form.querySelector('[data-revert]').disabled = busy || !dirty || !!retry;
    form.querySelector('[data-reload]').disabled = busy;
    form.querySelector('[type=submit]').textContent = busy ? 'Saving…' : retry ? 'Retry save' : 'Save changes';
  }
  function change(key, value) {
    if (equal(value, valueAt(projection.effective_settings, key))) delete draft[key]; else draft[key] = value;
    status.textContent = retry ? 'Reload to reconcile the previous save before changing this request.' : Object.keys(draft).length ? 'Unsaved changes' : 'No unsaved changes';
    controls();
  }
  function filter() {
    const query = search.value.trim().toLocaleLowerCase();
    const section = root.querySelector('[data-section][aria-pressed=true]').dataset.section;
    let visible = 0;
    form.querySelectorAll('fieldset').forEach(fieldset => {
      let matches = 0;
      fieldset.querySelectorAll('.settings-row,.naming-row').forEach(row => {
        const text = [fieldset.dataset.section, row.textContent, ...[...row.querySelectorAll('[data-key]')].map(input=>input.dataset.key)].join(' ').toLocaleLowerCase();
        row.hidden = !!query && !text.includes(query); if (!row.hidden) matches++;
      });
      fieldset.hidden = query ? matches === 0 : fieldset.dataset.section !== section;
      if (!fieldset.hidden) visible += matches;
    });
    root.querySelector('[data-search-empty]').hidden = !!visible;
  }
  search.addEventListener('input', filter);
  root.querySelectorAll('nav [data-section]').forEach(button => button.addEventListener('click', () => {
    root.querySelectorAll('nav [data-section]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));
    search.value = ''; filter();
  }));
  function renderNaming(settings) {
    const container = root.querySelector('[data-naming]'); container.replaceChildren();
    root.querySelector('[data-emoji-note]').textContent = settings.role_icons?.enabled === false ? 'Emoji are off globally. Category preferences are retained.' : '';
    for (const [category,label,pin,role] of [['controller','Controllers','tasks',''],['unit','Units','units',''],['lead','Leads','leads','Designer'],['worker','Workers','workers','Developer']]) {
      const row = document.createElement('div'); row.className = 'naming-row';
      const heading = document.createElement('h3'); heading.textContent = label; row.append(heading);
      const inputs = {};
      for (const [suffix,caption,key,kind] of [['template','Title template',`task_titles.${category}_template`,'text'],['emoji','Show emoji',`task_titles.${category}_show_emoji`,'checkbox'],['pin','Auto-pin',`lifecycle.pin_created_${pin}`,'checkbox']]) {
        const wrap = document.createElement('div'); wrap.className = `naming-${suffix}`;
        const name = document.createElement('label'); name.textContent = caption;
        const input = document.createElement('input'); input.type = kind; input.id = `setting-${key}`; input.dataset.key = key;
        input.setAttribute('aria-label', `${label} ${caption}`); name.htmlFor = input.id;
        const value = Object.hasOwn(draft,key) ? draft[key] : valueAt(settings,key);
        input.disabled = true;
        input.setAttribute('aria-describedby', 'naming-availability');
        input.title = 'Unavailable until host support is verified.';
        if (kind==='text') {input.value = typeof value==='string'?value:'';input.spellcheck=false;} else input.checked = value === true;
        wrap.append(name,input); row.append(wrap); inputs[suffix] = input;
      }
      const example = document.createElement('p'); example.className = 'naming-example'; example.id = `example-${category}`; example.setAttribute('aria-live','polite');
      inputs.template.setAttribute('aria-describedby', `naming-availability ${example.id}`); row.querySelector('.naming-template').append(example);
      function preview() {
        inputs.template.setCustomValidity(''); inputs.template.removeAttribute('aria-invalid');
        if (!projection?.descriptors?.some(item=>item.key===`task_titles.${category}_template` && item.type==='string') || typeof valueAt(settings,`task_titles.${category}_template`) !== 'string' || typeof valueAt(settings,`task_titles.${category}_show_emoji`) !== 'boolean' || typeof settings.role_icons?.enabled !== 'boolean') {example.textContent='Example unavailable in this settings scope.';return;}
        try {
          example.textContent = 'Example only: ' + namingExample(inputs.template.value,{project:'Example project',unit:category==='unit'?'Interface Lab':'',role,responsibility:category==='controller'?'':'UI'},'📋',settings.role_icons.enabled && inputs.emoji.checked);
        } catch (error) {inputs.template.setCustomValidity(error.message);inputs.template.setAttribute('aria-invalid','true');example.textContent=error.message;}
      }
      preview(); container.append(row);
    }
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
        change(key, value);
        if (key === defaultKey) { render(); root.querySelector(`[data-key="${key}"]`).focus(); }
      });
      row.append(labelNode, hint, control); fields.append(row);
    }
    renderNaming(settings); filter(); controls();
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
      projection = result; draft = {}; retry = null; render(); status.textContent = 'Saved.';
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
