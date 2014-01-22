#!/usr/bin/python
# -*- coding: utf-8 -*-

import cgi
import redis
import json
import re

QUEUE_NAME = "check_email_queue"
UID_PREFIX = "check_email_task:"
MAIL_PATTERN = re.compile("^[_a-zA-Z0-9-]+(\.[_a-zA-Z0-9-]+)*@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*(\.[a-zA-Z]{2,6})$")

def make_key(uid):
    return UID_PREFIX+uid

if __name__ == "__main__":
    form = cgi.FieldStorage()

    email   = form.getvalue("email", None)
    uid     = form.getvalue("uid", None)

    print "Content-type: text/html"
    print

    if not uid:
        print json.dumps({"status":"ERROR"})
        raise SystemExit

    if not email:
        print json.dumps({"status":"ERROR"})
        raise SystemExit

    # XXX
    # check_uid(uid)
    # uid can be checked via redis in example

    # check email on regular expression
    if not MAIL_PATTERN.match(email):
        print json.dumps({"status":"ERROR"})
        raise SystemExit

    r = redis.StrictRedis(host="localhost")
    key = make_key(uid)

    # check if task exists
    old_email=r.hget(key, "email")
    if old_email == email:
        status = r.hget(key, "status")
        if not status:
            status = "QUEUED"
            
    else:
    # create uid for an hour and queue it
        r.hset(key, "email", email)
        r.expire(key, 60*60)
        r.sadd(QUEUE_NAME, key)
        status = "QUEUED"

    print json.dumps({"status":status})
    print

