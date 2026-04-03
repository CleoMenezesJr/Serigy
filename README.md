<h1 align="center">
  <img src="data/icons/hicolor/scalable/apps/io.github.cleomenezesjr.Serigy.svg" alt="Serigy" height="170"/>
  <br>
  Serigy
</h1>

<p align="center">Manage your clipboard minimally</p>

<p align="center">
  <img src ="data/screenshots/1.png" /></a>
</p>

A minimalist clipboard manager that captures your copies and keeps only what matters.

## Features

- **Automatic capture** - Monitors clipboard in the background
- **Limited slots** (6, 9, or 12) - Keeps only what matters
- **Favorites** - Pin important items so they don't get replaced
- **Incognito mode** - Pause monitoring temporarily (Ctrl+Alt+Shift+I)
- **Global shortcut** - Quick access from anywhere (default: Ctrl+Super+V)
- **Image support** - Captures images (requires "Force Image Detection")

## Build

#### Requirements:

- org.gnome.Sdk
- flatpak-builder

#### Clone, build and run:

```bash
# You may need to add gnome-nightly flatpaks to get the 'master' GNOME SDK flatpak
# flatpak remote-add --user --if-not-exists gnome-nightly https://nightly.gnome.org/gnome-nightly.flatpakrepo
git clone https://github.com/CleoMenezesJr/Serigy.git
cd Serigy
flatpak-builder build io.github.cleomenezesjr.Serigy.json --user --install --force-clean --install-deps-from=gnome-nightly
flatpak run io.github.cleomenezesjr.Serigy
```

## Debugging

```bash
flatpak run --env=LOGLEVEL=DEBUG io.github.cleomenezesjr.Serigy
```

## Translation

```bash
xgettext --files-from=po/POTFILES --output=po/serigy.pot --from-code=UTF-8 --add-comments --keyword=_ --keyword=C_:1c,2
```
