import re
import sys
import time
import socket
import select

from git import Repo
from optparse import OptionParser


VERSION = Repo(search_parent_directories=True).git.describe()


class Client:

    def __init__(self, server, connection):
        self.server = server
        self.connection = connection


class Server:

    def __init__(self, options):
        self.channels = {}
        self.clients = {}
        self.nicknames = {}

        self.ports = options.ports
        self.verbose = options.verbose
        self.debug = options.debug

        if options.listen:
            self.address = socket.gethostbyname(options.listen)
        else:
            self.address = ""

        server_name_limit = 63
        self.name = socket.getfqdn(self.address)[:server_name_limit]

    def print_info(self, msg):
        if self.verbose:
            print(msg)
            sys.stdout.flush()

    def print_debug(self, msg):
        if self.debug:
            print(msg)
            sys.stdout.flush()

    def print_error(self, msg):
        sys.stderr.write("%s\n" % msg)

    def start(self):
        server_sockets = []
        for port in self.ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            try:
                s.bind((self.address, port))
            except socket.error as e:
                self.print_error("Could not bind port %s: %s." % (port, e))
                sys.exit(1)

            s.listen(5)
            server_sockets.append(s)

            self.print_info("Listening on port %d." % port)

        try:
            self.run(server_sockets)
        except:
            self.print_error("Fatal exception")
            raise

    def run(self, server_sockets):
        last_aliveness_check = time.time()

        while True:
            (iwtd, owtd, ewtd) = select.select(server_sockets + [x.socket for x in self.clients.values()], [x.socket for x in self.clients.values() if x.write_queue_size() > 0], [], 10)
            for x in iwtd:
                if x in self.clients:
                    self.clients[x].socket_readable_notification()
                else:
                    (connection, address) = x.accept()
                    try:
                        self.clients[connection] = Client(self, connection)
                        self.print_info("Accepted connection from %s:%s." % (address[0], address[1]))
                    except socket.error as e:
                        try:
                            self.print_error("Socket Error: %s" % e)
                            connection.close()
                        except socket.error as e:
                            self.print_error("Socket Error: %s" % e)
                            pass

            for x in owtd:
                if x in self.clients:
                    self.clients[x].socket_writable_notification()

            now = time.time()
            if last_aliveness_check + 10 < now:
                for client in list(self.clients.values()):
                    client.check_aliveness()
                last_aliveness_check = now


def main(argv):
    op = OptionParser(version=VERSION, description="Simple IRC chat server.")
    op.add_option("--debug", action="store_true", help="print debug messages to stdout")
    op.add_option("--verbose", action="store_true", help="be verbose (print some progress messages to stdout)")
    op.add_option("--listen", metavar="X", help="listen on specific IP address X")
    op.add_option("--ports", metavar="X", help="listen to ports X (a list separated by comma or whitespace)")
    (options, args) = op.parse_args(argv[1:])

    if options.debug:
        options.verbose = True
    if options.ports is None:
        options.ports = "8888"

    ports = []
    for port in re.split(r"[,\s]+", options.ports):
        try:
            ports.append(int(port))
        except ValueError:
            op.error("Bad port: %r" % port)
    options.ports = ports

    server = Server(options)
    try:
        server.start()
    except KeyboardInterrupt:
        server.print_error("Interrupted.")


main(sys.argv)
