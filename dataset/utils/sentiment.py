from transformers import pipeline

# مسیر ذخیره مدل در پوشه assets/models
MODEL_PATH = "assets/models/sentiment_model"

# دانلود و ذخیره مدل
sentiment_pipeline = pipeline("sentiment-analysis", model="HooshvareLab/bert-fa-base-uncased")
sentiment_pipeline.model.save_pretrained(MODEL_PATH)
sentiment_pipeline.tokenizer.save_pretrained(MODEL_PATH)

print(f"✅ مدل در مسیر {MODEL_PATH} ذخیره شد.")