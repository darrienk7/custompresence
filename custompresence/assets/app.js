const form = document.querySelector('#form');
const feedback = document.querySelector('#feedback');
const headers = {'Content-Type':'application/json', 'X-Presence-Token':document.querySelector('meta[name="presence-token"]').content};
const activityLabels = {playing:'Playing', listening:'Listening to', watching:'Watching', competing:'Competing in'};
const advancedDialog = document.querySelector('#advanced-dialog');
const advancedMenu = document.querySelector('#advanced-menu');
let activeUpload = null, uploadEnabled = false;
const checkedLinks = new Map();

function setBusy(value) {
    for (const button of form.querySelectorAll('button')) button.disabled = value;
    for (const button of form.querySelectorAll('[data-upload]')) button.disabled = value || !uploadEnabled;
    for (const input of form.querySelectorAll('[data-file]')) input.disabled = value || !uploadEnabled;
    for (const button of form.querySelectorAll('[data-cancel-upload]')) button.disabled = false;
}
function showFeedback(message, error = false) {
    for (const element of [feedback, document.querySelector('#advanced-feedback')]) {
        element.className = error ? 'error' : '';
        element.textContent = message;
    }
}
function showUploadStatus(show) {
    for (const element of form.querySelectorAll('[data-upload-status]')) element.hidden = !show;
    if (show) for (const element of form.querySelectorAll('[data-upload-message]')) element.textContent = 'Preparing your image…';
}
async function api(path, options = {}) {
    const response = await fetch(path, {...options, cache:'no-store', headers:{...headers, ...options.headers}});
    const result = await response.json();
    if (!response.ok) {
        const error = new Error(Array.isArray(result.detail) ? result.detail.map(x => x.msg).join(' ') : result.detail || 'Request failed.');
        error.status = response.status; error.details = result.detail; throw error;
    }
    return result;
}
function localTime(seconds) {
    if (!seconds) return '';
    const date = new Date(seconds * 1000);
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0,19);
}
function integer(value) { return value === '' ? null : Number(value); }
function timestamp(id) {
    const value = document.querySelector(id).value;
    return value ? Math.floor(new Date(value).getTime() / 1000) : null;
}
function collect() {
    const data = Object.fromEntries(new FormData(form));
    data.name = data.name.trim();
    data.instance = form.elements.instance.checked;
    data.start = timestamp('#start-time');
    data.end = timestamp('#end-time');
    data.party_current = integer(data.party_current);
    data.party_max = integer(data.party_max);
    data.buttons = [];
    for (let i = 1; i <= 2; i++) {
        const label = data[`button_${i}_label`].trim(), url = data[`button_${i}_url`].trim();
        if (label || url) data.buttons.push({label, url});
        delete data[`button_${i}_label`]; delete data[`button_${i}_url`];
    }
    return data;
}
function restoreFields(saved) {
    form.reset();
    checkedLinks.clear();
    for (const receipt of form.querySelectorAll('[data-upload-receipt]')) {
        receipt.replaceChildren(); receipt.hidden = true;
    }
    for (const message of form.querySelectorAll('[data-image-feedback]')) message.textContent = '';
    for (const field of form.elements) {
        if (field.name && typeof saved[field.name] === 'string') field.value = saved[field.name];
    }
    form.elements.name.value = saved.name ?? '';
    form.elements.instance.checked = saved.instance !== false;
    for (const name of ['party_current','party_max']) form.elements[name].value = saved[name] ?? '';
    document.querySelector('#start-time').value = localTime(saved.start);
    document.querySelector('#end-time').value = localTime(saved.end);
    (saved.buttons || []).forEach((button, i) => {
        if (i < 2) { form.elements[`button_${i+1}_label`].value = button.label; form.elements[`button_${i+1}_url`].value = button.url; }
    });
    updateImageModes(); preview();
    for (const name of ['image','small_image']) {
        try {
            const host = new URL(form.elements[name].value).hostname;
            if (['giphy.com','www.giphy.com','tenor.com','www.tenor.com','imgur.com','www.imgur.com','m.imgur.com'].includes(host)) checkImage(name).catch(() => {});
        } catch {}
    }
}
function updateImageModes() {
    for (const select of form.querySelectorAll('[data-image-mode]')) {
        const target = select.dataset.imageMode;
        form.querySelector(`[data-upload-panel="${target}"]`).hidden = select.value !== 'upload';
        form.querySelector(`[data-link-panel="${target}"]`).hidden = select.value !== 'link';
    }
}
function showAdvancedPanel(name = null) {
    const button = [...form.querySelectorAll('[data-open-panel]')].find(item => item.dataset.openPanel === name);
    advancedMenu.hidden = Boolean(button);
    for (const panel of form.querySelectorAll('[data-advanced-panel]')) panel.hidden = !button || panel.dataset.advancedPanel !== name;
    document.querySelector('#advanced-back').hidden = !button;
    document.querySelector('#advanced-title').textContent = button ? button.querySelector('.option-title').textContent : 'Advanced options';
    document.querySelector('#advanced-description').textContent = button ? button.dataset.description : 'Choose what you’d like to customize.';
    advancedDialog.querySelector('.dialog-body').scrollTop = 0;
    if (advancedDialog.open) document.querySelector('#advanced-title').focus({preventScroll:true});
}
function showAdvanced(open, panel = null) {
    if (!open) {
        advancedDialog.close();
        document.documentElement.classList.remove('advanced-open');
        return;
    }
    showAdvancedPanel(panel);
    if (!advancedDialog.open) advancedDialog.showModal();
    document.documentElement.classList.add('advanced-open');
    document.querySelector('#advanced').setAttribute('aria-expanded', 'true');
    document.querySelector('#advanced-title').focus({preventScroll:true});
}
function panelForField(name) {
    if (name === 'buttons') return 'buttons';
    if (name === 'start' || name === 'end') return 'timer';
    return form.elements.namedItem(name)?.closest('[data-advanced-panel]')?.dataset.advancedPanel;
}
function setArt(element, url) {
    const valid = url.trim().startsWith('https://');
    element.hidden = !valid;
    if (valid && element.getAttribute('src') !== url.trim()) element.src = url.trim();
    if (!valid) element.removeAttribute('src');
    return valid;
}
function preview() {
    const data = collect();
    document.querySelector('#title').textContent = activityLabels[data.activity_type] + ' ' + data.name;
    document.querySelector('#details').textContent = data.details;
    const party = data.party_current && data.party_max ? ` (${data.party_current} of ${data.party_max})` : '';
    let state = data.state || (party ? 'In a party' : '');
    if (party && data.activity_type !== 'playing' && state.length + party.length > 128) {
        state = state.slice(0, 127 - party.length).replace(/[\uD800-\uDBFF]$/, '').trimEnd() + '…';
    }
    document.querySelector('#state').textContent = state + party;
    const art = document.querySelector('#art');
    document.querySelector('#placeholder').hidden = setArt(art, data.image);
    art.title = data.large_text;
    setArt(document.querySelector('#small-art'), data.small_image);
    document.querySelector('#small-art').title = data.small_text;
    const buttons = document.querySelector('#preview-buttons'); buttons.replaceChildren();
    for (const button of data.buttons) { const element = document.createElement('span'); element.textContent = button.label || 'Button'; buttons.append(element); }
    renderTimer();
}
function renderTimer() {
    const start = timestamp('#start-time'), end = timestamp('#end-time'), now = Math.floor(Date.now()/1000);
    const seconds = end ? Math.max(0, end-now) : start ? Math.max(0, now-start) : null;
    document.querySelector('#timer').textContent = seconds === null ? '' : `${Math.floor(seconds/3600).toString().padStart(2,'0')}:${Math.floor(seconds%3600/60).toString().padStart(2,'0')}:${(seconds%60).toString().padStart(2,'0')} ${end ? 'remaining' : 'elapsed'}`;
}
for (const id of ['art','small-art']) document.querySelector('#'+id).onerror = () => {
    document.querySelector('#'+id).hidden = true;
    if (id === 'art') document.querySelector('#placeholder').hidden = false;
};
form.addEventListener('input', preview);
form.addEventListener('change', () => { updateImageModes(); preview(); });
document.querySelector('#advanced').onclick = () => showAdvanced(true);
document.querySelector('#back-basic').onclick = () => showAdvanced(false);
document.querySelector('#close-advanced').onclick = () => showAdvanced(false);
document.querySelector('#advanced-back').onclick = () => showAdvancedPanel();
for (const button of form.querySelectorAll('[data-open-panel]')) button.onclick = () => showAdvancedPanel(button.dataset.openPanel);
advancedDialog.addEventListener('close', () => {
    if (advancedDialog.open) return;
    document.documentElement.classList.remove('advanced-open');
    document.querySelector('#advanced').setAttribute('aria-expanded', 'false');
    document.querySelector('#advanced').focus({preventScroll:true});
});

let showingInvalidField = false;
form.addEventListener('invalid', event => {
    event.preventDefault();
    if (showingInvalidField) return;
    showingInvalidField = true;
    const panel = event.target.closest('[data-advanced-panel]')?.dataset.advancedPanel;
    if (panel) showAdvanced(true, panel);
    showFeedback(event.target.validationMessage, true);
    event.target.focus();
    setTimeout(() => { showingInvalidField = false; }, 0);
}, true);
form.addEventListener('keydown', event => {
    if (event.key !== 'Enter' || event.isComposing || event.target.tagName !== 'INPUT' || ['file','checkbox'].includes(event.target.type)) return;
    event.preventDefault();
    const button = document.querySelector(advancedDialog.open ? '#advanced-apply' : '#apply-activity');
    if (!button.disabled) form.requestSubmit(button);
});
document.querySelector('#start-now').onclick = () => { document.querySelector('#start-time').value = localTime(Math.floor(Date.now()/1000)); renderTimer(); };
document.querySelector('#clear-timer').onclick = () => { document.querySelector('#start-time').value = ''; document.querySelector('#end-time').value = ''; renderTimer(); };

async function checkImage(target, quiet = false) {
    const field = form.elements[target], value = field.value.trim();
    const message = form.querySelector(`[data-image-feedback="${target}"]`);
    if (!value || !value.startsWith('https://')) return;
    if (!quiet) message.textContent = 'Checking the image…';
    try {
        const result = checkedLinks.get(value) || await api('/api/images/check', {method:'POST', body:JSON.stringify({url:value})});
        checkedLinks.set(value, result); checkedLinks.set(result.url, result);
        if (field.value.trim() !== value) return;
        field.value = result.url;
        message.textContent = `${result.converted ? 'Image link found. ' : ''}${result.format} · ${result.width} × ${result.height}. Ready to use.`;
        preview();
    } catch (error) { message.textContent = error.message; throw error; }
}
for (const button of form.querySelectorAll('[data-check]')) button.onclick = () => checkImage(button.dataset.check).catch(() => {});
for (const name of ['image','small_image']) form.elements[name].addEventListener('change', () => checkImage(name).catch(() => {}));

async function request(method) {
    setBusy(true); showFeedback(method === 'POST' ? 'Checking your artwork…' : 'Connecting to Discord…');
    try {
        if (method === 'POST') await Promise.all(['image','small_image'].map(name => checkImage(name, true)));
        const result = await api('/api/activity', {method, body:method === 'POST' ? JSON.stringify(collect()) : undefined}); showFeedback(result.message);
    }
    catch (error) {
        showFeedback(error.message, true);
        if (method === 'POST' && Array.isArray(error.details)) {
            const panel = error.details.map(item => panelForField(item.loc?.[1])).find(Boolean);
            if (panel) showAdvanced(true, panel);
            else if (error.details.some(item => !['name','image','image_mode','activity_type'].includes(item.loc?.[1]))) showAdvanced(true);
        }
    }
    finally { setBusy(false); }
}
form.addEventListener('submit', event => { event.preventDefault(); request('POST'); });
document.querySelector('#stop').onclick = () => request('DELETE');
document.querySelector('#reset-settings').onclick = async () => {
    setBusy(true);
    try { await api('/api/settings', {method:'DELETE'}); restoreFields({}); showFeedback('Saved settings removed. Already uploaded images remain with their host.'); }
    catch (error) { showFeedback(error.message, true); }
    finally { setBusy(false); }
};
document.querySelector('#forget-uploads').onclick = async () => {
    setBusy(true);
    try { const result = await api('/api/images/cache', {method:'DELETE'}); showFeedback(result.message); }
    catch (error) { showFeedback(error.message, true); }
    finally { setBusy(false); }
};
async function cancelUpload() {
    if (activeUpload) activeUpload.abort(); activeUpload = null;
    showUploadStatus(false);
    setBusy(false); showFeedback('Upload cancelled in this app. A file already received by ImgBB may still be hosted there.');
}
for (const button of form.querySelectorAll('[data-cancel-upload]')) button.onclick = cancelUpload;
for (const button of form.querySelectorAll('[data-upload]')) button.onclick = () => form.querySelector(`[data-file="${button.dataset.upload}"]`).click();
for (const input of form.querySelectorAll('[data-file]')) input.onchange = async () => {
    const file = input.files[0]; if (!file) return;
    if (file.size > 8 * 1024 * 1024) { showFeedback('Choose an image or GIF up to 8 MB.', true); input.value = ''; return; }
    setBusy(true);
    const controller = new AbortController(); activeUpload = controller;
    showUploadStatus(true); showFeedback('');
    try {
        const result = await api('/api/images', {method:'POST', body:file, headers:{'Content-Type':'application/octet-stream'}, signal:controller.signal});
        if (activeUpload !== controller) return;
        form.elements[input.dataset.file].value = result.url;
        checkedLinks.set(result.url, result);
        const receipt = form.querySelector(`[data-upload-receipt="${input.dataset.file}"]`);
        receipt.replaceChildren(document.createTextNode(result.reused ? 'Reused your existing upload. ' : 'Uploaded. ')); receipt.hidden = false;
        if (result.delete_url) {
            const link = document.createElement('a'); link.href = result.delete_url; link.target = '_blank'; link.rel = 'noreferrer';
            link.textContent = 'Keep this removal link'; receipt.append(link);
        }
        preview();
        showFeedback(result.remembered === false ? 'Image linked, but it could not be remembered for next time.' :
            result.reused ? 'Existing upload reused. Click Apply activity to use it.' : 'Image uploaded and linked. Click Apply activity to use it.');
    } catch (error) { if (activeUpload === controller) showFeedback(error.message, true); }
    finally {
        input.value = '';
        if (activeUpload === controller) { activeUpload = null; showUploadStatus(false); setBusy(false); }
    }
};
setInterval(renderTimer, 1000);
restoreFields({});
setBusy(true);
Promise.all([
    api('/api/settings').then(restoreFields),
    api('/api/uploads/config').then(config => {
        uploadEnabled = config.enabled;
        if (!config.enabled) for (const hint of form.querySelectorAll('[data-upload-hint]')) hint.textContent = 'Uploads are not enabled in this build yet. Choose Paste public link to add artwork.';
    })
]).catch(error => showFeedback(error.message,true)).finally(() => setBusy(false));
updateImageModes(); preview();
