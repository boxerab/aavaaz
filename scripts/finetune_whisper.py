# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "accelerate",
#     "av<19",
#     "faster-whisper",
#     "jiwer",
#     "requests",
#     "torch",
#     "transformers>=5",
# ]
# ///
import argparse
import csv
import random

import jiwer
import torch
from faster_whisper.audio import decode_audio
from transformers import (
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
    WhisperForConditionalGeneration,
    WhisperProcessor,
)

SAMPLE_RATE = 16000


class SpeechDataset(torch.utils.data.Dataset):
    def __init__(self, rows: list[tuple[str, str]], processor: WhisperProcessor):
        self.rows = rows
        self.processor = processor

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        audio_path, transcription = self.rows[index]
        audio = decode_audio(audio_path, sampling_rate=SAMPLE_RATE)
        features = self.processor.feature_extractor(audio, sampling_rate=SAMPLE_RATE)
        return {
            "input_features": features.input_features[0],
            "labels": self.processor.tokenizer(transcription).input_ids,
        }


class SpeechCollator:
    def __init__(self, processor: WhisperProcessor, decoder_start_token_id: int):
        self.processor = processor
        self.decoder_start_token_id = decoder_start_token_id

    def __call__(self, items):
        batch = self.processor.feature_extractor.pad(
            [{"input_features": item["input_features"]} for item in items], return_tensors="pt"
        )
        padded = self.processor.tokenizer.pad(
            [{"input_ids": item["labels"]} for item in items], return_tensors="pt"
        )
        labels = padded["input_ids"].masked_fill(padded["attention_mask"].ne(1), -100)
        # the model prepends the decoder start token itself during training
        if (labels[:, 0] == self.decoder_start_token_id).all():
            labels = labels[:, 1:]
        batch["labels"] = labels
        return batch


def main():
    parser = argparse.ArgumentParser(description="Fine-tune Whisper on a CSV manifest")
    parser.add_argument("--manifest", required=True, help="CSV with audio_path,transcription")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--base-model", default="openai/whisper-small")
    parser.add_argument("--language", required=True, help="Language code, such as en")
    parser.add_argument("--epochs", type=float, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument(
        "--eval-fraction", type=float, default=0.1, help="Share of rows held out for WER"
    )
    args = parser.parse_args()

    with open(args.manifest, newline="") as manifest:
        rows = [(row["audio_path"], row["transcription"]) for row in csv.DictReader(manifest)]
    random.Random(0).shuffle(rows)
    eval_count = max(1, int(len(rows) * args.eval_fraction))
    if eval_count >= len(rows):
        raise ValueError(f"{args.manifest} has {len(rows)} rows, too few to hold any out")

    processor = WhisperProcessor.from_pretrained(
        args.base_model, language=args.language, task="transcribe"
    )
    model = WhisperForConditionalGeneration.from_pretrained(args.base_model)
    model.generation_config.language = args.language
    model.generation_config.task = "transcribe"

    def word_error_rate(prediction):
        label_ids = prediction.label_ids
        label_ids[label_ids == -100] = processor.tokenizer.pad_token_id
        predicted = processor.batch_decode(prediction.predictions, skip_special_tokens=True)
        expected = processor.batch_decode(label_ids, skip_special_tokens=True)
        return {"wer": jiwer.wer(expected, predicted)}

    training_arguments = Seq2SeqTrainingArguments(
        output_dir=args.output_dir,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        num_train_epochs=args.epochs,
        warmup_steps=0.1,
        fp16=torch.cuda.is_available(),
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=1,
        load_best_model_at_end=True,
        metric_for_best_model="wer",
        greater_is_better=False,
        predict_with_generate=True,
        generation_max_length=225,
        report_to="none",
    )
    trainer = Seq2SeqTrainer(
        model=model,
        args=training_arguments,
        train_dataset=SpeechDataset(rows[eval_count:], processor),
        eval_dataset=SpeechDataset(rows[:eval_count], processor),
        data_collator=SpeechCollator(processor, model.config.decoder_start_token_id),
        compute_metrics=word_error_rate,
        processing_class=processor.feature_extractor,
    )
    print("WER before fine-tuning:", trainer.evaluate()["eval_wer"])
    trainer.train()
    print("WER after fine-tuning:", trainer.evaluate()["eval_wer"])
    trainer.save_model(args.output_dir)
    processor.save_pretrained(args.output_dir)


if __name__ == "__main__":
    main()
