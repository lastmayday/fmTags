#-*- coding:utf-8 -*-

import json
from flask import Flask, Blueprint, request, session, jsonify
from flask import render_template, make_response, redirect, url_for
from flask import g, flash
import tasks

import hashlib
import requests
import math
import pymongo
import random
from bson import json_util
import HTMLParser
from functools import wraps
from urlparse import urlparse
import re
import urllib2
import urllib
from ghost import Ghost


ghost = Ghost()
html_parser = HTMLParser.HTMLParser()
mod = Blueprint('tags', __name__, url_prefix='')


def requires_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            flash(u'少年请先登录~（≧▼≦；)')
            return redirect(url_for("tags.index", next=request.path))
        return f(*args, **kwargs)
    return decorated_function


@mod.before_request
def before_request():
    g.user = None
    if 'user' in session:
        g.user = tasks.users.find_one({'user_id': session['user']})
    

@mod.route("/")
def index():
    bid_url = "http://douban.fm/common_login?redir=/mine"
    bid_r = urllib2.Request(bid_url)
    content = urllib2.urlopen(bid_r)
    cookie = content.headers.get('Set-Cookie')
    bid_re = re.compile(r'bid=\"([\s\S]+?)\";')
    bid = bid_re.findall(cookie)[0]
    captcha_url = "http://douban.fm/j/new_captcha"
    captcha_r = urllib2.Request(captcha_url)
    captcha_content = urllib2.urlopen(captcha_r)
    captcha_id = captcha_content.read().strip('"')
    img_url = "http://douban.fm/misc/captcha?size=m&id="+captcha_id
    return render_template('index.html', captcha_id=captcha_id, captcha_url=img_url, bid=bid)


@mod.route("/fm", methods=['POST', 'GET'])
def get_fm():
    if request.method == 'POST':
        email = request.form['user_email']
        passwd = request.form['user_passwd']
        captcha = request.form['captcha']
        captcha_id = request.form['captcha_id']
        bid = request.form['bid']
        login_url = "http://douban.fm/j/login"
        data = {
            "source": "radio",
            "alias": email,
            "form_password": passwd,
            "captcha_solution": captcha,
            "captcha_id": captcha_id,
        }
        login_s = requests.Session()
        login_r = login_s.post(login_url, data=data)
        ck = (login_r.cookies["ck"]).strip('"')
        like_url = "http://douban.fm/mine?type=liked#!type=liked"
        like_r = login_s.get(like_url)
        like_content = like_r.content
        script_re = re.compile(r'<script>([\s\S]+?)</script>')
        scripts = script_re.findall(like_content)
        script = scripts[-2]
        spbid, resources = ghost.evaluate(script+';window.user_id_sign;')
        spbid = urlparse(spbid+bid).geturl()
        try:
            res = login_r.json()
            if  'err_msg' in res:
                error = res['err_msg']
                flash(error, 'error')
                return redirect(url_for("tags.index"))
            else:
                user_id = hashlib.md5(email).hexdigest()
                res = tasks.fm_task.apply_async((login_s, bid, ck, user_id, spbid))
                context = {"id": res.task_id}
                resp = make_response(render_template('tags.html', encode_script=script))
                session['user'] = user_id
                resp.set_cookie('task_id', context['id'])
                return resp
        except Exception:
            flash(u'登录错误...', 'error')
            return redirect(url_for("tags.index"))
    else:
        return redirect(url_for("tags.mine"))


@mod.route("/fm/result/<task_id>")
def fm_result(task_id):
    retval = tasks.fm_task.AsyncResult(task_id).get(timeout=300)
    if retval == False:
        return jsonify({'error': True})
    data = {'error': False, 'tags': []}
    for res in retval:
        res = json.loads(res)
        tag = html_parser.unescape(res['tag'])
        per = math.ceil(res['per'])
        data['tags'].append({'tag': tag.title(), 'per': per})
    return jsonify(data=data)


@mod.route("/mine")
@requires_login
def mine_tags():
    return render_template("tags.html")


@mod.route("/shuffle")
def shuffle():
    return render_template("shuffle.html")


@mod.route("/api/shuffle")
def shuffle_api():
    user_count = tasks.users.count()
    num = random.randint(1, user_count-1)
    user = tasks.users.find().limit(-1).skip(num).next()
    user_id = user['_id']
    res = tasks.tags.find({'user_id':user_id}).sort([('per', pymongo.DESCENDING)]).limit(60)
    retval = [json.dumps(tmp, default=json_util.default) for tmp in res]
    if retval == False:
        return jsonify({'error': True})
    data = {'error': False, 'tags': []}
    for res in retval:
        res = json.loads(res)
        tag = html_parser.unescape(res['tag'])
        per = math.ceil(res['per'])
        data['tags'].append({'tag': tag.title(), 'per': per})
    return jsonify(data=data)

if __name__ == '__main__':
    mod.run(debug=True)
