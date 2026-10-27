# End-to-end encrypted recordings

## Recommendation

Aavaaz can provide end-to-end encrypted meeting recordings when capture,
transcription, and post-processing run on the user's device. The server then
stores only encrypted video, audio, transcripts, captions, and metadata.

Cloud transcription can provide zero-access storage after processing, but it
cannot provide end-to-end encryption. Whisper must receive plaintext audio.
The cloud worker can therefore read the recording while it transcribes it.

Aavaaz should expose these as two separate modes:

- Private local mode transcribes and encrypts on the user's device. Aavaaz
  never receives plaintext content.
- Cloud transcription mode uses the existing server inference and encrypts
  retained content for the user after processing. The worker sees plaintext
  during the job.

Private local mode should be the default for users who select end-to-end
encryption. Cloud transcription should state its weaker protection before an
upload begins.

## Terms

Server-side encryption protects storage devices and snapshots. The service
controls the keys and decrypts data for authorized application roles.

Zero-access encryption stores data under a key that the service does not
possess. The service may receive plaintext before storage, then encrypt it to
the user's public key. Proton describes incoming mail from external providers
this way.

End-to-end encryption encrypts content before it reaches the service. Only an
authorized user device decrypts it. The service never receives the plaintext.

Proton documents the distinction in its
[zero-access encryption explanation](https://proton.me/learn/encryption/types-of-encryption/zero-access).

## Current Aavaaz data paths

Aavaaz currently relies on AWS server-side encryption. S3 encrypts new objects
with SSE-S3 by default. DynamoDB encrypts all stored table data. Lambda encrypts
its temporary storage. These controls protect durable media, but AWS and the
Aavaaz application roles can read the data.

Relevant AWS documentation:

- [S3 encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingEncryption.html)
- [DynamoDB encryption at rest](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/EncryptionAtRest.html)
- [Lambda temporary storage](https://docs.aws.amazon.com/lambda/latest/dg/configuration-ephemeral-storage.html)

The current batch and live paths expose plaintext in several places:

- Files larger than 4 MB are uploaded directly to S3 through a presigned POST.
  `dashboard/src/app/dashboard/upload/page.tsx` selects this path.
- `aavaaz/serverless/lambda_handler.py` downloads the S3 object into Lambda
  temporary storage, transcribes it, writes the transcript to S3, and deletes
  the input object.
- Small files are sent as base64 JSON and decoded into a temporary plaintext
  file before transcription.
- Authenticated jobs can save the original filename and complete transcript
  text in DynamoDB through `_record_usage`.
- `aavaaz/api/dynamo_store.py` performs transcript substring search over that
  plaintext text.
- The live dashboard sends raw Float32 PCM audio to the Modal WebSocket.
- Large-upload S3 keys include the original filename. S3 metadata can include
  the user ID, hotwords, feature settings, and callback URL.

The checked-in Lambda deployment does not set `AAVAAZ_REQUIRE_API_KEY`, so API
key enforcement defaults to disabled. When authentication is enabled, the
transcription status route validates the API key but does not verify that the
caller owns the requested upload key. Authentication and job ownership must be
fixed before encrypted storage is added.

## Private meeting recording flow

The end-to-end encrypted meeting flow is:

```text
camera, microphone, screen, or imported video
                    |
                    v
        local audio extraction
                    |
                    v
        local Whisper transcription
                    |
                    v
 local formatting, captions, and analysis
                    |
                    v
       authenticated local encryption
                    |
                    v
          ciphertext upload
                    |
                    v
             S3 and DynamoDB
```

The original video does not need to be decoded into image frames for speech
recognition. The client extracts its audio track locally and passes that audio
to Whisper. The original video can be encrypted in chunks while transcription
runs.

The client encrypts all content that could reveal the meeting:

- Original video and extracted audio
- Transcript text, words, timestamps, and captions
- Filename and meeting title
- Speaker names and diarization results
- Tags, summaries, topics, and entities
- Thumbnails, waveforms, and preview images
- Custom vocabulary and hotwords attached to the recording

The server can retain an opaque recording ID, ciphertext locations, wrapped
keys, creation time, ciphertext sizes, and billing quantities. Account IDs,
access times, file sizes, and duration remain visible metadata unless the
product removes or pads those values.

## Client architecture

A browser implementation is suitable for a proof and for short recordings.
Transformers.js documents Whisper inference through WebGPU. WebGPU support and
performance still vary by browser and device.

[Transformers.js WebGPU guide](https://huggingface.co/docs/transformers.js/guides/webgpu)

The whisper.cpp browser implementation supports local WebAssembly inference.
Its documentation reports useful performance for the `tiny` and `base` models
and considers models larger than `small` unsuitable for normal browser memory
and performance.

[whisper.cpp browser documentation](https://github.com/ggml-org/whisper.cpp/blob/master/examples/whisper.wasm/README.md)

An installed desktop application is the practical target for hour-long
meetings. It can:

- Capture microphone, camera, screen, tab, and system audio with explicit OS
  permissions.
- Use native FFmpeg to demux and resample audio without uploading the video.
- Run larger Whisper models through the user's CPU or GPU.
- Continue transcription and encryption in the background.
- Upload encrypted chunks without holding the entire recording in memory.
- Store private keys in the operating system credential store.

The web dashboard can remain the account, playback, search, and sharing client.
It downloads and decrypts authorized content locally. A signed desktop client
provides a stronger security boundary because the web server can replace
browser JavaScript on the next page load.

## Encryption format

Each recording receives a random data-encryption key. The client uses that key
to encrypt the recording and its derived data. The client then wraps the data
key for every authorized user.

Large video and audio files require authenticated streaming encryption. Aavaaz
should use an existing construction instead of defining nonce and chunk rules.
Libsodium provides XChaCha20-Poly1305 `secretstream` for authenticated files and
multipart messages. It authenticates every chunk, marks the final chunk, and
handles rekeying.

- [Libsodium secretstream](https://doc.libsodium.org/secret-key_cryptography/secretstream)
- [libsodium.js releases](https://github.com/jedisct1/libsodium.js/releases)

Small transcript and metadata objects can use the same format or a single
authenticated XChaCha20-Poly1305 message. Every encrypted object needs a
versioned envelope containing its format version, object ID, content type,
stream header, wrapped data keys, and authenticated non-secret metadata.

The format must support partial video retrieval. Playback downloads encrypted
chunks, verifies and decrypts them locally, then feeds plaintext chunks into the
browser or desktop media pipeline. Plaintext chunks remain in memory and are
never uploaded.

## Account keys and recovery

The client generates the account encryption key. The server stores the public
key and an encrypted private-key package. It never stores the unlocked private
key or the secret that unlocks it.

Cognito authentication remains separate from content encryption. A user can
authenticate successfully and still need to unlock the encrypted vault.

The unlock secret can be a separate vault password or recovery key. A recovery
phrase or downloadable recovery file is required for password resets and lost
devices. If the user loses every private key and all recovery material, the
recordings cannot be recovered. Adding a server recovery key would allow the
server to decrypt content and would invalidate the zero-access claim.

Key rotation should create a new account key and rewrap each recording's small
data key. The video and transcript ciphertext do not need to be rewritten.

## Teams and sharing

Every team member has a public encryption key. Sharing a recording adds a copy
of its data key wrapped to that member. The recording ciphertext remains
unchanged.

Removing a member deletes their wrapped key and prevents future downloads. It
cannot revoke plaintext or keys that the member already downloaded. The user
interface and security documentation must state this limitation.

Adding a new device requires approval from an existing device or use of the
account recovery material. The server cannot approve a new encryption key by
itself without weakening protection against account and server compromise.

## Product changes

End-to-end encryption moves several current server features into the client:

- Transcript search uses a local encrypted index. Proton uses the same design
  for encrypted message search.
  [Proton content search](https://proton.me/support/search-message-content)
- Formatting, PII removal, summaries, topics, and tags run locally before
  encryption.
- Speaker diarization runs locally or is unavailable in private mode until a
  suitable local implementation exists.
- Webhooks either send ciphertext to a recipient with a registered public key
  or run from an authorized client after decryption.
- API clients need an encryption SDK and local key storage.
- Server-generated thumbnails, previews, and media transcoding are disabled.
  The client generates encrypted derivatives instead.
- Billing can use duration supplied by the client, or retain duration as clear
  metadata. Client-supplied duration is not trustworthy for enforcement.

The existing cloud pipeline can continue supporting users who need `large-v3`,
server-side diarization, webhooks, or devices that cannot run local models. Its
interface must state that the cloud worker processes plaintext.

## Security boundaries

End-to-end encryption protects stored recordings from an S3 or DynamoDB leak,
an AWS role that can read application data, and later access by the Aavaaz
service.

It does not protect content from:

- Malware or another user on an unlocked device
- A compromised browser page after the vault is unlocked
- Screen capture or audio capture performed by meeting participants
- An authorized team member who saves a decrypted copy
- Traffic analysis based on account activity, time, and ciphertext size

The design needs an independent cryptographic and application security review
before it supports production recordings. The clients and encryption format
should be open source so users can inspect the implementation and build signed
clients from source.

## Implementation sequence

### 1. Fix authentication and ownership

Require authenticated users on batch, status, cancellation, and live routes.
Associate every job with its user and verify ownership on every read and
delete. Remove original filenames from S3 keys and logs. Define retention for
temporary plaintext cloud jobs.

### 2. Prove local transcription

Run representative five-minute and one-hour recordings through browser WebGPU
and a desktop local engine. Measure word accuracy, elapsed time, peak memory,
model download size, battery use, and supported hardware. Compare the results
with the current `large-v3` cloud output.

### 3. Prove the encrypted recording format

Encrypt a large video and transcript on the client, upload only ciphertext,
reload the client, download selected chunks, and decrypt them for playback.
Test corruption, truncation, reordered chunks, interrupted uploads, and resume.

### 4. Add single-user encrypted storage

Add account key creation, vault unlock, recovery material, encrypted metadata,
encrypted uploads, local playback, and local transcript viewing. Do not add
team sharing until recovery and key rotation work across multiple devices.

### 5. Add encrypted search and sharing

Build the local transcript index. Add per-user wrapped recording keys, device
approval, key rotation, and removal behavior.

### 6. Add private live meetings

Capture and transcribe audio locally while encrypting recording chunks. Upload
completed encrypted chunks in the background. Keep plaintext audio and partial
transcripts in client memory only.

## Proof acceptance criteria

The first proof is successful when:

- Network inspection shows no plaintext audio, video, transcript, filename, or
  meeting title leaving the client.
- S3 and DynamoDB contain only ciphertext and permitted metadata.
- Restarting the client can resume an interrupted encrypted upload.
- Modified, missing, duplicated, and reordered chunks fail authentication.
- An account without the private key cannot decrypt a recording even with full
  S3, DynamoDB, and application-role access.
- A recovery key restores access on a second device.
- Losing both the private key and recovery key leaves the content unrecoverable.
- The measured local transcription quality and speed meet the selected product
  target.

## Decisions required before implementation

- Decide whether private mode starts as a browser feature or a desktop
  application. A desktop application is recommended for full meetings.
- Select the largest local Whisper model that meets the target device and
  transcription-time requirements.
- Decide whether private mode stores the original video, the transcript only,
  or both.
- Decide whether team sharing and multiple devices are required in the first
  release.
- Decide which metadata the server may retain for billing and abuse controls.
- Define the cloud mode retention period and the exact statement shown before
  plaintext cloud processing begins.
