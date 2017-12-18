import re
import sys
import time
import socket
import select
import string

from optparse import OptionParser
from setuptools_scm import get_version


VERSION = get_version()


def lower(s):
    return s.translate(str.maketrans(string.ascii_lowercase.upper() + "[]\\^", string.ascii_lowercase + "{}|~"))


class Channel(object):

    def __init__(self, server, name):
        self.server = server
        self.name = name
        self.clients = set()
        self._topic = ""
        self._key = None

    def add_member(self, client):
        self.clients.add(client)

    def get_topic(self):
        return self._topic

    def set_topic(self, value):
        self._topic = value

    topic = property(get_topic, set_topic)

    def get_key(self):
        return self._key

    def set_key(self, value):
        self._key = value

    key = property(get_key, set_key)

    def remove_client(self, client):
        self.clients.discard(client)
        if not self.clients:
            self.server.remove_channel(self)


class Client(object):
    __validate_nickname_regexp = re.compile(r"^[][`_^{|}A-Za-z][][`_^{|}A-Za-z0-9-]{0,50}$")

    def __init__(self, server, connection):
        self.channels = {}

        self.server = server
        self.connection = connection

        self.nickname = None
        self.user = None
        self.real_name = None

        (self.host, self.port) = connection.getpeername()

        self.__timestamp = time.time()
        self.__read_buffer = ""
        self.__write_buffer = ""
        self.__sent_ping = False
        self.__handle_command = self.__registration_handler

    def get_prefix(self):
        return "%s!%s@%s" % (self.nickname, self.user, self.host)
    prefix = property(get_prefix)

    def check_aliveness(self):
        now = time.time()
        if self.__timestamp + 180 < now:
            self.disconnect("ping timeout")
            return
        if not self.__sent_ping and self.__timestamp + 90 < now:
            if self.__handle_command == self.__command_handler:
                self.message("PING :%s" % self.server.name)
                self.__sent_ping = True
            else:
                self.disconnect("ping timeout")

    def write_queue_size(self):
        return len(self.__write_buffer)

    def __parse_read_buffer(self):
        lines = re.compile(r"\r?\n").split(self.__read_buffer)
        self.__read_buffer = lines[-1]
        lines = lines[:-1]
        for line in lines:
            if not line:
                continue
            x = line.split(" ", 1)
            command = x[0].upper()
            if len(x) == 1:
                arguments = []
            else:
                if len(x[1]) > 0 and x[1][0] == ":":
                    arguments = [x[1][1:]]
                else:
                    y = x[1].split(" :", 1)
                    arguments = y[0].split()
                    if len(y) == 2:
                        arguments.append(y[1])
            self.__handle_command(command, arguments)

    def __registration_handler(self, command, arguments):
        server = self.server
        if command == "NICK":
            if len(arguments) < 1:
                self.reply("431 :No nickname given")
                return
            nick = arguments[0]
            if server.get_client(nick):
                self.reply("433 * %s :Nickname is already in use" % nick)
            elif not self.__validate_nickname_regexp.match(nick):
                self.reply("432 * %s :Error in nickname" % nick)
            else:
                self.nickname = nick
                server.client_changed_nickname(self, None)
        elif command == "USER":
            if len(arguments) < 4:
                self.reply("461 %s USER :Not enough parameters" % self.nickname)
                return
            self.user = arguments[0]
            self.real_name = arguments[3]
        elif command == "QUIT":
            self.disconnect("Client quit")
            return

        if self.nickname and self.user:
            self.reply("001 %s :Hi, welcome to Chat" % self.nickname)
            self.reply("002 %s :Your host is %s, running version is %s" % (self.nickname, server.name, VERSION))
            self.reply("003 %s %s chat-%s o o" % (self.nickname, server.name, VERSION))
            self.send_list_users()
            self.__handle_command = self.__command_handler

    def __send_names(self, arguments, for_join=False):
        server = self.server
        valid_channel_re = re.compile(r"^[&#+!][^\x00\x07\x0a\x0d ,:]{0,50}$")
        if len(arguments) > 0:
            channel_names = arguments[0].split(",")
        else:
            channel_names = sorted(self.channels.keys())
        if len(arguments) > 1:
            keys = arguments[1].split(",")
        else:
            keys = []
        keys.extend((len(channel_names) - len(keys)) * [None])
        for (i, channel_name) in enumerate(channel_names):
            if for_join and lower(channel_name) in self.channels:
                continue
            if not valid_channel_re.match(channel_name):
                self.reply("403 %s %s :No such channel" % (self.nickname, channel_name))
                continue
            channel = server.get_channel(channel_name)
            if channel.key is not None and channel.key != keys[i]:
                self.reply("475 %s %s :Cannot join channel (+k) - bad key" % (self.nickname, channel_name))
                continue

            if for_join:
                channel.add_member(self)
                self.channels[lower(channel_name)] = channel
                self.message_channel(channel, "JOIN", channel_name, True)
                if channel.topic:
                    self.reply("332 %s %s :%s" % (self.nickname, channel.name, channel.topic))
                else:
                    self.reply("331 %s %s :No topic is set" % (self.nickname, channel.name))

            names_prefix = "353 %s = %s :" % (self.nickname, channel_name)
            names = ""
            names_max_len = 512 - (len(server.name) + 2 + 2)
            for name in sorted(x.nickname for x in channel.members):
                if not names:
                    names = names_prefix + name
                elif len(names) + len(name) >= names_max_len:
                    self.reply(names)
                    names = names_prefix + name
                else:
                    names += " " + name
            if names:
                self.reply(names)
            self.reply("366 %s %s :End of NAMES list" % (self.nickname, channel_name))

    def __command_handler(self, command, arguments):
        def join_handler():
            if len(arguments) < 1:
                self.reply("461 %s JOIN :Not enough parameters" % self.nickname)
                return
            if arguments[0] == "0":
                for (channel_name, channel) in self.channels.items():
                    self.message_channel(channel, "PART", channel_name, True)
                    server.remove_client_from_channel(self, channel_name)
                self.channels = {}
                return
            self.__send_names(arguments, for_join=True)

        def list_handler():
            if len(arguments) < 1:
                channels = server.channels.values()
            else:
                channels = []
                for channel_name in arguments[0].split(","):
                    if server.has_channel(channel_name):
                        channels.append(server.get_channel(channel_name))
            sorted_channels = sorted(channels, key=lambda x: x.name)
            for channel in sorted_channels:
                self.reply("322 %s %s %d :%s" % (self.nickname, channel.name, len(channel.members), channel.topic))
            self.reply("323 %s :End of LIST" % self.nickname)

        def list_users_handler():
            self.send_list_users()

        def names_handler():
            self.__send_names(arguments)

        def nick_handler():
            if len(arguments) < 1:
                self.reply("431 :No nickname given")
                return
            new_nick = arguments[0]
            client = server.get_client(new_nick)
            if new_nick == self.nickname:
                pass
            elif client and client is not self:
                self.reply("433 %s %s :Nickname is already in use" % (self.nickname, new_nick))
            elif not self.__validate_nickname_regexp.match(new_nick):
                self.reply("432 %s %s :Erroneous Nickname" % (self.nickname, new_nick))
            else:
                old_nickname = self.nickname
                self.nickname = new_nick
                server.client_changed_nickname(self, old_nickname)

        def send_message_handler():
            if len(arguments) == 0:
                self.reply("411 %s :No recipient given (%s)" % (self.nickname, command))
                return
            if len(arguments) == 1:
                self.reply("412 %s :No text to send" % self.nickname)
                return

            target_name = arguments[0]
            message = arguments[1]
            client = server.get_client(target_name)
            if client:
                client.message(":%s %s %s :%s" % (self.prefix, command, target_name, message))
            elif server.has_channel(target_name):
                channel = server.get_channel(target_name)
                self.message_channel(channel, command, "%s :%s" % (channel.name, message))
            else:
                self.reply("401 %s %s :No such nick/channel" % (self.nickname, target_name))

        def ping_handler():
            if len(arguments) < 1:
                self.reply("409 %s :No origin specified" % self.nickname)
                return
            self.reply("PONG %s :%s" % (server.name, arguments[0]))

        def pong_handler():
            pass

        def quit_handler():
            if len(arguments) < 1:
                quit_message = self.nickname
            else:
                quit_message = arguments[0]
            self.disconnect(quit_message)

        handler_table = {
            "JOIN": join_handler,
            "LIST": list_handler,
            "LUSERS": list_users_handler,
            "NAMES": names_handler,
            "NICK": nick_handler,
            "SENDMSG": send_message_handler,
            "PING": ping_handler,
            "PONG": pong_handler,
            "SENDMSGP": send_message_handler,
            "QUIT": quit_handler,
        }

        server = self.server
        try:
            handler_table[command]()
        except KeyError:
            self.reply("421 %s %s :Unknown command" % (self.nickname, command))

    def socket_readable_notification(self):
        try:
            data = self.connection.recv(2 ** 10)
            self.server.print_debug("[%s:%d] -> %r" % (self.host, self.port, data))
            quit_message = "EOT"
        except socket.error as x:
            data = b""
            quit_message = x
        if data:
            self.__read_buffer += data.decode()
            self.__parse_read_buffer()
            self.__timestamp = time.time()
            self.__sent_ping = False
        else:
            self.disconnect(quit_message)

    def socket_writable_notification(self):
        try:
            sent = self.connection.send(self.__write_buffer.encode())
            self.server.print_debug("[%s:%d] <- %r" % (self.host, self.port, self.__write_buffer[:sent]))
            self.__write_buffer = self.__write_buffer[sent:]
        except socket.error as x:
            self.disconnect(x)

    def disconnect(self, quit_message):
        self.message("ERROR :%s" % quit_message)
        self.server.print_info("Disconnected connection from %s:%s (%s)." % (self.host, self.port, quit_message))
        self.connection.close()
        self.server.remove_client(self, quit_message)

    def message(self, msg):
        self.__write_buffer += msg + "\r\n"

    def reply(self, msg):
        self.message(":%s %s" % (self.server.name, msg))

    def message_channel(self, channel, command, message, include_self=False):
        line = ":%s %s %s" % (self.prefix, command, message)
        for client in channel.members:
            if client != self or include_self:
                client.message(line)

    def send_list_users(self):
        self.reply("251 %s :There are %d users on server" % (self.nickname, len(self.server.clients)))


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

    def has_channel(self, name):
        return lower(name) in self.channels

    def get_channel(self, channel_name):
        if lower(channel_name) in self.channels:
            channel = self.channels[lower(channel_name)]
        else:
            channel = Channel(self, channel_name)
            self.channels[lower(channel_name)] = channel
        return channel

    def remove_channel(self, channel):
        del self.channels[lower(channel.name)]

    def client_changed_nickname(self, client, old_nickname):
        if old_nickname:
            del self.nicknames[lower(old_nickname)]
        self.nicknames[lower(client.nickname)] = client

    def remove_client_from_channel(self, client, channel_name):
        if lower(channel_name) in self.channels:
            channel = self.channels[lower(channel_name)]
            channel.remove_client(client)

    def get_client(self, nickname):
        return self.nicknames.get(lower(nickname))

    def remove_client(self, client, quit_message):
        for x in client.channels.values():
            client.channel_log(x, "quit (%s)" % quit_message, meta=True)
            x.remove_client(client)
        if client.nickname and lower(client.nickname) in self.nicknames:
            del self.nicknames[lower(client.nickname)]
        del self.clients[client.connection]

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
        except RuntimeError:
            self.print_error("Fatal exception")
            raise

    def run(self, server_sockets):
        last_aliveness_check = time.time()

        while True:
            (iwtd, owtd, ewtd) = select.select(server_sockets + [x.connection for x in self.clients.values()], [x.connection for x in self.clients.values() if x.write_queue_size() > 0], [], 10)
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


if __name__ == "__main__":
    main(sys.argv)
