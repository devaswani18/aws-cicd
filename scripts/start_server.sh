#!/bin/bash
exit 1  # Forces the script to fail
systemctl start httpd
systemctl enable httpd
