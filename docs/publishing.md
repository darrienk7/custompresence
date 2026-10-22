# Before publishing

## Repository

- Upload source files, documentation, packaging files, and `.github/workflows/`.
- Keep `.env`, `.venv/`, `.idea/`, `build/`, `dist/`, logs, and Python caches out of Git. `.gitignore` already excludes them. Include `.env.example`, which contains placeholders only. Git ignores do not protect files manually dragged into GitHub's web uploader: do not drag the entire local folder there.
- Keep your ImgBB key on the upload server. Do not include it in the repository or a desktop build. If a real secret ever entered a public commit, revoke it and replace it; deleting the latest copy is insufficient.
- The code is licensed under MIT; keep the included `LICENSE` with the source and distributions. The service terms are separate from the software license. Third-party components retain their own licenses.
- Support and privacy contact is [chasekw2007@gmail.com](mailto:chasekw2007@gmail.com), already included in the README, package metadata, and policy pages.

## Repository and future updates

The public repository is [darrienk7/custompresence](https://github.com/darrienk7/custompresence), with `main` as its default branch.

For future changes without a terminal, use [GitHub Desktop](https://desktop.github.com/):

1. Choose **File → Add local repository** and select the project folder, or clone the published repository on another computer.
2. Review **Changes**, checking that `.env`, `.venv`, `build`, and `dist` are absent. `.env.example` should stay tracked.
3. Commit the intended changes and click **Push origin**. Choose **Repository → View on GitHub** to verify them.

Source can be public before setting up downloads. GitHub Pages publishes policy documents; it does not run the Python upload service.

## Terms and privacy pages

1. Review `custompresence/assets/legal/terms.html` and `privacy.html`. They already include the maintainer email and describe public uploads, host rules, local settings and the upload reuse index, deletion, external services, and the included forwarding service. Update any deployment-specific data retention or hosting details. Change the effective date when you change the policies.
2. In the repository's **Settings → Pages**, select **GitHub Actions**.
3. In **Actions → Publish policy pages**, click **Run workflow**. The workflow publishes the same pages included in the app.
4. Open the completed run's summary and check the public links: [Terms of Service](https://darrienk7.github.io/custompresence/terms.html) and [Privacy Policy](https://darrienk7.github.io/custompresence/privacy.html). Use the workflow's actual URLs if the Pages domain changes.
5. Open the [Discord application's General Information](https://discord.com/developers/applications/1562607151912845352/information). Paste the public links into **Terms of Service URL** and **Privacy Policy URL**, then save.

These pages do not require a separate paid website. GitHub Pages availability depends on repository visibility and your plan.

## Downloads and in-app uploads

1. Deploy the included upload service on an HTTPS host, with `IMGBB_API_KEY` in that host's secrets. Check its `/health` endpoint, configure proxy/rate limits, and document the host's logging and retention. See [upload setup](imgbb.md).
2. Add the public `/v1/images` URL in the repository's **Settings → Secrets and variables → Actions → Variables** as `CUSTOMPRESENCE_UPLOAD_URL`. The desktop app receives this URL; the host key stays on the server. The release workflow requires this value.
3. Check the app on Windows with Discord open: blank and named activities, all supported activity types, both artwork modes, repeated selection of the same file, Apply, and Clear. Check installation and launch on each supported Mac architecture before describing those builds as verified. See [development](development.md) for automated checks and packaging.
4. Publish a GitHub Release to start the download build workflow. Distribute the resulting installers through Releases, rather than committing executable files. Review the workflow results and test the downloads before announcing them. Signing is not configured, so users may see operating-system warnings.

Publishing source and policy pages does not require a running upload service; public download builds do. Pasted public links remain usable when no upload service is configured.
