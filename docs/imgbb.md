# In-app ImgBB uploads

Users choose **Image / GIF → Upload → Choose image / GIF**, select a file, and click **Apply activity** after it uploads. No browser, host login, API-key field, or Discord developer setup is shown. The app validates PNG, JPG, GIF, WebP, and AVIF file contents, up to 8 MB. Successful uploads return a direct image URL automatically and, when available, a removal link for the uploader to keep.

## Local owner setup

The [ImgBB upload API](https://api.imgbb.com/) requires one API key. Create a `.env` file in the repository root containing `IMGBB_API_KEY=your_key_here`, then reopen Custom Presence. `.env.example` shows the format. The actual `.env` is excluded from Git and Docker, and is not included by the desktop packager. Do not paste the key into chat, commit it to GitHub, or embed it in an installer.

Source runs load the repository's `.env`. The locally built `dist/CustomPresence.exe` also checks that parent repository's `.env`; installed executables can use a `.env` beside the executable for owner testing. File values are read at startup and only the two documented configuration names are used. Windows user variables are optional. This is a one-time owner setup for local testing; ordinary users do not do this.

Process environment variables also work and take priority over `.env`. A Windows user variable is used as a fallback. No key is returned by the local API or saved with activity settings. Key values are sent in the HTTPS upload request body to ImgBB, rather than in logged request URLs.

## One shared configuration for downloaded apps

A desktop binary cannot keep a shared API key secret. For public downloads, run the included small FastAPI upload service and keep `IMGBB_API_KEY` in that service's secret environment. Downloaded apps contain only its public URL.

- Service entry point: `custompresence.upload_service:create_upload_service` with Uvicorn's `--factory` option.
- Upload route: `POST /v1/images`, a raw image body.
- Health route: `GET /health`; ready is true when the host key is configured.
- The included `Dockerfile` starts this service. Configure `IMGBB_API_KEY` as a hosting secret, expose HTTPS, and use the host's normal restart and network controls.
- The service keeps uploaded bytes in memory, forwards them to ImgBB, and returns the image/removal links. It does not create a media library or store activity text.
- It limits files to 8 MB, simultaneous uploads to two per process, and requests to six per source IP per minute. Expired source-IP counters are removed on the next upload request or process restart. Use one worker for these in-memory limits, configure trusted proxy addresses for your host, and add provider-level/global rate and spend limits before a public rollout. A public endpoint can be called by software other than this app.
- Hosting costs and limits are separate from ImgBB. A permanently free shared backend is not promised.

In the GitHub repository, add an **Actions variable** named `CUSTOMPRESENCE_UPLOAD_URL`, for example `https://your-upload-host.example/v1/images`. The release workflow embeds this public URL into each Windows/Mac build. Do not put the ImgBB key in an Actions variable or build secret: it belongs only on the upload server. Local source builds can use that same URL as an environment variable, or set `UPLOAD_SERVICE_URL` in `custompresence/config.py` before packaging.

Without a local owner key or configured service URL, uploads are disabled with an explanation; pasted public links remain usable. Public release builds require the shared URL. This repository does not deploy a host or create an ImgBB account automatically.

## Public links

Giphy GIF-page links such as `https://giphy.com/gifs/cZ7rmKfFYOvYI` are converted to `https://media.giphy.com/media/cZ7rmKfFYOvYI/giphy.gif`. Tenor `/view/` pages are resolved through their public image metadata. Single-image Imgur links are converted to `https://i.imgur.com/...`; `.gifv` video wrappers are changed to `.gif`. Imgur albums and gallery pages require the address of one image. MP4 videos do not work as artwork.

**Check link** verifies the actual response type, image bytes, dimensions, and size. Applying an unchecked link also verifies it. Removed Imgur images are rejected instead of displaying the host's removal placeholder. Link checks only connect to public HTTPS addresses and recheck redirects; the connection is pinned to the checked IP while retaining the original TLS hostname. Files are not uploaded as part of a link check.

For a static image example, use `https://cdn.discordapp.com/embed/avatars/0.png`. Host links can change after a successful check, and Discord controls final display and animation.

## Host rules and removal

Uploads are public and subject to ImgBB's current [Terms](https://imgbb.com/tos), [Privacy Policy](https://imgbb.com/privacy), availability, and enforcement. Its current Terms restrict use to people 18 or older. Free service does not guarantee unlimited usage or permanent hosting. File checks do not moderate image content, scan every GIF frame for appropriateness, or guarantee removal of embedded metadata. Host enforcement does not ban users from this app.

Keep the removal link shown after uploading, or use the host's account/support controls. Removal links are saved in the private local upload index, separately from activity settings; selecting the same file again displays its remembered link. Clearing presence, cancelling an upload request, or resetting local settings does not delete a file already received by ImgBB.

## Reuse and retention

Applying or clearing an activity never uploads an image. Selecting a file computes a SHA-256 fingerprint locally and checks a small persistent index. Identical file contents reuse the existing ImgBB URL, even with a different filename or after reopening the app. Before reuse, a lightweight HEAD request checks the existing URL; only a definite 404/410 response triggers a new upload. Temporary host errors do not cause duplicate uploads. Changed bytes count as a different file, and the index is specific to that device rather than shared across users.

The index keeps up to 100 recently used fingerprints, public URLs, removal links, image dimensions/format, and last-use times. It stores no original image files, filenames, file paths, or API keys. **Advanced → Saved data → Forget remembered uploads** deletes that local index. Keep any removal links you need first. Forgetting an entry does not delete its hosted file; choosing that file again may create a new upload.

Stopping the app leaves uploaded media online so saved links continue working. ImgBB's documented API has an optional `expiration` setting of 60–15,552,000 seconds, but no documented deletion endpoint for clearing files when an activity stops. This app does not request automatic expiry. Fixed expiry would eventually break saved artwork and require the user to select the original file again; the app does not retain file bytes to restore it automatically. The supplied host removal link remains the deletion control.
