let dt_data;

//************************************************
// Step 2
// Load csv
//************************************************
$.fn.dataTable.ext.errMode = 'throw';
$(document).ready(function() {
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
        complete: function(results) {
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
function createMetaDataRows(adColumns){
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
function changeDType(select, i){
    let selected_value = select.options[select.selectedIndex].value;
    if(selected_value === 'Text'){
        let select_di_type = document.getElementById('group-a['+ i +'][col_di_type]');
        select_di_type.options.length = 0;
        select_di_type.add(new Option('None', 'None'));
        select_di_type.add(new Option('NER', 'NER'));
    }
    else if(selected_value === 'Number'){
        let select_di_type = document.getElementById('group-a['+ i +'][col_di_type]');
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

function generateColMetaData()
{
    cols = [];
    var div_container = document.querySelector('#div_container')
    var rows = div_container.children;
    for (let i = 0; i < rows.length; i++) {
        if(rows[i].style.display != 'none')
        {
            var name = document.getElementsByName("group-a[" + i + "][col_name]")[0].value
            var dtype = document.getElementsByName("group-a[" + i + "][col_dtype]")[0].value
            var desc = document.getElementsByName("group-a[" + i + "][col_desc]")[0].value
            var di_type = document.getElementsByName("group-a[" + i + "][col_di_type]")[0].value
            //var di_status = '<img alt="User" class="rounded-circle" src="{% static \'svg/flags/fr.svg" width="32">'
            var di_status = '<button class="btn btn-primary" type="button">کمنام سازی</button>'
            const col = {'name':name, 'dtype':dtype, 'desc':desc, 'di_type':di_type, 'di_status':di_status};
            cols.push(col)
        }
    }

     $('#tb_metadata').DataTable( {
        data: cols,
        "bDestroy": true,
        columns: [
            { data: 'name' },
            { data: 'dtype' },
            { data: 'desc' },
            { data: 'di_type' },
            { data: 'di_status' }
            ]
        } );
}

$('#tb_metadata').DataTable( {
    data: [],
    columns: [
        { data: 'name' },
        { data: 'dtype' },
        { data: 'desc' },
        { data: 'di_type' },
        { data: 'di_status' }
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
// De Identification
//**************************************************

function de_identification_dataset(){
    let input_dataset = dt_data;
    let output_dataset = '';
    console.log('de_identification');
    for (let i = 0; i < cols.length; i++) {
         if(cols[i]['di_type'] == 'Mean'){
            input_dataset = replaceAllWithMean(input_dataset, cols[i]['name'])
         }
         else if(cols[i]['di_type'] == 'Median'){
            input_dataset = replaceAllWithMedian(input_dataset, cols[i]['name'])
         }
         else if(cols[i]['di_type'] == 'Min'){
            input_dataset = replaceAllWithMin(input_dataset, cols[i]['name'])
         }
         else if(cols[i]['di_type'] == 'Max'){
            input_dataset = replaceAllWithMax(input_dataset, cols[i]['name'])
         }
         //else if(cols[i]['di_type'] == 'NER'){
            //input_dataset = replaceAllWithNER(input_dataset, cols[i]['name'])
         //}
     }
    output_dataset = input_dataset;
    console.log(output_dataset);
    //console.log(anonymizeJson(dt_data));
}


//**************************************************


function replaceAllWithNER(data, column) {
    return data.map(item => ({
        ...item,
        [column]: anonymizeEmail(item)
    }));
}

//**************************************************
function calculateMean(data, column) {
    const sum = data.reduce((acc, item) => acc + item[column], 0);
    return sum / data.length;
}

function replaceAllWithMean(data, column) {
    const meanValue = calculateMean(data, column);

    return data.map(item => ({
        ...item,
        [column]: meanValue
    }));
}


//**************************************************
function calculateMedian(data, column) {
    const sortedValues = data.map(item => item[column]).sort((a, b) => a - b);
    const middle = Math.floor(sortedValues.length / 2);

    if (sortedValues.length % 2 === 0) {
        return (sortedValues[middle - 1] + sortedValues[middle]) / 2;
    } else {
        return sortedValues[middle];
    }
}

function replaceAllWithMedian(data, column) {
    const medianValue = calculateMedian(data, column);

    return data.map(item => ({
        ...item,
        [column]: medianValue
    }));
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
// NER Anonymize

function anonymizeJson(data) {
    if (typeof data === "object" && data !== null) {
        if (Array.isArray(data)) {
            return data.map(anonymizeJson); // Process array elements
        } else {
            let anonymizedObj = {};
            for (let key in data) {
                anonymizedObj[key] = anonymizeValue(key, data[key]);
            }
            return anonymizedObj;
        }
    }
    return data;
}

function anonymizeValue(key, value) {
        value = anonymizeEmail(value);
        value = anonymizePhone(value);
        //value = anonymizeCard(value);
        //value = anonymizeIP(value);
        //value = anonymizeSSN(value);
        //value = anonymizeName(value);
        //value = anonymizeAddress(value);
    return value;
}

function anonymizeValue_old(key, value) {
    console.log(typeof value)
    if (typeof value === "string") {
        // Apply different anonymization rules based on key names
        if (/email/i.test(key)) return anonymizeEmail(value);
        if (/phone|mobile/i.test(key)) return anonymizePhone(value);
        if (/card|credit/i.test(key)) return anonymizeCard(value);
        if (/ip/i.test(key)) return anonymizeIP(value);
        if (/ssn/i.test(key)) return anonymizeSSN(value);
        if (/name/i.test(key)) return anonymizeName(value);
        if (/address/i.test(key)) return anonymizeAddress(value);
    } else if (typeof value === "object") {
        return anonymizeJson(value); // Recursive anonymization for nested objects
    }
    return value;
}

// **Anonymization Helper Functions**
function anonymizeEmail(email) {
    return email.replace(/^(.)(.*)(@.*)$/, (match, first, middle, domain) =>
        first + "*".repeat(middle.length) + domain
    );
}

function anonymizePhone(phone) {
    return phone.replace(/\d(?=\d{4})/g, "*");
}

function anonymizeCard(cardNumber) {
    return cardNumber.replace(/\d(?=\d{4})/g, "*");
}

function anonymizeIP(ip) {
    return ip.replace(/(\d+\.\d+\.\d+)\.\d+/, "$1.***");
}

function anonymizeSSN(ssn) {
    return ssn.replace(/\d(?=\d{4})/g, "*");
}

function anonymizeName(name) {
    return name.replace(/\b(\w)\w+/g, "$1.");
}

function anonymizeAddress(address) {
    return address.replace(/^(\d+)\s+(.+)$/, "$1 *****");
}


//************************************************
// Step 5
// Insert Dataset Metadata to DB
//************************************************

function checkTempMetaData() {
    let question_verify = $('#question_verify').is(':checked');
    if (question_verify ){
        saveTempMetaData();
    }
}

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      // Does this cookie string begin with the name we want?
      if (cookie.substring(0, name.length + 1) === (name + "=")) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

async function saveTempMetaData(){
    let dataset_name = $('#dataset_name').val();
    let dataset_owner = $('#dataset_owner').val();
    let dataset_language = JSON.stringify($('#dataset_language').val());
    let dataset_license = $('#dataset_license').val();
    let dataset_format = $('#dataset_format').val();
    let dataset_desc = $('#dataset_desc').val();
    let dataset_columnDataType = JSON.stringify(cols);

    const url="{% url 'dataset:saveTempMetaData' %}"
    const newDataset = {
        dataset_name: dataset_name,
        dataset_owner: dataset_owner,
        dataset_language: dataset_language,
        dataset_license: dataset_license,
        dataset_format: dataset_format,
        dataset_desc: dataset_desc,
        dataset_columnDataType: dataset_columnDataType
    }

    await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({dataset: newDataset })
    })
    .then(response => response.json())
    .then(data => {
      console.log(data);
    });
}

