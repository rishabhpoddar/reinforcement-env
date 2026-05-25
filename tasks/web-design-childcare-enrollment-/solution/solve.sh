#!/bin/bash
# Reference solution: copy the original generated website files
cp /solution/site_files/* /app/ 2>/dev/null || true
# Copy assets if they exist in the solution
if [ -d /solution/site_files/assets ]; then
    cp -r /solution/site_files/assets /app/assets 2>/dev/null || true
fi
