#!/bin/bash

# Application name
APP_ID="io.github.ppgllrd.GNOME-Sign"

echo "--- Generating modules ---"
req2flatpak --requirements-file requirements.txt --target-platforms 312-x86_64 312-aarch64 > python-modules.json

# clean previous builts
echo "--- Cleaninng previous compilations ---"
flatpak-builder --force-clean build-dir ${APP_ID}.json
rm -rf .flatpak-builder build-dir

# build Flatpak
echo "--- Building Flatpak ---"
flatpak-builder --user --install --force-clean build-dir ${APP_ID}.json

if [ $? -eq 0 ]; then
  echo "--- Sucessful Flatpack built! ---"
  echo "You can run the application with:"
  echo "flatpak run ${APP_ID}"
else
  echo "--- There was an error during the build process. ---"
fi