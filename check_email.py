#!/usr/bin/python
# -*- coding: utf-8 -*-

import os,sys
import socket
import re

'''
Standart scenario:

Trying 213.180.193.89...
Connected to mx.yandex.ru.
Escape character is '^]'.
220 mxfront3h.mail.yandex.net (Want to use Yandex.Mail for your domain? Visit http://pdd.yandex.ru)
ehlo ok.com
250-mxfront3h.mail.yandex.net
250-8BITMIME
250-PIPELINING
250-SIZE 42991616
250-STARTTLS
250-DSN
250 ENHANCEDSTATUSCODES
mail from:<a@rnd.stcnet.ru>
250 2.1.0 <a@rnd.stcnet.ru> ok
rcpt to:<aa4454544322343242@yandex.ru>
550 5.7.1 No such user!
rcpt to:<dp81@yandex.ru>
250 2.1.5 <dp81@yandex.ru> recipient ok
quit
221 2.0.0 Closing connection.
Connection closed by foreign host.
'''

'''
mail.ru checks via submission
# telnet smtp.mail.ru 587

Trying 94.100.177.1...
Connected to smtp.mail.ru.
Escape character is '^]'.
220 smtp21.mail.ru ESMTP ready
EHLO ok.com
250-smtp21.mail.ru
250-SIZE 73400320
250-8BITMIME
250-AUTH PLAIN LOGIN
250 STARTTLS
AUTH LOGIN
334 VXNlcm5hbWU6
dGVzdDE0MTQxNDg4LmNvbQ==
334 UGFzc3dvcmQ6
dGVzdDE0MTQxNDg4LmNvbQ==
535 Incorrect authentication data: user not found for <test14141488.com@mail.ru>
'''


RE220 = re.compile("^220 .*")
RE250 = re.compile("^250 .*")
RE550 = re.compile("^55[0-9] .*")
RE540 = re.compile("^54[0-9] .*")

#mail.ru
REMAILRUYESUSER = re.compile("^535 Incorrect authentication data: authentication failed for.*")
REMAILRUNOUSER = re.compile("^535 Incorrect authentication data: user not found for.*")

DEBUG = False
MAXREPLY = 65536

CONNECTION_TIMEOUT = 1
OPERATION_TIMEOUT = 20 # minimal for gmail if miss

UNDECIDED = 'UNDECIDED'
VALID = 'VALID'
NOT_VALID = 'NOT_VALID'
ABORT = 'ABORT'

def rcpt_to(email):
    return "RCPT TO: <%s>\n" % email

def auth_plain(email):
    from base64 import encodestring
    return "AUTH PLAIN %s\n" % encodestring("\x00%s\x000324420b9b8c9e2a9ee383a09992eb49cc6649e\x00" % email)

# [ out or None, [(match_expression, action: True is valid, False is nogo, None is continue) ]
steps_smtp = [( '', [(RE220, UNDECIDED),] ), 
                ( "EHLO a.rnd.stcnet.ru\n", [(RE250, UNDECIDED),]),
                ( "MAIL FROM:<ashcan@rnd.stcnet.ru>\n", [(RE250, UNDECIDED),]),
                ( rcpt_to, [ (RE550, NOT_VALID), (RE540, NOT_VALID), (RE250, VALID)]),
                ( "QUIT\n", [])]

steps_mail_ru = [( '', [(RE220, UNDECIDED),] ),
                ( "EHLO a.rnd.stcnet.ru\n", [(RE250, UNDECIDED),]),
                ( auth_plain, [ (REMAILRUNOUSER, NOT_VALID), (REMAILRUYESUSER, VALID) ]),
                ("QUIT\n", [])]

Screenplays = {
    'mail.ru' : ( None, '_SUBMISSION', steps_mail_ru ),
    'bk.ru' : ( None, '_SUBMISSION', steps_mail_ru ),
    'inbox.ru' : ( None, '_SUBMISSION', steps_mail_ru ),
    'list.ru' : ( None, '_SUBMISSION', steps_mail_ru ),
    'default' : (None, 'SMTP', steps_smtp ),
}

def find_mx(domain):
    import dns.resolver

    try:
        mxs = [x.to_text().split() for x in dns.resolver.query(domain, 'MX')]
    except dns.resolver.NXDOMAIN:
        host = domain
    except dns.resolver.NoAnswer:
        host = domain
    else:
        mxs.sort(key=lambda x: int(x[0]))
        host = mxs[0][1]
    if DEBUG: print "MX resolved to:", host
    return host

def find_submission(domain):
    import dns.resolver

    port = None

    try:
        mxs = [x.to_text().split() for x in dns.resolver.query("_submission._tcp.%s" % domain, 'SRV')]
    except dns.resolver.NXDOMAIN:
        host = None
    else:
        mxs = filter(lambda x: int(x[1]), mxs)
        mxs.sort(key=lambda x: int(x[0]))
        if mxs:
            host = mxs[0][3]
            port = int(mxs[0][2])

    if DEBUG: print "_SUBMISSION resolved to:", host, ":", port
    return (host, port)
            
    
def connect(server, port, domain):
    real_port = port
    if server is None:
        if port == "SMTP":
            real_port = 25
            server = find_mx(domain)
        elif port == "_SUBMISSION":
            (server, real_port) = find_submission(domain)

    if not server:
        if (DEBUG): print "Server is None, but auto detection unavailable for the port. Giving up."
        return None

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(CONNECTION_TIMEOUT)

    try:
        sock.connect((server, real_port))
    except socket.error,why:
        if DEBUG: print "Unable to connect:", why
        return None

    return sock

def execute_shot(s, shot, email):
    send_smth, receive_patterns = shot

    if isinstance(send_smth, basestring):
        send_data = send_smth
    elif callable(send_smth):
        send_data = send_smth(email)
    else:
        print "Should be the string or the callable object!"
        return ABORT

    s.settimeout(OPERATION_TIMEOUT)
    if send_data:
        if DEBUG: print "Writing:", send_data
        try:
            s.send(send_data)
        except socket.timeout:
            if DEBUG: print "Write socket timeout, aborting."
            return ABORT
        except socket.error, why:
            if DEBUG: print "Socket error on write, aborting."
            return ABORT

    try:
        reply = s.recv(MAXREPLY)
    except socket.timeout:
        if DEBUG: print "Read socket timeout, aborting."
        return ABORT
    except socket.error, why:
        if DEBUG: print "Socket error on read, aborting."
        return ABORT
    else:
        if DEBUG: print "Got reply:", reply

    if not receive_patterns:
        return UNDECIDED
    for s in reply.split('\n'):
        for (pattern, retcode) in receive_patterns:
            if pattern.match(s):    # XXX the first one takes it all
                if DEBUG: print "Matched pattern to return:", retcode
                return retcode

    if DEBUG: print "Returning ABORT on strange reply!"
    return ABORT # XXX we didn't match any pattern, probably smth goes completely wrong

# True - ok, False - absent, None - don't know
def check_email(email):
    return_result = UNDECIDED

    # XXX simpliest way
    try:
        (username, domain) = email.split('@')
    except ValueError:
        return NOT_VALID

    if Screenplays.has_key(domain):
        (server, port, screenplay,) = Screenplays[domain]
    elif Screenplays.has_key('default'):
        (server, port, screenplay,) = Screenplays['default']
    else:
        return UNDECIDED

    s = connect(server, port, domain)
    if not s: return NOT_VALID
    
    for shot in screenplay:
        result = execute_shot(s, shot, email)
        if result == ABORT:
            return UNDECIDED
        elif result in (VALID, NOT_VALID):
            return_result = result # XXX probably one can remeber only the first decision value

    try:
        s.shutdown(socket.SHUT_RDWR)
        s.close()
    except socket.error:
        pass

    return return_result

if __name__ == '__main__':
    if len(sys.argv) > 1:
        DEBUG = True
        result = check_email(sys.argv[1])
        print "Email:", sys.argv[1], ":", result
    else:
        print "Usage:", sys.argv[0], "email@address"
