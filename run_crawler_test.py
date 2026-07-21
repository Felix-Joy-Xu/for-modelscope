#!/usr/bin/env python3
"""
测试启动器：用 mongomock 替代真实 MongoDB，运行 crawler.main()
"""
import os
import sys

# 配置测试环境变量
os.environ['MONGO_URI'] = 'mongodb://localhost:27017/test_crawler'
os.environ['GITHUB_TOKEN_1'] = 'test_token'
os.environ['GITHUB_TOKEN_2'] = ''
os.environ['GITHUB_TOKEN_3'] = ''
os.environ['REDDIT_CLIENT_ID'] = ''
os.environ['REDDIT_CLIENT_SECRET'] = ''

# 用 mongomock 替换 pymongo
import mongomock
import pymongo
pymongo.MongoClient = mongomock.MongoClient

# 运行主爬虫
import crawler
crawler.main()
