#!/bin/sh
supervisord -c supervisord.conf
/opt/startup/startup.sh
