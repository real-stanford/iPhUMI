//
//  USBManager.swift
//  Anysense
//
//  Created by Raunaq Bhirangi on 1/13/25.
//

import Network
import UIKit
import Compression


struct PeerTalkHeader {
    var a: UInt32
    var b: UInt32
    var c: UInt32
    var body_size: UInt32
}

class USBManager {
    var port: Int
    private var listener: NWListener?
    private var activeConnection: NWConnection?
    private var disconnectCompletion: (() -> Void)?
    private var ptHeader = PeerTalkHeader(a:1, b:1, c:1, body_size: 0)

    init(port: Int) {
        self.port = port
    }

    func connect() {
        do {
            listener = try NWListener(using: .tcp, on: NWEndpoint.Port(rawValue: in_port_t(port))!)
            listener?.stateUpdateHandler = { [weak self] state in
                guard let self = self else { return }
                switch state {
                case .ready:
                    print("Server ready and listening on port \(self.port)")
                case .failed(let error):
                    print("Listener failed with error: \(error)")
                case .cancelled:
                    DispatchQueue.main.async {
                        self.disconnectCompletion?()
                        self.disconnectCompletion = nil
                        self.listener = nil
                    }
                default:
                    break
                }
            }

            listener?.newConnectionHandler = { [weak self] connection in
                print("Connection received")
                self?.handleConnection(connection: connection)
            }

            listener?.start(queue: .main)
        } catch {
            print("Failed to start listener: \(error)")
        }
    }
    
    func disconnect(completion: (() -> Void)? = nil) {
        // Cancel the active connection first
        if let connection = activeConnection {
            connection.cancel()
            print("Connection cancelled")
        }
        activeConnection = nil

        if let listener = listener {
            disconnectCompletion = completion
            listener.cancel()
            print("Listener cancelled")
            // listener = nil and completion are handled in stateUpdateHandler when .cancelled
        } else {
            listener = nil
            if let completion = completion {
                DispatchQueue.main.async { completion() }
            }
        }
    }
    
    private func handleConnection(connection: NWConnection) {
        self.activeConnection = connection
        connection.stateUpdateHandler = { [weak self] state in
            switch state {
            case .cancelled, .failed:
                self?.activeConnection = nil
            default:
                break
            }
        }
        connection.start(queue: .global())
    }

    func sendData(
        data: Data,
    ) {
        guard let activeConnection = activeConnection else {
            print("No active connection. Cannot send data.")
            return
        }

        self.ptHeader.body_size = UInt32(data.count).bigEndian
        let ptHeaderData = Data(bytes: &self.ptHeader, count:MemoryLayout<PeerTalkHeader>.size)
        
        let completeMessage = ptHeaderData + data
        print("Sending data of size: \(completeMessage.count)")
        activeConnection.send(content: completeMessage, completion: .contentProcessed { [weak self] error in
            if let error = error {
                print("Failed to send data: \(error)")
                self?.activeConnection = nil
            } else {
                print("Image data sent successfully")
            }
        })
    }
    
    func sendData(connection: NWConnection, message: String) {
        let data = message.data(using: .utf8)!
        connection.send(content: data, completion: .contentProcessed { error in
            if let error = error {
                print("Failed to send data: \(error)")
            } else {
                print("Data sent successfully")
            }
        })
    }

    func isConnected() -> Bool {
        return activeConnection != nil
    }
    
}
