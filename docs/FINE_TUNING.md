# Fine-tuning Whisper for Aavaaz

Train on your own audio, convert the result to CTranslate2, and serve it with `aavaaz serve --model <dir>`.

## 1. Manifest

A CSV with an `audio_path` and a `transcription` column. Any format PyAV decodes works, audio is resampled to 16 kHz on load.

```csv
audio_path,transcription
/data/audio/001.wav,the patient shows symptoms of hypertension
/data/audio/002.wav,administer fifty milligrams of metoprolol
```

Write transcriptions the way you want them to come out. The model learns the casing, punctuation and number style of the labels.

## 2. Train

```bash
uv run scripts/finetune_whisper.py \
  --manifest data/manifest.csv \
  --output-dir models/whisper-medical \
  --language en
```

The dependencies are declared in the script header, so `uv run` installs them in a throwaway environment.

| Flag | Default |
|---|---|
| `--base-model` | `openai/whisper-small` |
| `--epochs` | 3 |
| `--batch-size` | 8 |
| `--learning-rate` | 1e-5 |
| `--eval-fraction` | 0.1 |

The script holds out `--eval-fraction` of the rows, prints their WER before and after training, and keeps the epoch with the lowest WER. Training uses fp16 when CUDA is available.

## 3. Convert

```bash
uvx --from ctranslate2 --with transformers --with torch ct2-transformers-converter \
  --model models/whisper-medical \
  --output_dir models/whisper-medical-ct2 \
  --quantization int8 \
  --copy_files tokenizer.json preprocessor_config.json
```

faster-whisper reads `tokenizer.json` and `preprocessor_config.json` from the model directory, so `--copy_files` is required.

## 4. Serve

```bash
aavaaz serve --model models/whisper-medical-ct2
```

A `--model` value that is a path loads that directory. The REST `/health` route reports it as the model.

## Reference run

whisper-tiny, 40 espeak-ng clips of drug-dosing sentences, 5 epochs at `--learning-rate 1e-4`: held-out WER went from 0.92 to 0.0 in 40 s on an RTX 3060. On a new sentence, base tiny gave "lots of tune, and that or master tune", the fine-tuned model gave "losartan and atorvastatin". Synthetic speech overfits easily, so expect smaller gains on real recordings.
