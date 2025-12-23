pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()
moduledir = pkgdatadir / 'serigy'
gnome = import('gnome')

blueprints = custom_target('blueprints',
  input: files(
    'gtk/window.blp',
    'gtk/overlay-button.blp',
    'gtk/copy-alert-window.blp',
    'gtk/preferences.blp',
    'gtk/shortcuts-dialog.blp',
  ),
  output: '.',
  command: [find_program('blueprint-compiler'), 'batch-compile', '@OUTPUT@', '@CURRENT_SOURCE_DIR@', '@INPUT@'],
)

gnome.compile_resources('serigy',
  'serigy.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
  dependencies: blueprints,
)

python = import('python')

conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3').full_path())
conf.set('VERSION', meson.project_version())
conf.set('localedir', get_option('prefix') / get_option('localedir'))
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'serigy.in',
  output: 'serigy',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'r-xr-xr-x'
)

install_subdir('logging', install_dir: moduledir)

serigy_sources = [
  '__init__.py',
  'main.py',
  'window.py',
  'overlay_button.py',
  'copy_alert_window.py',
  'settings.py',
  'preferences.py',
  'shortcut_portal.py',
  'setup_shortcut_portal.py',
  'clipboard_monitor.py',
  'clipboard_manager.py',
  configure_file(
    input: 'define.py.in',
    output: 'define.py',
    configuration: conf
  ),
]


install_data(serigy_sources, install_dir: moduledir)
