#!/bin/bash

# Deploy script for MigrationAnalyzer
# Push local changes to Gitea

BRANCH="main"
REMOTE_URL="https://dnrapp110.naturenet.state.co.us/git/ShinyDev/MigrationAnalyzer.git"

echo "=================================================="
echo "Pushing MigrationAnalyzer to Gitea"
echo "  Branch: $BRANCH"
echo "=================================================="
echo ""

git push origin $BRANCH

if [ $? -ne 0 ]; then
    echo ""
    echo "Push failed. Check:"
    echo "  1. Is your tunnel up?"
    echo "  2. Does the repo exist on Gitea? Create it at:"
    echo "     https://dnrapp110.naturenet.state.co.us/git/ShinyDev -> New Repository"
    exit 1
fi

echo ""
echo "Pushed to Gitea successfully"
