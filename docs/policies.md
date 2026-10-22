# Publish Terms and Privacy for Discord

The app includes [Terms of Service](../custompresence/assets/legal/terms.html) and a [Privacy Policy](../custompresence/assets/legal/privacy.html), linked from its footer. The same standalone pages can be hosted on GitHub Pages. They describe the current implementation: local settings and upload fingerprints/removal links, Discord IPC, public ImgBB uploads, host enforcement limits, deletion controls, and external services. See [the publishing checklist](publishing.md) for the remaining repository and release preparation.

The public repository is [darrienk7/custompresence](https://github.com/darrienk7/custompresence). To publish or update its policies:

1. Upload the source, including `.github/workflows/pages.yml`.
2. In the repository's **Settings → Pages**, choose **GitHub Actions** as the source.
3. Open **Actions → Publish policy pages → Run workflow**. Future policy changes on `main` publish automatically. If your default branch has another name, update the workflow's branch filter.
4. Open the completed run's summary. It shows the actual Terms and Privacy links. Check both public pages.
5. Open the [Discord Developer Portal application](https://discord.com/developers/applications/1562607151912845352/information) and fill in **Terms of Service URL** and **Privacy Policy URL**, then save.

The policy links for this repository are:

- [Terms of Service](https://darrienk7.github.io/custompresence/terms.html)
- [Privacy Policy](https://darrienk7.github.io/custompresence/privacy.html)

Check that deployment succeeded before using these links in Discord. Use the workflow's actual URLs if a custom domain is added. GitHub Pages availability depends on the repository's visibility and plan. Localhost URLs cannot serve as public Discord policy links.

Both policy pages use [chasekw2007@gmail.com](mailto:chasekw2007@gmail.com) as the maintainer's support/privacy contact. Before release, confirm that the policies match your actual upload-service deployment and its hosting logs/retention. Update the policies and effective date if you introduce telemetry, accounts, payments, or different data retention. Provider policies do not eliminate the app maintainer's own obligations.
