#-*- coding:utf-8 -*-

from __future__ import absolute_import
from celery import Celery
from fm import app

celery = Celery('tasks', broker="redis://localhost:6379/0")
celery.config_from_object('config')

import urllib
import requests
from Queue import Queue
import pymongo
import re
import threading
import json
from bson import json_util

connection = pymongo.MongoClient()
db = connection.fm
tags = db.tags
queue = Queue()
users = db.users


def get_songs(email, passwd, captcha, captcha_id):
    login_url = "http://douban.fm/j/login"
    print email, passwd, captcha, captcha_id
    data = {
        "source": "radio",
        "alias": email,
        "form_password": passwd,
        "captcha_solution": captcha,
        "captcha_id": captcha_id,
    }
    login_s = requests.Session()
    login_r = login_s.post(login_url, data=data)
    like_url = "http://douban.fm/mine?type=liked#!type=liked"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip,deflate,sdch",
        "Accept-Language": "zh-CN,zh;q=0.8",
        "Connection": "keep-alive",
        "User-Agent": "Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1500.71 Safari/537.36"
    }
    like_r = login_s.get(like_url)
    try:
        ck = (like_r.cookies["ck"]).strip('"')
    except Exception:
        print "login error."
        return False
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip,deflate,sdch",
        "Accept-Language": "zh-CN,zh;q=0.8",
        "Connection": "keep-alive",
        "Host": "douban.fm",
        "Referer": "http://douban.fm/mine",
        "User-Agent": "Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1500.71 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest"
    }
    start = 0
    songs = []
    while True:
        songs_url = "http://douban.fm/j/play_record?ck=" + ck + "&type=liked&start=" + str(start)
        songs_r = login_s.get(songs_url, headers=headers)
        songs_temp = songs_r.json()['songs']
        if len(songs_temp) == 0:
            break
        songs += songs_temp
        start += 15
    songs_url = []
    for song in songs:
        songs_url.append(song['path'])
    print "get songs done."
    return songs_url


def get_tags(url):
    tag_re = re.compile(r'<a href="http://music.douban.com/tag/(.+?)">(.*?)</a>\((\d+)\)')
    tag_r = requests.get(url)
    tag_content = tag_r.content
    res = tag_re.findall(tag_content)
    res_tags = []
    for t in res:
        res_tags.append((t[1],t[2]))
    return res_tags


class threadUrl(threading.Thread):
    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.queue = queue

    def run(self):
        while True:
            info = self.queue.get()
            url = info[0]
            tag_user_id = info[1]
            print tag_user_id
            print url, 'start'
            res_tags = get_tags(url)
            amount = 0.0
            for t in res_tags:
                amount += int(t[1])
            for t in res_tags:
                tag = t[0].lower()
                tmp = tags.find_one({'user_id': tag_user_id, 'tag': tag})
                per = int(t[1])/amount
                if tmp:
                    tag_id = tmp['_id']
                    per_ori = tmp['per']
                    tags.update({"_id": tag_id},
                                {"$set": {'per': per_ori+per}})
                else:
                    tags.insert({'tag': tag, 'per': per, 'user_id': tag_user_id})
            self.queue.task_done()


@celery.task()
def fm(user_id, email, passwd, catpcha, captcha_id):
    for i in range(10):
        t = threadUrl(queue)
        t.setDaemon(True)
        t.start()

    songs_url = get_songs(email, passwd, catpcha, captcha_id)
    user_tmp = users.find_one({'user_id': user_id})
    if user_tmp:
        users.remove({'user_id': user_id})
    tag_user_id = users.insert({'user_id': user_id})

    if songs_url != False:
        for url in songs_url:
            queue.put((url, tag_user_id))
    else:
        return False

    queue.join()      
    res = tags.find({'user_id':tag_user_id}).sort([('per', pymongo.DESCENDING)]).limit(60)
    data = [json.dumps(tmp, default=json_util.default) for tmp in res]
    return data


if __name__ == '__main__':
    celery.start()
