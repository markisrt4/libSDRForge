#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

base=main
title=
body=
draft=()
while (($#)); do
    case "$1" in
        --base|--title|--body)
            if (($# < 2)) || [[ -z "$2" ]]; then
                echo "Missing value for $1" >&2
                exit 2
            fi
            case "$1" in
                --base) base=$2 ;;
                --title) title=$2 ;;
                --body) body=$2 ;;
            esac
            shift 2 ;;
        --draft) draft=(--draft); shift ;;
        -h|--help)
            echo "Usage: bash ci/open_pr.sh [--base BRANCH] [--title TITLE] [--body BODY] [--draft]"
            exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

command -v gh >/dev/null || { echo "GitHub CLI (gh) is required." >&2; exit 1; }
branch=$(git symbolic-ref --quiet --short HEAD) || {
    echo "A checked-out branch is required." >&2
    exit 1
}
if [[ "$branch" == "$base" ]]; then
    echo "Source and target branches must differ." >&2
    exit 1
fi

url=$(gh pr list --head "$branch" --base "$base" --state open \
    --json url --jq '.[0].url // empty')
if [[ -z "$url" ]]; then
    # Refuse implicit pushes by gh; the remote must already contain HEAD.
    remote=$(git ls-remote --exit-code origin "refs/heads/$branch")
    if [[ "${remote%%[[:space:]]*}" != "$(git rev-parse HEAD)" ]]; then
        echo "Push the current branch to origin before creating a PR." >&2
        exit 1
    fi
    args=(--base "$base" --head "$branch" --fill)
    [[ -z "$title" ]] || args+=(--title "$title")
    [[ -z "$body" ]] || args+=(--body "$body")
    url=$(gh pr create "${args[@]}" "${draft[@]}")
fi

printf '\nGitHub Pull Request:\n%s\n\n' "$url"
if command -v termux-clipboard-set >/dev/null; then
    if ! timeout 10s termux-clipboard-set "$url"; then
        echo "PR URL could not be copied to clipboard." >&2
    fi
fi
