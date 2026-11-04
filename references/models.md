# Local model routing

The local-only configuration is [config/models.local.json](../config/models.local.json).
It routes image understanding and word planning to **Doubao 2.0-lite** at
`ep-20260914174304-5d8v2`, and photographic generation/editing to **Seedream 5.0 Pro**
at `ep-20260914155654-cjmcd`. The `model` request field is the endpoint ID, not the display name.
These labels reflect the user's deployment mapping; only a live authorized call can confirm
the provider-side deployment, permissions and model-specific parameters.

## Configure the two credentials

The packaged configuration keeps the requested endpoint mapping but contains no API keys
or machine-specific credential paths. Set two role-specific environment variables before
calling the wrapper:

```bash
export ARK_TEXT_API_KEY="your-doubao-key"
export ARK_IMAGE_API_KEY="your-seedream-key"
```

`ARK_TEXT_API_KEY` is used only for analysis and `ARK_IMAGE_API_KEY` only for image
generation. There is no cross-model credential fallback and no shared `ARK_API_KEY`
fallback. If a private raw-key file is preferred, add an absolute `api_key_file` path to
the matching role in `config/models.local.json`; keep `api_key_file_format` set to
`raw_key_text`. Never put a key inside that JSON file.

The wrapper reads only the explicitly configured environment variables or files; normal
invocation must not search other skills or credential stores. It never displays keys or
places them into model payloads. Local key files are parsed as data, never executed as
shell scripts. Never place credentials in Git, an archive or a debugging transcript.
Exclude `.env`, `.env.*` and credential files from every package.

Check readiness without showing key values or sending a paid request:

```bash
<python-with-pillow> scripts/ark_models.py check-keys
```

It reports only `analysis` and `image_generation` readiness booleans. This is not a live
validation of the keys or endpoint access. Do not put keys in source, JSON, prompts, shell
history or chat; use only the configured private files or role-specific environment variables.

## Understand the source

Use `scripts/ark_models.py analyze` for the model-planning step, then review the returned
spec for image grounding, anchors and face visibility before running the existing renderer:

```bash
<python-with-pillow> scripts/ark_models.py analyze \
  --input /absolute/path/photo.jpg \
  --output /absolute/path/new-spec.json
<python-with-pillow> scripts/render_crossword_collage.py \
  --input /absolute/path/photo.jpg \
  --spec /absolute/path/new-spec.json \
  --output /absolute/path/collage.png
```

Repeat `--input` for multiple photos. `--brief` supplies the user's content directions;
`--variant` controls renderer variation. The default `--grid-style random` preserves the
seeded 50/50 full-grid/no-grid behavior. Use `full` or `none` when explicitly requested.

## Optional photographic generation

Preserve-source overlay remains the default; configuring Seedream does not mean every
collage must regenerate the user's photo. When the user requests cutouts or a transformed
photographic layer, put its art direction in a UTF-8 prompt file and call:

```bash
<python-with-pillow> scripts/ark_models.py generate \
  --input /absolute/path/photo.jpg \
  --prompt-file /absolute/path/photo-layer-prompt.txt \
  --output /absolute/path/generated-layer.png
```

The prompt should retain the input's distinctive subject/details and request no final
letters, crossword tiles or grid. Inspect the generated layer, analyze that layer with
Doubao, and apply final typography/grid with the renderer. Generation defaults to one
image at `2K`; `--size` and `--timeout` can be adjusted for the endpoint's supported values.
The wrapper requests base64 and converts the response to PNG, without downloading URLs.

Calls send EXIF-stripped JPEG previews (longest edge at most 2048 px) to the configured
Beijing Ark API and may incur charges. They make one request with no automatic retries,
fallback models or telemetry. Missing credentials, endpoint errors, malformed responses
or timeouts should stop the model step; do not silently substitute another model.
The original source file is not modified. Existing output paths are refused by the CLI.

The endpoint IDs in this package are configuration, not credentials. Review access,
privacy and billing before using them, and never publish role-specific API keys.

API shapes verified against the provider's primary sources:
[image-generation implementation](https://github.com/volcengine/volcengine-python-sdk/blob/master/volcenginesdkarkruntime/resources/images/images.py),
[image-input schema](https://github.com/volcengine/volcengine-python-sdk/blob/master/volcenginesdkarkruntime/types/chat/chat_completion_content_part_image_param.py),
[API base URL](https://github.com/volcengine/volcengine-python-sdk/blob/master/volcenginesdkarkruntime/_constants.py).
