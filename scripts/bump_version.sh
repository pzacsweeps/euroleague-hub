#!/bin/sh
# Run after changing style.css or app.js: makes browsers fetch the new files instead of cached ones.
v=$(date -u +%Y%m%d%H%M)
sed -i -E "s/(style\.css|app\.js)(\?v=[0-9]+)?\"/\1?v=$v\"/g" "$(dirname "$0")/../index.html"
echo "asset version $v"
