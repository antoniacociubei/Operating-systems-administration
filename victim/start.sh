#!/bin/bash
echo "Starting Telnet server on Victim..."
echo "root:root" | chpasswd
service xinetd start
tail -f /dev/null
