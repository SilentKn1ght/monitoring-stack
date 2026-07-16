#!/bin/sh
grep -q ':2378 00000000000000000000000000000000:0000 0A' /proc/net/tcp6 && exit 0
grep -q ':2378.*:0000.*0A' /proc/net/tcp6 && exit 0
exit 1
