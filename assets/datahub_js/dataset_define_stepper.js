$.fn.dataTable.ext.errMode = 'throw';
let cols;


//************************************************
// Step 1
//
//************************************************
async function get_predefined_tags() {
    try {
        const response = await fetch('/dataset/predefined_tags/');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error fetching predefined tags:', error);
        return []; // Return empty array as fallback
    }
}

async function loadDatasetTags() {
    try {
        const dataset_tags_El = document.querySelector('#dataset_tags');
        if (!dataset_tags_El) {
            console.error('Dataset tags element not found');
            return;
        }

        // Fetch tags before initializing Tagify
        const predefinedTags = await get_predefined_tags();

        const tagify = new Tagify(dataset_tags_El, {
            pattern: /^[a-zA-Z0-9]{3,}$/,
            whitelist: predefinedTags,
            dropdown: {
                position: 'text',
                enabled: 1, // show suggestions after 1 character
                maxItems: 20,
                closeOnSelect: false
            },
            editTags: true,
            duplicates: false
        });

        const button = dataset_tags_El.nextElementSibling;
        if (button) {
            button.addEventListener('click', () => tagify.addEmptyTag());
        }

        // Optional: Handle form submission to convert tags to comma-separated string
        if (dataset_tags_El.form) {
            dataset_tags_El.form.addEventListener('submit', function() {
                const values = tagify.value.map(item => item.value);
                dataset_tags_El.value = values.join(',');
            });
        }

    } catch (error) {
        console.error('Error initializing Tagify:', error);
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', loadDatasetTags);




//************************************************
// Step 2
//
//************************************************


function generateColMetaData() {
    cols = [];
    var div_container = document.querySelector('#div_container')
    var rows = div_container.children;
    for (let i = 0; i < rows.length; i++) {
        if (rows[i].style.display != 'none') {
            var name = document.getElementsByName("group-a[" + i + "][col_name]")[0].value
            var dtype = document.getElementsByName("group-a[" + i + "][col_dtype]")[0].value
            var desc = document.getElementsByName("group-a[" + i + "][col_desc]")[0].value
            const col = {'name': name, 'dtype': dtype, 'desc': desc};
            cols.push(col)
        }
    }

    $('#tb_metadata').DataTable({
        data: cols,
        "bDestroy": true,
        columns: [
            {data: 'name'},
            {data: 'dtype'},
            {data: 'desc'}
        ]
    });
}


$('#tb_metadata').DataTable({
    data: [],
    columns: [
        {data: 'name'},
        {data: 'dtype'},
        {data: 'desc'}
    ],
    layout: {
        topStart: {
            buttons: [
                {
                    extend: 'csv',
                    text: 'Export CSV',
                    className: 'btn-space',
                    exportOptions: {
                        orthogonal: null
                    }
                },

                {
                    extend: 'selectAll',
                    className: 'btn-space'
                },
                'selectNone'
            ]
        }

    },
    select: true
});


//************************************************
// Step 4
//
//************************************************


// Utility function to get cookies
function getCookie(name) {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        cookie = cookie.trim();
        if (cookie.startsWith(name + '=')) {
            return decodeURIComponent(cookie.substring(name.length + 1));
        }
    }
    return null;
}

// Configuration
const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB chunks
let uploadId = null;
let totalChunks = 0;
let uploadedChunks = 0;

// UI Elements
const progressBar = document.getElementById('upload-progress');
const progressText = document.getElementById('upload-progress-text');
const uploadStatus = document.getElementById('upload-status');

async function uploadChunk(file, chunkNumber, totalChunks, url, csrfToken) {
    const start = chunkNumber * CHUNK_SIZE;
    const end = Math.min(start + CHUNK_SIZE, file.size);
    const chunk = file.slice(start, end);

    const formData = new FormData();
    formData.append('file', chunk);
    formData.append('chunkNumber', chunkNumber);
    formData.append('totalChunks', totalChunks);
    formData.append('uploadId', uploadId);
    formData.append('fileName', file.name);
    formData.append('fileSize', file.size);
    formData.append('fileType', file.type);

    if (chunkNumber === 0) {
        // First chunk includes metadata
        formData.append('metadata', JSON.stringify(getMetadata()));
    }

    const response = await fetch(url, {
        method: "POST",
        headers: {
            "X-CSRFToken": csrfToken,
        },
        body: formData
    });

    if (!response.ok) {
        throw new Error(`Chunk ${chunkNumber + 1} upload failed: ${response.status}`);
    }

    return await response.json();
}

function getMetadata() {
    return {
        dataset_name: $('#dataset_name').val(),
        dataset_owner: $('#dataset_owner').val(),
        dataset_language: $('#dataset_language').val()?.join(',') || '',
        dataset_license: $('#dataset_license').val(),
        dataset_format: $('#dataset_format').val(),
        dataset_desc: $('#dataset_desc').val(),
        dataset_tags: getTags(),
        dataset_columnDataType: cols ? JSON.stringify(cols) : '{}'
        //dataset_columnDataType: window.cols ? JSON.stringify(window.cols) : '{}'
    };
}

function getTags() {
    try {
        const tagsValue = $('#dataset_tags').val();
        return tagsValue ? JSON.parse(tagsValue).map(item => item.value).join(',') : '';
    } catch (e) {
        console.warn('Error parsing tags:', e);
        return '';
    }
}

async function uploadFile(file, url, csrfToken) {
    totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    uploadedChunks = 0;
    uploadId = null;

    updateProgress(0, 'Starting upload...');

    try {
        for (let i = 0; i < totalChunks; i++) {
            updateProgress(i / totalChunks * 100, `Uploading chunk ${i + 1} of ${totalChunks}...`);

            const result = await uploadChunk(file, i, totalChunks, url, csrfToken);

            if (i === 0 && result.upload_id) {
                uploadId = result.upload_id;
            }

            uploadedChunks++;
            updateProgress(uploadedChunks / totalChunks * 100, `Uploaded chunk ${i + 1} of ${totalChunks}`);
        }

        updateProgress(100, 'Finalizing upload...');
        const finalResponse = await finalizeUpload(url, csrfToken, uploadId);
        return finalResponse;

    } catch (error) {
        updateProgress(uploadedChunks / totalChunks * 100, `Upload failed: ${error.message}`, true);
        throw error;
    }
}

async function finalizeUpload(url, csrfToken, uploadId) {
    if (!uploadId) {
        throw new Error('Missing upload ID for finalization');
    }

    try {
        // Extract just the numeric part of the upload ID
        const cleanUploadId = uploadId.split('-')[0];

        const response = await fetch(`${url}?finalize=true&uploadId=${encodeURIComponent(uploadId)}`, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                action: 'complete',
                upload_id: cleanUploadId  // Send clean ID in body too
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(
                `Finalization failed (${response.status}): ${errorData.message || response.statusText}`
            );
        }

        return await response.json();
    } catch (error) {
        console.error('Finalization error details:', {
            originalUploadId: uploadId,
            cleanUploadId: uploadId.split('-')[0],
            error: error.message
        });
        throw error;
    }
}




function updateProgress(percent, message, isError = false) {
    progressBar.style.width =`${percent}%`;
    progressBar.setAttribute('aria-valuenow', percent);
    progressText.textContent = message;

    // Set RTL direction for progress text
    progressText.style.direction = 'rtl';
    progressText.style.textAlign = 'right';

    if (isError) {
        progressBar.classList.remove('bg-success');
        progressBar.classList.add('bg-danger');
        uploadStatus.textContent = 'آپلود ناموفق بود';
        uploadStatus.style.direction = 'rtl';
    } else if (percent >= 100) {
        progressBar.classList.remove('bg-danger');
        progressBar.classList.add('bg-success');
        uploadStatus.textContent = 'آپلود با موفقیت انجام شد!';
        uploadStatus.style.direction = 'rtl';
    } else {
        progressBar.classList.remove('bg-danger');
        progressBar.classList.remove('bg-success');
        uploadStatus.textContent = 'در حال آپلود...';
        uploadStatus.style.direction = 'rtl';
    }
}

async function checkTempMetaData() {
    if (!$('#question_verify').is(':checked')) {
        alert('Please verify your submission');
        return;
    }

    const fileInput = document.getElementById('dataset_file');
    if (!fileInput.files || fileInput.files.length === 0) {
        alert('Please select a file to upload');
        return;
    }

    const file = fileInput.files[0];
    const csrfToken = getCookie('csrftoken') || window.csrfToken;

    try {
        document.getElementById('upload-container').style.display = 'block';
        const result = await uploadFile(file, saveMetaDataUrl, csrfToken);
        console.log('Upload successful:', result);
        alert('File and metadata saved successfully!');
        return result;
    } catch (error) {
        console.error('Upload failed:', error);
        alert(`Upload failed: ${error.message}`);
        throw error;
    }
}

// Event listener
document.getElementById('btn_upload_dataset').addEventListener('click', async function() {
    try {
        await checkTempMetaData();
    } catch (error) {
        console.error('Upload error:', error);
    }
});