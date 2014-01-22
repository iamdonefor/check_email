#!/usr/bin/python
# -*- coding: utf-8 -*-

import redis
from time import sleep
from threading import Thread
from datetime import datetime
from check_email import check_email

class EmailChecker():
    QUEUE_NAME = "check_email_queue"
    MAX_WORKERS = 4 
    CYCLE_SLEEP = 1

    def __init__(self, host, port=6379, **kw):
        self.redis_host = host
        self.redis_port = port
        self.rc = None
        self.workers = []
        self.__dict__.update(kw)

    def rc_connect(self, reconnect=False):
        if reconnect:
            del self.rc
            self.rc = None

        if self.rc:
            try:
                self.rc.ping()
            except redis.exceptions.ConnectionError, why:
                del self.rc
                self.rc = None
            else:
                return

        while True:
            try:
                self.rc = redis.StrictRedis(host=self.redis_host, port=self.redis_port, db=0)
                self.rc.ping()
            except redis.exceptions.ConnectionError, why:
                print "unable to ping redis server, sleeping for 10 seconds\n", why
                del self.rc
                sleep(10)
            else:
                break
                 

    def get_next_id(self):
        return self.rc.spop(self.QUEUE_NAME) # may be set, may be list, still choosing 

    def worker(self, cid, email):
        self.rc.hset(cid, "status", "PROCESSING")
        status = check_email(email)
        print ">", cid, ":", email, "::", status
        self.rc.hset(cid, "status", status)

    def create_worker(self, cid):
        email = self.rc.hget(cid, "email")
        if not email:   # strange but report job undeclined
#            email=cid
            self.rc.hset(cid, "status", "ERROR")
            return

        self.rc.hset(cid, "status", "PROCESSING")
        t = Thread(target=self.worker, args=(cid, email,))
        start = datetime.now()
        self.workers.append((t, start.strftime("%s")))
        t.daemon = True
        t.start()
    
    def run(self):
        self.rc_connect() # moved here cause theres endless loop in connection

        while True:
            for (t,tstart) in self.workers[:]:
                if not t.is_alive():
                    print "joining:", t
                    t.join()
                    self.workers.remove((t,tstart))

            if len(self.workers) >= self.MAX_WORKERS:
                sleep(self.CYCLE_SLEEP)
                continue

            try:
                cid = self.get_next_id()
                if cid:
                    self.create_worker(cid)
                else:
                    sleep(self.CYCLE_SLEEP)
            except redis.exceptions.RedisError:
                # probably error with server, so reconnect
                self.rc_connect(reconnect=True)
                
if __name__ == '__main__':
    ec = EmailChecker("localhost")
    ec.run()

