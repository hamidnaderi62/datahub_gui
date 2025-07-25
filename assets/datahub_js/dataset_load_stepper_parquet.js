let dt_data;
let anonymized_data;
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
// Load csv
//************************************************
$.fn.dataTable.ext.errMode = 'throw';
$(document).ready(function () {
    const my_file = document.getElementById('my_file1')
    if (my_file) {
        my_file.addEventListener("change", () => {
            read_csv_big(my_file);
        });
    }
});

function read_csv_big(my_file) {
    Papa.parse(my_file.files[0], {
        header: true,
        worker: true,
        complete: function (results) {
            dt_data = results.data
            console.log(dt_data);
            json_datatable(dt_data);
        }
    });
}

function json_datatable(json_data) {
    var adColumns = [];
    Object.keys(json_data[0]).forEach(key => {
        var col = {
            data: key,
            title: key
        };
        adColumns.push(col);
    });

    var tb_container = document.getElementById('tb_container');
    tb_container.innerHTML = '<table class="datatables-basic table" id="tb1"></table>';
    console.log(adColumns);

    $('#tb1').DataTable({
        data: json_data,
        columns: adColumns,
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

    createMetaDataRows(adColumns);
    // generateColMetaData();
}

//************************************************
// Step 3
// createMetaDataRow
//************************************************
function createMetaDataRows(adColumns) {
    let metaHtml = '';

    for (let i = 0; i < adColumns.length; i++) {
        let metaHtmlRow = ` <div class="repeater-wrapper pt-0 pt-md-0" data-repeater-item>
                                <div class="d-flex border rounded position-relative pe-0">
                                    <div class="row w-100 p-3">

                                        <div class="col-md-3 col-12 mb-md-0 mb-3">
                                            <input class="form-control mb-3" id="group-a[${i}][col_name]" name="group-a[${i}][col_name]" min="3" value="${adColumns[i]['data']}" placeholder="عنوان" type="text"/>
                                        </div>

                                        <div class="col-md-2 col-12 mb-md-0 mb-3">
                                            <select class="form-select mb-3" id="group-a[${i}][col_dtype]" name="group-a[${i}][col_dtype]" onchange="changeDType(this ,${i})">
                                                <option value="Text" selected>Text</option>
                                                <option value="Number">Number</option>
                                            </select>
                                        </div>

                                        <div class="col-md-5 col-12 mb-md-0 mb-3">
                                            <textarea id="group-a[${i}][col_desc]" name="group-a[${i}][col_desc]" class="form-control" placeholder="توضیحات" rows="1"></textarea>
                                        </div>

                                        <div class="col-md-2 col-12 mb-md-0 mb-3">
                                            <select class="form-select mb-3" id="group-a[${i}][col_di_type]" name="group-a[${i}][col_di_type]">
                                                <option value="None" selected>None</option>
                                                <option value="NER">NER</option>
                                            </select>
                                        </div>
                                        
                                        
                                    </div>
                                    <div class="d-flex flex-column align-items-center justify-content-between border-start p-2">
                                        <i class="ti ti-x cursor-pointer" data-repeater-delete></i>
                                    </div>
                                </div>
                            </div>`
        metaHtml = metaHtml + metaHtmlRow;

    }
    let div_container = document.getElementById('div_container');
    div_container.innerHTML = metaHtml;

    // let col_dtype_val = document.getElementById('group-a[0][col_dtype]').value;
}

// Change De-identification list by datatype column
function changeDType(select, i) {
    let selected_value = select.options[select.selectedIndex].value;
    if (selected_value === 'Text') {
        let select_di_type = document.getElementById('group-a[' + i + '][col_di_type]');
        select_di_type.options.length = 0;
        select_di_type.add(new Option('None', 'None'));
        select_di_type.add(new Option('NER', 'NER'));
    } else if (selected_value === 'Number') {
        let select_di_type = document.getElementById('group-a[' + i + '][col_di_type]');
        select_di_type.options.length = 0;
        select_di_type.add(new Option('None', 'None'));
        select_di_type.add(new Option('Mean', 'Mean'));
        select_di_type.add(new Option('Median', 'Median'));
        select_di_type.add(new Option('Min', 'Min'));
        select_di_type.add(new Option('Max', 'Max'));
    }
}

//************************************************
// Step 4
// generateColMetaData
// create datatable for show ColMetaData
//************************************************
$.fn.dataTable.ext.errMode = 'throw';
let cols;

function generateColMetaData() {
    cols = [];
    var div_container = document.querySelector('#div_container')
    var rows = div_container.children;
    for (let i = 0; i < rows.length; i++) {
        if (rows[i].style.display != 'none') {
            var name = document.getElementsByName("group-a[" + i + "][col_name]")[0].value
            var dtype = document.getElementsByName("group-a[" + i + "][col_dtype]")[0].value
            var desc = document.getElementsByName("group-a[" + i + "][col_desc]")[0].value
            var di_type = document.getElementsByName("group-a[" + i + "][col_di_type]")[0].value
            //var di_status = '<img alt="User" class="rounded-circle" src="{% static \'svg/flags/fr.svg" width="32">'
            const col = {'name': name, 'dtype': dtype, 'desc': desc, 'di_type': di_type};
            cols.push(col)
        }
    }

    $('#tb_metadata').DataTable({
        data: cols,
        "bDestroy": true,
        columns: [
            {data: 'name'},
            {data: 'dtype'},
            {data: 'desc'},
            {data: 'di_type'},
        ]
    });
}

$('#tb_metadata').DataTable({
    data: [],
    columns: [
        {data: 'name'},
        {data: 'dtype'},
        {data: 'desc'},
        {data: 'di_type'},
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

//**************************************************
// De-Identification
//**************************************************

function de_identification_dataset() {
    let input_dataset = dt_data;
    let output_dataset = '';
    console.log('de_identification');
    for (let i = 0; i < cols.length; i++) {
        if (cols[i]['di_type'] == 'Mean') {
            input_dataset = replaceAllWithMean(input_dataset, cols[i]['name'])
        } else if (cols[i]['di_type'] == 'Median') {
            input_dataset = replaceAllWithMedian(input_dataset, cols[i]['name'])
        } else if (cols[i]['di_type'] == 'Min') {
            input_dataset = replaceAllWithMin(input_dataset, cols[i]['name'])
        } else if (cols[i]['di_type'] == 'Max') {
            input_dataset = replaceAllWithMax(input_dataset, cols[i]['name'])
        } else if (cols[i]['di_type'] == 'NER') {
            input_dataset = replaceAllWithNER(input_dataset, cols[i]['name'])
        }
    }
    output_dataset = input_dataset;
    anonymized_data = output_dataset
    anonymized_datatable(anonymized_data)
    console.log(output_dataset);
    //console.log(anonymizeJson(dt_data));
}


//**************************************************
function calculateMean(data, column) {
    // 1. Extract and convert values to numbers, filtering out invalid entries
    const numericValues = data
        .map(item => {
            const value = item[column];
            // Handle both string-numbers and actual numbers
            const num = typeof value === 'string' ? parseFloat(value) : value;
            return typeof num === 'number' && !isNaN(num) ? num : null;
        })
        .filter(value => value !== null);

    if (numericValues.length === 0) {
        console.warn(`Column "${column}" has no valid numeric values.`);
        return NaN;
    }

    // 2. Calculate mean
    const sum = numericValues.reduce((acc, num) => acc + num, 0);
    return sum / numericValues.length;
}

function replaceAllWithMean(data, column) {
    const meanValue = calculateMean(data, column);

    if (isNaN(meanValue)) {
        console.warn(`Cannot replace: No valid numeric values in column "${column}".`);
        return data; // Return original if mean is invalid
    }

    // Replace only valid numeric values (leave invalid entries as-is)
    return data.map(item => {
        const value = item[column];
        const num = typeof value === 'string' ? parseFloat(value) : value;
        const shouldReplace = typeof num === 'number' && !isNaN(num);

        return {
            ...item,
            [column]: shouldReplace ? meanValue : value
        };
    });
}

//**************************************************
function calculateMedian(data, column) {
    // 1. Extract and convert values to numbers, filtering out invalid entries
    const numericValues = data
        .map(item => {
            const value = item[column];
            // Handle both string-numbers and actual numbers
            const num = typeof value === 'string' ? parseFloat(value) : value;
            return typeof num === 'number' && !isNaN(num) ? num : null;
        })
        .filter(value => value !== null)
        .sort((a, b) => a - b); // Numeric sort

    if (numericValues.length === 0) {
        console.warn(`Column "${column}" has no valid numeric values.`);
        return NaN;
    }

    // 2. Calculate median
    const mid = Math.floor(numericValues.length / 2);
    return numericValues.length % 2 === 0
        ? (numericValues[mid - 1] + numericValues[mid]) / 2 // Even length
        : numericValues[mid]; // Odd length
}

function replaceAllWithMedian(data, column) {
    const medianValue = calculateMedian(data, column);

    if (isNaN(medianValue)) {
        console.warn(`Cannot replace: No valid numeric values in column "${column}".`);
        return data; // Return original if median is invalid
    }

    // Replace only valid numeric values (leave invalid entries as-is)
    return data.map(item => {
        const value = item[column];
        const num = typeof value === 'string' ? parseFloat(value) : value;
        const shouldReplace = typeof num === 'number' && !isNaN(num);

        return {
            ...item,
            [column]: shouldReplace ? medianValue : value
        };
    });
}

//**************************************************
function calculateMin(data, column) {
    return Math.min(...data.map(item => item[column]));
}

function replaceAllWithMin(data, column) {
    const minValue = calculateMin(data, column);

    return data.map(item => ({
        ...item,
        [column]: minValue
    }));
}

//**************************************************
function calculateMax(data, column) {
    return Math.max(...data.map(item => item[column]));
}

function replaceAllWithMax(data, column) {
    const maxValue = calculateMax(data, column);

    return data.map(item => ({
        ...item,
        [column]: maxValue
    }));
}

//**************************************************
// NER Anonymize - Solution 1

function replaceAllWithNER(data, column) {
    return data.map(item => ({
        ...item,
        [column]: applyNERTags(item[column]) // Replace with standardized tags
    }));
}

function applyNERTags(text) {
    if (typeof text !== "string") return text; // Skip non-strings

 // English NER patterns (unchanged)
    let result = text
        .replace(/\b[\w.-]+@[\w.-]+\.\w+\b/g, '[EMAIL]') // Emails
        .replace(/(\+\d{1,3}[- ]?)?(\(\d{3}\)[- ]?|\d{3}[- ]?)\d{3}[- ]?\d{4}\b/g, '[PHONE]') // Phone numbers
        .replace(/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/g, '[IP]') // IPv4 addresses
        .replace(/\b\d{3}-\d{2}-\d{4}\b/g, '[SSN]') // Social Security Numbers
        .replace(/\b(?:\d[ -]*?){13,16}\b/g, '[CREDIT_CARD]') // Credit cards
        .replace(/\b[A-Z][a-z]+ [A-Z][a-z]+\b/g, '[NAME]') // Full names (e.g., "John Doe")
        .replace(/\b\d+ [A-Za-z]+,? [A-Za-z]+,? [A-Z]{2}\b/g, '[ADDRESS]'); // Simple addresses (e.g., "123 Main St, New York, NY")

    // Persian NER patterns
    result = result
        // Persian names (matches common name patterns)
        .replace(/[\u0600-\u06FF]{2,}(?:\s+[\u0600-\u06FF]{2,})+/g, '[NAME_FA]')
        // Persian phone numbers (09XXXXXXXXX or +98...)
        .replace(/(\+98|\u06F9\u06F8|\u06F9)[\s\u200C\-]?(\d[\s\u200C\-]?){10}/g, '[PHONE_FA]')
        // Iranian national ID (10 digits)
        .replace(/\b\d{10}\b/g, '[NATIONAL_ID_IR]')
        // Persian addresses (simple pattern)
        .replace(/[\u0600-\u06FF]+\s+[\u0600-\u06FF]+,\s*[\u0600-\u06FF]+/g, '[ADDRESS_FA]')
        // Dates in Persian format (1402/05/15)
        .replace(/\b\d{4}\/\d{2}\/\d{2}\b/g, '[DATE_FA]');

    return result;
}


//************************************************
// Step 5
// Show De-Identified Data Table
//************************************************
function anonymized_datatable(anonymized_data) {
    var adColumns = [];
    Object.keys(anonymized_data[0]).forEach(key => {
        var col = {
            data: key,
            title: key
        };
        adColumns.push(col);
    });

    var tb_anonymized_container = document.getElementById('tb_anonymized_container');
    tb_anonymized_container.innerHTML = '<table class="datatables-basic table" id="tb1_anonymized"></table>';
    console.log(adColumns);

    $('#tb1_anonymized').DataTable({
        data: anonymized_data,
        columns: adColumns,
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
}

//************************************************
// Step 6
// Insert Dataset Metadata to DB
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

// Function to convert JSON to Parquet
async function convertJsonToParquet1(jsonFile) {
    updateProgress(0, 'Converting JSON to Parquet...');

    try {
        // Read the JSON file
        const jsonData = await readFileAsText(jsonFile);
        const jsonArray = JSON.parse(jsonData);

        // Convert to Parquet (using parquetjs library)
        const parquetBuffer = await jsonToParquet(jsonArray);

        return new Blob([parquetBuffer], { type: 'application/octet-stream' });
    } catch (error) {
        console.error('Conversion error:', error);
        throw new Error('Failed to convert JSON to Parquet');
    }
}

async function convertJsonToParquet(jsonInput) {
    updateProgress(0, 'Converting JSON to Parquet...');

    try {
        let jsonArray;

        // Handle different input types
        if (jsonInput instanceof File || jsonInput instanceof Blob) {
            // If input is a File/Blob, read it
            const jsonData = await readFileAsText(jsonInput);
            jsonArray = JSON.parse(jsonData);
        } else if (typeof jsonInput === 'string') {
            // If input is a JSON string
            jsonArray = JSON.parse(jsonInput);
        } else if (typeof jsonInput === 'object') {
            // If input is already a JavaScript object
            jsonArray = Array.isArray(jsonInput) ? jsonInput : [jsonInput];
        } else {
            throw new Error('Invalid input type for JSON conversion');
        }

        // Convert to Parquet (using parquetjs library)
        const parquetBuffer = await jsonToParquet(jsonArray);

        return new Blob([parquetBuffer], { type: 'application/octet-stream' });
    } catch (error) {
        console.error('Conversion error:', error);
        throw new Error('Failed to convert JSON to Parquet: ' + error.message);
    }
}

// Helper function to read file as text
function readFileAsText(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsText(file);
    });
}

// Function to convert JSON array to Parquet
async function jsonToParquet(jsonArray) {
    // Load parquetjs library dynamically
    ////const parquetjs = await import('https://cdn.jsdelivr.net/npm/parquetjs@latest/+esm');
    const parquetjs = await import('https://cdn.jsdelivr.net/npm/parquetjs@0.11.2/parquet.min.js');
    await import('https://unpkg.com/parquetjs-lite@1.0.0-alpha.6/dist/parquet.js');

    // Define schema (you may want to customize this based on your data)
    const schema = inferSchemaFromJson(jsonArray[0]);

    // Create a writer
    const writer = await parquetjs.ParquetWriter.openStream(schema, {
        useDataPageV2: true,
        compression: 'GZIP'
    });

    // Write all records
    for (const record of jsonArray) {
        await writer.appendRow(record);
    }

    // Close the writer and get the buffer
    return writer.close();
}

// Helper function to infer schema from JSON
function inferSchemaFromJson(sampleObj) {
    const schema = {};
    for (const [key, value] of Object.entries(sampleObj)) {
        schema[key] = inferFieldType(key, value);
    }
    return new parquet.ParquetSchema(schema);
}

function inferFieldType(key, value) {
    if (typeof value === 'string') {
        return { type: 'UTF8' };
    } else if (typeof value === 'number') {
        return { type: 'DOUBLE' };
    } else if (typeof value === 'boolean') {
        return { type: 'BOOLEAN' };
    } else if (value instanceof Date) {
        return { type: 'TIMESTAMP_MILLIS' };
    } else if (Array.isArray(value)) {
        return { type: 'JSON', repeated: true };
    } else if (value === null || value === undefined) {
        return { type: 'UTF8', optional: true }; // Default to string for nulls
    } else {
        return { type: 'JSON' }; // For nested objects
    }
}

async function uploadChunk(file, chunkNumber, totalChunks, url, csrfToken) {
    const start = chunkNumber * CHUNK_SIZE;
    const end = Math.min(start + CHUNK_SIZE, file.size);
    const chunk = file.slice(start, end);

    const formData = new FormData();
    formData.append('file', chunk);
    formData.append('chunkNumber', chunkNumber);
    formData.append('totalChunks', totalChunks);
    formData.append('uploadId', uploadId);
    formData.append('fileName', file.name.replace('.json', '.parquet'));
    formData.append('fileSize', file.size);
    formData.append('fileType', 'application/octet-stream');

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
        dataset_format: 'parquet', // Always parquet now
        dataset_recordsNum: $('#dataset_recordsNum').val(),
        dataset_price: $('#dataset_price').val(),
        dataset_requestRequired: $('#dataset_requestRequired').val(),
        dataset_desc: $('#dataset_desc').val(),
        dataset_tags: getTags(),
        dataset_columnDataType: cols ? JSON.stringify(cols) : '{}'
    };
}

async function uploadFile(file, url, csrfToken) {
    try {
        // First convert the JSON file to Parquet
        updateProgress(0, 'Converting JSON to Parquet...');
        const parquetFile = await convertJsonToParquet(file);

        // Now upload the Parquet file in chunks
        totalChunks = Math.ceil(parquetFile.size / CHUNK_SIZE);
        uploadedChunks = 0;
        uploadId = null;

        updateProgress(10, 'Starting upload...');

        for (let i = 0; i < totalChunks; i++) {
            const progress = 10 + (i / totalChunks * 90); // Conversion took first 10%
            updateProgress(progress, `Uploading chunk ${i + 1} of ${totalChunks}...`);

            const result = await uploadChunk(parquetFile, i, totalChunks, url, csrfToken);

            if (i === 0 && result.upload_id) {
                uploadId = result.upload_id;
            }

            uploadedChunks++;
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
            throw new Error(`Finalization failed (${response.status}): ${errorData.message || response.statusText}`);
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

async function checkTempMetaData1() {
    if (!$('#question_verify').is(':checked')) {
        alert('Please verify your submission');
        return;
    }

    const fileInput = document.getElementById('dataset_file');
    parquet_dataset = convertJsonToParquet()
    if (!parquet_dataset) {
        alert('no parquet file ');
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

async function checkTempMetaData2(jsonFile) {
    if (!$('#question_verify').is(':checked')) {
        alert('Please verify your submission');
        return;
    }

    // Convert the JSON file to Parquet
    let parquet_dataset;
    try {
        parquet_dataset = await convertJsonToParquet(jsonFile);
        if (!parquet_dataset) {
            alert('Failed to create Parquet file');
            return;
        }
    } catch (error) {
        alert(`Error converting to Parquet: ${error.message}`);
        return;
    }

    const csrfToken = getCookie('csrftoken') || window.csrfToken;

    try {
        document.getElementById('upload-container').style.display = 'block';
        // Upload the Parquet file instead of the original JSON
        const result = await uploadFile(parquet_dataset, saveMetaDataUrl, csrfToken);
        console.log('Upload successful:', result);
        alert('File and metadata saved successfully!');
        return result;
    } catch (error) {
        console.error('Upload failed:', error);
        alert(`Upload failed: ${error.message}`);
        throw error;
    }
}

async function checkTempMetaData(jsonInput) {
    if (!$('#question_verify').is(':checked')) {
        alert('Please verify your submission');
        return;
    }

    try {
        const parquet_dataset = await convertJsonToParquet(jsonInput);
        if (!parquet_dataset) {
            alert('Failed to create Parquet file');
            return;
        }

        const csrfToken = getCookie('csrftoken') || window.csrfToken;
        document.getElementById('upload-container').style.display = 'block';

        const result = await uploadFile(parquet_dataset, saveMetaDataUrl, csrfToken);
        console.log('Upload successful:', result);
        alert('File and metadata saved successfully!');
        return result;
    } catch (error) {
        console.error('Error:', error);
        alert(`Error: ${error.message}`);
        throw error;
    }
}


// Event listener
document.getElementById('btn_upload_dataset').addEventListener('click', async function() {
    try {
        await checkTempMetaData(anonymized_data);
    } catch (error) {
        console.error('Upload error:', error);
    }
});

