# Development and release maintenance

End users download an installer from GitHub Releases. These commands are only for developers working on the source.

## Setup

Python 3.11+ is required. Dependencies live in `pyproject.toml`.

Windows:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\custom-presence.exe
```

macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/custom-presence
```

Alternatively run `python app.py`. For browser development run `custom-presence-server` and open http://127.0.0.1:8000. The browser server remains running until its process is stopped.

## Publish from the GitHub website

1. Create a GitHub repository and upload this project's source, including `.github/workflows/release.yml`. Exclude `.venv`, `build`, `dist`, and the other files listed in `.gitignore`.
2. On GitHub, choose **Releases → Draft a new release**. Create a version tag such as `v0.1.0`, then click **Publish release**.
3. The **Build desktop downloads** workflow tests and builds Windows, Apple Silicon Mac, and Intel Mac packages, then attaches all three downloads to that release after every build succeeds.
4. Link users to that repository's **Releases** page. Once the repository exists, README download buttons can point directly at `/releases/latest/download/CustomPresence-Windows-Setup.exe` and the corresponding Mac filenames.

No terminal is needed for publishing from GitHub. **Actions → Build desktop downloads → Run workflow** also builds test downloads without publishing a release. Workflow files must exist in the released source. Actions must be enabled for the repository.

The shared, public Discord Application ID is in `custompresence/config.py` and is bundled into every build. It is not a token or client secret. Users cannot change it through the activity form or API. Old saved settings containing an Application ID are read without exposing that field again.

Uploads use [ImgBB's API](imgbb.md). Put `IMGBB_API_KEY=your_key_here` in the repository's ignored `.env` for local owner testing. Released apps use a public upload-service URL configured once by the owner, keeping the account key on that service. The presence editor only loads bundled scripts and never exposes a key field.

Publish the included [Terms and Privacy pages](policies.md) with the separate GitHub Pages workflow and enter their public links in the Discord application settings. A repository must exist before those links can be published.

## Local builds

Using the virtual environment's Python:

```sh
python -m PyInstaller custompresence.spec
```

This creates `dist/CustomPresence.exe` on Windows or `dist/CustomPresence.app` on macOS, including Python, dependencies, and interface assets.

The window, executable, and installer use the bundled Custom Presence icon, independently of activity artwork. The Mac application bundle uses its ICNS version. To regenerate these assets after changing the geometric design, run `python scripts/build_icons.py` before packaging.

For release installers, use:

```sh
python scripts/package_release.py
```

Windows installer builds require Inno Setup 6. The GitHub Windows runner includes it. Packaging downloads Microsoft's small WebView2 bootstrapper and embeds it in the installer; end users only need internet access if WebView2 is missing. Mac packaging uses the system `hdiutil` command and includes an Applications shortcut in the DMG.

Build separately on each OS and Mac architecture. These builds are unsigned; production signing and macOS notarization require the developer's certificates and are not configured yet. Unsigned downloads can show OS security warnings, especially on macOS.

## Checks

```sh
python -m unittest discover -s tests -v
```

Tests cover advanced-field validation and RPC mapping, settings persistence and invite-token exclusion, native API upload requests with simulated host responses, persistent upload reuse and bounded history, concurrent identical uploads, local-history deletion, file validation, public-link conversion and checks, private-address rejection, upload-service limits, Discord handshake timeouts, and server/window lifecycle. Discord IPC and native windows are mocked in unit tests. Actual uploads need the owner's ImgBB configuration; actual profile display requires Discord desktop and activity sharing to be enabled.

Settings are saved in the user's platform-specific CustomPresence data folder; logs are in its platform-specific log folder. On Windows these are `%LOCALAPPDATA%/CustomPresence/settings.json` and `%LOCALAPPDATA%/CustomPresence/Logs/desktop.log`. On macOS they are `~/Library/Application Support/CustomPresence/settings.json` and `~/Library/Logs/CustomPresence/desktop.log`.

The private upload reuse index is `uploads.json` beside `settings.json`. It remembers up to 100 file-content hashes and host receipts, including removal links. It contains no original image files or API keys. See [upload retention](imgbb.md#reuse-and-retention).

The webview uses a private browser session. Editor assets and API responses use `Cache-Control: no-store`, and the client bypasses cached responses. Startup resets form defaults before applying saved preferences, so old browser form state cannot supply example artwork. Earlier versions may have left a `webview` directory beside the settings file; the current version does not use it.

## Rich Presence fields

The app uses `pypresence` and Discord desktop's `SET_ACTIVITY` RPC, rather than Discord's Social SDK. These APIs have different capabilities. Blank optional fields are sent as `None` so applying a simpler presence replaces previously configured fields.

Activity names can be empty in the editor and saved settings. Discord rejects a truly empty name, so the RPC payload uses one space for a blank name. Legacy settings that contain the old automatic "Custom Presence" name are restored as empty; new explicitly saved names are preserved.

When party sizes are set, an empty State is sent as `In a party`. A missing party ID is generated per app session and stays stable across updates; supplied game-integration IDs are preserved. Playing uses Discord's native party count. Listening, Watching, and Competing also include the count in State text because their layouts may omit the native badge. The preview follows the same text rule. Generated values do not overwrite the user's saved State or party ID. Removing sizes clears the automatic state and party data. Check the expanded activity card after applying; the compact member-list status is not the full presence card.

| Discord field | Editor control |
| --- | --- |
| `type` | Basic activity type |
| `name` | Basic Activity name |
| `details`, `state` | Advanced activity text |
| `status_display_type` | Status-line text selection |
| `details_url`, `state_url` | Text links |
| `assets` | Main/small image, hover text, click-through links |
| `timestamps` | Local date/time inputs converted to Unix seconds for pypresence |
| `party` | ID, current size, maximum size |
| `buttons` | Up to two HTTPS links |
| `secrets` | Join, spectate, and match tokens; excluded from disk settings |
| `instance` | Instanced-session checkbox |
| `supportedPlatforms` | Unavailable through this RPC; disabled with explanation |

Join/spectate fields only publish supplied tokens. This application does not register game-join handlers or implement a game lobby. Asset keys entered as image values refer to assets already uploaded to the shared Discord application; ordinary users should use HTTPS links or the in-app uploader. Discord determines supported animation and final rendering.
