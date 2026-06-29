/*
See LICENSE folder for this sample’s licensing information.

Abstract:
Main view controller for the AR experience.
*/

import UIKit
import RealityKit
import ARKit
import VisionKit
import MultipeerConnectivity
import Speech
import ObjectiveC
import MediaPlayer
import Foundation
import AVKit

extension UIButton {
    func setTitleKeepingFont(_ title: String?) {
        guard
            configuration != nil,
            let title,
            let currentFont = titleLabel?.font
        else {
            setTitle(title, for: .normal)
            return
        }

        let paragraphStyle = NSMutableParagraphStyle()
        paragraphStyle.alignment = .center
        let attributes: [NSAttributedString.Key: Any] = [
            .font: currentFont,
            .paragraphStyle: paragraphStyle
        ]
        let attributedTitle = NSAttributedString(string: title, attributes: attributes)
        setAttributedTitle(attributedTitle, for: .normal)
    }
}

class DataPacket {
    var transformMatrix: simd_float4x4
    var timestamp: Double

    init(transformMatrix: simd_float4x4, timestamp: Double) {
        self.transformMatrix = transformMatrix
        self.timestamp = timestamp
    }
    func toBytes() -> Data {
        var data = Data()

        // Append pose data
        for i in 0..<4 {
            for j in 0..<4 {
                var val = transformMatrix[i][j]
                data.append(Data(bytes: &val, count: MemoryLayout<Float>.size))
            }
        }

        // Append timestamp
        var timestampVal = timestamp
        data.append(Data(bytes: &timestampVal, count: MemoryLayout<Int64>.size))

        return data
    }
}

enum PhoneSide: Int {
    case left = 0
    case right = 1
    case head = 2

    var recordingNameComponent: String {
        switch self {
        case .left:
            return "left"
        case .right:
            return "right"
        case .head:
            return "head"
        }
    }
}


extension ARFrame {
    func getCapturedUltraWideImage() -> CVPixelBuffer? {
        // magic to get access to ultrawide image
        let ivarName = "_capturedUltraWideImage"

        guard let ivar = class_getInstanceVariable(ARFrame.self, ivarName) else {
            print("Failed to find ivar: \(ivarName)")
            return nil
        }

        let ptr = UnsafeRawPointer(Unmanaged.passUnretained(self).toOpaque()).advanced(by: ivar_getOffset(ivar))
        let pixelBuffer = ptr.load(as: CVPixelBuffer?.self)

        return pixelBuffer
    }
    
    func getUltraWideTimestamp() -> TimeInterval? {
        // magic to get access to ultrawide timestamp
        let ivarName = "_ultraWideImageTimestamp"

        guard let ivar = class_getInstanceVariable(ARFrame.self, ivarName) else {
            print("Failed to find ivar: \(ivarName)")
            return nil
        }
        
        let ptr = UnsafeRawPointer(Unmanaged.passUnretained(self).toOpaque()).advanced(by: ivar_getOffset(ivar))
        let timestamp = ptr.load(as: Double?.self)

        return timestamp
    }
    
    func getUltraWideCamera() -> ARCamera? {
        // magic to get access to ultrawide camera device
        let ivarName = "_ultraWideCamera"

        guard let ivar = class_getInstanceVariable(ARFrame.self, ivarName) else {
            print("Failed to find ivar: \(ivarName)")
            return nil
        }
        
        let ptr = UnsafeRawPointer(Unmanaged.passUnretained(self).toOpaque()).advanced(by: ivar_getOffset(ivar))
        let arCamera = ptr.load(as: ARCamera?.self)

        return arCamera
    }
}

class RecordingMessage : NSObject, NSSecureCoding {
    var startRecording: Bool
    var recordingName: NSString?
    var recordingStartTime: NSDate?
    // Settings snapshot — present only when startRecording = true so the
    // recipient can verify consistency before committing to the recording.
    var recordTypeSegmentIndex: NSNumber?
    var labelTypeSegmentIndex: NSNumber?
    var tasks: [String]?
    var sessionName: NSString?
    var gripperID: NSString?
    var phoneSide: NSNumber?
    var sidesPresent: [String]?

    init(startRecording: Bool, recordingName: NSString?, recordingStartTime: NSDate?,
         recordTypeSegmentIndex: NSNumber? = nil, labelTypeSegmentIndex: NSNumber? = nil,
         tasks: [String]? = nil, sessionName: NSString? = nil,
         gripperID: NSString? = nil, phoneSide: NSNumber? = nil,
         sidesPresent: [String]? = nil) {
        self.startRecording = startRecording
        self.recordingName = recordingName
        self.recordingStartTime = recordingStartTime
        self.recordTypeSegmentIndex = recordTypeSegmentIndex
        self.labelTypeSegmentIndex = labelTypeSegmentIndex
        self.tasks = tasks
        self.sessionName = sessionName
        self.gripperID = gripperID
        self.phoneSide = phoneSide
        self.sidesPresent = sidesPresent
    }

    static var supportsSecureCoding: Bool { return true }

    required init?(coder decoder: NSCoder) {
        startRecording = decoder.decodeBool(forKey: "startRecording")
        recordingName = decoder.decodeObject(of: NSString.self, forKey: "recordingName")
        recordingStartTime = decoder.decodeObject(of: NSDate.self, forKey: "recordingStartTime")
        recordTypeSegmentIndex = decoder.decodeObject(of: NSNumber.self, forKey: "recordTypeSegmentIndex")
        labelTypeSegmentIndex = decoder.decodeObject(of: NSNumber.self, forKey: "labelTypeSegmentIndex")
        if let arr = decoder.decodeObject(of: [NSArray.self, NSString.self], forKey: "tasks") as? NSArray {
            tasks = arr.compactMap { $0 as? String }
        }
        sessionName = decoder.decodeObject(of: NSString.self, forKey: "sessionName")
        gripperID = decoder.decodeObject(of: NSString.self, forKey: "gripperID")
        phoneSide = decoder.decodeObject(of: NSNumber.self, forKey: "phoneSide")
        if let arr = decoder.decodeObject(of: [NSArray.self, NSString.self], forKey: "sidesPresent") as? NSArray {
            sidesPresent = arr.compactMap { $0 as? String }
        }
    }

    func encode(with coder: NSCoder) {
        coder.encode(startRecording, forKey: "startRecording")
        coder.encode(recordingName, forKey: "recordingName")
        coder.encode(recordingStartTime, forKey: "recordingStartTime")
        coder.encode(recordTypeSegmentIndex, forKey: "recordTypeSegmentIndex")
        coder.encode(labelTypeSegmentIndex, forKey: "labelTypeSegmentIndex")
        coder.encode(tasks as NSArray?, forKey: "tasks")
        coder.encode(sessionName, forKey: "sessionName")
        coder.encode(gripperID, forKey: "gripperID")
        coder.encode(phoneSide, forKey: "phoneSide")
        coder.encode(sidesPresent as NSArray?, forKey: "sidesPresent")
    }
}

class SettingsSyncMessage: NSObject, NSSecureCoding {
    var recordTypeSegmentIndex: Int
    var labelTypeSegmentIndex: Int
    var tasks: [String]
    var sessionName: String
    var gripperID: String
    var errorCorrectionMode: Bool

    init(recordTypeSegmentIndex: Int, labelTypeSegmentIndex: Int, tasks: [String], sessionName: String, gripperID: String, errorCorrectionMode: Bool) {
        self.recordTypeSegmentIndex = recordTypeSegmentIndex
        self.labelTypeSegmentIndex = labelTypeSegmentIndex
        self.tasks = tasks
        self.sessionName = sessionName
        self.gripperID = gripperID
        self.errorCorrectionMode = errorCorrectionMode
    }

    static var supportsSecureCoding: Bool { return true }

    required init?(coder decoder: NSCoder) {
        recordTypeSegmentIndex = decoder.decodeInteger(forKey: "recordTypeSegmentIndex")
        labelTypeSegmentIndex = decoder.decodeInteger(forKey: "labelTypeSegmentIndex")
        if let nsArray = decoder.decodeObject(of: [NSArray.self, NSString.self], forKey: "tasks") as? NSArray {
            tasks = nsArray.compactMap { $0 as? String }
        } else {
            tasks = []
        }
        sessionName = (decoder.decodeObject(of: NSString.self, forKey: "sessionName") as String?) ?? "no-session"
        gripperID = (decoder.decodeObject(of: NSString.self, forKey: "gripperID") as String?) ?? "default"
        errorCorrectionMode = decoder.decodeBool(forKey: "errorCorrectionMode")
    }

    func encode(with coder: NSCoder) {
        coder.encode(recordTypeSegmentIndex, forKey: "recordTypeSegmentIndex")
        coder.encode(labelTypeSegmentIndex, forKey: "labelTypeSegmentIndex")
        coder.encode(tasks as NSArray, forKey: "tasks")
        coder.encode(sessionName as NSString, forKey: "sessionName")
        coder.encode(gripperID as NSString, forKey: "gripperID")
        coder.encode(errorCorrectionMode, forKey: "errorCorrectionMode")
    }
}

enum RecordingMode {
    case single
    case both
    case none
}

class DemonstrationTasksState {
    var currentTaskIndex: Int = 0
    var tasks: [String] = []
    var currentlyRecordingTask: Bool = false
    var taskSegmentationEvents: [TaskSegmentation] = []
    var labelType: DemonstrationLabelType = .None
    
    init() {
        reset()
    }
    
    func reset() {
        currentTaskIndex = 0
        tasks = []
        currentlyRecordingTask = false
        taskSegmentationEvents = []
    }
}

class ViewController: UIViewController, ARSessionDelegate {
    
    @IBOutlet weak var messageLabel: MessageLabel!
    @IBOutlet weak var peerCountLabel: UILabel!
    
    @IBOutlet weak var poseLabel: UILabel!
    @IBOutlet weak var stateLabel: UILabel!
    @IBOutlet weak var recordingModeIcon: UIImageView!
    @IBOutlet weak var leftRightSegmentedControl: UISegmentedControl!
    @IBOutlet weak var recordTypeSegmentedControl: UISegmentedControl!
    @IBOutlet weak var nameSessionButton: UIButton!
    @IBOutlet weak var currentTaskLabel: UILabel!
    @IBOutlet weak var labelTypeSegmentedControl: UISegmentedControl!
    @IBOutlet weak var recordButton: UIButton!
    @IBOutlet weak var tasksButton: UIButton!
    @IBOutlet weak var demosButton: UIButton!
    @IBOutlet weak var micView: UIImageView!
    @IBOutlet weak var setGripperIDButton: UIButton!
    @IBOutlet weak var returnHomeButton: UIButton!
    @IBOutlet weak var settingsButton: UIButton!
    @IBOutlet weak var deleteLastButton: UIButton!
    
    @IBOutlet var arViewHolder: UIView!
    var arView: ARView? // exists only if enabled by user
    @objc var session: ARSession = ARSession()
    
    var multipeerSession: MultipeerSession?
    var multipeerEnabled: Bool = true
    
    var coachingOverlay: ARCoachingOverlayView?
    
    // A dictionary to map MultiPeer IDs to ARSession ID's.
    // This is useful for keeping track of which peer created which ARAnchors.
    var peerSessionIDs = [MCPeerID: String]()
    
    var sessionIDObservation: NSKeyValueObservation?
    
    var configuration: ARWorldTrackingConfiguration?
    
    var prevTimestampThisDevice: Double = 0.0
    var previousRecordingPoseTransform: simd_float4x4? = nil
    var maxRecordingPoseDeltaMetersPerSecond: Double = 0.0
    let maxPoseDeltaMetersPerSecond: Double = 7.0
    var isHostSide: Bool = true
    var phoneSide: PhoneSide = .right
    
    var dataScanner: DataScannerViewController?
    
    // world anchor
    var justAddedWorldOrigin: Bool = false
    var worldAnchorInitialCountdown: Int = 60
    var worldAnchorCountdown: Int = -1
    var worldAnchor: ARAnchor? = nil
    var peerParticipantAnchorFound: Bool = false

    // Non-host periodically requests world frame re-send if not yet aligned.
    // -1 = inactive; >= 0 counts down frames; fires a request when it hits 0 then resets.
    let worldFrameRequestInterval: Int = 300  // ~5 s at 60 fps
    var worldFrameRequestCountdown: Int = -1
    
    // local anchor
    var localAnchorInitialCountdown: Int = 60
    var localAnchorCountdown: Int = -1
    var localWorldAnchor: ARAnchor? = nil
    
    var isRecording: Bool = false
    var recordingName: String = ""
    var recordingStartTime: Date?
    var demonstrationData: DemonstrationData?
    var arKitTimeOffset: Double = 0
    
    var recordingMode: RecordingMode = .none
    
    var useViewer: Bool = false
    
    var entireDemoSpeechRecognizer: SpeechRecognizer?
    var liveSpeechRecognizer: SpeechRecognizer?
    var speechRecognizerEnabled: Bool = true
    var multipeerVoiceHost: Bool = false
    var errorCorrectionMode: Bool = UserDefaults.standard.object(forKey: "errorCorrectionMode") as? Bool ?? false
    var narrationTaskCount: Int = 0
    var currentNarrationText: String = ""
    var narrationCurrentTaskSegmentStart: Int = 0
    var lastNarrationWordArrivalDate: Date? = nil
    
    var tasksState: DemonstrationTasksState = DemonstrationTasksState()
    
    private let gripperIDDefaultsKey = "gripperID"
    private var gripperID: String = "default" {
        didSet {
            UserDefaults.standard.set(gripperID, forKey: gripperIDDefaultsKey)
            setRecordingMode(mode: recordingMode)
        }
    }
    
    var iAmRecordingInitiator = false
    var recordingSidesPresent: [String] = []
    var lastRecordedName: String? = nil
    var pendingPreRecordingResponses: [MCPeerID: (side: Int, ready: Bool, voiceHost: Bool, voiceCommandsEnabled: Bool, reason: String)]? = nil
    var pendingPreRecordingExpectedCount: Int = 0

    var cachedDemoCount: Int = 0
    var cachedCalibCount: Int = 0
    var cachedTotalDemoCount: Int = 0
    var cachedTotalCalibCount: Int = 0
    var cachedPeerDistances: [Float] = []
    private var calibrationGripperIDCache: [String: String] = [:]
    var lastPeerPoseDates: [String: Date] = [:]

    var micInitiallyFound: Bool = false
    var micCurrentlyConnected: Bool = false
    var isFinalizingRecording: Bool = false
    var dismissOnReturn: Bool = false
    
    private var eventInteraction: AVCaptureEventInteraction?
    
    var fps: Double = 0
    
    var mainIntrinsincs: simd_float3x3?
    var ultrawideIntrinsics: simd_float3x3?
    private var arKitFirstFrameDate: Date?
        
    override func viewDidLoad() {
        poseLabel.text = ""
        stateLabel.text = ""
        recordButton.isEnabled = false
        
        // set defaults if not already set
        let defaults = UserDefaults.standard
        var gripperCalibrationRunName = defaults.object(forKey: "gripperCalibrationRunName") as? String
        if gripperCalibrationRunName == nil {
            defaults.set("", forKey: "gripperCalibrationRunName")
        }
        var sessionName = defaults.object(forKey: "sessionName") as? String
        if sessionName == nil || sessionName == "" {
            defaults.set("no-session", forKey: "sessionName")
            sessionName = "no-session"
        }
        // Initialize gripper ID with default if needed
        let savedGripperID = defaults.string(forKey: gripperIDDefaultsKey)
        if let saved = savedGripperID, !saved.isEmpty {
            gripperID = saved
        } else {
            gripperID = "default"
        }
        // Sync gripper calibration to current session: use existing for this session if any, else unset
        let currentSessionName = (defaults.object(forKey: "sessionName") as? String) ?? "no-session"
        do {
            if let calibration = try DemonstrationData.mostRecentGripperCalibrationRunName(forSessionName: currentSessionName) {
                defaults.set(calibration, forKey: "gripperCalibrationRunName")
            } else {
                defaults.set("", forKey: "gripperCalibrationRunName")
            }
        } catch {
            defaults.set("", forKey: "gripperCalibrationRunName")
        }
        var tasks = defaults.object(forKey: "tasks") as? [String]
        if tasks == nil {
            defaults.set([], forKey: "tasks")
        }
        var labelSelectedSegmentID = defaults.object(forKey: "labelSelectedSegmentID") as? Int
        if labelSelectedSegmentID == nil {
            labelSelectedSegmentID = 0
            defaults.set(0, forKey: "labelSelectedSegmentID")
        }
        labelTypeSegmentedControl.selectedSegmentIndex = labelSelectedSegmentID!

        var sideRaw = defaults.object(forKey: "phoneSide") as? Int
        if sideRaw == nil {
            if let oldRight = defaults.object(forKey: "isRight") as? Bool {
                sideRaw = oldRight ? PhoneSide.right.rawValue : PhoneSide.left.rawValue
            } else {
                sideRaw = leftRightSegmentedControl.selectedSegmentIndex
            }
            defaults.set(sideRaw!, forKey: "phoneSide")
        }
        leftRightSegmentedControl.selectedSegmentIndex = sideRaw!
        phoneSide = PhoneSide(rawValue: sideRaw!) ?? .right
        multipeerEnabled = defaults.object(forKey: "multipeerEnabled") as? Bool ?? true
        multipeerVoiceHost = defaults.object(forKey: "multipeerVoiceHost") as? Bool ?? false
        updatePeerUI(multipeerEnabled: multipeerEnabled)
        updateDemoCountLabel()
        
        // setup AR view and session        
        var useViewer = defaults.object(forKey: "useViewer") as? Bool
        if useViewer == nil {
            useViewer = false
            defaults.set(useViewer, forKey: "useViewer")
        }
        self.useViewer = useViewer!
        
        initialSetPreferredMicToHeadset()
        
        // init AR configuration
        configuration = ARWorldTrackingConfiguration()
        
        // record audio
        configuration?.providesAudioData = true
        
        // if using the viewer then initialize an ARView
        if useViewer! {
            arView = ARView(frame: view.bounds)
            arView!.session = session
            arViewHolder.insertSubview(arView!, at: 0)
        }
        
        updateTaskUI()
        
        speechRecognizerEnabled = UserDefaults.standard.object(forKey: "speechRecognizerEnabled") as? Bool ?? true
        
        configureHardwareInteraction()
    }
    
    func initialSetPreferredMicToHeadset() {
        let audioSession = AVAudioSession.sharedInstance()
        
        do {
            try audioSession.setCategory(.record, mode: .measurement, options: .duckOthers)
            try audioSession.setActive(true)

            if let availableInputs = audioSession.availableInputs {
                for input in availableInputs {
                    if input.portType == .headsetMic {
//                        try audioSession.setPreferredInput(input)
                        micInitiallyFound = true
                        micCurrentlyConnected = true
                        messageLabel.displayMessage("Contact mic connected!")
                        onMicStateUpdate()
                        return
                    }
                }
            }
        } catch {
            messageLabel.displayMessage("Error setting headset microphone: \(error.localizedDescription)")
        }
        
        onMicStateUpdate()
    }
    
    private func configureHardwareInteraction() {
        // Create a new capture event interaction with a handler that captures a photo.
        let interaction = AVCaptureEventInteraction { [weak self] event in
            // Capture a photo on "press up" of a hardware button.
            if event.phase == .ended {
                self!.recordButtonPress()
            }
        }
        // Add the interaction to the view controller's view.
        view.addInteraction(interaction)
        eventInteraction = interaction
    }

    override func viewDidAppear(_ animated: Bool) {

        super.viewDidAppear(animated)

        // Clear lastRecordedName if the recording was manually deleted while away (e.g. in the demos interface)
        if let name = lastRecordedName, !DemonstrationData.hasDataType(recordingName: name, demonstrationSaveType: .JSON) {
            lastRecordedName = nil
            updateDeleteLastButton()
        }

        if dismissOnReturn {
            dismissOnReturn = false
            dismiss(animated: false, completion: nil)
            return
        }

        session.delegate = self

        // Turn off ARView's automatically-configured session
        // to create and set up your own configuration.
        arView?.automaticallyConfigureSession = false

        // Enable a collaborative session.
        configuration?.isCollaborationEnabled = true
        
        // Enable realistic reflections.
        configuration?.environmentTexturing = .automatic
        
        // Enable the sceneDepth frame semantics
        if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
            configuration!.frameSemantics.insert(.sceneDepth)
            print("added .sceneDepth from AR configuration")
        } else {
            print("Scene depth is not supported on this device.")
        }

        // Reset session state so the local anchor countdown fires and MultipeerSession
        // is created fresh — handles both first launch and returning from a modal VC.
        initializeSession()

        // Begin the session.
        session.run(configuration!)

        // Start speech recognizer after ARKit has claimed the audio session
        if speechRecognizerEnabled && liveSpeechRecognizer == nil && !micCurrentlyConnected {
            liveSpeechRecognizer = SpeechRecognizer(shouldReportPartialResults: true, callback: narrationCallback)
            liveSpeechRecognizer!.startTranscribingWithExternalAudio()
        }
        
        // Use key-value observation to monitor your ARSession's identifier.
        sessionIDObservation = observe(\.session.identifier, options: [.new]) { object, change in
            print("SessionID changed to: \(change.newValue!)")
            
            // Tell all other peers about your ARSession's changed ID, so
            // that they can keep track of which ARAnchors are yours.
            guard let multipeerSession = self.multipeerSession else { return }
            self.sendARSessionIDTo(peers: multipeerSession.connectedPeers)
            self.computeARKitTimeOffset()
        }
        
        if useViewer {
            coachingOverlay = ARCoachingOverlayView()
            setupCoachingOverlay()
        }
        
        // Prevent the screen from being dimmed to avoid interrupting the AR experience.
        UIApplication.shared.isIdleTimerDisabled = true

        warmUpVideoEncodersIfNeeded()

        computeARKitTimeOffset()
        
        // subscribe to headphone connected events
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(audioRouteChanged),
            name: AVAudioSession.routeChangeNotification,
            object: nil
        )
    }
    
    override func viewWillDisappear(_ animated: Bool) {
        // including this function solves an issue where if this view is closed and then reopened the new session thinks the old session is a peer that it can try to connect to
        super.viewWillDisappear(animated)
        // Tear down multipeer and AR so reopening the view doesn't see the previous session as a "peer"
        sessionIDObservation?.invalidate()
        sessionIDObservation = nil
        multipeerSession?.endSession()
        multipeerSession = nil
        peerSessionIDs.removeAll()
        session.pause()
        UIApplication.shared.isIdleTimerDisabled = false
    }
    
    @objc private func audioRouteChanged(notification: Notification) {
        guard let userInfo = notification.userInfo,
              let reasonValue = userInfo[AVAudioSessionRouteChangeReasonKey] as? UInt,
              let reason = AVAudioSession.RouteChangeReason(rawValue: reasonValue) else {
            return
        }
        
        switch reason {
        case .newDeviceAvailable, .oldDeviceUnavailable:
            checkForHeadsetMic()
        default:
            break
        }
    }
    
    private func checkForHeadsetMic() {
        let session = AVAudioSession.sharedInstance()
        let inputs = session.availableInputs ?? []
        
        for input in inputs {
            if input.portType == .headsetMic {
                do {
//                    try session.setPreferredInput(input)
                    if micInitiallyFound {
                        if !micCurrentlyConnected {
                            messageLabel.displayMessage("🎤 Contact mic connected!")
                        }
                    } else if !micCurrentlyConnected{
                        messageLabel.displayMessage("Found contact mic, resetting the view")
                        dismiss(animated: true)
                    }
                    micCurrentlyConnected = true
                } catch {
                    messageLabel.displayMessage("Failed to set headset mic to preferred input!")
                    micCurrentlyConnected = false
                }
                
                onMicStateUpdate()
                
                return
            }
        }
        if micCurrentlyConnected {
            messageLabel.displayMessage("Contact mic disconnected")
        }
        
        micCurrentlyConnected = false
        onMicStateUpdate()
    }
    
    func onMicStateUpdate() {
        if micInitiallyFound && micCurrentlyConnected {
            self.micView.image = UIImage(systemName: "microphone.fill")
            if speechRecognizerEnabled {
                liveSpeechRecognizer = nil
            }

            // make sure mode isn't narration
            if labelTypeSegmentedControl.selectedSegmentIndex == 1 {
                labelTypeSegmentedControl.selectedSegmentIndex = 0
                labelTypeSegmentedControlUpdated()
            }
            labelTypeSegmentedControl.setEnabled(false, forSegmentAt: 1)
        } else {
            self.micView.image = UIImage(systemName: "microphone.slash.fill")
            labelTypeSegmentedControl.setEnabled(true, forSegmentAt: 1)

            if speechRecognizerEnabled && micInitiallyFound {
                liveSpeechRecognizer = SpeechRecognizer(shouldReportPartialResults: true, callback: narrationCallback)
                liveSpeechRecognizer!.startTranscribingWithExternalAudio()
            }
        }
    }
    
    func computeARKitTimeOffset() {
        // set the ARKit time offset by converting from seconds from boot time to UNIX time
        let uptime = ProcessInfo.processInfo.systemUptime; // Get NSTimeInterval of uptime i.e. the delta: now - bootTime
        let nowTimeIntervalSince1970 = Date().timeIntervalSince1970
        arKitTimeOffset = nowTimeIntervalSince1970 - uptime;
    }
    
    func initializeSession() {
        // global world anchor
        worldAnchorCountdown = worldAnchorInitialCountdown
        justAddedWorldOrigin = false
        if worldAnchor != nil {
            session.remove(anchor: worldAnchor!)
            print("removed world anchor")
            worldAnchor = nil
        }
        
        // local world anchor
        localAnchorCountdown = localAnchorInitialCountdown
        if localWorldAnchor != nil {
            session.remove(anchor: localWorldAnchor!)
            print("removed local world anchor")
            localWorldAnchor = nil
        }
        
        // set recording icon to none
        
        
        // other
        worldFrameRequestCountdown = -1
        peerParticipantAnchorFound = false
        loggedFirstCollabSend = false
        loggedFirstCollabReceive = false
        lastPeerPoseDates = [:]
        recomputeHostStatus()
        demonstrationData = nil
        setRecordingState(false)
        DispatchQueue.main.async { if self.multipeerEnabled { self.peerCountLabel.text = "Peers: 0" } }
        
//        resetSocket()
        setRecordingMode(mode: .none)
    }
    
    func updatePeerUI(multipeerEnabled: Bool) {
        if multipeerEnabled {
            peerCountLabel.text = "Peers: 0"
            recordingModeIcon.image = UIImage(systemName: "xmark")
        } else {
            peerCountLabel.text = "Disabled"
            recordingModeIcon.image = UIImage(systemName: "person.fill.xmark")
        }
    }

    func setRecordingControlsState(isRecording: Bool) {

        recordTypeSegmentedControl.isEnabled = !isRecording
        labelTypeSegmentedControl.isEnabled = !isRecording
        leftRightSegmentedControl.isEnabled = !isRecording
        demosButton.isEnabled = !isRecording
        nameSessionButton.isEnabled = !isRecording
        setGripperIDButton.isEnabled = !isRecording
        returnHomeButton.isEnabled = !isRecording
        settingsButton.isEnabled = !isRecording
        deleteLastButton.isEnabled = !isRecording

        updateDeleteLastButton()
        updateTaskUI()
    }

    func updateDeleteLastButton() {
        deleteLastButton.isEnabled = !isRecording && !isFinalizingRecording && lastRecordedName != nil
    }
    
    func setRecordingMode(mode: RecordingMode) {
        self.recordingMode = mode
        DispatchQueue.main.async {
            var collaborationSatisfied = false

            if self.multipeerEnabled {
                switch mode {
                case .none:
                    self.recordingModeIcon.image = UIImage(systemName: "xmark")
                    collaborationSatisfied = false
                case .single:
                    self.recordingModeIcon.image = UIImage(systemName: "person.fill")
                    // Block recording if a peer is connected but world frame not yet aligned.
                    let hasPeer = !(self.multipeerSession?.connectedPeers.isEmpty ?? true)
                    collaborationSatisfied = !hasPeer
                case .both:
                    let connectedCount = self.multipeerSession?.connectedPeers.count ?? 1
                    let personIcon = connectedCount >= 2 ? "person.3.fill" : "person.2.fill"
                    self.recordingModeIcon.image = UIImage(systemName: personIcon)
                    collaborationSatisfied = true
                }
            } else {
                collaborationSatisfied = true
            }

            
            let unmetConditions = self.unmetRecordingConditions()
            let localSatisfied = unmetConditions == nil
            self.recordButton.isEnabled = (collaborationSatisfied && localSatisfied) || self.isRecording

            if !self.isRecording {
                let defaults = UserDefaults.standard
                let sessionName = (defaults.object(forKey: "sessionName") as? String) ?? "no-session"
                let sessionNameSatisfied = sessionName != "no-session"
                let peerCount = self.multipeerSession?.connectedPeers.count ?? 0
                let peerText = peerCount == 0 ? " (no peers)" : " (\(peerCount) \(peerCount == 1 ? "peer" : "peers"))"
                let isErrorCorrectionDemo = self.errorCorrectionMode && self.getDemonstrationType() == .Demonstration
                let recordingLabel = isErrorCorrectionDemo ? "Start Error Correction" : "Start Recording"
                var buttonText = sessionNameSatisfied ? "\(recordingLabel)\(peerText)\nSession: \(sessionName), Gripper: \(self.gripperID), Side: \(self.phoneSide.recordingNameComponent)" : "\(recordingLabel)\(peerText)"
                self.recordButton.backgroundColor = .systemGray6
                if !self.recordButton.isEnabled {
                    if !collaborationSatisfied {
                        let hasPeer = !(self.multipeerSession?.connectedPeers.isEmpty ?? true)
                        buttonText = hasPeer ? "Point phones in the same direction to align and slowly move both" : "ARKit still initializing"
                    } else if let mismatch = unmetConditions {
                        buttonText = mismatch
                    }
                }

                if isErrorCorrectionDemo {
                    let font = self.recordButton.titleLabel?.font ?? UIFont.systemFont(ofSize: UIFont.buttonFontSize)
                    let paragraphStyle = NSMutableParagraphStyle()
                    paragraphStyle.alignment = .center
                    let redAttrs: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: UIColor.red, .paragraphStyle: paragraphStyle]
                    self.recordButton.setAttributedTitle(NSAttributedString(string: buttonText, attributes: redAttrs), for: .normal)
                } else {
                    self.recordButton.setTitleColor(.systemBlue, for: .normal)
                    self.recordButton.setTitleKeepingFont(buttonText)
                }
            } else {
                // When recording, use attributed title with white text so it isn't overridden by tint (setTitleKeepingFont uses attributed string without color).
                let font = self.recordButton.titleLabel?.font ?? UIFont.systemFont(ofSize: UIFont.buttonFontSize)
                let whiteAttrs: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: UIColor.white]
                if self.shouldRecordButtonBeNextTaskButton() {
                    // recording button should become next task button if we are on all tasks except the last task or if we are on the last task, but haven't confirmed it yet
                    self.recordButton.setAttributedTitle(NSAttributedString(string: "Next Task", attributes: whiteAttrs), for: .normal)
                    self.recordButton.setTitleColor(.white, for: .normal)
                    self.recordButton.backgroundColor = .blue
                } else {
                    // recording button should be stop button
                    self.recordButton.setAttributedTitle(NSAttributedString(string: "Stop Recording", attributes: whiteAttrs), for: .normal)
                    self.recordButton.setTitleColor(.white, for: .normal)
                    self.recordButton.backgroundColor = .red
                }
            }
        }
    }

    func recomputeHostStatus() {
        let oldValue = isHostSide
        if peerSessionIDs.isEmpty {
            isHostSide = true
            if oldValue != isHostSide {
                messageLabel.displayMessage("Host status reset (no peers)")
            }
        } else {
            // The phone with the lexicographically smallest ARKit session UUID is the host.
            // All devices compute this independently and reach the same result.
            let myID = session.identifier.uuidString
            isHostSide = peerSessionIDs.values.allSatisfy { myID < $0 }
            // Always log when peers are present — the host phone starts as true by default
            // so oldValue == isHostSide on first election and the change guard would miss it.
            let role = isHostSide ? "host" : "not host"
            print("Now this phone has isHostSide: \(isHostSide)")
            messageLabel.displayMessage("Role determined: \(role) (my UUID: \(myID.prefix(8)))")
        }
    }
    
    func session(_ session: ARSession, didOutputAudioSampleBuffer audioSampleBuffer: CMSampleBuffer) {
        if isRecording && micCurrentlyConnected && micInitiallyFound {
            demonstrationData?.logAudio(audioSampleBuffer: audioSampleBuffer)
        }
        if let liveSpeechRecognizer {
            Task { await liveSpeechRecognizer.appendAudioSampleBuffer(audioSampleBuffer) }
        }
        if let entireDemoSpeechRecognizer {
            Task { await entireDemoSpeechRecognizer.appendAudioSampleBuffer(audioSampleBuffer) }
        }
    }
        
    func addLocalWorldAnchor() {
        localWorldAnchor = ARAnchor(name: "local world frame", transform: matrix_identity_float4x4)
        session.add(anchor: localWorldAnchor!)
        print("Added local world frame")
        messageLabel.displayMessage("Added local world frame anchor")

        // Start looking for other players via MultiPeerConnectivity.
        // Guard against recreating the session if already running — that would disconnect any
        // currently connected peers and tear down the ARKit collaborative session.
        guard multipeerSession == nil else { return }
        guard multipeerEnabled else { return }
        multipeerSession = MultipeerSession(receivedDataHandler: receivedData, peerJoinedHandler:
                                            peerJoined, peerLeftHandler: peerLeft, peerDiscoveredHandler: peerDiscovered)
        messageLabel.displayMessage("Started MultipeerConnectivity — looking for peers")
    }
    
    func addWorldAnchor() {
        worldAnchor = ARAnchor(name: "world frame", transform: matrix_identity_float4x4)
        session.add(anchor: worldAnchor!)
        print("Added world anchor for peer")
        messageLabel.displayMessage("Sent world coordinate frame to peers")
    }

    @IBAction func viewDemosButtonPress(_ sender: Any) {
        let storyboard = UIStoryboard(name: "Main", bundle: nil)
        let secondVC = storyboard.instantiateViewController(identifier: "DemonstrationsViewController") as! DemonstrationsViewController

        secondVC.onDismiss = { [weak self] in
            self?.updateDemoCountLabel()
        }

        secondVC.onExportRequested = { [weak self, weak secondVC] in
            secondVC?.dismiss(animated: true) {
                guard let self = self else { return }
                let exportVC = ExportViewController()
                exportVC.modalPresentationStyle = .fullScreen
                self.present(exportVC, animated: true)
            }
        }

        if #available(iOS 15.0, *) {
            if let sheet = secondVC.sheetPresentationController {
                sheet.detents = [.large()]
                sheet.prefersGrabberVisible = true
            }
        }

        present(secondVC, animated: true, completion: nil)
    }
    
    @IBAction func viewTasksButtonPress(_ sender: Any) {
        let storyboard = UIStoryboard(name: "Main", bundle: nil)
        let secondVC = storyboard.instantiateViewController(identifier: "TasksViewController") as TasksViewController

        secondVC.onExit = { [weak self] in
            self?.updateTaskUI()
        }

        if #available(iOS 15.0, *) {
            if let sheet = secondVC.sheetPresentationController {
                sheet.detents = [.large()]
                sheet.prefersGrabberVisible = true
            }
        }

        present(secondVC, animated: true, completion: nil)
    }
    
    enum MyError: Error {
        case error
    }
    
    func shouldRecordButtonBeNextTaskButton() -> Bool {
        // recording button should become next task button if we are on all tasks except the last task or if we are on the last task, but haven't confirmed it yet
        return isRecording && getDemonstrationType() == .Demonstration && tasksState.labelType == .Predefined && (tasksState.currentTaskIndex != tasksState.tasks.count - 1 || !tasksState.currentlyRecordingTask)
    }
    
    @IBAction func recordButtonPress(_ sender: UIButton) {
        recordButtonPress()
    }
    
    func recordButtonPress() {
        // this can be called either from pressing the volume button or by pressing the record button on the screen
        if !recordButton.isEnabled {
            return
        }
        
        if shouldRecordButtonBeNextTaskButton() {
            nextTaskButtonPress()
            if recordingMode == .both, let nextTaskData = "NextTask".data(using: .utf8) {
                multipeerSession?.sendToAllPeers(nextTaskData, reliably: true)
            }
        } else if !isRecording && recordingMode == .both {
            initiatePreRecordingCheck()
        } else {
            startStopRecording()
        }
    }

    func initiatePreRecordingCheck() {
        let hasPeers = multipeerSession?.connectedPeers.isEmpty == false
        let storageGB = availableStorageGB()
        if storageGB < 1.0 {
            let storageStr = String(format: "%.2f", storageGB)
            let prefix = hasPeers ? "The \(phoneSide.recordingNameComponent) phone does" : "This phone does"
            let alert = UIAlertController(
                title: "Recording Failed — Insufficient Storage",
                message: "\(prefix) not have enough free storage to start recording (\(storageStr) GB free, need at least 1 GB). Free up space and try again.",
                preferredStyle: .alert
            )
            alert.addAction(UIAlertAction(title: "OK", style: .default))
            present(alert, animated: true)
            return
        }

        guard let mp = multipeerSession, !mp.connectedPeers.isEmpty else {
            startStopRecording()
            return
        }
        sendSettingsSyncToPeers()
        pendingPreRecordingResponses = [:]
        pendingPreRecordingExpectedCount = mp.connectedPeers.count
        if let data = "PreRecordingCheck".data(using: .utf8) {
            mp.sendToAllPeers(data, reliably: true)
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) { [weak self] in
            self?.handlePreRecordingCheckTimeout()
        }
    }

    func handlePreRecordingCheckTimeout() {
        guard pendingPreRecordingResponses != nil else { return }
        pendingPreRecordingResponses = nil
        let alert = UIAlertController(
            title: "Recording Failed",
            message: "Could not get status from all peers in time. Check that all devices are connected and try again.",
            preferredStyle: .alert
        )
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        present(alert, animated: true)
    }

    func evaluatePreRecordingStatusAndProceed() {
        guard let responses = pendingPreRecordingResponses else { return }
        pendingPreRecordingResponses = nil

        // Check all peers are ready
        if let notReady = responses.first(where: { !$0.value.ready }) {
            let reason = notReady.value.reason.isEmpty ? "Device is not ready to record." : notReady.value.reason
            let sideStr = PhoneSide(rawValue: notReady.value.side)?.recordingNameComponent ?? "peer"
            let alert = UIAlertController(
                title: "Recording Failed — Peer Not Ready",
                message: "The \(sideStr) phone cannot start recording: \(reason).",
                preferredStyle: .alert
            )
            alert.addAction(UIAlertAction(title: "OK", style: .default))
            present(alert, animated: true)
            return
        }

        // At most one device may have voice commands enabled
        let voiceCommandsCount = (speechRecognizerEnabled ? 1 : 0) + responses.values.filter { $0.voiceCommandsEnabled }.count
        if voiceCommandsCount > 1 {
            let alert = UIAlertController(title: "Recording Aborted — Voice Commands Conflict", message: "Multiple devices (\(voiceCommandsCount)) have Voice Commands enabled. At most one device should have it enabled in Settings.", preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "OK", style: .default))
            present(alert, animated: true)
            return
        }

        // In narration mode, exactly one device must be the voice host
        if tasksState.labelType == .Narration {
            var voiceHostCount = multipeerVoiceHost ? 1 : 0
            voiceHostCount += responses.values.filter { $0.voiceHost }.count
            if voiceHostCount != 1 {
                let message = voiceHostCount == 0
                    ? "No device has Multipeer Voice Host enabled. Exactly one device must have it enabled in Settings for narration mode."
                    : "Multiple devices have Multipeer Voice Host enabled (\(voiceHostCount)). Exactly one device must have it enabled in Settings for narration mode."
                let alert = UIAlertController(title: "Recording Aborted — Voice Host Conflict", message: message, preferredStyle: .alert)
                alert.addAction(UIAlertAction(title: "OK", style: .default))
                present(alert, animated: true)
                return
            }
        }

        // Check all sides are unique
        var allSides = [phoneSide.rawValue]
        allSides.append(contentsOf: responses.values.map { $0.side })

        if Set(allSides).count != allSides.count {
            let conflictName = PhoneSide(rawValue: allSides.first { raw in allSides.filter { $0 == raw }.count > 1 }!)?.recordingNameComponent ?? "unknown"
            let alert = UIAlertController(
                title: "Recording Aborted — Side Conflict",
                message: "Multiple devices are set to the same side (\(conflictName)). Each device must have a different side selected. Update the side on each device and try recording again.",
                preferredStyle: .alert
            )
            alert.addAction(UIAlertAction(title: "OK", style: .default))
            present(alert, animated: true)
            return
        }

        recordingSidesPresent = allSides.compactMap { PhoneSide(rawValue: $0)?.recordingNameComponent }
        startStopRecording()
    }

    func startStopRecording() {
        // if a recording hasn't finish saving yet then don't allow this button to be pressed
        if isFinalizingRecording {
            return
        }
        
        if !isRecording {
            // about to start recording
            let storageGB = availableStorageGB()
            if storageGB < 1.0 {
                let alert = UIAlertController(
                    title: "Recording Failed — Insufficient Storage",
                    message: "This phone does not have enough free storage to start recording (\(String(format: "%.2f", storageGB)) GB free, need at least 1 GB). Free up space and try again.",
                    preferredStyle: .alert
                )
                alert.addAction(UIAlertAction(title: "OK", style: .default))
                present(alert, animated: true)
                return
            }
            iAmRecordingInitiator = true
            recordingStartTime = Date()
            recordingName = DateManager.getISOFormatter().string(from: recordingStartTime!)
            if recordingSidesPresent.isEmpty {
                recordingSidesPresent = [phoneSide.recordingNameComponent]
            }
            
            var number = String()
            for _ in 1...5 {
               number += "\(Int.random(in: 1...9))"
            }
            
            recordingName += "_\(number)"
        }
        
        setRecordingState(!isRecording)
        
        if multipeerSession != nil {
            let multipeerSession = multipeerSession!
            if !multipeerSession.connectedPeers.isEmpty {
                let message = isRecording ? "start" : "stop"
//
//                let commandData = "Recording:\(message)".data(using: .utf8)!
//                multipeerSession.sendToAllPeers(commandData, reliably: true)
                                
                let defaults = UserDefaults.standard
                let currentSessionName = (defaults.object(forKey: "sessionName") as? String) ?? "no-session"
                let currentTasks = (defaults.object(forKey: "tasks") as? [String]) ?? []
                let data = RecordingMessage(
                    startRecording: isRecording,
                    recordingName: isRecording ? NSString(string: recordingName) : nil,
                    recordingStartTime: isRecording ? recordingStartTime as NSDate? : nil,
                    recordTypeSegmentIndex: isRecording ? NSNumber(value: recordTypeSegmentedControl.selectedSegmentIndex) : nil,
                    labelTypeSegmentIndex: isRecording ? NSNumber(value: labelTypeSegmentedControl.selectedSegmentIndex) : nil,
                    tasks: isRecording ? currentTasks : nil,
                    sessionName: isRecording ? NSString(string: currentSessionName) : nil,
                    gripperID: isRecording ? NSString(string: gripperID) : nil,
                    phoneSide: isRecording ? NSNumber(value: phoneSide.rawValue) : nil,
                    sidesPresent: isRecording ? recordingSidesPresent : nil
                )
                if !isRecording { recordingSidesPresent = [] }
                
                guard let encodedData = try? NSKeyedArchiver.archivedData(withRootObject: data, requiringSecureCoding: true)
                else { fatalError("Unexpectedly failed to encode recording message.") }
                // Use reliable mode if the data is critical, and unreliable mode if the data is optional.
                multipeerSession.sendToAllPeers(encodedData, reliably: true)
                
                print("sent recording message")
                print("Sent recording command to peer: \(message)")
            }
        }
    }
    
    func fpsDropAlert(side: String? = nil) {
        let sidePrefix = side.map { "The \($0) phone's recording was abandoned" } ?? "Current recording was abandoned"
        let alertController = UIAlertController(title: "Warning: Recording discarded", message: "\(sidePrefix) due to FPS dropping below 30! This can either be due to overheating which causes the phone to drop to 30fps or if the app was interrupted for some reason. Can also occur for the first demo collected after the app is restarted, in which case just try again.", preferredStyle: .alert)
        
        let okAction = UIAlertAction(title: "Dismiss", style: .default) { _ in
            alertController.dismiss(animated: true, completion: nil)
            // do nothing
        }
        alertController.addAction(okAction)
        self.present(alertController, animated: true, completion: nil)
    }
    
    // Discards the current recording locally without sending any peer messages.
    // Use this instead of abandonCurrentRecording() in abort flows so we don't
    // generate extra stop messages that could interfere with the abort sequence.
    private func discardCurrentRecordingLocally() {
        guard isRecording else { return }
        let nameToDiscard = demonstrationData?.recordingName ?? recordingName
        if !nameToDiscard.isEmpty {
            do { try DemonstrationData.discard(recordingName: nameToDiscard) }
            catch { print("Failed to discard recording \(nameToDiscard): \(error)") }
        }
        demonstrationData = nil
        setRecordingState(false)
    }

    // Returns a human-readable description of any settings that differ between
    // the received RecordingMessage and this device's current state, or nil if
    // everything matches (or the message pre-dates settings embedding).
    private func recordingSettingsMismatch(_ message: RecordingMessage) -> String? {
        guard let recvRecordType = message.recordTypeSegmentIndex?.intValue,
              let recvLabelType  = message.labelTypeSegmentIndex?.intValue,
              let recvTasks      = message.tasks,
              let recvSessionName = message.sessionName as String? else {
            return nil  // Old message format without settings — skip check
        }
        let defaults = UserDefaults.standard
        let localTasks       = (defaults.object(forKey: "tasks") as? [String]) ?? []
        let localSessionName = (defaults.object(forKey: "sessionName") as? String) ?? "no-session"
        var mismatches: [String] = []
        if recvRecordType   != recordTypeSegmentedControl.selectedSegmentIndex  { mismatches.append("demonstration type") }
        if recvLabelType    != labelTypeSegmentedControl.selectedSegmentIndex    { mismatches.append("label type") }
        if recvTasks        != localTasks                                        { mismatches.append("task list") }
        if recvSessionName  != localSessionName                                  { mismatches.append("session name") }
        if let recvGripperID = message.gripperID as String?, recvGripperID != gripperID { mismatches.append("gripper ID") }
        return mismatches.isEmpty ? nil : mismatches.joined(separator: ", ")
    }

    private func availableStorageGB() -> Double {
        if let attrs = try? FileManager.default.attributesOfFileSystem(forPath: NSHomeDirectory()),
           let free = attrs[.systemFreeSize] as? Int64 {
            return Double(free) / 1_073_741_824
        }
        return Double.infinity
    }

    private func cachedGripperIDForCalibration(_ name: String) -> String {
        if let cached = calibrationGripperIDCache[name] { return cached }
        let id = (try? DemonstrationData.gripperIDForCalibration(recordingName: name)) ?? "default"
        calibrationGripperIDCache[name] = id
        return id
    }

    private func unmetRecordingConditions() -> String? {
        let defaults = UserDefaults.standard
        let sessionName = (defaults.object(forKey: "sessionName") as? String) ?? "no-session"
        var mismatches: [String] = []

        if sessionName == "no-session" { mismatches.append("session name not set") }

        if getDemonstrationType() == .Demonstration {
            let gripperCalibrationRunName = defaults.object(forKey: "gripperCalibrationRunName") as? String ?? ""
            if phoneSide != .head {
                let sideComponent = phoneSide.recordingNameComponent
                if gripperCalibrationRunName.isEmpty {
                    mismatches.append("gripper calibration missing")
                } else if !gripperCalibrationRunName.contains("_grippercalibration_\(sideComponent)") {
                    mismatches.append("gripper calibration is for wrong side (need \(sideComponent))")
                } else if cachedGripperIDForCalibration(gripperCalibrationRunName) != gripperID {
                    mismatches.append("Session name matches but gripper ID doesn't. Please record another gripper calibration for this new gripper.")
                }
            }
            if tasksState.labelType == .Predefined && tasksState.tasks.isEmpty {
                mismatches.append("task list empty")
            }
        }

        if let maxDist = cachedPeerDistances.max(), maxDist > 1.0 {
            mismatches.append("peer too far (\(String(format: "%.2f", maxDist))m, must be ≤1m)")
        }
        if multipeerEnabled {
            let connectedSessionIDs = Array(peerSessionIDs.values)
            if !connectedSessionIDs.isEmpty {
                let now = Date()
                let stalePeers = connectedSessionIDs.filter { sid in
                    lastPeerPoseDates[sid].map { now.timeIntervalSince($0) > 1.0 } ?? true
                }
                if !stalePeers.isEmpty {
                    mismatches.append("missing pose from \(stalePeers.count) peer\(stalePeers.count == 1 ? "" : "s")")
                }
            }
        }
        if fps <= 50 { mismatches.append("FPS too low") }
        if isFinalizingRecording { mismatches.append("still saving previous recording") }

        return mismatches.isEmpty ? nil : mismatches.joined(separator: ", ")
    }

    private func hasSideConflict(_ message: RecordingMessage) -> Bool {
        guard let recvSide = message.phoneSide?.intValue else { return false }
        return recvSide == phoneSide.rawValue
    }

    private func showSettingsMismatchAlert(detail: String? = nil) {
        var message = "The recording was aborted because the settings on the two devices do not match. Set the settings on one device and use the \"Peer Sync\" button to push them to the other device, then try recording again."
        if let detail = detail {
            message += "\n\nMismatched settings: \(detail)."
        }
        let alert = UIAlertController(title: "Recording Aborted — Settings Mismatch", message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        present(alert, animated: true)
    }

    private func showSideConflictAlert() {
        let alert = UIAlertController(
            title: "Recording Aborted — Side Conflict",
            message: "Both devices are set to the same side (\(phoneSide.recordingNameComponent)). Each device must have a different side selected. Update the side on each device and try recording again.",
            preferredStyle: .alert
        )
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        present(alert, animated: true)
    }

    func abandonCurrentRecording() {
        if isRecording {
            print("Abandoning in progress recording!")
            discardCurrentRecordingLocally()
            if let abortData = "AbortRecording:FPSDrop:\(phoneSide.recordingNameComponent)".data(using: .utf8) {
                multipeerSession?.sendToAllPeers(abortData, reliably: true)
            }
        }
    }

    func abandonCurrentRecordingWithPoseDelta(metersPerSecond: Double) {
        if isRecording {
            let mpsStr = String(format: "%.2f", metersPerSecond)
            print("Abandoning in progress recording due to pose delta \(mpsStr) m/s!")
            discardCurrentRecordingLocally()
            if let abortData = "AbortRecording:PoseDelta:\(phoneSide.recordingNameComponent):\(mpsStr)".data(using: .utf8) {
                multipeerSession?.sendToAllPeers(abortData, reliably: true)
            }
        }
    }

    func poseDeltaAlert(side: String? = nil, metersPerSecond: Double) {
        let mpsStr = String(format: "%.2f", metersPerSecond)
        let sidePrefix = side.map { "The \($0) phone's recording was abandoned" } ?? "Current recording was abandoned"
        let alertController = UIAlertController(
            title: "Warning: Recording discarded",
            message: "\(sidePrefix) due to a pose jump of \(mpsStr) m/s exceeding the \(String(format: "%.1f", maxPoseDeltaMetersPerSecond)) m/s threshold. This typically indicates a SLAM tracking failure.",
            preferredStyle: .alert
        )
        alertController.addAction(UIAlertAction(title: "Dismiss", style: .default) { _ in
            alertController.dismiss(animated: true, completion: nil)
        })
        self.present(alertController, animated: true, completion: nil)
    }
    
    func getDemonstrationType() -> DemonstrationType {
        switch recordTypeSegmentedControl.selectedSegmentIndex {
        case 0: return .GripperCalibration
        case 1: return .Demonstration
        default:
            return .Demonstration
        }
    }
    
    func setRecordingState(_ newIsRecording: Bool) {
        // if newIsRecording, expects that `recordingName` has already been set
        let wasRecording = isRecording
        isRecording = newIsRecording
        if !isRecording {
            iAmRecordingInitiator = false
            previousRecordingPoseTransform = nil
        } else {
            maxRecordingPoseDeltaMetersPerSecond = 0.0
        }
        if isRecording {
            // recording started
            // recompute ARkit time offset in case it got messed up
            computeARKitTimeOffset()
            
            // determine the recording name
            var recordingName = "\(recordingName)".replacingOccurrences(of: ":", with: "-")
            
            // add session name to recording name
            let defaults = UserDefaults.standard
            var sessionName = (defaults.object(forKey: "sessionName") as? String)!
            recordingName += "_\(sessionName)"
            
            // add demonstration type to recording name
            if getDemonstrationType() == .GripperCalibration {
                recordingName += "_grippercalibration"
            } else {
                recordingName += "_demonstration"
            }
            
            // add side to recording name
            recordingName += "_\(phoneSide.recordingNameComponent)"
            
            // create the demonstration data
            let gripperCalibrationRunName = defaults.object(forKey: "gripperCalibrationRunName") as? String
            
            demonstrationData = DemonstrationData(recordingName: recordingName, side: phoneSide.recordingNameComponent, recordingStartTime: recordingStartTime!, demonstrationType: getDemonstrationType(), gripperCalibrationRunName: gripperCalibrationRunName!, sessionName: sessionName, gripperID: gripperID, labelType: tasksState.labelType, isVoiceHost: multipeerVoiceHost, sidesPresent: recordingSidesPresent, mainCameraIntrinsics: mainIntrinsincs!, ultrawideCameraIntrinsics: ultrawideIntrinsics!)
            demonstrationData?.isErrorCorrection = errorCorrectionMode && getDemonstrationType() == .Demonstration

            // start audio transcription
            if getDemonstrationType() == .Demonstration && demonstrationData!.labelType == .Narration {
                if !micCurrentlyConnected {
                    liveSpeechRecognizer = nil
                    entireDemoSpeechRecognizer = SpeechRecognizer(shouldReportPartialResults: true, callback: narrationCallback)
                    entireDemoSpeechRecognizer!.startTranscribingWithExternalAudio()
                }
            }
            
            tasksState.reset()
            narrationTaskCount = 0
            currentNarrationText = ""
            narrationCurrentTaskSegmentStart = 0
            lastNarrationWordArrivalDate = nil

            setRecordingControlsState(isRecording: true)
            
            // if this is a predefined demonstration, then see if we should start right away or confirm first
            if getDemonstrationType() == .Demonstration && demonstrationData!.labelType == .Predefined {
                if tasksState.tasks[0] == "CONFIRM" {
                    tasksState.currentTaskIndex += 1
                } else {
                    markTaskStart(time: Date())
                }
            }
        } else if wasRecording {
            // recording ended

            isFinalizingRecording = true

            if let demonstrationData = demonstrationData {
                Task { // have to do this processing aysnc because we need to wait until transcription finishes if present
                    // stop audio recording
                    var speechResult: SFSpeechRecognitionResult?
                    var speechStartTime: Date?
                    if getDemonstrationType() == .Demonstration && demonstrationData.labelType == .Narration {
                        if let entireDemoSpeechRecognizer = entireDemoSpeechRecognizer {
                            await entireDemoSpeechRecognizer.finishTranscribing()
                            if entireDemoSpeechRecognizer.transcriptionSuccessful {
                                speechResult = entireDemoSpeechRecognizer.speechRecognitionResult
                                speechStartTime = await entireDemoSpeechRecognizer.startTranscriptionTimestamp
                            } else {
                                print("Transcription not successful or no speech detected")
                            }
                        }
                    }

                    // if task is in progress, mark it as done
                    if demonstrationData.labelType == .Narration {
                        markTaskEnd(time: Date())
                    }
                    if tasksState.currentlyRecordingTask {
                        markTaskEnd(time: Date(), enableAutoStep: false)
                    }

                    // save the recording to disk
                    do {
                        // set recording name
                        let recordingName = demonstrationData.recordingName
                        if getDemonstrationType() == .GripperCalibration {
                            let defaults = UserDefaults.standard
                            defaults.set(recordingName, forKey: "gripperCalibrationRunName")
                            self.recordTypeSegmentedControl.selectedSegmentIndex = 1  // switch to Demonstration mode
                        }

                        demonstrationData.setFinalData(speechRecognitionResult: speechResult, transcriptionStartTime: speechStartTime, taskSegmentationEvents: tasksState.taskSegmentationEvents)
                        try demonstrationData.saveLocally()
                    } catch RecordingError.ultrawideNotYetInitialized {
                        let message = "FAILURE: recording too short so no ultrawide frames were captured... abandoning recording"
                        messageLabel.displayMessage(message)
                    } catch {
                        let message = "FAILURE: Failed to save demo data!"
                        messageLabel.displayMessage(message)
                    }

                    // restart live recognizer only after the recording is fully saved
                    if demonstrationData.labelType == .Narration && speechRecognizerEnabled && !micCurrentlyConnected {
                        liveSpeechRecognizer = SpeechRecognizer(shouldReportPartialResults: true, callback: narrationCallback)
                        liveSpeechRecognizer!.startTranscribingWithExternalAudio()
                    }

                    self.lastRecordedName = demonstrationData.recordingName
                    self.demonstrationData = nil
                    self.isFinalizingRecording = false
                    self.setRecordingControlsState(isRecording: false)
                    self.updateDemoCountLabel()
                }
            } else {
                self.setRecordingControlsState(isRecording: false)
                self.isFinalizingRecording = false
            }
        }
        updateTaskUI()
    }

    func updateDemoCountLabel() {
        let defaults = UserDefaults.standard
        let sessionName = (defaults.object(forKey: "sessionName") as? String) ?? "no-session"
        DispatchQueue.global(qos: .background).async {
            let all = (try? DemonstrationData.listDemonstrations()) ?? []
            let demoCount = all.filter { $0.contains("_demonstration_") && $0.contains("_\(sessionName)_") }.count
            let calibCount = all.filter { $0.contains("_grippercalibration_") && $0.contains("_\(sessionName)_") }.count
            let totalDemoCount = all.filter { $0.contains("_demonstration_") }.count
            let totalCalibCount = all.filter { $0.contains("_grippercalibration_") }.count
            DispatchQueue.main.async {
                self.cachedDemoCount = demoCount
                self.cachedCalibCount = calibCount
                self.cachedTotalDemoCount = totalDemoCount
                self.cachedTotalCalibCount = totalCalibCount
                self.updateDeleteLastButton()
                self.setRecordingMode(mode: self.recordingMode)
            }
        }
    }
    
    func updateTaskUI() {
        // tasks buttons
        tasksButton.isEnabled = !self.isRecording && recordTypeSegmentedControl.selectedSegmentIndex == 1
        switch labelTypeSegmentedControl.selectedSegmentIndex {
        case 0:
            tasksState.labelType = .None
            tasksButton.isEnabled = false
            break
        case 1:
            tasksState.labelType = .Narration
            tasksButton.isEnabled = false
            break
        case 2:
            tasksState.labelType = .Predefined
            break
        default:
            // invalid
            break
        }
        
        // tasks from task list UI
        tasksState.tasks = (UserDefaults.standard.object(forKey: "tasks") as? [String])!
        
        labelTypeSegmentedControl.isEnabled = getDemonstrationType() == .Demonstration && !isRecording
        
        // text above record button
        if isRecording {
            if getDemonstrationType()  == .Demonstration {
                guard let demonstrationData else { return }
                switch demonstrationData.labelType {
                case .None:
                    currentTaskLabel.text = "Not collecting task labels"
                case .Narration:
                    let doneStr = narrationTaskCount > 0 ? "Tasks done: \(narrationTaskCount)\n" : ""
                    if currentNarrationText.isEmpty {
                        currentTaskLabel.text = "\(doneStr)Waiting for task label..."
                    } else {
                        currentTaskLabel.text = "\(doneStr)Current task: \(currentNarrationText)"
                    }
                case .Predefined:
                    if tasksState.tasks.count == 0 {
                        currentTaskLabel.text = "No task specified"
                    } else {
                        let taskName = tasksState.tasks[tasksState.currentTaskIndex]
                        if tasksState.currentlyRecordingTask {
                            currentTaskLabel.text = "\(taskName) (Recording)"
                        } else {
                            currentTaskLabel.text = "\(taskName) (Confirm?)"
                        }
                    }
                }
            } else if getDemonstrationType() == .GripperCalibration {
                currentTaskLabel.text = "Start recording and slowly fully close and fully open the gripper five times, then stop recording."
            } else {
                currentTaskLabel.text = ""
            }
        } else {
            if getDemonstrationType() == .Demonstration {
                switch tasksState.labelType {
                case .None:
                    currentTaskLabel.text = "Not collecting task labels"
                case .Narration:
                    currentTaskLabel.text = "Narration Mode: say your task name, then execute the task, then say next task name and repeat. The previous task will be marked as finished when the next task is narrated or when you say \"done\""
                case .Predefined:
                    // recording not started, so list all the tasks
                    if tasksState.tasks.count == 0 {
                        currentTaskLabel.text = "No tasks specified, use the \"Edit task list\" button to specify the series of tasks"
                    } else {
                        currentTaskLabel.text = tasksState.tasks.joined(separator: " -> ")
                    }
                }
            } else if getDemonstrationType() == .GripperCalibration {
                currentTaskLabel.text = "Start recording and slowly fully close and fully open the gripper five times, then stop recording."
            } else {
                currentTaskLabel.text = ""
            }
        }
    }

    @IBAction func leftRightSegmentedControlValueChanged(_ sender: Any) {
        phoneSide = PhoneSide(rawValue: leftRightSegmentedControl.selectedSegmentIndex) ?? .right
        UserDefaults.standard.set(phoneSide.rawValue, forKey: "phoneSide")
        recomputeHostStatus()
    }
    
    @IBAction func recordTypeSegmentedControlValueChanged(_ sender: Any) {
        updateTaskUI()
    }
    
    func nextTaskButtonPress() {
        assert(isRecording)
        switch demonstrationData!.labelType {
        case .None:
            // stop the recording
            startStopRecording()
        case .Narration:
            // indicates end of the task
            markTaskEnd(time: Date())
        case .Predefined:
            if tasksState.currentlyRecordingTask {
                // case 1: we are currently recording a task so mark task as done
                markTaskEnd(time: Date())
            } else {
                // case 2: we are not currently recording a task, start the next task
                markTaskStart(time: Date())
            }
        }
    }
    
    func session(_ session: ARSession, didAdd anchors: [ARAnchor]) {
        var foundParticipantAnchor = false
        var foundWorldAnchor = false
        
        for anchor in anchors {
//            messageLabel.displayMessage("new anchor! \(anchor.name)", duration: 2.0)
//            let anchorEntity = AnchorEntity(anchor: anchor)
//            let coordinateSystem2 = MeshResource.generateCoordinateSystemAxes()
//            anchorEntity.addChild(coordinateSystem2)
//            arView.scene.addAnchor(anchorEntity)
            
            if let participantAnchor = anchor as? ARParticipantAnchor {
                let peerUUID = participantAnchor.sessionIdentifier?.uuidString ?? "unknown"
                messageLabel.displayMessage("Participant anchor found — peer UUID: \(peerUUID.prefix(8))")

                // Always update host election and add visual for the new peer.
                recomputeHostStatus()
                let anchorEntity = AnchorEntity(.anchor(identifier: participantAnchor.identifier))
                let coordinateSystem = MeshResource.generateCoordinateSystemAxes()
                anchorEntity.addChild(coordinateSystem)
                let color = participantAnchor.sessionIdentifier?.toRandomColor() ?? .white
                let coloredSphere = ModelEntity(mesh: MeshResource.generateSphere(radius: 0.03),
                                                materials: [SimpleMaterial(color: color, isMetallic: true)])
                anchorEntity.addChild(coloredSphere)
                arView?.scene.addAnchor(anchorEntity)

                foundParticipantAnchor = true

                if recordingMode == .both {
                    // Already fully aligned — a new 3rd device joined an existing session.
                    // ARKit collaboration will automatically share the host's world anchor
                    // with the new peer. Don't tear down the established world frame.
                    messageLabel.displayMessage("New peer joined established session — world frame will be shared automatically")
                    setRecordingMode(mode: .both) // refresh icon for new peer count
                } else {
                    // Not yet aligned — do the full world-frame setup.
                    if localWorldAnchor == nil {
                        print("found participantAnchor with no localWorldAnchor — adding it now")
                        addLocalWorldAnchor()
                        localAnchorCountdown = -1
                    }
                    peerParticipantAnchorFound = true
                    worldAnchorCountdown = worldAnchorInitialCountdown
                    // Clean up a stale world anchor from a previous connection.
                    if worldAnchor != nil {
                        session.remove(anchor: worldAnchor!)
                        worldAnchor = nil
                    }
                    if !isHostSide {
                        worldFrameRequestCountdown = worldAnchorInitialCountdown + worldFrameRequestInterval
                    }
                    messageLabel.displayMessage("World anchor countdown started (\(worldAnchorInitialCountdown) frames)")
                    setRecordingMode(mode: .none)
                }
            } else if anchor.name == "world frame" {
                foundWorldAnchor = true
                if multipeerSession?.connectedPeers.isEmpty ?? true {
                    messageLabel.displayMessage("WARNING: received world frame but no MCP peers connected — ignoring.")
                    continue
                }
                if peerSessionIDs.isEmpty {
                    messageLabel.displayMessage("WARNING: received world frame before peer session ID — proceeding anyway.")
                }

                // --- Stale-anchor guards (before any visual or state changes) ---

                if anchor.sessionIdentifier == session.identifier {
                    // Our own world frame reflected back by ARKit.  If worldAnchor is nil we
                    // already removed it (clearWorldFrameAnchors) but the peer's mirrored copy
                    // survived the disconnect and is being re-shared — discard it.
                    if worldAnchor == nil {
                        messageLabel.displayMessage("WARNING: received own stale world frame re-shared by peer — removing")
                        session.remove(anchor: anchor)
                        continue
                    }
                    messageLabel.displayMessage("Received own world coordinate frame (host)")
                } else {
                    messageLabel.displayMessage("Received world coordinate frame from peer")
                    if isHostSide {
                        // Stale peer world frame slipped through during reconnect race.
                        // Remove it on both sides: removing it here causes ARKit collaboration
                        // to propagate the removal to the peer.
                        messageLabel.displayMessage("WARNING: host received world frame from peer — removing stale anchor")
                        session.remove(anchor: anchor)
                        continue
                    }
                    if recordingMode == .both {
                        // Already aligned — duplicate frame, remove it.
                        messageLabel.displayMessage("WARNING: non-host received duplicate world frame — removing stale anchor")
                        session.remove(anchor: anchor)
                        continue
                    }
                    // Apply the peer's coordinate frame
                    let pose = anchor.transform
                    session.setWorldOrigin(relativeTransform: pose)
                    messageLabel.displayMessage("Applied world origin from peer's coordinate frame")
                }

                // --- Anchor is valid: add visual, finalize state ---

                let anchorEntity = AnchorEntity(.anchor(identifier: anchor.identifier))
                let coordinateSystem = MeshResource.generateCoordinateSystemAxes()
                anchorEntity.addChild(coordinateSystem)
                arView?.scene.addAnchor(anchorEntity)

                justAddedWorldOrigin = true

                if localWorldAnchor != nil {
                    session.remove(anchor: localWorldAnchor!)
                    print("removed local world anchor")
                    localWorldAnchor = nil
                } else {
                    messageLabel.displayMessage("Note: world frame received before local anchor was ready (harmless)")
                }

                worldFrameRequestCountdown = -1

                messageLabel.displayMessage("Coordinate frames aligned — ready to record")
                setRecordingMode(mode: .both)
            } else if anchor.name == "local world frame" {
                if anchor.sessionIdentifier == session.identifier {
                    let anchorEntity = AnchorEntity(.anchor(identifier: anchor.identifier))
                    let coordinateSystem = MeshResource.generateCoordinateSystemAxes()
                    anchorEntity.addChild(coordinateSystem)

                    arView?.scene.addAnchor(anchorEntity)

                    messageLabel.displayMessage("Local world frame confirmed by ARKit")
                    setRecordingMode(mode: .single)
                }
            }
        }
        
        if foundParticipantAnchor && foundWorldAnchor {
            messageLabel.displayMessage("Note: participant anchor and world frame arrived in the same batch (harmless)")
        }
    }
    
    var loggedFirstCollabSend = false
    var loggedFirstCollabReceive = false

    /// - Tag: DidOutputCollaborationData
    func session(_ session: ARSession, didOutputCollaborationData data: ARSession.CollaborationData) {
        guard let multipeerSession = multipeerSession else {
            return
        }
        if !multipeerSession.connectedPeers.isEmpty {
            guard let encodedData = try? NSKeyedArchiver.archivedData(withRootObject: data, requiringSecureCoding: true)
            else { fatalError("Unexpectedly failed to encode collaboration data.") }
            let dataIsCritical = data.priority == .critical
            if !loggedFirstCollabSend {
                loggedFirstCollabSend = true
                messageLabel.displayMessage("Sending first collaboration data to peer (critical: \(dataIsCritical))")
            }
            multipeerSession.sendToAllPeers(encodedData, reliably: dataIsCritical)
        }
    }
    
    func poseToText(_ pose: simd_float4x4, _ fps: Double) -> String {
        return "X: \(String(format: "%.3f", pose[3][0]))m\nY: \(String(format: "%.3f", pose[3][1]))m\nZ: \(String(format: "%.3f", pose[3][2]))m\nFPS: \(String(format: "%.1f", fps))"
    }
    
    func alertError(message: String) {
        DispatchQueue.main.async {
            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "hh:mm:ss"
            let date = dateFormatter.string(from: Date())
            
            // Present the error that occurred.
            let alertController = UIAlertController(title: "Error: \(date)", message: message, preferredStyle: .alert)
            
            let restartAction = UIAlertAction(title: "Restart Session", style: .default) { _ in
                self.dismiss(animated: true, completion: nil)
            }
            alertController.addAction(restartAction)
            
            self.present(alertController, animated: true, completion: nil)
        }
    }
    
    // ARSessionDelegate method
    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        setRecordingMode(mode: self.recordingMode) // refresh recording state
        
        if mainIntrinsincs == nil {
            mainIntrinsincs = session.currentFrame?.camera.intrinsics
        }
        
        if ultrawideIntrinsics == nil {
            ultrawideIntrinsics = frame.getUltraWideCamera()?.intrinsics
        }

        if arKitFirstFrameDate == nil { arKitFirstFrameDate = Date() }
        let storedLensPosition = UserDefaults.standard.object(forKey: "arKitUltrawideLensPosition") as? Float ?? 0
        if storedLensPosition == 0,
           Date().timeIntervalSince(arKitFirstFrameDate!) >= 2.0,
           let device = AVCaptureDevice.default(.builtInUltraWideCamera, for: .video, position: .back),
           device.lensPosition > 0 {
            UserDefaults.standard.set(device.lensPosition, forKey: "arKitUltrawideLensPosition")
        }
        
        // Compute L2 distance to each connected peer for display.
        var peerDistances: [Float] = []
        var updatedPeerSessionIDs: [String] = []
        let myPosition = frame.camera.transform.columns.3
        if !peerSessionIDs.isEmpty {
            for anchor in frame.anchors {
                guard
                    let sessionID = anchor.sessionIdentifier?.uuidString,
                    peerSessionIDs.values.contains(sessionID),
                    sessionID == anchor.identifier.uuidString
                else {
                    continue
                }
                let peerPosition = anchor.transform.columns.3
                let diff = simd_float3(myPosition.x - peerPosition.x,
                                       myPosition.y - peerPosition.y,
                                       myPosition.z - peerPosition.z)
                peerDistances.append(simd_length(diff))
                updatedPeerSessionIDs.append(sessionID)
            }
        }
        
        let defaults = UserDefaults.standard
        var currentDate = Date()
        
        // pose of this iPhone
        let transform = frame.camera.transform
        let timestamp = frame.timestamp // in seconds
        let arPoseDate = arTimeStampToDate(timestamp)
        let x = transform.columns.3.x
        let y = transform.columns.3.y
        let z = transform.columns.3.z
        fps = 1 / (timestamp - self.prevTimestampThisDevice)
        
        if isRecording {
            // abort demonstration if fps drops from 60 to 30
            // sometimes the FPS temporarily drops right at the start of the recording and then goes back up to 60. In those cases we will only abandon the recording if the FPS drops after the first second of recording
            if fps < 31 && currentDate.timeIntervalSince1970 - recordingStartTime!.timeIntervalSince1970 > 1 {
                let wasInitiator = iAmRecordingInitiator
                let droppedSide = phoneSide.recordingNameComponent
                abandonCurrentRecording()
                if wasInitiator { fpsDropAlert(side: droppedSide) }
            }

            // abort demonstration if pose jump exceeds threshold
            let dt = timestamp - prevTimestampThisDevice
            if let prevPose = previousRecordingPoseTransform, dt > 0 {
                let prevPos = prevPose.columns.3
                let dx = Double(transform.columns.3.x - prevPos.x)
                let dy = Double(transform.columns.3.y - prevPos.y)
                let dz = Double(transform.columns.3.z - prevPos.z)
                let metersPerSecond = sqrt(dx*dx + dy*dy + dz*dz) / dt
                maxRecordingPoseDeltaMetersPerSecond = max(maxRecordingPoseDeltaMetersPerSecond, metersPerSecond)
                if metersPerSecond > maxPoseDeltaMetersPerSecond {
                    let wasInitiator = iAmRecordingInitiator
                    let side = phoneSide.recordingNameComponent
                    abandonCurrentRecordingWithPoseDelta(metersPerSecond: metersPerSecond)
                    if wasInitiator { poseDeltaAlert(side: side, metersPerSecond: metersPerSecond) }
                }
            }
            if isRecording { previousRecordingPoseTransform = transform }

            let ultrawideImage = frame.getCapturedUltraWideImage()
            let ultrawideTime = frame.getUltraWideTimestamp()
            let ultrawideDate = ultrawideTime != nil ? arTimeStampToDate(ultrawideTime!) : nil

            demonstrationData?.logFrame(pose: transform, poseTime: arPoseDate, rgb: frame.capturedImage, depthMap: frame.sceneDepth?.depthMap, ultrawidergb: ultrawideImage, arkitTimestamp: frame.timestamp)
        }

        let displayString = "Cur iPhone:     x: \(String(format: "%.4f", transform[3][0])), y: \(String(format: "%.4f", transform[3][1])), z: \(String(format: "%.4f", transform[3][2])), fps: \(String(format: "%.3f", fps))"
//        print(displayString)
        prevTimestampThisDevice = timestamp
        
        // update the UI label
        let minePoseText = poseToText(transform, fps)
        let sessionName = (defaults.object(forKey: "sessionName") as? String)!
        let peerCount = multipeerSession?.connectedPeers.count ?? 0
        let capturedUseViewer = useViewer
        let capturedIsRecording = isRecording
        let capturedMaxPoseDelta = maxRecordingPoseDeltaMetersPerSecond
        let capturedUpdatedPeerSessionIDs = updatedPeerSessionIDs
        DispatchQueue.main.async {
            self.cachedPeerDistances = peerDistances
            let now = Date()
            for sid in capturedUpdatedPeerSessionIDs { self.lastPeerPoseDates[sid] = now }
            self.poseLabel.text = minePoseText
            for (index, dist) in peerDistances.enumerated() {
                self.poseLabel.text! += "\nPeer\(index + 1): \(String(format: "%.3f", dist))m"
            }

            if self.multipeerEnabled { self.peerCountLabel.text = "Peers: \(peerCount)" }
            self.stateLabel.text = ""
            self.stateLabel.text! += "Session: \(sessionName)"
            self.stateLabel.text! += "\nGripper ID: \(self.gripperID)"
            self.stateLabel.text! += "\nDemos: \(self.cachedDemoCount) (\(self.cachedTotalDemoCount)) | Calibs: \(self.cachedCalibCount) (\(self.cachedTotalCalibCount))"
            self.stateLabel.text! += "\nVoice commands: \(self.speechRecognizerEnabled ? "on" : "off")"
            if peerCount > 0 {
                self.stateLabel.text! += "\nVoice host: \(self.multipeerVoiceHost ? "on" : "off")"
            }
            if capturedUseViewer {
                self.stateLabel.text! += "\nWARNING: viewer degrades performance"
            }
            if capturedIsRecording {
                self.stateLabel.text! += "\nMax Δpose: \(String(format: "%.2f", capturedMaxPoseDelta)) m/s"
            }
        }
        

        
        // countdown to add world anchor
        if peerParticipantAnchorFound {
            if worldAnchorCountdown == 0 {
                if isHostSide {
                    messageLabel.displayMessage("World anchor countdown fired — isHostSide: \(isHostSide)")
                    addWorldAnchor()
                }
                worldAnchorCountdown -= 1
            } else if worldAnchorCountdown > 0 {
                worldAnchorCountdown -= 1
            }
        }

        // non-host: periodically ask the host to re-send the world frame if not yet aligned
        if !isHostSide && multipeerEnabled && worldFrameRequestCountdown >= 0 {
            if worldFrameRequestCountdown == 0 {
                messageLabel.displayMessage("Re-requesting world frame from host, point phones in same direction and keep moving around")
                if let data = "RequestWorldFrame".data(using: .utf8) {
                    multipeerSession?.sendToAllPeers(data, reliably: true)
                }
                worldFrameRequestCountdown = worldFrameRequestInterval
            } else {
                worldFrameRequestCountdown -= 1
            }
        }
        
        // countdown to add local anchor
        if localAnchorCountdown == 0 {
            addLocalWorldAnchor()
            localAnchorCountdown -= 1
        } else if localAnchorCountdown > 0 {
            localAnchorCountdown -= 1
        }
    }
    
    func markTaskStart(time: Date) {
        assert(!tasksState.currentlyRecordingTask)
        tasksState.currentlyRecordingTask = true
        let taskSegmentationEvent = TaskSegmentation()
        taskSegmentationEvent.taskStart = time
        
        if demonstrationData!.labelType == .Predefined {
            // if repeating predefined tasks, we already know the sequence of tasks so we can assign the language label now
            taskSegmentationEvent.name = tasksState.tasks[tasksState.currentTaskIndex]
        }
        
        tasksState.taskSegmentationEvents.append(taskSegmentationEvent)
        
        updateTaskUI()
    }
    
    func markTaskEnd(time: Date, newTaskStartTime: Date? = nil, enableAutoStep: Bool = true) {
        switch demonstrationData!.labelType {
        case .Narration:
            assert(!tasksState.currentlyRecordingTask) // only mark the end with narration
            
            // create segmentation event because there was no explicit start
            let taskSegmentationEvent = TaskSegmentation()
            tasksState.taskSegmentationEvents.append(taskSegmentationEvent)
            
        case .Predefined:
            assert(tasksState.currentlyRecordingTask) // task should have been previously marked as started
        case .None:
            assert(false)
        }
        
        tasksState.currentlyRecordingTask = false
        tasksState.taskSegmentationEvents[tasksState.taskSegmentationEvents.count - 1].taskEnd = time
        
        if demonstrationData!.labelType == .Predefined && enableAutoStep {
            if tasksState.currentTaskIndex == tasksState.tasks.count - 1 {
                // end the demonstration
                startStopRecording()
            } else {
                tasksState.currentTaskIndex += 1
                
                // if the next task is a confirmation, then wait until starting the next task
                if tasksState.tasks[tasksState.currentTaskIndex] == "CONFIRM" {
                    // don't record data for the confirmation task, but also don't start the next task yet
                    tasksState.currentTaskIndex += 1
                } else {
                    var newTaskStartTime = newTaskStartTime
                    if newTaskStartTime == nil {
                        newTaskStartTime = time
                    }
                    // if no confirmation then just start the next task right away
                    markTaskStart(time: newTaskStartTime!)
                }
            }
        }
        
        updateTaskUI()
    }
    
    func narrationCallback(result: SFSpeechRecognitionResult, startIndex: Int) {
        let allSegments = result.bestTranscription.segments
        var didDone = false

        allSegments[startIndex..<allSegments.count].forEach { segment in
            segment.substring.split(separator: " ").forEach { wordSlice in
                let word = String(wordSlice)
                if NarrationCommands.isStopWord(word) {
                    handleLiveStopWord()
                } else if NarrationCommands.isDoneWord(word) {
                    handleLiveDoneWord()
                    didDone = true
                } else if NarrationCommands.isStartWord(word) {
                    handleLiveStartWord()
                } else if NarrationCommands.isDeleteWord(word) {
                    handleLiveDeleteWord()
                }
            }
        }

        guard isRecording, let data = demonstrationData, data.labelType == .Narration else { return }

        let now = Date()
        let hasNewContent = startIndex < allSegments.count
        if hasNewContent {
            if !didDone, let lastDate = lastNarrationWordArrivalDate, now.timeIntervalSince(lastDate) > 0.5 {
                narrationCurrentTaskSegmentStart = startIndex
            }
            lastNarrationWordArrivalDate = now
        }

        if didDone { narrationCurrentTaskSegmentStart = allSegments.count }

        currentNarrationText = allSegments[min(narrationCurrentTaskSegmentStart, allSegments.count)..<allSegments.count]
            .flatMap { $0.substring.split(separator: " ").map(String.init) }
            .filter { !NarrationCommands.isStopWord($0) && !NarrationCommands.isDoneWord($0) && !NarrationCommands.isStartWord($0) && !NarrationCommands.isDeleteWord($0) }
            .joined(separator: " ")
        updateTaskUI()
    }
    
    func handleLiveStartWord() {
        if !isRecording {
            recordButtonPress()
        } else {
            switch demonstrationData!.labelType {
            case .None:
                break
            case .Narration:
                break
            case .Predefined:
                if !tasksState.currentlyRecordingTask {
                    markTaskStart(time: Date())
                    if recordingMode == .both, let nextTaskData = "NextTask".data(using: .utf8) {
                        multipeerSession?.sendToAllPeers(nextTaskData, reliably: true)
                    }
                }
            }
        }
    }

    func handleLiveDoneWord() {
        guard isRecording, let data = demonstrationData, data.labelType == .Narration else { return }
        if speechRecognizerEnabled {
            markTaskEnd(time: Date())
            narrationTaskCount += 1
        }
    }

    func handleLiveStopWord() {
        if isRecording {
            if getDemonstrationType() == .GripperCalibration {
                recordButtonPress()
                return
            }
            switch demonstrationData!.labelType {
            case .None:
                recordButtonPress()
            case .Narration:
                if speechRecognizerEnabled { recordButtonPress() }
            case .Predefined:
                if tasksState.currentlyRecordingTask {
                    markTaskEnd(time: Date())
                    if recordingMode == .both, let nextTaskData = "NextTask".data(using: .utf8) {
                        multipeerSession?.sendToAllPeers(nextTaskData, reliably: true)
                    }
                }
            }
        }
    }
    
    func handleLiveDeleteWord() {
        if !isRecording {
            deleteLastButtonPressed(self)
        }
    }

    func arTimeStampToDate(_ arTimeStamp: TimeInterval) -> Date {
        // for debugging:
//        let uptime = ProcessInfo.processInfo.systemUptime;
//        let nowTimeIntervalSince1970 = Date().timeIntervalSince1970
//        print("uptime \(uptime) now \(nowTimeIntervalSince1970) offset \(arKitTimeOffset) arTimeStamp: \(arTimeStamp) corrected time \(arTimeStamp + arKitTimeOffset)")
        
        return Date(timeIntervalSince1970: arTimeStamp + arKitTimeOffset)
    }

    func receivedData(_ data: Data, from peer: MCPeerID) {
        // collaboration data
        if let collaborationData = try? NSKeyedUnarchiver.unarchivedObject(ofClass: ARSession.CollaborationData.self, from: data) {
            if !loggedFirstCollabReceive {
                loggedFirstCollabReceive = true
                messageLabel.displayMessage("Received first collaboration data from peer")
            }
            session.update(with: collaborationData)
            return
        }
        
        // session ID
        let sessionIDCommandString = "SessionID:"
        if let commandString = String(data: data, encoding: .utf8), commandString.starts(with: sessionIDCommandString) {
            let newSessionID = String(commandString[commandString.index(commandString.startIndex,
                                                                     offsetBy: sessionIDCommandString.count)...])
            DispatchQueue.main.async {
                // peerSessionIDs is read on the ARSession delegate queue every frame — mutate
                // only on main to avoid a data race that corrupts the Swift dictionary.
                if let oldSessionID = self.peerSessionIDs[peer] {
                    self.removeAllAnchorsOriginatingFromARSessionWithID(oldSessionID)
                }
                self.peerSessionIDs[peer] = newSessionID
                self.recomputeHostStatus()
            }
            return
        }
        
        // non-host confirms it received the world frame
        // pre-recording validation handshake — request
        if let commandString = String(data: data, encoding: .utf8), commandString == "PreRecordingCheck" {
            DispatchQueue.main.async {
                let worldFrameReady = self.recordingMode == .both
                var unmetConditions = self.unmetRecordingConditions()
                let storageGB = self.availableStorageGB()
                if storageGB < 1.0 {
                    let storageReason = "insufficient storage (\(String(format: "%.2f", storageGB)) GB free, need ≥ 1 GB)"
                    unmetConditions = unmetConditions.map { "\($0), \(storageReason)" } ?? storageReason
                }
                let isReady = worldFrameReady && unmetConditions == nil
                let reason = unmetConditions ?? (worldFrameReady ? "" : "world frame not yet aligned")
                let response = "PreRecordingStatus:\(self.phoneSide.rawValue):\(isReady ? 1 : 0):\(self.multipeerVoiceHost ? 1 : 0):\(self.speechRecognizerEnabled ? 1 : 0):\(reason)"
                if let responseData = response.data(using: .utf8) {
                    self.multipeerSession?.sendToPeers(responseData, reliably: true, peers: [peer])
                }
            }
            return
        }

        // pre-recording validation handshake — response
        if let commandString = String(data: data, encoding: .utf8), commandString.starts(with: "PreRecordingStatus:") {
            let parts = commandString.dropFirst("PreRecordingStatus:".count).split(separator: ":", maxSplits: 4)
            if parts.count >= 3, let sideRaw = Int(parts[0]), let readyRaw = Int(parts[1]), let voiceHostRaw = Int(parts[2]) {
                let voiceCommandsEnabled = parts.count >= 4 ? (Int(parts[3]) == 1) : false
                let reason = parts.count >= 5 ? String(parts[4]) : ""
                DispatchQueue.main.async {
                    guard self.pendingPreRecordingResponses != nil else { return }
                    self.pendingPreRecordingResponses![peer] = (side: sideRaw, ready: readyRaw == 1, voiceHost: voiceHostRaw == 1, voiceCommandsEnabled: voiceCommandsEnabled, reason: reason)
                    if self.pendingPreRecordingResponses!.count >= self.pendingPreRecordingExpectedCount {
                        self.evaluatePreRecordingStatusAndProceed()
                    }
                }
            }
            return
        }

        // task step from peer
        if let commandString = String(data: data, encoding: .utf8), commandString == "NextTask" {
            DispatchQueue.main.async {
                guard self.isRecording else { return }
                self.nextTaskButtonPress()
            }
            return
        }

        // recording abort from peer
        if let commandString = String(data: data, encoding: .utf8), commandString == "AbortRecording" {
            let senderPeer = peer
            DispatchQueue.main.async {
                let wasInitiator = self.iAmRecordingInitiator
                self.discardCurrentRecordingLocally()
                if wasInitiator { self.showSettingsMismatchAlert() }
                // Host forwards to remaining peers, excluding the sender to avoid double-alert.
                if self.isHostSide, let mp = self.multipeerSession {
                    let otherPeers = mp.connectedPeers.filter { $0 != senderPeer }
                    if !otherPeers.isEmpty, let abortData = "AbortRecording".data(using: .utf8) {
                        mp.sendToPeers(abortData, reliably: true, peers: otherPeers)
                    }
                }
            }
            return
        }

        // recording abort due to FPS drop on peer
        if let commandString = String(data: data, encoding: .utf8), commandString.hasPrefix("AbortRecording:FPSDrop") {
            let senderPeer = peer
            let parts = commandString.split(separator: ":", maxSplits: 2)
            let droppedSide = parts.count == 3 ? String(parts[2]) : nil
            DispatchQueue.main.async {
                let wasInitiator = self.iAmRecordingInitiator
                self.discardCurrentRecordingLocally()
                if wasInitiator { self.fpsDropAlert(side: droppedSide) }
                if self.isHostSide, let mp = self.multipeerSession {
                    let otherPeers = mp.connectedPeers.filter { $0 != senderPeer }
                    if !otherPeers.isEmpty, let abortData = commandString.data(using: .utf8) {
                        mp.sendToPeers(abortData, reliably: true, peers: otherPeers)
                    }
                }
            }
            return
        }

        // recording abort due to pose delta on peer
        if let commandString = String(data: data, encoding: .utf8), commandString.hasPrefix("AbortRecording:PoseDelta") {
            let senderPeer = peer
            let parts = commandString.split(separator: ":", maxSplits: 3)
            let abortedSide = parts.count >= 3 ? String(parts[2]) : nil
            let metersPerSecond = parts.count >= 4 ? Double(parts[3]) ?? 0.0 : 0.0
            DispatchQueue.main.async {
                let wasInitiator = self.iAmRecordingInitiator
                self.discardCurrentRecordingLocally()
                if wasInitiator { self.poseDeltaAlert(side: abortedSide, metersPerSecond: metersPerSecond) }
                if self.isHostSide, let mp = self.multipeerSession {
                    let otherPeers = mp.connectedPeers.filter { $0 != senderPeer }
                    if !otherPeers.isEmpty, let abortData = commandString.data(using: .utf8) {
                        mp.sendToPeers(abortData, reliably: true, peers: otherPeers)
                    }
                }
            }
            return
        }

        // recording abort due to side conflict
        if let commandString = String(data: data, encoding: .utf8), commandString == "AbortRecording:SideConflict" {
            let senderPeer = peer
            DispatchQueue.main.async {
                let wasInitiator = self.iAmRecordingInitiator
                self.discardCurrentRecordingLocally()
                if wasInitiator { self.showSideConflictAlert() }
                if self.isHostSide, let mp = self.multipeerSession {
                    let otherPeers = mp.connectedPeers.filter { $0 != senderPeer }
                    if !otherPeers.isEmpty, let abortData = "AbortRecording:SideConflict".data(using: .utf8) {
                        mp.sendToPeers(abortData, reliably: true, peers: otherPeers)
                    }
                }
            }
            return
        }

        // recording start/stop
        if let recordingMessage = try? NSKeyedUnarchiver.unarchivedObject(ofClasses: [RecordingMessage.self, NSString.self, NSDate.self, NSNumber.self, NSArray.self], from: data) as? RecordingMessage {
            if recordingMessage.startRecording {
                recordingName = recordingMessage.recordingName! as String
                recordingStartTime = recordingMessage.recordingStartTime! as Date
                messageLabel.displayMessage("Received start recording command from peer")
            } else {
                messageLabel.displayMessage("Received end recording command from peer")
            }
            let shouldRecord = recordingMessage.startRecording
            let incomingSidesPresent = recordingMessage.sidesPresent
            DispatchQueue.main.async {
                if shouldRecord {
                    if self.hasSideConflict(recordingMessage) {
                        if let abortData = "AbortRecording:SideConflict".data(using: .utf8) {
                            self.multipeerSession?.sendToAllPeers(abortData, reliably: true)
                        }
                        return
                    } else if let mismatch = self.recordingSettingsMismatch(recordingMessage) {
                        if let abortData = "AbortRecording".data(using: .utf8) {
                            self.multipeerSession?.sendToAllPeers(abortData, reliably: true)
                        }
                        return
                    }
                    if let sp = incomingSidesPresent { self.recordingSidesPresent = sp }
                } else {
                    self.recordingSidesPresent = []
                }
                self.setRecordingState(shouldRecord)
            }
            return
        }
        
        // world frame re-send request from non-host
        if let commandString = String(data: data, encoding: .utf8), commandString == "RequestWorldFrame" {
            DispatchQueue.main.async {
                guard self.isHostSide else { return }
                self.messageLabel.displayMessage("Peer requested world frame re-send — re-adding world anchor")
                if self.worldAnchor != nil {
                    self.session.remove(anchor: self.worldAnchor!)
                    self.worldAnchor = nil
                }
                self.addWorldAnchor()
            }
            return
        }

        // settings sync
        if let syncMsg = try? NSKeyedUnarchiver.unarchivedObject(ofClasses: [SettingsSyncMessage.self, NSArray.self, NSString.self], from: data) as? SettingsSyncMessage {
            DispatchQueue.main.async {
                let defaults = UserDefaults.standard

                self.recordTypeSegmentedControl.selectedSegmentIndex = syncMsg.recordTypeSegmentIndex

                self.labelTypeSegmentedControl.selectedSegmentIndex = syncMsg.labelTypeSegmentIndex
                defaults.set(syncMsg.labelTypeSegmentIndex, forKey: "labelSelectedSegmentID")

                defaults.set(syncMsg.tasks, forKey: "tasks")

                defaults.set(syncMsg.sessionName, forKey: "sessionName")
                do {
                    if let calibration = try DemonstrationData.mostRecentGripperCalibrationRunName(forSessionName: syncMsg.sessionName) {
                        defaults.set(calibration, forKey: "gripperCalibrationRunName")
                    } else {
                        defaults.set("", forKey: "gripperCalibrationRunName")
                    }
                } catch {
                    defaults.set("", forKey: "gripperCalibrationRunName")
                }

                self.gripperID = syncMsg.gripperID

                self.errorCorrectionMode = syncMsg.errorCorrectionMode
                UserDefaults.standard.set(syncMsg.errorCorrectionMode, forKey: "errorCorrectionMode")

                self.updateTaskUI()
                self.setRecordingMode(mode: self.recordingMode)
                self.updateDemoCountLabel()
                self.messageLabel.displayMessage("Settings synced from peer")
            }
            return
        }

        messageLabel.displayMessage("Received unknown data from peer")
    }
    
    func peerDiscovered(_ peer: MCPeerID) -> Bool {
        guard let multipeerSession = multipeerSession else { return false }
        
        if multipeerSession.connectedPeers.count > 2 {
            // Do not accept more than three users in the experience.
            messageLabel.displayMessage("A fourth peer wants to join the experience. This app is limited to three users.")
            return false
        } else {
            return true
        }
    }
    /// - Tag: PeerJoined
    func peerJoined(_ peer: MCPeerID) {
        let myName = UIDevice.current.name
        messageLabel.displayMessage("Peer joined — me: \(myName), peer: \(peer.displayName)")
        messageLabel.displayMessage("A peer wants to join the experience. Hold the phones next to each other.")
        // Provide your session ID to the new user so they can keep track of your anchors.
        sendARSessionIDTo(peers: [peer])
        let joinedCount = multipeerSession?.connectedPeers.count ?? 0
        DispatchQueue.main.async {
            if self.multipeerEnabled { self.peerCountLabel.text = "Peers: \(joinedCount)" }
            // Re-arm world-frame establishment for reconnects.  clearWorldFrameAnchors()
            // (called from peerLeft) resets peerParticipantAnchorFound and worldAnchorCountdown.
            // On reconnect the ARParticipantAnchor may not re-fire, so nothing would restart
            // the host countdown or the non-host retry.  Doing it here is safe for first
            // connections too — the participant anchor handler will reset the same values if
            // it fires, and peerLeft always dispatches to main before peerJoined so this
            // block always runs after clearWorldFrameAnchors().
            if self.localWorldAnchor == nil {
                self.addLocalWorldAnchor()
                self.localAnchorCountdown = -1
            }
            self.peerParticipantAnchorFound = true
            self.worldAnchorCountdown = self.worldAnchorInitialCountdown
            // worldFrameRequestCountdown is gated on !isHostSide at fire time, so setting
            // it unconditionally here is safe — the host just won't use it.
            self.worldFrameRequestCountdown = self.worldAnchorInitialCountdown + self.worldFrameRequestInterval
        }
    }

    func peerLeft(_ peer: MCPeerID) {
        let mcCount = multipeerSession?.connectedPeers.count ?? 0
        DispatchQueue.main.async {
            if let sessionID = self.peerSessionIDs[peer] {
                self.messageLabel.displayMessage("Peer left: \(sessionID.prefix(8)) — MCSession peers remaining: \(mcCount), peerSessionIDs tracked: \(self.peerSessionIDs.count)")
                self.peerSessionIDs.removeValue(forKey: peer)
                self.lastPeerPoseDates.removeValue(forKey: sessionID)
                self.recomputeHostStatus()
                self.removeAllAnchorsOriginatingFromARSessionWithID(sessionID)
            } else {
                self.messageLabel.displayMessage("Note: peerLeft fired for untracked peer (no session ID) — MCSession peers remaining: \(mcCount)")
            }
            if self.multipeerEnabled { self.peerCountLabel.text = "Peers: \(self.peerSessionIDs.count)" }
            // When the last peer leaves, purge all world frame anchors so they cannot
            // be re-shared by ARKit collaboration when the next peer connects.  Without
            // this, the stale anchor reaches the new peer before the participant-anchor
            // handler fires, causing the "did not expect to be host and receive world
            // frame from peer" error when UUID ordering flips after a reset.
            if self.peerSessionIDs.isEmpty {
                self.clearWorldFrameAnchors()
                self.setRecordingMode(mode: .single)
            } else if self.recordingMode == .both {
                // Some peers remain. Check whether the world frame anchor still exists
                // in the ARKit session (removed if the host just left).
                let worldFramePresent = self.session.currentFrame?.anchors
                    .contains { $0.name == "world frame" } ?? false
                if worldFramePresent {
                    // Non-host left: host's anchor is intact, remaining devices stay aligned.
                    self.setRecordingMode(mode: .both) // refresh icon for new peer count
                } else {
                    // Host left: world frame is gone — re-arm establishment for remaining peers.
                    self.worldAnchor = nil
                    self.peerParticipantAnchorFound = true
                    self.worldAnchorCountdown = self.worldAnchorInitialCountdown
                    self.worldFrameRequestCountdown = self.worldAnchorInitialCountdown + self.worldFrameRequestInterval
                    self.setRecordingMode(mode: .none)
                    self.messageLabel.displayMessage("Host left — re-establishing world frame with remaining peers")
                }
            }
        }
    }
    
    @IBAction func nameSessionButtonPress(_ sender: Any) {
        let applySessionName: (String) -> Void = { [weak self] cleanedText in
            guard let self else { return }
            let defaults = UserDefaults.standard
            defaults.set(cleanedText, forKey: "sessionName")
            var hasCalibration = false
            do {
                if let calibration = try DemonstrationData.mostRecentGripperCalibrationRunName(forSessionName: cleanedText) {
                    defaults.set(calibration, forKey: "gripperCalibrationRunName")
                    hasCalibration = true
                } else {
                    defaults.set("", forKey: "gripperCalibrationRunName")
                }
            } catch {
                defaults.set("", forKey: "gripperCalibrationRunName")
            }
            if !hasCalibration && cleanedText != "no-session" {
                self.recordTypeSegmentedControl.selectedSegmentIndex = 0
                self.updateTaskUI()
            }
            self.setRecordingMode(mode: self.recordingMode)
            self.updateDemoCountLabel()
        }

        let sheet = UIAlertController(title: "Session Name", message: "The session name is used to group and identify a set of demonstrations. Ex: \"041926-outdoor-cup-task\"", preferredStyle: .actionSheet)

        sheet.addAction(UIAlertAction(title: "Set custom name…", style: .default, handler: { [weak self] _ in
            guard let self else { return }
            let textAlert = UIAlertController(title: "Enter session name", message: nil, preferredStyle: .alert)
            textAlert.addTextField { textField in
                let current = (UserDefaults.standard.object(forKey: "sessionName") as? String) ?? "no-session"
                textField.text = current == "no-session" ? "" : current
                textField.placeholder = "Session name"
                textField.autocorrectionType = .no
            }
            textAlert.addAction(UIAlertAction(title: "Cancel", style: .cancel))
            textAlert.addAction(UIAlertAction(title: "Set", style: .default) { [weak textAlert] _ in
                let raw = textAlert?.textFields?.first?.text ?? ""
                let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
                var cleaned = String(trimmed.unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) || $0 == "-" || $0 == "_" || $0 == " " })
                cleaned = cleaned.trimmingCharacters(in: .whitespacesAndNewlines)
                    .replacingOccurrences(of: "_", with: "-")
                    .replacingOccurrences(of: " ", with: "-")
                if cleaned.isEmpty { cleaned = "no-session" }
                applySessionName(cleaned)
            })
            self.present(textAlert, animated: true)
        }))

        sheet.addAction(UIAlertAction(title: "Clear session name", style: .destructive) { _ in
            applySessionName("no-session")
        })

        sheet.addAction(UIAlertAction(title: "Cancel", style: .cancel))

        // anchor popover for iPad / landscape
        if let popover = sheet.popoverPresentationController {
            popover.sourceView = nameSessionButton
            popover.sourceRect = nameSessionButton.bounds
        }

        present(sheet, animated: true)
    }
    
    @IBAction func labelTypeSegmentedControlValueUpdate(_ sender: Any) {
        labelTypeSegmentedControlUpdated()
    }
    
    func labelTypeSegmentedControlUpdated() {
        UserDefaults.standard.set(labelTypeSegmentedControl.selectedSegmentIndex, forKey: "labelSelectedSegmentID")
        
        updateTaskUI()
    }
    
    func session(_ session: ARSession, didFailWithError error: Error) {
        guard error is ARError else { return }
        
        let errorWithInfo = error as NSError
        let messages = [
            errorWithInfo.localizedDescription,
            errorWithInfo.localizedFailureReason,
            errorWithInfo.localizedRecoverySuggestion
        ]
        
        // Remove optional error messages.
        var errorMessage = messages.compactMap({ $0 }).joined(separator: "\n")
        
        errorMessage += " If you get required sensor failed error, this can occur if you have headphones like AirPods connected. If you have the contact mic connected it might not be setup properly as headphone input (see usage.md for details). If you already set up as headphones try unplugging and replugging the contact mic."
        
        DispatchQueue.main.async {
            // Present the error that occurred.
            let alertController = UIAlertController(title: "The AR session failed.", message: errorMessage, preferredStyle: .alert)
            let restartAction = UIAlertAction(title: "Restart Session", style: .default) { _ in
                alertController.dismiss(animated: true, completion: nil)
                self.resetAll()
            }
            alertController.addAction(restartAction)
            self.present(alertController, animated: true, completion: nil)
        }
    }
    
    func resetAll() {
        multipeerSession?.endSession()
        
        let peerIDs = Array(peerSessionIDs.keys)
        for peerID in peerIDs {
            if let sessionID = peerSessionIDs[peerID] {
                removeAllAnchorsOriginatingFromARSessionWithID(sessionID)
            }
            peerSessionIDs.removeValue(forKey: peerID)
        }
        
        initializeSession()
        
        print("Resetting tracking")
        session.run(configuration!, options: [.resetTracking, .removeExistingAnchors])
        
//        multipeerSession = MultipeerSession(receivedDataHandler: receivedData, peerJoinedHandler:
//                                            peerJoined, peerLeftHandler: peerLeft, peerDiscoveredHandler: peerDiscovered)
    }
    
    override var prefersStatusBarHidden: Bool {
        // Request that iOS hide the status bar to improve immersiveness of the AR experience.
        return true
    }
    
    override var prefersHomeIndicatorAutoHidden: Bool {
        // Request that iOS hide the home indicator to improve immersiveness of the AR experience.
        return true
    }
    
    // Removes all world frame anchors that this device owns so they are not re-shared via
    // ARKit collaboration when a new peer connects.  Must be called whenever all peers leave.
    private func clearWorldFrameAnchors() {
        if worldAnchor != nil {
            session.remove(anchor: worldAnchor!)
            worldAnchor = nil
        }
        if localWorldAnchor != nil {
            session.remove(anchor: localWorldAnchor!)
            localWorldAnchor = nil
        }
        // Catch orphaned anchors whose Swift references were lost (edge cases / reconnects).
        if let frame = session.currentFrame {
            for anchor in frame.anchors {
                guard anchor.sessionIdentifier == session.identifier else { continue }
                if anchor.name == "world frame" || anchor.name == "local world frame" {
                    session.remove(anchor: anchor)
                }
            }
        }
        peerParticipantAnchorFound = false
        worldAnchorCountdown = -1
        worldFrameRequestCountdown = -1
        justAddedWorldOrigin = false
        messageLabel.displayMessage("Cleared world frame anchors (all peers disconnected)")
    }

    private var videoEncodersWarmedUp = false
    private func warmUpVideoEncodersIfNeeded() {
        guard !videoEncodersWarmedUp else { return }
        videoEncodersWarmedUp = true
        DispatchQueue.global(qos: .userInitiated).async {
            // Creating AVAssetWriter + AVAssetWriterInput the first time spins up the
            // hardware H.264 and AAC encoder stacks, which takes ~200 ms and causes a
            // visible FPS drop on the very first recording.  Creating and immediately
            // cancelling dummy writers here primes those stacks so the first real
            // recording starts cleanly.
            let tempURL = URL(fileURLWithPath: NSTemporaryDirectory())
                .appendingPathComponent("encoder_warmup_\(UUID().uuidString).mov")
            guard let writer = try? AVAssetWriter(outputURL: tempURL, fileType: .mov) else { return }

            let videoSettings: [String: Any] = [
                AVVideoCodecKey: AVVideoCodecType.h264,
                AVVideoWidthKey: 1920,
                AVVideoHeightKey: 1440
            ]
            let videoInput = AVAssetWriterInput(mediaType: .video, outputSettings: videoSettings)
            videoInput.expectsMediaDataInRealTime = true
            writer.add(videoInput)

            let audioSettings: [String: Any] = [
                AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
                AVSampleRateKey: 48000,
                AVNumberOfChannelsKey: 2
            ]
            let audioInput = AVAssetWriterInput(mediaType: .audio, outputSettings: audioSettings)
            audioInput.expectsMediaDataInRealTime = true
            writer.add(audioInput)

            writer.startWriting()
            writer.cancelWriting()
            try? FileManager.default.removeItem(at: tempURL)
        }
    }

    private func removeAllAnchorsOriginatingFromARSessionWithID(_ identifier: String) {
        guard let frame = session.currentFrame else { return }
        for anchor in frame.anchors {
            guard let anchorSessionID = anchor.sessionIdentifier else { continue }
            if anchorSessionID.uuidString == identifier {
                session.remove(anchor: anchor)
            }
        }
    }
    
    private func sendARSessionIDTo(peers: [MCPeerID]) {
        guard let multipeerSession = multipeerSession else { return }
        let idString = session.identifier.uuidString
        let command = "SessionID:" + idString
        if let commandData = command.data(using: .utf8) {
            multipeerSession.sendToPeers(commandData, reliably: true, peers: peers)
        }
    }
    
    // Function to convert a GMT date to a local timezone string
    func formatDateForDisplay(_ date: Date, _ includeMS: Bool = false) -> String {
        // 1. Define a DateFormatter to format the date
        let dateFormatter = DateFormatter()
        
        // Set the formatter's time zone to the local time zone
        dateFormatter.timeZone = TimeZone.current
        
        // Set the desired date format
        if includeMS {
            dateFormatter.dateFormat = "yyyy-MM-dd hh:mm:ss:SSS a" // Customize the format as needed
        } else {
            dateFormatter.dateFormat = "yyyy-MM-dd hh:mm:ss a" // Customize the format as needed
        }
        
        
        // Convert the date to a formatted string in the local timezone
        let localDateString = dateFormatter.string(from: date)
        
        return localDateString
    }
    
    @IBAction func returnHomeButtonPress(_ sender: Any) {
        let defaults = UserDefaults.standard
        defaults.set(nil, forKey: "appMode")
        
        self.dismiss(animated: true, completion: nil)
    }
    
    @IBAction func setGripperIDButtonPress(_ sender: Any) {
        let sheet = UIAlertController(
            title: "Gripper ID",
            message: "Leave as \"default\" unless you've customized the gripper design.",
            preferredStyle: .actionSheet
        )

        sheet.addAction(UIAlertAction(title: "Set custom ID…", style: .default) { [weak self] _ in
            guard let self else { return }
            let textAlert = UIAlertController(title: "Enter gripper ID", message: nil, preferredStyle: .alert)
            textAlert.addTextField { textField in
                let current = UserDefaults.standard.string(forKey: self.gripperIDDefaultsKey) ?? "default"
                textField.text = current == "default" ? "" : current
                textField.placeholder = "Gripper ID"
                textField.autocorrectionType = .no
            }
            textAlert.addAction(UIAlertAction(title: "Cancel", style: .cancel))
            textAlert.addAction(UIAlertAction(title: "Set", style: .default) { [weak textAlert] _ in
                guard let text = textAlert?.textFields?.first?.text else { return }
                let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
                var cleaned = String(trimmed.unicodeScalars.filter {
                    CharacterSet.alphanumerics.contains($0) || $0 == "-" || $0 == "_" || $0 == " "
                })
                cleaned = cleaned.trimmingCharacters(in: .whitespacesAndNewlines)
                    .replacingOccurrences(of: "_", with: "-")
                    .replacingOccurrences(of: " ", with: "-")
                if cleaned.isEmpty { cleaned = "default" }
                self.gripperID = cleaned
            })
            self.present(textAlert, animated: true)
        })

        sheet.addAction(UIAlertAction(title: "Use default", style: .default) { _ in
            self.gripperID = "default"
        })

        sheet.addAction(UIAlertAction(title: "Cancel", style: .cancel))

        // anchor popover for iPad / landscape
        if let popover = sheet.popoverPresentationController {
            popover.sourceView = setGripperIDButton
            popover.sourceRect = setGripperIDButton.bounds
        }

        present(sheet, animated: true)
    }
    func sendSettingsSyncToPeers() {
        guard let multipeerSession = multipeerSession else { return }
        let defaults = UserDefaults.standard
        let sessionName = (defaults.object(forKey: "sessionName") as? String) ?? "no-session"
        let tasks = (defaults.object(forKey: "tasks") as? [String]) ?? []
        let msg = SettingsSyncMessage(
            recordTypeSegmentIndex: recordTypeSegmentedControl.selectedSegmentIndex,
            labelTypeSegmentIndex: labelTypeSegmentedControl.selectedSegmentIndex,
            tasks: tasks,
            sessionName: sessionName,
            gripperID: gripperID,
            errorCorrectionMode: errorCorrectionMode
        )
        guard let encoded = try? NSKeyedArchiver.archivedData(withRootObject: msg, requiringSecureCoding: true) else { return }
        multipeerSession.sendToAllPeers(encoded, reliably: true)
    }

    @IBAction func settingsButtonPressed(_ sender: Any) {
        let settings = SettingsViewController()

        settings.onViewerToggled = { [weak self] _ in
            // Dismiss the settings sheet, then dismiss the ARKit VC so it reopens with the new viewer state.
            self?.dismiss(animated: true) {
                self?.dismiss(animated: true)
            }
        }

        settings.onMultipeerToggled = { [weak self] enabled in
            guard let self else { return }
            self.multipeerEnabled = enabled
            self.updatePeerUI(multipeerEnabled: enabled)
            if enabled {
                guard self.multipeerSession == nil else { return }
                self.multipeerSession = MultipeerSession(receivedDataHandler: self.receivedData,
                                                        peerJoinedHandler: self.peerJoined,
                                                        peerLeftHandler: self.peerLeft,
                                                        peerDiscoveredHandler: self.peerDiscovered)
                self.messageLabel.displayMessage("Started MultipeerConnectivity — looking for peers")
            } else {
                self.multipeerSession?.endSession()
                self.multipeerSession = nil
                self.worldFrameRequestCountdown = -1
                self.messageLabel.displayMessage("Stopped MultipeerConnectivity")
            }
        }

        settings.onSpeechRecognizerToggled = { [weak self] enabled in
            guard let self else { return }
            self.speechRecognizerEnabled = enabled
            if enabled {
                self.liveSpeechRecognizer = SpeechRecognizer(shouldReportPartialResults: true, callback: self.narrationCallback)
                self.liveSpeechRecognizer!.startTranscribingWithExternalAudio()
            } else {
                self.liveSpeechRecognizer = nil
            }
        }

        settings.onMultipeerVoiceHostToggled = { [weak self] enabled in
            self?.multipeerVoiceHost = enabled
        }

        settings.onErrorCorrectionToggled = { [weak self] enabled in
            self?.errorCorrectionMode = enabled
            self?.setRecordingMode(mode: self?.recordingMode ?? .none)
        }

        settings.onManualPeerSync = { [weak self] in
            self?.sendSettingsSyncToPeers()
        }

        settings.isPeerConnected = { [weak self] in
            !(self?.multipeerSession?.connectedPeers.isEmpty ?? true)
        }

        let nav = UINavigationController(rootViewController: settings)
        if #available(iOS 15.0, *) {
            if let sheet = nav.sheetPresentationController {
                sheet.detents = [.medium()]
                sheet.prefersGrabberVisible = true
            }
        }
        present(nav, animated: true)
    }
    @IBAction func deleteLastButtonPressed(_ sender: Any) {
        guard !isRecording, !isFinalizingRecording, let nameToDelete = lastRecordedName else { return }
        guard DemonstrationData.hasDataType(recordingName: nameToDelete, demonstrationSaveType: .JSON) else {
            lastRecordedName = nil
            updateDeleteLastButton()
            print("deleteLastButtonPressed: recording not found on disk: \(nameToDelete)")
            messageLabel.displayMessage("Recording not found — already deleted")
            return
        }
        do {
            try DemonstrationData.discard(recordingName: nameToDelete)
            lastRecordedName = nil

            // If the deleted recording was the active gripper calibration, clear it
            let defaults = UserDefaults.standard
            let savedCalib = defaults.object(forKey: "gripperCalibrationRunName") as? String ?? ""
            if !savedCalib.isEmpty && nameToDelete == savedCalib {
                defaults.set("", forKey: "gripperCalibrationRunName")
            }

            updateDeleteLastButton()
            updateDemoCountLabel()
            messageLabel.displayMessage("Deleted: \(nameToDelete)")
        } catch {
            messageLabel.displayMessage("Failed to delete: \(error.localizedDescription)")
        }
    }
}
