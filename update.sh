#!/usr/bin/env bash
git push
rm -rf ~/.cache/nix
nix profile upgrade kubux-mail-client
