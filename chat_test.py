import re
import os
import time
import signal
import socket
import subprocess

from nose.tools import assert_not_in, assert_true


SERVER_PORT = 12345


class ServerFixture:

    def setUp(self):
        pid = os.fork()
        if pid == 0:
            subprocess.call(["python", "chat.py", "--debug", "--ports=%s" % SERVER_PORT])
        self.child_pid = pid
        self.connections = {}

    def tearDown(self):
        os.kill(self.child_pid, signal.SIGTERM)
        os.waitpid(self.child_pid, 0)
        for connection in self.connections.values():
            connection.close()

    def send(self, name, message):
        self.connections[name].write(message + "\n\r")
        self.connections[name].flush()

    def connect(self, nick):
        assert_not_in(nick, self.connections)
        s = socket.socket()
        tries_left = 100
        while tries_left > 0:
            try:
                s.connect(("localhost", SERVER_PORT))
                break
            except socket.error:
                tries_left -= 1
                time.sleep(0.01)
        self.connections[nick] = s.makefile(mode="rw")
        self.send(nick, "NICK %s" % nick)
        self.send(nick, "USER %s * * %s" % (nick, nick))
        self.expect(nick, r":local\S+ 001 %s :.*" % nick)
        self.expect(nick, r":local\S+ 002 %s :.*" % nick)
        self.expect(nick, r":local\S+ 003 %s :.*" % nick)
        self.expect(nick, r":local\S+ 251 %s :.*" % nick)
        self.expect(nick, r":local\S+ 422 %s :.*" % nick)

    def expect(self, nick, regexp):
        def timeout_handler(signum, frame):
            raise AssertionError("timeout while waiting for %r" % regexp)
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(1)  # Give the server 1 second to respond
        line = self.connections[nick].readline().rstrip()
        signal.alarm(0)  # Cancel the alarm
        regexp = ("^%s$" % regexp).replace(r"local\S+", socket.getfqdn())
        m = re.match(regexp, line)
        if m:
            return m
        else:
            assert_true(False, "Regexp %r didn't match %r" % (regexp, line))


class TestBasicFunctionality(ServerFixture):

    def test_registration(self):
        self.connect("john")

    def test_bad_ping(self):
        self.connect("john")
        self.send("john", "PING")
        self.expect("john", r"\S+ 409 apa :.*")

    def test_good_ping(self):
        self.connect("john")
        self.send("john", "PING :fisk")
        self.expect("john", r":local\S+ PONG \S+ :fisk")

    def test_list_users(self):
        self.connect("john")
        self.send("john", "lusers")
        self.expect("john", r":local\S+ 251 apa :There are \d+ users on servers*")
