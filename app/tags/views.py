import json
from flask import Flask, Blueprint, abort, request, session, jsonify
from flask import render_template, make_response, redirect, url_for, abort
from flask import g, flash
import tasks
#from tasks import fm_task, users, tags


import hashlib
import requests
import math
import pymongo
import random
from bson import json_util
import HTMLParser
from functools import wraps

html_parser = HTMLParser.HTMLParser()

mod = Blueprint('tags', __name__, url_prefix='')


def requires_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            flash(u'U need to be signed in for this page.')
            return redirect(url_for("index", next=request.path))
        return f(*args, **kwargs)
    return decorated_function


@mod.before_request
def before_request():
    g.user = None
    if 'user' in session:
        g.user = tasks.users.find_one({'user_id': session['user']})
    

@mod.route("/")
def index():
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip,deflate,sdch",
        "Accept-Language": "zh-CN,zh;q=0.8",
        "Connection": "keep-alive",
        "User-Agent": "Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1500.71 Safari/537.36"
    }
    captcha_url = "http://douban.fm/j/new_captcha"
    captcha_r = requests.get(captcha_url, headers=headers)
    captcha_id = captcha_r.content.strip('"')
    img_url = "http://douban.fm/misc/captcha?size=m&id="+captcha_id
    return render_template('index.html', captcha_id=captcha_id, captcha_url=img_url)


@mod.route("/fm", methods=['POST', 'GET'])
def get_fm():
    if request.method == 'POST':
        email = request.form['user_email']
        passwd = request.form['user_passwd']
        captcha = request.form['captcha']
        captcha_id = request.form['captcha_id']
        user_id = hashlib.md5(email).hexdigest()
        res = tasks.fm_task.apply_async((user_id, email, passwd, captcha, captcha_id))
        context = {"id": res.task_id}
        resp = make_response(render_template('tags.html'))
        session['user'] = user_id
        resp.set_cookie('task_id', context['id'])
        return resp
    else:
        return render_template("tags.html")


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
