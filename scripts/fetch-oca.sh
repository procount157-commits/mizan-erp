#!/usr/bin/env bash
# Clone (or update) every OCA repository listed in third_party/oca-repos.txt.
# Shallow clones keep the tree at a few hundred MB instead of ~1.4 GB.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
list="$root/third_party/oca-repos.txt"
dest="$root/third_party/OCA"

mkdir -p "$dest"

while read -r branch url; do
    case "$branch" in ''|\#*) continue ;; esac
    name="$(basename "$url" .git)"
    if [ -d "$dest/$name/.git" ]; then
        echo "updating $name"
        git -C "$dest/$name" fetch --depth 1 origin "$branch"
        git -C "$dest/$name" reset --hard "origin/$branch"
    else
        echo "cloning  $name"
        git clone --depth 1 --branch "$branch" "$url" "$dest/$name"
    fi
done < "$list"

echo
echo "Done. Load the addons into the container with: scripts/sync-oca.sh"
