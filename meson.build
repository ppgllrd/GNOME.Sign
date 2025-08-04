project('gnomesign', 'python',
  version: '1.0.1',
  meson_version: '>= 0.59.0',
  default_options: ['warning_level=1'])

python = import('python').find_installation(get_option('python_version'))

gnome = import('gnome')

i18n = import('i18n')

subdir('src')
subdir('po')

install_data(
  'org.pepeg.GnomeSign.desktop',
  install_dir: join_paths(get_option('datadir'), 'applications')
)

install_data(
  'org.pepeg.GnomeSign.metainfo.xml',
  install_dir: join_paths(get_option('datadir'), 'metainfo')
)

install_data(
  'svg/org.pepeg.GnomeSign.svg',
  install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'apps')
)
