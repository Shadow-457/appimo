# Appimo — landing page plan

Status: draft for review. Nothing here is built yet; this is the plan plus the copy
deck, so the page can be written and shipped without another round of decisions.

## 1. What we're selling

**Appimo turns any AppImage into a real, installed application.**

An AppImage is a brilliant *distribution* format and a terrible *installation*
format. You download one, and then it lives in `~/Downloads`, invisible to your
application menu, with no icon, no name, no search result, and no way to uninstall
it. Every other app on your desktop is one keystroke away; the AppImage isn't
anywhere.

Appimo closes that gap. Point it at any `.AppImage` and it produces a proper
desktop application: a launcher in the start menu, the publisher's own icon and
name, in a stable location — per-user, no root, on any distro.

- **One-liner:** AppImages, integrated. One command or one click.
- **Product shape:** one core, two front ends — a `appimo` CLI and a Flet GUI, so
  terminal users script it and desktop users click it. Same engine, same result.

## 2. Audience

Primary — the Linux user who already uses AppImages and is annoyed by them.
They're on Reddit, HN, Lemmy and distro forums, they run `--appimage-extract`
by hand today, and they will judge us on the install command and the man page.

Secondary — the desktop-only user who'd use Gear Lever if they knew it existed.
They need the GUI and a screenshot before they read a single feature bullet.

Tertiary — the packager/maintainer who ships an AppImage and would link to
"integrate this with Appimo" instead of writing their own install docs.

## 3. Name and voice

`appimo` — lowercase always in the wordmark, "Appimo" when starting a sentence.
Reads as *AppImage* + *-mo*. Decent to say out loud, unique enough to own a
search result, and `appimo` is free as a CLI name in the usual places.

Tagline, in order of preference:

1. **Any AppImage. In your start menu.** (used on the banner)
2. AppImages, integrated.
3. Stop hunting for it in `~/Downloads`.

Voice: plain, dry, specific. No "revolutionise", no "seamless", no exclamation
marks, no rocket emoji. The audience is technical and allergic to marketing.
Terminal output is part of the brand — it should look good in screenshots.

## 4. Goals and how we'll know

| Goal | Metric | Where it comes from |
| --- | --- | --- |
| Get installed | GitHub release / PyPI download counts | Release + PyPI stats — no phone-home |
| Explain the product in one screen | Bounce rate < 55%, median time > 45 s | Analytics |
| Convert before the app is released | Waitlist signups | Form provider |
| Earn credibility | GitHub stars, docs page views | GitHub, analytics |
| Rank for the query | Position for "appimage start menu", "integrate appimage" | Search console |

We deliberately do **not** count curl installs by having the script phone home by
default. Release download counts are good enough and keep the privacy promise
that a Linux audience expects. If we ever ping, it's an explicit, documented,
opt-out-able counter with no identifiers.

## 5. Integrity rules for launch copy

The repo has a licence and a copyright but no code yet. The page must not
pretend otherwise.

- No testimonials, no "trusted by", no logos of companies that don't use it, no
  invented star counts, no fake download numbers.
- No "works on every distro" as a bare claim. The support matrix ships with the
  page and untested cells are labelled untested.
- GUI screenshots wait until the GUI exists. Until then the GUI section uses
  either a clearly-labelled interface mock-up or is cut. A screenshot of a
  window that doesn't exist is the fastest way to lose this audience.
- Status badge is real: version, build state, licence (GPL-3.0).

## 6. Page structure

Single scrolling page. Sticky header, then seven sections, then footer. Every
section earns its place by either explaining the product or removing an objection.

```
┌ Header ────────────────────────────────────────────────────┐
│ [mark] appimo      How it works  Features  Distros  Docs   │
│                                    [★ GitHub] [Install]    │
├ Hero ──────────────────────────────────────────────────────┤
│        Turn any AppImage into a real app.                  │
│   A launcher in your start menu, the right icon, the right  │
│   name. One command, or one click — on any Linux distro.    │
│                                                            │
│   ┌ $ curl -fsSL https://appimo.dev/install.sh | sh ─────┐ │
│   │                                            [ copy ]  │ │
│   └──────────────────────────────────────────────────────┘ │
│     Ubuntu · Debian · Fedora · Arch · openSUSE · immutable  │
│     No root. Ever.                     [See how it works ↓] │
├ 1. The problem ────────────────────────────────────────────┤
│  Three-up: no menu entry · no icon · gone in Downloads      │
├ 2. How it works ───────────────────────────────────────────┤
│  Point → Integrate → Launch, with a real terminal transcript│
├ 3. Features ───────────────────────────────────────────────┤
│  CLI + GUI · no root · any distro · keep or extract ·       │
│  real metadata · clean uninstall · scriptable · upkeep      │
├ 4. GUI (Flet) ─────────────────────────────────────────────┤
│  Drag an AppImage, click Integrate. Screenshot/loop.        │
├ 5. Distro support ─────────────────────────────────────────┤
│  Table with a tested/untested/known-issue column.           │
├ 6. FAQ ────────────────────────────────────────────────────┤
│  Safe? Root? FUSE 2? Immutable? Undo? Why not X? Licence?   │
├ Footer ────────────────────────────────────────────────────┤
│  Docs · GitHub · Changelog · Licence (GPL-3.0) · Contribute │
└────────────────────────────────────────────────────────────┘
```

## 7. Copy deck

### Hero

> # Turn any AppImage into a real app.
>
> A launcher in your start menu, the right icon, the right name, in a place
> that survives a reboot. One command, or one click — on any Linux distro.
>
> **Install Appimo**
> ```bash
> curl -fsSL https://appimo.dev/install.sh | sh
> ```
> `Ubuntu · Debian · Fedora · Arch · openSUSE · immutable` — no root, ever.

Primary CTA is the copy button, because copying the command *is* the conversion.
Secondary CTA: **Star on GitHub**. A tertiary text link jumps to the demo.

Button states matter: `Copy` → `Copied ✓` with an `aria-live` announcement. The
button is the only interactive JS above the fold, so it must work with
keyboard and without JS the command is still selectable text.

### Section 1 — The problem

> ## An AppImage isn't an installation. It's a file.
>
> It never asked to be in your menu. So it isn't. No launcher, no icon, no
> search result, no `apt remove`. Just a 200 MB file in `~/Downloads` that you
> keep re-downloading because you can't remember where you put it.

Three cards, one line each: **Invisible to your launcher** · **Anonymous to
your icon theme** · **Orphaned in Downloads**.

### Section 2 — How it works

> ## Three steps, once per app.

Real transcript, not a mock-up — this is the section people screenshot:

```
$ appimo install ~/Downloads/Cursor-0.45.AppImage

  reading   Cursor-0.45.AppImage
  name      Cursor
  icon      found 512x512 PNG
  moved     ~/Applications/Cursor.AppImage
  launcher  ~/.local/share/applications/dev.appimo.Cursor.desktop
  ✓ Launch "Cursor" from your start menu
```

> 1. **Point** Appimo at an AppImage — any path, or drag it into the GUI.
> 2. **Integrate** It reads the bundle's own desktop file and icon, puts the
>    file somewhere stable, and writes the launcher.
> 3. **Launch** The app appears in your start menu like it was always there.

### Section 3 — Features

> ## Built like a Linux tool, not a wrapper around one.

| | |
| --- | --- |
| **CLI and GUI** | `appimo` for your terminal, `appimo gui` for a window. One engine, so they never disagree. |
| **No root, ever** | Everything lands in `~/.local` and `~/Applications`. Nothing touches `/usr`, so nothing breaks on a package-managed system. |
| **Any distro** | Ubuntu, Debian, Fedora, Arch, openSUSE, and immutable images like Silverblue, Kinoite, Bazzite and SteamOS. |
| **Keep or extract** | Leave the AppImage intact, or unpack it for systems without working FUSE. Your choice, and it's reversible. |
| **Real metadata** | Name, icon, categories and MIME types read from the AppImage itself — never guessed from the filename. |
| **Clean uninstall** | `appimo remove cursor` takes out the launcher, the icon and the file. Nothing left behind. |
| **Scriptable** | `--json`, `--dry-run`, meaningful exit codes. `appimo list` for a machine-readable inventory. |
| **Upkeep** | `appimo update`, and `appimo doctor` when an old AppImage won't mount. |

### Section 4 — GUI

> ## Or don't touch the terminal at all.
>
> Drop an AppImage on the window, check the name and icon Appimo found, click
> **Integrate**. Everything the CLI does, with a preview of what it's about to
> change before it changes it.

*Screenshot/loop pending until the Flet app exists.*

### Section 5 — Distro support

> ## Any distro. Here's the honest list.

| System | Status | Notes |
| --- | --- | --- |
| Ubuntu / Debian | Tested | Per-user install; FUSE 2 is `libfuse2t64` on 24.04+ |
| Fedora / RHEL | Tested | `fuse` / `fuse-libs` only needed by older AppImages |
| Arch / Manjaro | Tested | `fuse2` for older images |
| openSUSE | Tested | `fuse` + `libfuse2` |
| Silverblue / Kinoite / Bazzite / SteamOS | Tested | User paths only; never writes `/usr` |
| Everything else | Should work | User-local XDG paths, so any freedesktop desktop qualifies — but untested is untested |

### Section 6 — FAQ

> **Is it safe? What does it actually touch?**
> Nothing outside your home directory. Appimo reads the AppImage, writes one
> `.desktop` file, one icon, and moves the file itself. It never runs the app
> to inspect it and never uses `sudo`. `appimo install --dry-run` prints every
> change before anything happens.

> **Do I need root?**
> No. That's a hard rule, not a preference. A GUI app running as root is a
> security problem and it creates root-owned files in your home directory.

> **My AppImage is old and won't mount. Now what?**
> FUSE 2 was dropped on some newer systems, and pre-2023 AppImages still want
> it. Appimo detects that and offers to extract instead of mount, or tells you
> which FUSE package your distro needs. `appimo doctor` explains the failure
> instead of dumping a mount error.

> **What about immutable distros?**
> That's the case Appimo is designed around: everything is per-user, so it works
> the same on Silverblue or Bazzite as it does on Arch. Only the app file's
> location changes.

> **How do I undo it?**
> `appimo remove <name>`. The launcher, the icon and the AppImage go away.

> **Why not just use Gear Lever, AppImageLauncher or `appimaged`?**
> They're good, and we've learned from them. Gear Lever is a GUI that also has a
> CLI; AppImageLauncher installs as a system package with deep hooks; `appimaged`
> silently watches directories. Appimo's bet is different: a first-class CLI for
> scripted and headless use, a GUI for everyone else, everything per-user,
> explicit about what it changes, and honest when it can't.

> **What's the licence?**
> GPL-3.0. It's yours to fork, package and ship.

## 8. The install story

This is the part of the page that has to be right, because the whole product is
"installable with a command".

**Stage 1 — bootstrap script.** `curl -fsSL https://appimo.dev/install.sh | sh`,
mirrored as `get.appimo.dev`. Rules so it doesn't look like malware:

- Served from a versioned path and published with a SHA-256 checksum.
- Prints what it will do, honours `--prefix`, and **never** escalates to root.
- `--dry-run` supported, and the docs show it.
- The page shows the checksum-verifying alternative underneath the one-liner for
  the people who won't pipe to `sh` — which is most of this audience:
  ```bash
  curl -fsSLO https://appimo.dev/install.sh
  less install.sh && sh install.sh
  ```
- Signed releases (minisign or cosign) as a milestone before the launch post.

**Stage 2 — package managers**, once there's a release to point at:

```bash
pipx install appimo        # CLI, isolated
uv tool install appimo     # CLI, if you use uv
flatpak install flathub dev.appimo.Appimo   # GUI, cross-distro
```

The page should show the CLI route and the GUI route separately, because they
have different audiences. `.deb` / `.rpm` come from the `flet build linux`
bundle; a bare AppImage is a poor delivery vehicle for an AppImage tool, so
Flatpak is the cross-distro GUI target.

**Stage 3 — distro repos.** AUR and COPR are cheap credibility wins and belong
on the page as a "packaged by the community" line.

## 9. Technical plan

**Recommendation: Astro, output static, deployed to Cloudflare Pages.**

- One `.astro` page plus components; zero JS shipped by default, and only the
  copy button and terminal demo opt into it. That keeps the page in the
  sub-100 KB range that earns "fastest site on the internet" jokes from the
  audience we want.
- Content collections give us `/docs` (install, troubleshooting, FUSE,
  immutable distros) and `/changelog` from Markdown later without a rewrite.
- Markdown-first keeps contributions from non-frontend people trivial — which
  matters for a GPL project.
- If you'd rather not run a Node toolchain next to the Python code, plain HTML
  + CSS with a ~40-line JS file achieves the same page. Take Astro if docs are
  coming; take plain HTML if the page is a one-off.

**Hosting:** Cloudflare Pages. Free tier is generous, the CDN is good, preview
deployments per PR are free, and it can later host a Worker for the waitlist
endpoint. GitHub Pages is the alternative if you want the site welded to the
repo, but it's explicitly not for primarily-commercial sites — worth knowing
before this feels like a startup.

**Proposed layout** (the site is separate from the app so Python tooling isn't
burdened with a Node toolchain):

```
landing/
  astro.config.mjs
  src/pages/index.astro
  src/components/{Hero,InstallCommand,Problem,HowItWorks,Features,Gui,
                  DistroMatrix,Faq,Footer}.astro
  src/content/docs/*.md
  src/styles/tokens.css        # imports the palette from assets/logo/README.md
  public/
    logo/*.svg                 # copied from assets/logo/ at build time
    appimo-banner.png          # 1200x630 OG card
    favicon.svg  favicon.ico
    install.sh                 # served verbatim; source of truth in scripts/
```

`install.sh` belongs in the app repo (`scripts/`) and is copied into the site at
build time so the two can't drift.

**Domains:** `appimo.dev` for the site, `get.appimo.dev` as a 302 to the
versioned installer. Decide and register before the launch post — the URL is
baked into every tweet and every README.

**Analytics:** Umami Cloud (free tier, 100k events/month, cookieless,
self-hostable under AGPL so it matches the project's ethos). PostHog only if we
later want funnels; it's more than a landing page needs. Track `install_copy`,
`install_run`, `waitlist_signup`, `github_click`, `docs_view`. Load analytics
after paint so it never blocks LCP.

**Waitlist:** Tally embed first — free, unlimited forms, no backend. If it needs
to live at `appimo.dev/api/waitlist` later, swap in a Cloudflare Pages Function
writing to D1. The form asks for an email and a distro, nothing else, and says
what we'll send (release announcements, nothing more).

**SEO / social:** `<title>Appimo — any AppImage, in your start menu</title>`,
a 150-character description, canonical URL, `sitemap.xml`, `robots.txt`, and
`SoftwareApplication` JSON-LD (`operatingSystem: Linux`, `offers: price 0`,
`license: GPL-3.0`). OG and Twitter cards use `appimo-banner.png`. Target
phrases: *appimage start menu*, *integrate appimage*, *appimage desktop entry*,
*appimage launcher linux*, *appimo*.

## 10. Quality bars

**Performance:** LCP < 1.0 s on a fast connection, total JS < 10 KB gzipped,
CLS 0, all-caps images AVIF/WebP with SVG for the logo, fonts self-hosted with
`font-display: swap` (the wordmark is already an outline, so the header needs no
webfont at all — keep it that way).

**Accessibility:** WCAG 2.2 AA. The white glyph on the tile is 3.4:1 and the
cyan accent on ink is 8.6:1, both verified; keep any new colour pairing at 4.5:1
for body text. Keyboard-operable copy button with an `aria-live` confirmation,
`prefers-reduced-motion` honoured by the terminal typing animation, one `<h1>`,
and the terminal transcript as real selectable text rather than an image.

**Browser support:** current Firefox, Chrome/Chromium, Safari and GNOME Web
(WebKitGTK), because the same engine renders the Flet GUI on Linux.

## 11. Build order

| Phase | Deliverable | Exit test |
| --- | --- | --- |
| M0 | Copy freeze, palette, logo — **done** | `assets/logo/` generated and verified |
| M1 | Hero + install command + waitlist, live on a Pages preview URL | Page loads, command copies, signup lands in Tally |
| M2 | Features, distro matrix, FAQ, OG tags, analytics | Lighthouse ≥ 98, OG card renders in a link preview |
| M3 | `/docs` (install, troubleshooting, FUSE, immutable) + `/changelog` | Docs build from Markdown, search works |
| M4 | Real CLI transcript + GUI screenshot/loop + 30 s demo video | Every screenshot is from a real build |
| M5 | Launch: HN, r/linux, r/AppImage, Lemmy, distro forums, Product Hunt | Framed as v0.1 pre-release, honest about untested distros |
| M6 | `pipx`/`uv` package, then Flatpak on Flathub, AUR + COPR | Primary CTA can become `flatpak install` |

## 12. Open decisions

1. **Domain** — `appimo.dev` assumed. Register before M5.
2. **Astro or plain HTML** — Astro if `/docs` is coming soon, plain HTML if this
   is a one-page launch.
3. **Does the site live in this repo** (`landing/`) or its own repo? In-repo is
   simpler; separate avoids adding a Node toolchain to a Python project.
4. **Waitlist or direct download** — a waitlist implies the app isn't ready.
   Since it isn't, that's honest — but the page must say so plainly.
5. **Tagline** — confirm #1 (*Any AppImage. In your start menu.*); it's already
   baked into `appimo-banner.svg` and is one line to regenerate.
6. **Screenshots** — cut the GUI section or use a labelled mock-up until the
   Flet app exists.

## Sources

Distro/FUSE behaviour, desktop-entry semantics and hosting limits in this plan
come from the AppImage and freedesktop specifications, the Gear Lever,
AppImageLauncher and go-appimage projects, Flet's Linux publishing docs, and the
Cloudflare Pages, GitHub Pages, Tally, Umami and Netlify plan pages, researched
October 2026.
