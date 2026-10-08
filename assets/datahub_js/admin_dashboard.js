(function () {
  'use strict';
  function refresh(row) {
    var url = row.dataset.importStatusUrl;
    if (!url) return;
    var badge = row.querySelector('[data-import-status]');
    var button = row.querySelector('.js-refresh-import');
    if (button) button.disabled = true;
    fetch(url, {headers: {'X-Requested-With': 'XMLHttpRequest'}})
      .then(function (response) { return response.json().then(function (data) { return {ok: response.ok, data: data}; }); })
      .then(function (result) {
        if (!result.ok) return;
        if (badge && result.data.status) {
          badge.textContent = result.data.status.replace('_', ' ');
          badge.className = 'ops-status status-' + result.data.status;
        }
        var error = row.querySelector('[data-import-error]');
        if (!error && result.data.error_code) {
          error = document.createElement('small');
          error.dataset.importError = 'true';
          error.className = 'text-danger';
          row.querySelector('div').appendChild(error);
        }
        if (error) error.textContent = result.data.error_code || '';
        if (result.data.dataset_url && !row.querySelector('[data-import-open]')) {
          var link = document.createElement('a');
          link.href = result.data.dataset_url; link.dataset.importOpen = 'true'; link.className = 'btn btn-sm btn-label-primary'; link.textContent = 'Open'; row.appendChild(link);
        }
      })
      .catch(function () {})
      .finally(function () { if (button) button.disabled = false; });
  }
  document.querySelectorAll('.js-refresh-import').forEach(function (button) {
    button.addEventListener('click', function () { refresh(button.closest('[data-import-status-url]')); });
  });
  document.querySelectorAll('[data-import-status-url]').forEach(function (row) {
    var status = row.querySelector('[data-import-status]');
    if (status && /queued|running/i.test(status.textContent)) window.setInterval(function () { refresh(row); }, 15000);
  });
}());
