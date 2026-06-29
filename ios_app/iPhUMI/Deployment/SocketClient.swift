import SocketIO
import simd

class SocketClient{
    private var manager: SocketManager?
     var socket: SocketIOClient?

    var ready: Bool = false
    var socketOpened: Bool
    
    var hostIP: String?
    var hostPort: Int?
    
    init(){
        socketOpened = false
    }

    func connect(hostIP: String, hostPort: Int) {
        self.hostIP = hostIP
        self.hostPort = hostPort
        self.ready = false
        print("Connecting to \(hostIP):\(hostPort)")
        self.manager = SocketManager(socketURL: URL(string: "http://\(hostIP):\(hostPort)")!, config: [.log(false), .compress])
//        usleep(100000)
        self.socket = self.manager?.defaultSocket
        
        // Connection event
        self.socket?.on(clientEvent: .connect) {data, ack in
            print("Socket connected")
            self.ready = true
            self.socketOpened = true
        }

        // Disconnection event
        self.socket?.on(clientEvent: .disconnect) {data, ack in
            print("Socket disconnected")
            self.ready = false
            self.socketOpened = false
        }

        // Error event
        self.socket?.on(clientEvent: .error) {data, ack in
            print("Socket error: \(data)")
            if let message = data.first as? String {
                if message == "Could not connect to the server." {
                    self.disconnect()
                    // don't try reconnecting immediately
                } else {
                    // messages could include: "Tried emitting when not connected", "Error", ...
                    self.disconnect()
                    self.connect(hostIP: hostIP, hostPort: hostPort)
                }
            }
        }

        // Attempting to reconnect
        self.socket?.on(clientEvent: .reconnectAttempt) {data, ack in
            print("Attempting to reconnect...")
        }
        
        self.socket?.connect()
//        usleep(100000)
        self.ready = true
    }
    
    func getStatus() -> String {
        return socket?.status.description ?? "Uninitialized"
    }
    
    func isConnected() -> Bool {
        return socket?.status == SocketIOStatus.connected
    }

    func sendData(_ data: String, channel: String) {
        if !ready {
            print("Not ready to send")
            return
        }
        self.ready = false
        self.socket?.emit(channel, data)
        self.ready = true
    }
    
    func validateConnection(validationEndpoint: String = "validate", timeoutSeconds: Double = 1) {
        if !ready {
            print("Not ready to validate connection")
            return
        }

        self.socket?.emitWithAck(validationEndpoint, "ping").timingOut(after: timeoutSeconds) { ackData in
            if ackData.isEmpty {
                if let hostIP = self.hostIP, let hostPort = self.hostPort {
                    print("No ACK received, resetting connection...")
                    self.disconnect()
                    self.connect(hostIP: hostIP, hostPort: hostPort)
                }
            } else {
//                print("ACK received: \(ackData)")
            }
        }
    }

    func disconnect() {
        self.ready = false
        socket?.disconnect()
//        usleep(100000) // 0.1 seconds
        self.socketOpened = false
    }
}
