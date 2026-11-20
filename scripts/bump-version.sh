#!/usr/bin/env bash
#
# Increment the application version and keep every mirrored reference in sync.
#
# Override the amount with the BUMP_AMOUNT environment variable:
#   BUMP_AMOUNT=0.0.1 ./scripts/bump-version.sh   # patch bump
#   BUMP_AMOUNT=0.1.0 ./scripts/bump-version.sh   # minor bump (default)
#   BUMP_AMOUNT=1.0.0 ./scripts/bump-version.sh   # major bump
#
# A non-zero higher-order component resets lower-order components, so
# 0.5.1 + 0.1.0 -> 0.6.0 and 0.5.1 + 1.0.0 -> 1.0.0.
#
# After updating, the script commits the changed version files and pushes the
# current branch to PUSH_REMOTE (default: origin).

set -euo pipefail

BUMP_AMOUNT="${BUMP_AMOUNT:-0.1.0}"
PUSH_REMOTE="${PUSH_REMOTE:-origin}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION_FILE="$ROOT/VERSION"
AFFECTED_FILES=(
  "$VERSION_FILE"
  "$ROOT/frontend/package.json"
  "$ROOT/frontend/package-lock.json"
  "$ROOT/.env.example"
  "$ROOT/docker-compose.yml"
  "$ROOT/backend/pyproject.toml"
  "$ROOT/backend/app/__init__.py"
  "$ROOT/README.md"
  "$ROOT/docs/DESIGN.md"
  "$ROOT/unraid/README.md"
)
CHANGED_FILES=()

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

command -v git >/dev/null 2>&1 || fail "git is required"
git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "$ROOT is not a git work tree"
branch="$(git -C "$ROOT" branch --show-current)"
[[ -n "$branch" ]] || fail "detached HEAD; check out a branch before bumping"
git -C "$ROOT" remote get-url "$PUSH_REMOTE" >/dev/null 2>&1 || fail "git remote '$PUSH_REMOTE' is not configured"

for file in "${AFFECTED_FILES[@]}"; do
  [[ -f "$file" ]] || fail "missing $file"
  rel="${file#"$ROOT/"}"
  if ! git -C "$ROOT" diff --quiet -- "$rel" || ! git -C "$ROOT" diff --cached --quiet -- "$rel"; then
    fail "uncommitted changes in $rel; commit or stash them first"
  fi
done

old_version="$(tr -d '[:space:]' < "$VERSION_FILE")"
[[ "$old_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "VERSION is not MAJOR.MINOR.PATCH: $old_version"
[[ "$BUMP_AMOUNT" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "BUMP_AMOUNT is not MAJOR.MINOR.PATCH: $BUMP_AMOUNT"

IFS=. read -r v_major v_minor v_patch <<< "$old_version"
IFS=. read -r a_major a_minor a_patch <<< "$BUMP_AMOUNT"

new_major=$((v_major + a_major))
new_minor=$((v_minor + a_minor))
new_patch=$((v_patch + a_patch))

# Semantic-version behavior: a major/minor bump resets lower components.
if (( a_major > 0 )); then
  new_minor=0
  new_patch=0
elif (( a_minor > 0 )); then
  new_patch=0
fi

new_version="$new_major.$new_minor.$new_patch"
[[ "$new_version" != "$old_version" ]] || fail "version did not change ($old_version + $BUMP_AMOUNT)"

replace_all() {
  local file="$1"
  local old="$2"
  local new="$3"
  local old_re

  [[ -f "$file" ]] || fail "missing $file"
  if grep -qF "$old" "$file"; then
    old_re="${old//./\\.}"
    sed -i.bak "s|$old_re|$new|g" "$file"
    rm -f "$file.bak"
    CHANGED_FILES+=("$file")
    printf 'updated %s\n' "${file#"$ROOT/"}"
  fi
}

replace_package_lock_versions() {
  local file="$1"
  local old="$2"
  local new="$3"
  local tmp

  [[ -f "$file" ]] || fail "missing $file"
  tmp="$(mktemp)"
  awk -v old="$old" -v new="$new" '
    BEGIN { changed = 0 }
    {
      needle = "\"version\": \"" old "\""
      pos = index($0, needle)
      if (changed < 2 && pos > 0) {
        $0 = substr($0, 1, pos - 1) "\"version\": \"" new "\"" substr($0, pos + length(needle))
        changed++
      }
      print
    }
  ' "$file" > "$tmp"
  cat "$tmp" > "$file"
  rm -f "$tmp"
  CHANGED_FILES+=("$file")
  printf 'updated %s\n' "${file#"$ROOT/"}"
}

replace_all "$VERSION_FILE" "$old_version" "$new_version"
replace_all "$ROOT/frontend/package.json" "\"version\": \"$old_version\"" "\"version\": \"$new_version\""
replace_package_lock_versions "$ROOT/frontend/package-lock.json" "$old_version" "$new_version"
replace_all "$ROOT/.env.example" "IMAGE_VERSION=$old_version" "IMAGE_VERSION=$new_version"
replace_all "$ROOT/docker-compose.yml" "IMAGE_VERSION:-$old_version" "IMAGE_VERSION:-$new_version"
replace_all "$ROOT/backend/pyproject.toml" "version = \"$old_version\"" "version = \"$new_version\""
replace_all "$ROOT/backend/app/__init__.py" "return \"$old_version\"" "return \"$new_version\""
replace_all "$ROOT/README.md" "$old_version" "$new_version"
replace_all "$ROOT/docs/DESIGN.md" "$old_version" "$new_version"
replace_all "$ROOT/unraid/README.md" "$old_version" "$new_version"

printf '\nVersion bumped: %s -> %s (increment %s)\n' "$old_version" "$new_version" "$BUMP_AMOUNT"

((${#CHANGED_FILES[@]} > 0)) || fail "no version references changed"

relative_changed=()
for file in "${CHANGED_FILES[@]}"; do
  relative_changed+=("${file#"$ROOT/"}")
done

git -C "$ROOT" add -- "${relative_changed[@]}"
git -C "$ROOT" commit -m "Bump version to $new_version" -- "${relative_changed[@]}"
git -C "$ROOT" push "$PUSH_REMOTE" "$branch"

printf 'Committed and pushed %s to %s/%s\n' "$new_version" "$PUSH_REMOTE" "$branch"
