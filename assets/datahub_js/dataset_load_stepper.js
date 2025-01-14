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
            var dt_data = results.data
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
            const col = {'name':name, 'dtype':dtype, 'desc':desc, 'di_type':di_type};
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
            { data: 'di_type' }
            ]
        } );
}

$('#tb_metadata').DataTable( {
    data: [],
    columns: [
        { data: 'name' },
        { data: 'dtype' },
        { data: 'desc' },
        { data: 'di_type' }
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

