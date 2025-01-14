const MAX_SEQUENCE_LENGTH = 113;
const getKey = (obj,val) => Object.keys(obj).find(key => obj[key] === val); // For getting tags by tagid


let model, emodel;
(async function() {
    // model = await tf.loadLayersModel('http://localhost:8081/tfjs_models/ner/model.json');
    model = await tf.loadLayersModel('model.json');
    let outputs_ = [model.output, model.getLayer("attention_vector").output];
    emodel = tf.model({inputs: model.input, outputs: outputs_});
    $('.loading-model').remove();
})();


function word_preprocessor(word) {
  word = word.replace(/[-|.|,|\?|\!]+/g, '');
  word = word.replace(/\d+/g, '1');
  word = word.toLowerCase();
  if (word != '') {
    return word;
  } else {
    return '.'
  }
};

function make_sequences(words_array) {
  let sequence = Array();
  words_array.slice(0, MAX_SEQUENCE_LENGTH).forEach(function(word) {
    word = word_preprocessor(word);
    let id = words_vocab[word];
    if (id == undefined) {
      sequence.push(words_vocab['<UNK>']);
    } else {
      sequence.push(id);
    }  
  });

  // pad sequence
  if (sequence.length < MAX_SEQUENCE_LENGTH) {
    let pad_array = Array(MAX_SEQUENCE_LENGTH - sequence.length);
    pad_array.fill(words_vocab['<UNK>']);
    sequence = sequence.concat(pad_array);
  }

  return sequence;
};

async function make_predict() {
    $(".main-result").html("");
    $('.attention-bar').html("");
    $(".tags-result").html("<h5>Tags review</h5><table class='table table-sm table-bordered tags-review'></table>");

    let words = $('#input_text').val().split(' ');
    let sequence = make_sequences(words);
    let tensor = tf.tensor1d(sequence, dtype='int32')
      .expandDims(0);
    let [predictions, attention_probs] = await emodel.predict(tensor);
    attention_probs = await attention_probs.data();
    
    predictions = await predictions.argMax(-1).data();
    let predictions_tags = Array();
    predictions.forEach(function(tagid) {
      predictions_tags.push(getKey(tags_vocab, tagid));
    });

    words.forEach(function(word, index) {
      let current_word = word;
      if (['B-ORG', 'I-ORG'].includes(predictions_tags[index])) {
        current_word += " <span class='badge badge-primary'>"+predictions_tags[index]+"</span>";
      };
      if (['B-PER', 'I-PER'].includes(predictions_tags[index])) {
        current_word += " <span class='badge badge-info'>"+predictions_tags[index]+"</span>";
      };
      if (['B-LOC', 'I-LOC'].includes(predictions_tags[index])) {
        current_word += " <span class='badge badge-success'>"+predictions_tags[index]+"</span>";
      };
      if (['B-MISC', 'I-MISC'].includes(predictions_tags[index])) {
        current_word += " <span class='badge badge-warning'>"+predictions_tags[index]+"</span>";
      };
      $(".main-result").append(current_word+' ');
    });

};

$("#get_ner_button").click(make_predict);
$('#input_text').keypress(function (e) {
    if (e.which == 13) {
      make_predict();
    }
  });