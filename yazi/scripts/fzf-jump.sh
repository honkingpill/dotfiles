#!/bin/bash
# Select directory with fzf and navigate yazi to it
dir=$(fd -t d . 2>/dev/null | fzf --preview 'ls {}' 2>/dev/null)
[ -n "$dir" ] && ya emit cd -- "$dir"
