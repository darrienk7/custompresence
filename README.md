# Custom Presence

Customize your Discord Rich Presence in a desktop app. No Discord account token or developer setup is needed for users.

## Download and open

Get the installer from [Releases](https://github.com/darrienk7/custompresence/releases). No Python, terminal commands, or Discord developer setup is needed.

| Your computer | Download |
| --- | --- |
| Windows 10/11 (64-bit) | `CustomPresence-Windows-Setup.exe` |
| Mac with Apple Silicon | `CustomPresence-macOS-AppleSilicon.dmg` |
| Intel Mac | `CustomPresence-macOS-Intel.dmg` |

On Windows, open the installer, then open **Custom Presence** from Start. The installer handles WebView2 if it is missing. On a Mac, open the DMG, drag **CustomPresence** into **Applications**, and open it.

Downloads will become available after the repository's first successful release build. Builds are currently unsigned; Windows and macOS may show a security warning. Mac release builds and installation still need verification on a Mac.

## Make it yours

1. Keep Discord desktop open and signed in.
2. Choose Playing, Listening, Watching, or Competing and optionally enter an **Activity** name, such as "my favorite game". Leave it blank to show only the activity type.
3. Under **Image / GIF**, select **Upload** or **Paste public link**. Choose a file to upload directly inside the app, or paste a link. Giphy, Tenor, and single-image Imgur page links are converted automatically. Use **Check link** to verify the actual image; album, video, missing, and removed-image links get a clear error.
4. Click **Apply activity**. Enable activity sharing in Discord if needed.

The basic screen contains activity type, Activity name, and artwork. Activity starts empty with the gray **What are you up to?** placeholder. **Advanced options** opens a grid: Activity text, Artwork, Timer, Party, Activity buttons, Game integration, and Saved data. Choose a category to open its screen, use **All options** to return to the grid, or **Done** to return to Basic. Values stay in place when switching screens; **Apply activity** sends them to Discord.

For **Party**, enter both sizes and apply the activity. Empty State text uses **In a party**, and a party ID is created automatically when needed. Other activity types also include the count in State text. Check Discord's expanded activity card to see these details.

Click **Clear** to remove the activity. Closing the app also clears it and stops everything. Last successfully applied settings are remembered for next time, except join/spectate/match tokens. Use **Advanced → Saved data → Reset saved settings** to remove saved settings.

Selecting the same image again reuses its existing upload, including after restarting the app. Up to 100 recently used files are remembered locally by their contents; original image files are not copied to disk. Applying and clearing activities never upload another copy. **Advanced → Saved data → Forget remembered uploads** removes this local history. Hosted files remain online until removed through the host; keep any removal links you need.

The app uses a shared Discord application behind the scenes. There is no Application ID field, login form, or account token to enter. Your picture appears on the activity card; it does not change your account avatar.

## Maintaining the app

Publishing a GitHub Release automatically tests and builds the Windows and Mac downloads. See [development and release instructions](docs/development.md) for source setup and packaging details.

Before uploading the repository or publishing downloads, follow the [publishing checklist](docs/publishing.md), including secret exclusions, publishing policies, and configuring the shared upload service.

Uploads use [ImgBB's API](https://api.imgbb.com/), with no website or browser popup. The owner configures the integration once; users never enter an API key. See [upload setup](docs/imgbb.md) for local owner testing and the shared upload service for released builds. If an upload service is not configured, public links still work. Its free service is subject to host limits and availability; this project cannot promise unlimited or permanently free hosting. Uploaded images are public. Hosting does not guarantee content approval, moderation of every GIF frame, or bans within this app. ImgBB's current [Terms](https://imgbb.com/tos) require users to be 18 or older. Users can instead paste an image link from a service they are eligible to use.

Custom Presence is independent of Discord and ImgBB. Users are responsible for the content they share and must follow each service's rules. The [Terms of Service](custompresence/assets/legal/terms.html) and [Privacy Policy](custompresence/assets/legal/privacy.html) are also linked inside the app. [Publish these pages for the Discord application](docs/policies.md) once the GitHub repository exists.

Discord controls the final display, including animation and button visibility. Streaming and custom status are not supported by this RPC connection. The Social SDK's `supportedPlatforms` flags are unavailable here. Invite tokens require a working integration that handles joining or spectating; filling a token field does not create that integration.

## License and contact

Custom Presence is licensed under the [MIT License](LICENSE). Third-party components retain their own licenses.

For support, privacy requests, or other project questions, email [chasekw2007@gmail.com](mailto:chasekw2007@gmail.com).
