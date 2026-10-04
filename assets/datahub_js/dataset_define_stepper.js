(function () {
  'use strict';

  const config = window.DataHubWorkflow || {messages: {}};
  const CHUNK_SIZE = 5 * 1024 * 1024;
  const state = {files: [], batchId: null, datasetId: null, complete: false, uploading: false, tagify: null};
  const $ = id => document.getElementById(id);
  const message = (key, fallback) => config.messages[key] || fallback;

  function getCookie(name) {
    return document.cookie.split(';').map(v => v.trim()).find(v => v.indexOf(name + '=') === 0)?.slice(name.length + 1) || '';
  }
  function csrfToken() { return decodeURIComponent(getCookie('csrftoken')) || config.csrfToken || ''; }
  function escapeHtml(value) { return String(value || '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
  function formatBytes(bytes) { if (!bytes) return '0 B'; const units = ['B','KB','MB','GB','TB']; const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1); return `${(bytes / Math.pow(1024, i)).toFixed(i ? 1 : 0)} ${units[i]}`; }
  function isArchive(file) { return /\.(zip|tar|tgz|gz|bz2|xz|7z|rar)$/i.test(file.name); }
  function relativePath(file) { return file.webkitRelativePath || file.name; }
  function openFilePicker(inputId) {
    const input = $(inputId);
    if (!input) return;
    try {
      if (typeof input.showPicker === 'function') input.showPicker();
      else input.click();
    } catch (error) {
      // Some browsers reject showPicker for hidden controls; click() remains
      // supported when called directly from the user's button event.
      input.click();
    }
  }

  async function loadTags() {
    const input = $('dataset_tags');
    if (!input || typeof Tagify === 'undefined') return;
    let whitelist = [];
    try { const response = await fetch(config.tagsUrl); if (response.ok) whitelist = await response.json(); } catch (error) { console.debug('Tag suggestions unavailable', error); }
    state.tagify = new Tagify(input, {whitelist, duplicates: false, dropdown: {enabled: 1, maxItems: 20, closeOnSelect: false}, editTags: true});
    $('add-dataset-tag')?.addEventListener('click', () => state.tagify.addEmptyTag());
  }
  function getTags() {
    if (state.tagify) return state.tagify.value.map(item => item.value).join(',');
    try { return JSON.parse($('dataset_tags')?.value || '[]').map(item => item.value).join(','); } catch (error) { return $('dataset_tags')?.value || ''; }
  }
  function metadata() {
    return {
      dataset_name: $('dataset_name')?.value.trim(), dataset_owner: $('dataset_owner')?.value.trim(),
      dataset_language: Array.from($('dataset_language')?.selectedOptions || []).map(o => o.value).join(','),
      dataset_license: $('dataset_license')?.value || '', dataset_format: $('dataset_format')?.value || '',
      dataset_recordsNum: $('dataset_recordsNum')?.value || '0', dataset_price: $('dataset_price')?.value || '0',
      dataset_requestRequired: $('dataset_requestRequired')?.value || 'No', dataset_desc: $('dataset_desc')?.value || '',
      dataset_tags: getTags(), dataset_columnDataType: []
    };
  }
  function addFiles(fileList) {
    Array.from(fileList || []).forEach(file => {
      const path = relativePath(file); const key = `${path}:${file.size}:${file.lastModified}`;
      if (!state.files.some(item => item.key === key)) state.files.push({file, key, path, status: 'waiting'});
    });
    renderFiles();
  }
  function renderFiles() {
    const queue = $('file-queue'); if (!queue) return;
    const total = state.files.reduce((sum, item) => sum + item.file.size, 0);
    $('file-count').textContent = state.files.length; $('file-size').textContent = formatBytes(total);
    if (!state.files.length) { queue.innerHTML = `<div class="inspection-empty">${escapeHtml(message('chooseFilesFirst', 'Choose at least one file or folder.'))}</div>`; return; }
    queue.innerHTML = state.files.map((item, index) => `<div class="file-row"><i class="ti ${isArchive(item.file) ? 'ti-file-zip' : 'ti-file'} text-primary"></i><div class="file-name"><strong>${escapeHtml(item.file.name)} ${isArchive(item.file) ? `<span class="summary-pill">${escapeHtml(message('archive', 'Archive'))}</span>` : ''}</strong><span class="file-path">${escapeHtml(item.path)}</span></div><span class="file-size">${formatBytes(item.file.size)}</span><span class="file-status text-muted">${escapeHtml(item.status)}</span><button class="btn btn-sm btn-icon btn-label-danger" data-remove-file="${index}" type="button" title="${escapeHtml(message('remove', 'Remove'))}"><i class="ti ti-x"></i></button></div>`).join('');
    queue.querySelectorAll('[data-remove-file]').forEach(button => button.addEventListener('click', () => { if (!state.uploading) { state.files.splice(Number(button.dataset.removeFile), 1); renderFiles(); } }));
  }
  function renderUploadQueue() {
    const queue = $('upload-file-queue'); if (!queue) return;
    queue.innerHTML = state.files.map((item, index) => `<div class="file-row" id="upload-file-${index}"><i class="ti ti-file text-primary"></i><div class="file-name"><strong>${escapeHtml(item.file.name)}</strong><span class="file-path">${escapeHtml(item.path)}</span></div><span class="file-size">${formatBytes(item.file.size)}</span><span class="file-status text-muted">${escapeHtml(item.status)}</span></div>`).join('');
  }
  function setFileStatus(index, status) { if (state.files[index]) state.files[index].status = status; const row = $(`upload-file-${index}`); if (row) row.querySelector('.file-status').textContent = status; renderFiles(); }
  function setProgress(percent, text, error) { const bar = $('upload-progress'); if (!bar) return; bar.style.width = `${percent}%`; bar.setAttribute('aria-valuenow', String(Math.round(percent))); bar.classList.toggle('bg-danger', !!error); bar.classList.toggle('bg-success', !error && percent >= 100); $('upload-progress-text').textContent = text; }

  async function createBatch() {
    const response = await fetch(config.createBatchUrl, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()}, body: JSON.stringify({metadata: metadata(), files: state.files.map(item => ({name: item.file.name, relative_path: item.path, size: item.file.size}))})});
    const data = await response.json().catch(() => ({})); if (!response.ok || data.status !== 'success') throw new Error(data.message || `Batch creation failed (${response.status})`);
    state.batchId = data.batch_id; state.datasetId = data.dataset_id; return data;
  }
  async function sendFileChunked(fileItem, index, totalBytes, uploadedBefore) {
    const file = fileItem.file; const chunks = Math.max(1, Math.ceil(file.size / CHUNK_SIZE)); let uploadId = null;
    for (let chunkNumber = 0; chunkNumber < chunks; chunkNumber += 1) {
      const start = chunkNumber * CHUNK_SIZE; const chunk = file.slice(start, Math.min(start + CHUNK_SIZE, file.size)); const body = new FormData();
      body.append('file', chunk, file.name); body.append('chunkNumber', String(chunkNumber)); body.append('totalChunks', String(chunks)); body.append('uploadId', uploadId || ''); body.append('batchId', state.batchId); body.append('relativePath', fileItem.path); body.append('fileName', file.name); body.append('fileSize', String(file.size)); body.append('fileType', file.type || 'application/octet-stream');
      if (chunkNumber === 0) body.append('metadata', JSON.stringify({relative_path: fileItem.path, original_name: file.name}));
      const response = await fetch(config.uploadUrl, {method: 'POST', headers: {'X-CSRFToken': csrfToken()}, body}); const data = await response.json().catch(() => ({}));
      if (!response.ok || data.status !== 'success') throw new Error(data.message || `Chunk ${chunkNumber + 1} failed`); uploadId = data.upload_id || uploadId;
      const uploaded = uploadedBefore + start + chunk.size; setProgress(totalBytes ? (uploaded / totalBytes) * 100 : 100, `${message('uploading', 'Uploading ...')} ${index + 1}/${state.files.length}`);
    }
    const final = await fetch(`${config.uploadUrl}?finalize=true&uploadId=${encodeURIComponent(uploadId)}`, {method: 'POST', headers: {'X-CSRFToken': csrfToken()}}); const result = await final.json().catch(() => ({}));
    if (!final.ok || result.status !== 'success') throw new Error(result.message || 'Finalization failed'); return result;
  }
  async function sendFileDirect(fileItem, index, totalBytes, uploadedBefore) {
    const file = fileItem.file;
    if (!file.size) throw new Error(`${file.name}: empty files cannot use multipart upload`);
    let session = null;
    let completionStarted = false;
    try {
      const sessionResponse = await fetch(config.directCreateUrl, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()}, body: JSON.stringify({batch_id: state.batchId, file_name: file.name, relative_path: fileItem.path, file_size: file.size, content_type: file.type || 'application/octet-stream'})});
      session = await sessionResponse.json().catch(() => ({}));
      if (!sessionResponse.ok || session.status !== 'success') throw new Error(session.message || 'Could not create multipart upload');
      const parts = [];
      for (let partNumber = 1; partNumber <= session.total_parts; partNumber += 1) {
        const start = (partNumber - 1) * session.part_size;
        const chunk = file.slice(start, Math.min(start + session.part_size, file.size));
        const urlResponse = await fetch(config.directPartUrl, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()}, body: JSON.stringify({upload_id: session.upload_id, part_number: partNumber})});
        const urlData = await urlResponse.json().catch(() => ({}));
        if (!urlResponse.ok || urlData.status !== 'success') throw new Error(urlData.message || `Could not create URL for part ${partNumber}`);
        const uploadResponse = await fetch(urlData.url, {method: 'PUT', body: chunk});
        if (!uploadResponse.ok) throw new Error(`Direct upload failed for part ${partNumber}`);
        const etag = uploadResponse.headers.get('ETag') || uploadResponse.headers.get('etag');
        if (!etag) throw new Error('Storage did not return an ETag; configure S3 CORS to expose ETag');
        parts.push({part_number: partNumber, etag});
        const uploaded = uploadedBefore + start + chunk.size;
        setProgress(totalBytes ? (uploaded / totalBytes) * 100 : 100, `${message('uploading', 'Uploading ...')} ${index + 1}/${state.files.length}`);
      }
      completionStarted = true;
      const completeResponse = await fetch(config.directCompleteUrl, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()}, body: JSON.stringify({upload_id: session.upload_id, parts})});
      const result = await completeResponse.json().catch(() => ({}));
      if (!completeResponse.ok || result.status !== 'success') throw new Error(result.message || 'Multipart completion failed');
      return result;
    } catch (error) {
      if (session?.upload_id && !completionStarted && config.directAbortUrl) {
        fetch(config.directAbortUrl, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()}, body: JSON.stringify({upload_id: session.upload_id})}).catch(() => {});
      }
      error.directUploadRecoverable = !completionStarted;
      throw error;
    }
  }
  async function sendFile(fileItem, index, totalBytes, uploadedBefore) {
    if (!config.directUploadEnabled) return sendFileChunked(fileItem, index, totalBytes, uploadedBefore);
    try {
      return await sendFileDirect(fileItem, index, totalBytes, uploadedBefore);
    } catch (error) {
      if (!config.directUploadFallback || !error.directUploadRecoverable) throw error;
      setFileStatus(index, message('uploading', 'Uploading ...'));
      return sendFileChunked(fileItem, index, totalBytes, uploadedBefore);
    }
  }
  async function startUpload() {
    if (state.uploading || state.complete) return; if (!state.files.length) { alert(message('chooseFilesFirst', 'Choose at least one file or folder.')); return; }
    state.uploading = true; $('btn_start_upload').disabled = true; renderUploadQueue(); $('upload-status').textContent = message('uploadStarted', 'Upload started');
    try {
      if (!state.batchId) await createBatch();
      const totalBytes = state.files.reduce((sum, item) => sum + item.file.size, 0); let uploadedBefore = state.files.reduce((sum, item) => sum + (item.status === 'complete' ? item.file.size : 0), 0);
      for (let index = 0; index < state.files.length; index += 1) {
        if (state.files[index].status === 'complete') continue;
        setFileStatus(index, 'uploading'); await sendFile(state.files[index], index, totalBytes, uploadedBefore); uploadedBefore += state.files[index].file.size; setFileStatus(index, 'complete');
      }
      state.complete = true; setProgress(100, message('batchComplete', 'All files uploaded; quality checks are processing.')); $('upload-status').textContent = message('batchComplete', 'All files uploaded; quality checks are processing.'); $('inspection-summary').textContent = message('batchComplete', 'All files uploaded; quality checks are processing.'); $('inspection-summary').className = 'alert alert-success'; renderInspection();
      // Upload completion is the gate for the inspection/QC stage. Move the
      // wizard forward only after every source asset has completed.
      if (typeof window.DataHubWorkflowNext === 'function') window.DataHubWorkflowNext();
    } catch (error) { $('upload-status').textContent = error.message; setProgress(Number($('upload-progress')?.getAttribute('aria-valuenow') || 0), error.message, true); alert(`${message('uploadFailed', 'Upload failed.')} ${error.message}`); } finally { state.uploading = false; $('btn_start_upload').disabled = state.complete; }
  }
  function renderInspection() {
    const tbody = document.querySelector('#tb_metadata tbody'); if (!tbody) return; tbody.innerHTML = state.files.map(item => `<tr><td><strong>${escapeHtml(item.file.name)}</strong><div class="small text-muted">${escapeHtml(item.path)}</div></td><td>${escapeHtml(item.file.type || 'unknown')}</td><td>${formatBytes(item.file.size)}</td><td><span class="badge bg-label-success">${escapeHtml(item.status)}</span></td></tr>`).join('');
  }
  async function saveAccessAndOpen() {
    if (!window.DataHubWorkflowValidateStep(5)) return;
    if (!state.batchId || !config.updateBatchUrl) { alert(message('batchComplete', 'Dataset submitted.')); return; }
    const response = await fetch(config.updateBatchUrl, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()}, body: JSON.stringify({
      batch_id: state.batchId, dataset_recordsNum: $('dataset_recordsNum')?.value || '0', dataset_price: $('dataset_price')?.value || '0', dataset_requestRequired: $('dataset_requestRequired')?.value || 'No'
    })});
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.status !== 'success') throw new Error(data.message || 'Could not save access settings');
    if (state.datasetId && config.datasetDetailUrl) window.location.href = config.datasetDetailUrl.replace('__DATASET_ID__', state.datasetId);
  }
  window.DataHubWorkflowValidateStep = function (step) {
    if (step === 1 && !$('dataset_name')?.value.trim()) { $('dataset_name')?.focus(); return false; }
    if (step === 2 && !state.files.length) { alert(message('chooseFilesFirst', 'Choose at least one file or folder.')); return false; }
    if (step === 3 && !state.complete) { alert(message('uploadStarted', 'Start the upload before continuing.')); return false; }
    if (step === 5 && !$('question_verify')?.checked) { alert(message('verify', 'Please confirm that you agree to submit the dataset.')); return false; }
    return true;
  };
  function initializeWorkflow() {
    loadTags();
    renderFiles();
    $('choose-files')?.addEventListener('click', event => { event.preventDefault(); openFilePicker('dataset_file'); });
    $('choose-folder')?.addEventListener('click', event => { event.preventDefault(); openFilePicker('dataset_folder'); });
    $('dataset_file')?.addEventListener('change', event => { addFiles(event.target.files); event.target.value = ''; });
    $('dataset_folder')?.addEventListener('change', event => { addFiles(event.target.files); event.target.value = ''; });
    $('btn_start_upload')?.addEventListener('click', startUpload);
    $('btn_upload_dataset')?.addEventListener('click', () => saveAccessAndOpen().catch(error => alert(error.message)));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initializeWorkflow, {once: true});
  else initializeWorkflow();
})();
