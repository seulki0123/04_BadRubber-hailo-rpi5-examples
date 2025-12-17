import json
import socket

from rubber_tracker.utils import ProcessLogger
from rubber_tracker.utils import CustomThread

class TCPServer(ProcessLogger):
    def __init__(self, host, port, name):
        super().__init__(self.__class__.__name__ + "_" + name)
        self.name = name
        self.host = host
        self.port = port
        self.socket = None
        self.clients = []          # connected client sockets
        self.send_buffers = {}     # socket -> pending send buffer

    def start(self):
        self.thread = CustomThread(
            name=self.__class__.__name__ + "_" + self.name,
            task=self._task,
            interval=0.01
        )
        self.thread.start()

    def broadcast(self, data):
        # Convert dict to JSON or str, append newline for framing
        msg = json.dumps(data) if isinstance(data, dict) else str(data)
        packet = (msg + "\n").encode("utf-8")

        # Store packet in each client's outgoing buffer
        for c in list(self.clients):
            try:
                self.send_buffers.setdefault(c, bytearray()).extend(packet)
            except Exception as e:
                self._remove_client(c, err=e)

    def _task(self):
        # Accept new clients + flush outgoing data
        self._accept()
        self._flush_send_buffers()

    def _flush_send_buffers(self):
        # Non-blocking send: flush as much as possible
        dead = []

        for c, buf in list(self.send_buffers.items()):
            if not buf:
                continue

            try:
                sent = c.send(buf)   # may send partial data
                if sent > 0:
                    try:
                        addr = c.getpeername()
                    except:
                        addr = "<unknown>"
                    self.log_info(f"Sent {sent} bytes to {addr}")

                    del buf[:sent]    # remove sent bytes

            except BlockingIOError:
                # Socket not ready for sending
                pass

            except Exception as e:
                # Any other error => close client
                self._remove_client(c, err=e)
                dead.append(c)

        # Remove closed clients from buffer list
        for c in dead:
            self.send_buffers.pop(c, None)

    def _remove_client(self, c, err=None):
        # Safely remove and close a client
        try:
            addr = c.getpeername()
        except:
            addr = "<unknown>"

        if err:
            self.log_error(f"Client {addr} removed due to error: {err}")
        else:
            self.log_info(f"Client {addr} disconnected")

        try:
            c.close()
        except:
            pass

        try:
            self.clients.remove(c)
        except:
            pass

        # Clear pending buffer
        self.send_buffers.pop(c, None)

    def _accept(self):
        # Accept new client if server socket is ready
        if self.socket is None:
            self._open()
            return

        try:
            client, addr = self.socket.accept()
            client.setblocking(False)

            self.clients.append(client)
            self.send_buffers[client] = bytearray()

            self.log_info(f"Client connected: {addr}")

        except BlockingIOError:
            # No pending connections
            pass
        except Exception as e:
            self.log_error(f"Accept error: {e}")

    def _open(self):
        # Create listening socket
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            self.socket.setblocking(False)

            self.log_info(f"TCPServer started on {self.host}:{self.port}")

        except Exception as e:
            self.log_error(f"Failed to start TCPServer: {e}")
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
