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


def test_some_random_staff():
    server = ServerMock()
    assert_true(True, "It is not true")
    assert_not_in(server, [], "Server is in container")
