(function () {
  'use strict';

  const config = window.DataHubWorkflow || {messages: {}};
  const MAX_CLIENT_BYTES = 50 * 1024 * 1024;
  const MAX_PREVIEW_ROWS = 100;
  const CHUNK_SIZE = 5 * 1024 * 1024;
  const state = {
    sourceFile: null,
    sourceRows: [],
    columns: [],
    policies: [],
    anonymizedRows: [],
    report: null,
    batchId: null,
    datasetId: null,
    uploadComplete: false,
    uploading: false,
    tagify: null,
  };

  const $ = id => document.getElementById(id);
  const message = (key, fallback) => config.messages[key] || fallback;
  const safeText = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));
  const formatBytes = bytes => {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return `${(bytes / Math.pow(1024, index)).toFixed(index ? 1 : 0)} ${units[index]}`;
  };

  function showActionMessage(text, level = 'success') {
    const element = $('workflow-action-message');
    if (!element) return;
    element.className = `alert alert-${level}`;
    element.textContent = text;
    element.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  }

  function csrfToken() {
    const cookie = document.cookie.split(';').map(value => value.trim()).find(value => value.indexOf('csrftoken=') === 0);
    return cookie ? decodeURIComponent(cookie.slice('csrftoken='.length)) : (config.csrfToken || '');
  }

  function getTags() {
    if (state.tagify) return state.tagify.value.map(item => item.value).join(',');
    try {
      return JSON.parse($('dataset_tags')?.value || '[]').map(item => item.value).join(',');
    } catch (error) {
      return $('dataset_tags')?.value || '';
    }
  }

  async function loadTags() {
    const input = $('dataset_tags');
    if (!input || typeof Tagify === 'undefined') return;
    let whitelist = [];
    try {
      const response = await fetch(config.tagsUrl);
      if (response.ok) whitelist = await response.json();
    } catch (error) {
      // Tag suggestions are optional and must not block a local upload.
    }
    state.tagify = new Tagify(input, {
      whitelist,
      duplicates: false,
      dropdown: {enabled: 1, maxItems: 20, closeOnSelect: false},
    });
    $('add-dataset-tag')?.addEventListener('click', () => state.tagify.addEmptyTag());
  }

  function metadata() {
    return {
      dataset_name: $('dataset_name')?.value.trim() || '',
      dataset_owner: $('dataset_owner')?.value.trim() || '',
      dataset_language: Array.from($('dataset_language')?.selectedOptions || []).map(option => option.value).join(','),
      dataset_license: $('dataset_license')?.value || '',
      dataset_format: $('dataset_format')?.value || 'Text',
      dataset_recordsNum: $('dataset_recordsNum')?.value || String(state.anonymizedRows.length || 0),
      dataset_price: $('dataset_price')?.value || '0',
      dataset_requestRequired: $('dataset_requestRequired')?.value || 'No',
      dataset_desc: $('dataset_desc')?.value || '',
      dataset_tags: getTags(),
      dataset_columnDataType: state.policies,
      privacy_plan: {
        schema_version: 'privacy-plan-v1',
        execution: 'client_preview_and_transform',
        source_name: state.sourceFile?.name || '',
        columns: state.policies,
        fail_on_residual_pii: true,
        residual_pii_count: state.report?.residualSignals || 0,
      },
    };
  }

  function isNumeric(value) {
    if (value === null || value === undefined || String(value).trim() === '') return false;
    return /^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$/.test(String(value).trim());
  }

  function isDateValue(value) {
    if (!value || isNumeric(value)) return false;
    const text = String(value).trim();
    if (!/^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}/.test(text)) return false;
    return !Number.isNaN(Date.parse(text));
  }

  function inferType(values) {
    const nonEmpty = values.filter(value => value !== null && value !== undefined && String(value).trim() !== '').slice(0, 500);
    if (!nonEmpty.length) return {type: 'Text', confidence: 0};
    const numeric = nonEmpty.filter(isNumeric).length / nonEmpty.length;
    const dates = nonEmpty.filter(isDateValue).length / nonEmpty.length;
    const booleans = nonEmpty.filter(value => /^(true|false|yes|no|بله|خیر)$/i.test(String(value).trim())).length / nonEmpty.length;
    if (numeric >= 0.95) return {type: 'Number', confidence: Math.round(numeric * 100)};
    if (dates >= 0.95) return {type: 'Date', confidence: Math.round(dates * 100)};
    if (booleans >= 0.95) return {type: 'Boolean', confidence: Math.round(booleans * 100)};
    return {type: 'Text', confidence: Math.round(Math.max(0.5, 1 - numeric) * 100)};
  }

  function likelyIdentifier(name) {
    return /(^|[_\s-])(id|uuid|email|phone|mobile|tel|passport|national|ssn|کد|تلفن|موبایل|ایمیل)([_\s-]|$)/i.test(name);
  }

  function defaultPolicy(name, type) {
    if (likelyIdentifier(name)) return 'Mask';
    if (type === 'Text' && /text|description|comment|note|address|متن|توضیح|نشانی/i.test(name)) return 'NER';
    return 'None';
  }

  function typeOptions(type, selected) {
    const options = {
      Text: [['None', message('none', 'None')], ['NER', message('ner', 'Detect and mask entities')]],
      Number: [['None', message('none', 'None')], ['Round', message('round', 'Round values')], ['Bin', message('bin', 'Group into ranges')]],
      Date: [['None', message('none', 'None')], ['Year', message('year', 'Keep year only')]],
      Boolean: [['None', message('none', 'None')]],
      Identifier: [['None', message('none', 'None')], ['Mask', message('mask', 'Replace with a redaction token')]],
    }[type] || [['None', message('none', 'None')]];
    return options.map(([value, label]) => `<option value="${safeText(value)}"${value === selected ? ' selected' : ''}>${safeText(label)}</option>`).join('');
  }

  function renderTable(container, rows, columns) {
    if (!container) return;
    if (!rows.length || !columns.length) {
      container.innerHTML = `<div class="alert alert-secondary mb-0">${safeText(message('noRows', 'The file has no rows.'))}</div>`;
      return;
    }
    const visible = rows.slice(0, MAX_PREVIEW_ROWS);
    const head = columns.map(column => `<th>${safeText(column)}</th>`).join('');
    const body = visible.map(row => `<tr>${columns.map(column => `<td>${safeText(row[column])}</td>`).join('')}</tr>`).join('');
    container.innerHTML = `<div class="table-responsive"><table class="table table-sm table-hover align-middle"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function renderSourceProfile(file) {
    const profile = $('source-profile');
    if (!profile) return;
    const numeric = state.columns.filter(column => column.type === 'Number').length;
    const protectedColumns = state.policies.filter(policy => policy.di_type !== 'None').length;
    profile.textContent = `${file.name} · ${formatBytes(file.size)} · ${state.sourceRows.length} rows · ${state.columns.length} columns · ${numeric} numeric · ${protectedColumns} protected`;
  }

  function renderPolicies() {
    const container = $('div_container');
    if (!container) return;
    container.innerHTML = state.policies.map((policy, index) => `<div class="repeater-wrapper pt-0 pt-md-0 mb-3" data-repeater-item data-column-index="${index}">
      <div class="d-flex border rounded position-relative pe-0"><div class="row w-100 p-3">
        <div class="col-md-3 col-12 mb-md-0 mb-3"><label class="form-label">${safeText(message('columnName', 'Column'))}</label><input class="form-control" data-role="col-name" value="${safeText(policy.name)}" type="text"></div>
        <div class="col-md-2 col-12 mb-md-0 mb-3"><label class="form-label">${safeText(message('dataType', 'Type'))}</label><select class="form-select" data-role="col-dtype">${['Text', 'Number', 'Date', 'Boolean', 'Identifier'].map(value => `<option value="${value}"${policy.dtype === value ? ' selected' : ''}>${safeText(message(value.toLowerCase(), value))}</option>`).join('')}</select></div>
        <div class="col-md-4 col-12 mb-md-0 mb-3"><label class="form-label">${safeText(message('description', 'Description'))}</label><textarea class="form-control" data-role="col-desc" rows="1">${safeText(policy.desc)}</textarea></div>
        <div class="col-md-3 col-12 mb-md-0 mb-3"><label class="form-label">${safeText(message('anonymization', 'Privacy action'))}</label><select class="form-select" data-role="col-di-type">${typeOptions(policy.dtype, policy.di_type)}</select><small class="text-muted" data-role="confidence">${safeText(message('confidence', 'Detected'))}: ${policy.confidence}%</small></div>
      </div><div class="d-flex flex-column align-items-center justify-content-between border-start p-2"><i class="ti ti-x cursor-pointer" data-repeater-delete aria-label="Remove"></i></div></div></div>`).join('');
    container.querySelectorAll('[data-role="col-dtype"]').forEach(select => select.addEventListener('change', () => {
      const row = select.closest('[data-column-index]');
      const index = Number(row.dataset.columnIndex);
      const action = row.querySelector('[data-role="col-di-type"]');
      action.innerHTML = typeOptions(select.value, select.value === state.policies[index].dtype ? state.policies[index].di_type : 'None');
      state.policies[index].dtype = select.value;
    }));
    container.querySelectorAll('[data-repeater-delete]').forEach(button => button.addEventListener('click', () => {
      const row = button.closest('[data-column-index]');
      state.policies.splice(Number(row.dataset.columnIndex), 1);
      renderPolicies();
    }));
    renderPolicySummary();
  }

  function renderPolicySummary() {
    const body = document.querySelector('#tb_metadata tbody');
    if (!body) return;
    body.innerHTML = state.policies.map(policy => `<tr><td><strong>${safeText(policy.name)}</strong></td><td>${safeText(policy.dtype)}</td><td>${safeText(policy.di_type)}</td><td><span class="badge bg-label-secondary">${safeText(policy.confidence)}%</span></td></tr>`).join('');
  }

  function collectPolicies() {
    const rows = Array.from(document.querySelectorAll('#div_container [data-column-index]'));
    const existing = state.policies;
    state.policies = rows.map(row => ({
      name: row.querySelector('[data-role="col-name"]')?.value.trim() || '',
      dtype: row.querySelector('[data-role="col-dtype"]')?.value || 'Text',
      desc: row.querySelector('[data-role="col-desc"]')?.value || '',
      di_type: row.querySelector('[data-role="col-di-type"]')?.value || 'None',
      confidence: existing[Number(row.dataset.columnIndex)]?.confidence || 0,
    })).filter(policy => policy.name);
    renderPolicySummary();
    return state.policies;
  }

  function createPolicies(rows) {
    const columns = Object.keys(rows[0] || {});
    state.columns = columns.map(name => {
      const inferred = inferType(rows.map(row => row[name]));
      const dtype = likelyIdentifier(name) ? 'Identifier' : inferred.type;
      return {name, type: dtype, confidence: inferred.confidence};
    });
    state.policies = state.columns.map(column => ({name: column.name, dtype: column.type, desc: '', di_type: defaultPolicy(column.name, column.type), confidence: column.confidence}));
    renderPolicies();
  }

  async function parseFile(file) {
    if (!file) return;
    if (file.size > MAX_CLIENT_BYTES) throw new Error(message('fileTooLarge', 'This local workflow supports files up to 50 MB. Use the scalable multi-file workflow for larger files.'));
    state.sourceFile = file;
    let rows;
    if (/\.(xlsx|xls)$/i.test(file.name)) {
      if (typeof XLSX === 'undefined') throw new Error(message('excelUnavailable', 'Excel support is unavailable. Please try CSV or enable the spreadsheet parser.'));
      const workbook = XLSX.read(await file.arrayBuffer(), {type: 'array', cellDates: true, cellFormula: false});
      const sheetName = workbook.SheetNames[0];
      if (!sheetName) throw new Error(message('profileFailed', 'Could not find a worksheet.'));
      rows = XLSX.utils.sheet_to_json(workbook.Sheets[sheetName], {defval: '', raw: false});
    } else {
      rows = await new Promise((resolve, reject) => Papa.parse(file, {header: true, worker: true, skipEmptyLines: 'greedy', complete: result => resolve(result.data || []), error: reject}));
    }
    state.sourceRows = rows.filter(row => row && Object.values(row).some(value => String(value ?? '').trim() !== ''));
    if (!state.sourceRows.length) throw new Error(message('noRows', 'The selected file has no data rows.'));
    if ($('final-records')) $('final-records').value = String(state.sourceRows.length);
    createPolicies(state.sourceRows);
    renderTable($('tb_container'), state.sourceRows, state.columns.map(column => column.name));
    renderSourceProfile(file);
  }

  const detectors = [
    {type: 'EMAIL', pattern: /\b[^\s@]+@[^\s@]+\.[^\s@]+\b/gi},
    {type: 'PHONE', pattern: /(?:\+?\d[\d\s().-]{7,}\d)/g},
    {type: 'IP', pattern: /\b(?:\d{1,3}\.){3}\d{1,3}\b/g},
    {type: 'CARD', pattern: /\b(?:\d[ -]*?){13,16}\b/g},
    {type: 'NATIONAL_ID', pattern: /\b\d{10}\b/g},
  ];

  function maskSensitiveText(value, useNer) {
    if (value === null || value === undefined) return value;
    let text = String(value);
    detectors.forEach(detector => { text = text.replace(detector.pattern, `[${detector.type}]`); });
    if (useNer && typeof window.nlp === 'function') {
      try {
        const documentView = window.nlp(text);
        if (documentView.people) documentView.people().replaceWith('[PERSON]');
        if (documentView.places) documentView.places().replaceWith('[LOCATION]');
        if (documentView.organizations) documentView.organizations().replaceWith('[ORG]');
        text = documentView.text();
      } catch (error) {
        // Regex detectors remain the safe fallback for unsupported languages.
      }
    }
    return text;
  }

  function transformValue(value, policy) {
    if (value === null || value === undefined || String(value).trim() === '') return value;
    if (policy.di_type === 'NER') return maskSensitiveText(value, true);
    if (policy.di_type === 'Mask') return '[REDACTED]';
    if (policy.di_type === 'Round' && isNumeric(value)) return Number(Number(value).toFixed(1));
    if (policy.di_type === 'Bin' && isNumeric(value)) return Math.floor(Number(value) / 5) * 5;
    if (policy.di_type === 'Year' && isDateValue(value)) return new Date(value).getUTCFullYear();
    return value;
  }

  function de_identification_dataset() {
    collectPolicies();
    const changedRows = new Set();
    state.anonymizedRows = state.sourceRows.map((row, rowIndex) => {
      const transformed = {...row};
      state.policies.forEach(policy => {
        const nextValue = transformValue(row[policy.name], policy);
        if (String(nextValue ?? '') !== String(row[policy.name] ?? '')) changedRows.add(rowIndex);
        transformed[policy.name] = nextValue;
      });
      return transformed;
    });
    let residualSignals = 0;
    state.anonymizedRows.slice(0, 1000).forEach(row => Object.values(row).forEach(value => {
      detectors.forEach(detector => { detector.pattern.lastIndex = 0; if (detector.pattern.test(String(value ?? ''))) residualSignals += 1; });
    }));
    state.report = {changedRows: changedRows.size, residualSignals};
    renderTable($('tb_anonymized_container'), state.anonymizedRows, state.policies.map(policy => policy.name));
    const summary = $('anonymized-summary');
    if (summary) {
      summary.className = residualSignals ? 'alert alert-warning' : 'alert alert-success';
      summary.textContent = `${message('transformSummary', 'Transformation complete')}: ${changedRows.size} rows changed. ${residualSignals ? message('residualPii', 'Review possible residual PII before publishing.') : message('noResidualPii', 'No common residual PII signals found in the sample.')}`;
    }
    showActionMessage(
      residualSignals ? `${message('deidentificationComplete', 'De-identification completed.')} ${message('residualPii', 'Review possible residual PII before publishing.')}` : message('deidentificationComplete', 'De-identification completed successfully. Review the preview.'),
      residualSignals ? 'warning' : 'success'
    );
    return state.anonymizedRows;
  }
  window.de_identification_dataset = de_identification_dataset;
  window.generateColMetaData = function () {
    collectPolicies();
    showActionMessage(message('changesSaved', 'Column privacy methods were saved successfully.'));
  };

  function csvFileFromRows() {
    const columns = state.policies.map(policy => policy.name);
    const rows = state.anonymizedRows.map(row => {
      const output = {};
      columns.forEach(column => {
        let value = row[column];
        if (typeof value === 'string' && /^[=+\-@]/.test(value)) value = `'${value}`;
        output[column] = value;
      });
      return output;
    });
    const csv = Papa.unparse(rows, {columns});
    const baseName = (state.sourceFile?.name || 'dataset').replace(/\.(csv|tsv|xlsx|xls)$/i, '');
    return new File([csv], `deidentified_${baseName}.csv`, {type: 'text/csv'});
  }

  async function createBatch(file) {
    const response = await fetch(config.createBatchUrl, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()}, body: JSON.stringify({metadata: metadata(), files: [{name: file.name, relative_path: file.name, size: file.size}]})});
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.status !== 'success') throw new Error(data.message || `Batch creation failed (${response.status})`);
    state.batchId = data.batch_id; state.datasetId = data.dataset_id;
  }

  function setProgress(percent, text, error) {
    const bar = $('upload-progress');
    if (bar) { bar.style.width = `${percent}%`; bar.setAttribute('aria-valuenow', String(Math.round(percent))); bar.classList.toggle('bg-danger', !!error); bar.classList.toggle('bg-success', !error && percent >= 100); }
    if ($('upload-progress-text')) $('upload-progress-text').textContent = text;
    if ($('upload-status')) $('upload-status').textContent = text;
  }

  async function uploadChunked(file) {
    const totalChunks = Math.max(1, Math.ceil(file.size / CHUNK_SIZE));
    let uploadId = null;
    for (let chunkNumber = 0; chunkNumber < totalChunks; chunkNumber += 1) {
      const start = chunkNumber * CHUNK_SIZE;
      const body = new FormData();
      body.append('file', file.slice(start, Math.min(start + CHUNK_SIZE, file.size)), file.name); body.append('chunkNumber', String(chunkNumber)); body.append('totalChunks', String(totalChunks)); body.append('uploadId', uploadId || ''); body.append('batchId', state.batchId); body.append('relativePath', file.name); body.append('fileName', file.name); body.append('fileSize', String(file.size)); body.append('fileType', file.type);
      if (chunkNumber === 0) body.append('metadata', JSON.stringify({relative_path: file.name, original_name: file.name, privacy_applied: true}));
      const response = await fetch(config.uploadUrl, {method: 'POST', headers: {'X-CSRFToken': csrfToken()}, body});
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.status !== 'success') throw new Error(data.message || `Chunk ${chunkNumber + 1} failed`);
      uploadId = data.upload_id || uploadId;
      setProgress(((start + Math.min(CHUNK_SIZE, file.size - start)) / file.size) * 100, `${message('uploading', 'Uploading ...')} ${chunkNumber + 1}/${totalChunks}`);
    }
    const response = await fetch(`${config.uploadUrl}?finalize=true&uploadId=${encodeURIComponent(uploadId)}`, {method: 'POST', headers: {'X-CSRFToken': csrfToken()}});
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.status !== 'success') throw new Error(data.message || 'Finalization failed');
    return data;
  }

  async function uploadDirect(file) {
    const sessionResponse = await fetch(config.directCreateUrl, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()}, body: JSON.stringify({batch_id: state.batchId, file_name: file.name, relative_path: file.name, file_size: file.size, content_type: file.type})});
    const session = await sessionResponse.json().catch(() => ({}));
    if (!sessionResponse.ok || session.status !== 'success') throw new Error(session.message || 'Could not start multipart upload');
    const parts = [];
    try {
      for (let partNumber = 1; partNumber <= session.total_parts; partNumber += 1) {
        const start = (partNumber - 1) * session.part_size;
        const urlResponse = await fetch(config.directPartUrl, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()}, body: JSON.stringify({upload_id: session.upload_id, part_number: partNumber})});
        const urlData = await urlResponse.json().catch(() => ({}));
        if (!urlResponse.ok || urlData.status !== 'success') throw new Error(urlData.message || `Could not sign part ${partNumber}`);
        const uploadResponse = await fetch(urlData.url, {method: 'PUT', body: file.slice(start, Math.min(start + session.part_size, file.size))});
        if (!uploadResponse.ok) throw new Error(`Direct upload failed for part ${partNumber}`);
        const etag = uploadResponse.headers.get('ETag') || uploadResponse.headers.get('etag');
        if (!etag) throw new Error('Storage did not expose the multipart ETag');
        parts.push({part_number: partNumber, etag});
        setProgress((Math.min(start + session.part_size, file.size) / file.size) * 100, `${message('uploading', 'Uploading ...')} ${partNumber}/${session.total_parts}`);
      }
      const completeResponse = await fetch(config.directCompleteUrl, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()}, body: JSON.stringify({upload_id: session.upload_id, parts})});
      const result = await completeResponse.json().catch(() => ({}));
      if (!completeResponse.ok || result.status !== 'success') throw new Error(result.message || 'Multipart completion failed');
      return result;
    } catch (error) {
      if (config.directAbortUrl) fetch(config.directAbortUrl, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()}, body: JSON.stringify({upload_id: session.upload_id})}).catch(() => {});
      error.directUploadRecoverable = true;
      throw error;
    }
  }

  async function uploadSanitizedFile() {
    if (state.uploading || state.uploadComplete) return;
    if (!state.anonymizedRows.length) throw new Error(message('deidentificationRequired', 'Run the de-identification preview before uploading.'));
    state.uploading = true;
    const button = $('btn_upload_dataset'); if (button) button.disabled = true;
    try {
      const file = csvFileFromRows();
      await createBatch(file);
      let result;
      if (config.directUploadEnabled) {
        try { result = await uploadDirect(file); } catch (error) { if (!config.directUploadFallback || !error.directUploadRecoverable) throw error; result = await uploadChunked(file); }
      } else result = await uploadChunked(file);
      state.uploadComplete = true;
      setProgress(100, message('uploadComplete', 'Sanitized dataset uploaded successfully.'));
      if (config.updateBatchUrl) {
        const response = await fetch(config.updateBatchUrl, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()}, body: JSON.stringify({batch_id: state.batchId, dataset_recordsNum: String(state.anonymizedRows.length), dataset_price: $('dataset_price')?.value || '0', dataset_requestRequired: $('dataset_requestRequired')?.value || 'No'})});
        if (!response.ok) throw new Error(message('uploadFailed', 'Could not save access settings.'));
      }
      if (state.datasetId && config.datasetDetailUrl) window.location.href = config.datasetDetailUrl.replace('__DATASET_ID__', state.datasetId);
      return result;
    } catch (error) {
      setProgress(0, `${message('uploadFailed', 'Upload failed.')} ${error.message}`, true);
      if (button) button.disabled = false;
      throw error;
    } finally {
      state.uploading = false;
    }
  }

  function validateStep(step) {
    if (step === 1) {
      const required = ['dataset_name', 'dataset_owner', 'dataset_language', 'dataset_format'];
      const missing = required.find(id => !$(id)?.value || (id === 'dataset_language' && !Array.from($(id).selectedOptions).length));
      if (missing) { $(missing)?.focus(); return false; }
    }
    if (step === 2 && !state.sourceRows.length) { alert(message('chooseFile', 'Choose a valid CSV or Excel file first.')); return false; }
    if (step === 3) {
      collectPolicies();
      const unprotected = state.policies.filter(policy => likelyIdentifier(policy.name) && policy.di_type === 'None');
      if (unprotected.length) { alert(`${message('privacyWarning', 'Sensitive columns need a privacy action')}: ${unprotected.map(policy => policy.name).join(', ')}`); return false; }
    }
    if ((step === 4 || step === 5) && !state.anonymizedRows.length) { alert(message('deidentificationRequired', 'Run the de-identification preview before continuing.')); return false; }
    if (step === 6 && !$('question_verify')?.checked) { alert(message('verify', 'Please confirm your consent.')); return false; }
    return true;
  }
  window.DataHubWorkflowValidateStep = validateStep;

  function initialize() {
    loadTags();
    $('my_file1')?.addEventListener('change', async event => {
      const file = event.target.files?.[0];
      if (!file) return;
      try { await parseFile(file); }
      catch (error) { state.sourceRows = []; state.columns = []; state.policies = []; if ($('tb_container')) $('tb_container').textContent = error.message; if ($('source-profile')) $('source-profile').textContent = message('profileFailed', 'Could not profile this file.'); }
    });
    $('btn_upload_dataset')?.addEventListener('click', () => uploadSanitizedFile().catch(error => alert(error.message)));
    $('div_container')?.addEventListener('change', event => { if (event.target.matches('[data-role="col-dtype"]')) collectPolicies(); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, {once: true});
  else initialize();
})();
