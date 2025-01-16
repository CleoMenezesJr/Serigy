<h1 align="center">
  <img src="data/icons/hicolor/scalable/apps/page.codeberg.cleomenezesjr.Serigy.svg" alt="Serigy" height="170"/>
  <br>
  Serigy
</h1>

<p align="center"> A proof of concept for a "clipboard pinner".</p>

<p align="center">
  <img src ="data/screenshots/1.png" /></a>
</p>

## Build

#### We need the following resources:

- org.gnome.Sdk
- flatpak-builder

#### Clone, build and run:

Clone the latest Serigy source from GitHub

```bash
git clone https://codeberg.org/CleoMenezesJr/Serigy.git
```

Enter the directory and build

```bash
cd Serigy
flatpak-builder build page.codeberg.cleomenezesjr.Serigy.json --user --install --force-clean
```

Run

```bash
cd Serigy
flatpak run page.codeberg.cleomenezesjr.Serigy
```

That's it!

## I want to create a pot file!

You can use this command to create a pot file for translation:

`xgettext --files-from=po/POTFILES --output=po/serigy.pot --from-code=UTF-8 --add-comments --keyword=_ --keyword=C_:1c,2`

<!-- ## I want to participate in the community! -->
<!-- Join [Aurea's room](https://matrix.to/#/%23aurea-app:matrix.org) at Matrix to ask questions and be part of the community. -->
