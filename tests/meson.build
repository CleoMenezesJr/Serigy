python_test = import('python').find_installation('python3')

# Pure-logic tests: no display, no compositor, no GTK. Run with `meson test`.
test(
  'detector',
  python_test,
  args: [files('test_detector.py')],
  workdir: meson.current_source_dir(),
)
