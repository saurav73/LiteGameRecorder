# Version control

How versioning and releases work for this project. Follow this on
every change so the version in the app, the changelog, the git tag,
and the downloads always agree.

## Version numbers

Semantic Versioning: MAJOR.MINOR.PATCH (for example 2.4.0).

- PATCH (2.4.0 -> 2.4.1): bug fixes and content fixes, no new
  features. Example: replacing the meme clips with real footage.
- MINOR (2.4.0 -> 2.5.0): new features, backwards compatible.
  Example: a new export preset or a new recording mode.
- MAJOR (2.4.0 -> 3.0.0): breaking changes, for example a new
  project file format old versions cannot open.

## Single source of truth

The version lives in exactly one place: `app_version.py`
(`__version__`). `app.py` and `installer.py` import it. Never
hardcode a version string anywhere else. The About dialog, the
window title, and the setup window all read from it.

## Making a release

1. Finish and test the work on `main` in small focused commits.
2. Bump `__version__` in `app_version.py`.
3. Move the changes from `Unreleased` in `CHANGELOG.md` into a new
   version section with the release date.
4. Commit the version bump and changelog together:
   `Bump version to X.Y.Z`.
5. Tag the release: `git tag -a vX.Y.Z -m "Lite Tutorial Maker vX.Y.Z - <one line>"`.
6. Push the commit and the tag: `git push origin main` then
   `git push origin vX.Y.Z`.
7. The GitHub Actions workflow (`.github/workflows/build-release.yml`)
   builds the app on Windows, macOS, and Linux, bundles each OS's
   FFmpeg plus sounds, meme videos, and templates, and publishes
   one Release with three zips attached. A release only publishes
   when all three OS builds succeed. The download links are then:
   `https://github.com/saurav73/LiteGameRecorder/releases/download/vX.Y.Z/LiteGameRecorder-vX.Y.Z-Windows.zip`
   (and the same pattern for `-macOS.zip` and `-Linux.zip`). The
   built-in updater matches assets by the OS name in the file name,
   so never rename the assets.

## Rules

- `main` is the release branch. Every commit on `main` should be
  shippable: the app starts, the tests pass, nothing half done.
- One feature or fix per commit, with a clear message.
- Never move or delete a tag after it is pushed. A bad release is
  fixed by a new patch version, never by rewriting the old tag.
- Never force-push to `main`. If a push is rejected, pull and
  rebase first.
- Never commit secrets, API keys, `__pycache__`, or `.pyc` files.
  See `.gitignore`.
- The `meme-videos/` and `sounds/` folders are content, not code:
  their sources are documented in `meme-videos/MANIFEST.json` and
  `sounds/SOURCES.txt`. Only legal free sources (public domain,
  Creative Commons, royalty-free) go in.
