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
#
# Scheduling a weekly bump with cron
# ----------------------------------
# The script is safe to run unattended, but cron starts it with a minimal
# environment and no terminal, so a few things must be true first:
#
#   1. The checkout is on a branch (not a detached HEAD) and PUSH_REMOTE is
#      configured, e.g. `git -C /opt/UnFiWifiTool checkout main`.
#   2. The version files are committed. The script refuses to run if any of
#      them has uncommitted changes, so the working tree must be clean.
#   3. git can push without prompting: use an SSH key with no passphrase or a
#      stored credential helper, and make sure the key is readable by the cron
#      user (HOME must resolve, since cron may not set it).
#   4. Use absolute paths, because cron's PATH usually does not include the
#      directory holding your git/bash binaries.
#
# Example crontab entry (every Monday at 03:00), added with `crontab -e`:
#
#   0 3 * * 1 cd /opt/UnFiWifiTool && HOME=/home/deploy PATH=/usr/local/bin:/usr/bin:/bin BUMP_AMOUNT=0.0.1 ./scripts/bump-version.sh >> /var/log/unfi-bump-version.log 2>&1
#
# Notes:
#   - Set BUMP_AMOUNT in the cron line (patch is the usual choice for a
#     scheduled run); omitting it defaults to a minor bump.
#   - Keep the log redirect so failures are visible; check that file if the
#     version stops moving.
#   - If the branch is protected and direct pushes are rejected, the push step
#     fails. Either allow the push for the cron user or run the script locally
#     and open a pull request instead.
#   - For shared machines, prefer a system cron file such as /etc/cron.d/unfi
#     (which takes an extra user field) over the invoking user's crontab.
#   - Verify the setup by running the same command once by hand from an empty
#     environment: `env -i /bin/bash -c '<cron command>'`.

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
