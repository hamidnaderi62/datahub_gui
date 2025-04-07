$.fn.dataTable.ext.errMode = 'throw';
let cols;
//************************************************
// Step 2
//
//************************************************


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
            const col = {'name':name, 'dtype':dtype, 'desc':desc};
            cols.push(col)
        }
    }

     $('#tb_metadata').DataTable( {
        data: cols,
        "bDestroy": true,
        columns: [
            { data: 'name' },
            { data: 'dtype' },
            { data: 'desc' }
            ]
        } );
}


$('#tb_metadata').DataTable( {
    data: [],
    columns: [
        { data: 'name' },
        { data: 'dtype' },
        { data: 'desc' }
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
    let dataset_language = $('#dataset_language').val().join(',');
    let dataset_license = $('#dataset_license').val();
    let dataset_format = $('#dataset_format').val();
    let dataset_desc = $('#dataset_desc').val();
    let dataset_tags = JSON.parse($('#dataset_tags').val()).map(item => item.value).join(',');
    let dataset_columnDataType = JSON.stringify(cols);


    const url="{% url 'dataset:saveTempMetaData' %}"
    const newDataset = {
        dataset_name: dataset_name,
        dataset_owner: dataset_owner,
        dataset_language: dataset_language,
        dataset_license: dataset_license,
        dataset_format: dataset_format,
        dataset_desc: dataset_desc,
        dataset_tags: dataset_tags,
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


function checkTempMetaData() {
    let question_verify = $('#question_verify').is(':checked');
    if (question_verify ){
        saveTempMetaData();
    }
}




