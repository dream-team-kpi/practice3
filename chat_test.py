import os
import signal

from nose.tools import assert_not_in, assert_true


SERVER_PORT = 12345


class ServerMock:

    def set_up(self):
        pid = os.fork()
        if pid == 0:
            arguments = ["chat.py", "--debug", "--ports=%s" % SERVER_PORT]
            os.execv("./chat.py", arguments)
        self.child_pid = pid
        self.connections = {}

    def tear_down(self):
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
        self.expect(nick, r":local\S+ 004 %s .*" % nick)
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


def test_some_random_staff():
    server = ServerMock()
    assert_true(True, "It is not true")
    assert_not_in(server, [], "Server is in container")
