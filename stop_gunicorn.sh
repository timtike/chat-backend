#!/bin/bash

# 获取包含"gunicorn"的进程ID列表
pids=$(ps -ef | grep gunicorn | grep -v grep | awk '{print $2}')

# 循环杀死每个进程
for pid in $pids; do
    echo "Killing process $pid"
    kill $pid
done

echo "All gunicorn processes killed."
