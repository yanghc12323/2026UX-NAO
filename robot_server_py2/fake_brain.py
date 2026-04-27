# -*- coding: utf-8 -*-
# 这是一个运行在同一台电脑上的测试脚本
import urllib2
import json

# 1. 我们要发送的数据（让机器人说话）
request_data = {
    "command": "speak",
    "payload": {
        "text": "你好，我是你的测试大脑，我已经成功连接上你了！"
    }
}

# 2. 打包成 JSON 并发送给你的 8000 端口
url = "http://127.0.0.1:8000/command"
json_data = json.dumps(request_data)
req = urllib2.Request(url, data=json_data, headers={'Content-Type': 'application/json'})

try:
    print("正在发送指令给机器人...")
    response = urllib2.urlopen(req)
    result = response.read()
    print("收到机器人的回复: ", result)
except Exception as e:
    print("发送失败: ", e)
