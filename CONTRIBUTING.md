# Contributing

Thanks for helping improve Image Crossword Collage.

## Before opening a pull request

1. Keep the semantic/model layer separate from deterministic rendering. The renderer should accept a documented JSON spec and should not require a hosted model or private service.
2. Do not commit user images, third-party reference artwork, model credentials, or generated files whose reuse rights are unclear.
3. Preserve reproducibility: the same source bytes, spec, and variant should produce the same output in the same supported environment.
4. Add or update tests for observable behavior rather than exact prose or a particular random layout.
5. Run:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
```

Small, focused pull requests are easier to review. Explain any visible design change and include a synthetic or freely licensed example when visual comparison is necessary.
