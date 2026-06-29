/*
See LICENSE folder for this sample's licensing information.

Abstract:
A simple abstraction of the MultipeerConnectivity API as used in this app.
*/

import MultipeerConnectivity

/// - Tag: MultipeerSession
class MultipeerSession: NSObject {
    static let serviceType = "ar-collab"
    static let discoveryUUIDKey = "peerUUID"

    private let myPeerID = MCPeerID(displayName: UIDevice.current.name)
    private let myUUID = UUID().uuidString
    private var session: MCSession!
    private var serviceAdvertiser: MCNearbyServiceAdvertiser!
    private var serviceBrowser: MCNearbyServiceBrowser!

    private let receivedDataHandler: (Data, MCPeerID) -> Void
    private let peerJoinedHandler: (MCPeerID) -> Void
    private let peerLeftHandler: (MCPeerID) -> Void
    private let peerDiscoveredHandler: (MCPeerID) -> Bool

    /// - Tag: MultipeerSetup
    init(receivedDataHandler: @escaping (Data, MCPeerID) -> Void,
         peerJoinedHandler: @escaping (MCPeerID) -> Void,
         peerLeftHandler: @escaping (MCPeerID) -> Void,
         peerDiscoveredHandler: @escaping (MCPeerID) -> Bool) {
        self.receivedDataHandler = receivedDataHandler
        self.peerJoinedHandler = peerJoinedHandler
        self.peerLeftHandler = peerLeftHandler
        self.peerDiscoveredHandler = peerDiscoveredHandler

        super.init()
        session = MCSession(peer: myPeerID, securityIdentity: nil, encryptionPreference: .required)
        session.delegate = self

        let discoveryInfo = [MultipeerSession.discoveryUUIDKey: myUUID]
        serviceAdvertiser = MCNearbyServiceAdvertiser(peer: myPeerID, discoveryInfo: discoveryInfo, serviceType: MultipeerSession.serviceType)
        serviceAdvertiser.delegate = self
        serviceAdvertiser.startAdvertisingPeer()

        serviceBrowser = MCNearbyServiceBrowser(peer: myPeerID, serviceType: MultipeerSession.serviceType)
        serviceBrowser.delegate = self
        serviceBrowser.startBrowsingForPeers()
    }

    func endSession() {
        serviceAdvertiser.stopAdvertisingPeer()
        serviceBrowser.stopBrowsingForPeers()
        session.disconnect()
    }

    func sendToAllPeers(_ data: Data, reliably: Bool) {
        sendToPeers(data, reliably: reliably, peers: connectedPeers)
    }

    /// - Tag: SendToPeers
    func sendToPeers(_ data: Data, reliably: Bool, peers: [MCPeerID]) {
        guard !peers.isEmpty else { return }
        do {
            try session.send(data, toPeers: peers, with: reliably ? .reliable : .unreliable)
        } catch {
            print("error sending data to peers \(peers): \(error.localizedDescription)")
        }
    }

    var connectedPeers: [MCPeerID] {
        return session.connectedPeers
    }
}

extension MultipeerSession: MCSessionDelegate {

    func session(_ session: MCSession, peer peerID: MCPeerID, didChange state: MCSessionState) {
        switch state {
        case .connected:
            peerJoinedHandler(peerID)
        case .notConnected:
            peerLeftHandler(peerID)
        case .connecting:
            print("Peer \(peerID.displayName) is connecting...")
        @unknown default:
            print("Unknown state \(state.rawValue) for peer \(peerID.displayName)")
        }
    }

    func session(_ session: MCSession, didReceive data: Data, fromPeer peerID: MCPeerID) {
        autoreleasepool {
            receivedDataHandler(data, peerID)
        }
    }

    func session(_ session: MCSession, didReceive stream: InputStream, withName streamName: String,
                 fromPeer peerID: MCPeerID) {
        print("This service does not send/receive streams.")
    }

    func session(_ session: MCSession, didStartReceivingResourceWithName resourceName: String,
                 fromPeer peerID: MCPeerID, with progress: Progress) {
        print("This service does not send/receive resources.")
    }

    func session(_ session: MCSession, didFinishReceivingResourceWithName resourceName: String,
                 fromPeer peerID: MCPeerID, at localURL: URL?, withError error: Error?) {
        print("This service does not send/receive resources.")
    }

}

extension MultipeerSession: MCNearbyServiceBrowserDelegate {

    /// - Tag: FoundPeer
    public func browser(_ browser: MCNearbyServiceBrowser, foundPeer peerID: MCPeerID, withDiscoveryInfo info: [String: String]?) {
        // Only let the peer with the lexicographically smaller UUID act as inviter.
        // This prevents both phones simultaneously inviting each other, which creates
        // duplicate connections that drop asymmetrically. UUIDs are unique per session
        // and reliable even when all devices share the same display name.
        guard let peerUUID = info?[MultipeerSession.discoveryUUIDKey] else {
            // Peer is not running our app version with UUID discovery info — skip.
            return
        }
        guard myUUID < peerUUID else { return }
        let accepted = peerDiscoveredHandler(peerID)
        if accepted {
            browser.invitePeer(peerID, to: session, withContext: nil, timeout: 10)
        }
    }

    public func browser(_ browser: MCNearbyServiceBrowser, lostPeer peerID: MCPeerID) {
        // This app doesn't do anything with non-invited peers, so there's nothing to do here.
    }

}

extension MultipeerSession: MCNearbyServiceAdvertiserDelegate {

    /// - Tag: AcceptInvite
    func advertiser(_ advertiser: MCNearbyServiceAdvertiser, didReceiveInvitationFromPeer peerID: MCPeerID,
                    withContext context: Data?, invitationHandler: @escaping (Bool, MCSession?) -> Void) {
        // Call the handler to accept the peer's invitation to join.
        invitationHandler(true, self.session)
    }
}
