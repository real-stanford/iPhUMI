/*
 from https://developer.apple.com/tutorials/app-dev-training/transcribing-speech-to-text
 */

import Foundation
import AVFoundation
import Speech
import SwiftUI

/// A helper for transcribing speech to text using SFSpeechRecognizer and AVAudioEngine.
actor SpeechRecognizer: ObservableObject {
    enum RecognizerError: Error {
        case nilRecognizer
        case notAuthorizedToRecognize
        case notPermittedToRecord
        case recognizerIsUnavailable
        
        var message: String {
            switch self {
            case .nilRecognizer: return "Can't initialize speech recognizer"
            case .notAuthorizedToRecognize: return "Not authorized to recognize speech"
            case .notPermittedToRecord: return "Not permitted to record audio"
            case .recognizerIsUnavailable: return "Recognizer is unavailable"
            }
        }
    }
    
    @MainActor var speechRecognitionResult: SFSpeechRecognitionResult?
    @MainActor var transcriptionFinished: Bool = false
    @MainActor var transcriptionSuccessful: Bool = false
    @MainActor var errorMessage: String = ""
    var startTranscriptionTimestamp: Date?

    private var audioEngine: AVAudioEngine?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var recognizer: SFSpeechRecognizer?
    private var shouldReportPartialResults: Bool
    private var callback: ((SFSpeechRecognitionResult, Int) -> Void)?
    @MainActor private var callbackNewContentStartIndex: Int = 0
    
    /**
     Initializes a new speech recognizer. If this is the first time you've used the class, it
     requests access to the speech recognizer and the microphone.
     */
    init(shouldReportPartialResults: Bool, callback: ((SFSpeechRecognitionResult, Int) -> Void)?) {
        self.shouldReportPartialResults = shouldReportPartialResults
        self.callback = callback
    }
    
    // Starts recognition fed by external CMSampleBuffers (e.g. from ARKit) instead of AVAudioEngine.
    // Use appendAudioSampleBuffer(_:) to feed audio. Does not touch the AVAudioSession.
    @MainActor func startTranscribingWithExternalAudio() {
        speechRecognitionResult = nil
        transcriptionFinished = false
        transcriptionSuccessful = false
        errorMessage = ""
        callbackNewContentStartIndex = 0
        Task {
            await resetForExternalAudio()
            await transcribeWithExternalAudio()
        }
    }

    func appendAudioSampleBuffer(_ sampleBuffer: CMSampleBuffer) {
        request?.appendAudioSampleBuffer(sampleBuffer)
    }

    @MainActor func startTranscribing() {
        speechRecognitionResult = nil
        transcriptionFinished = false
        transcriptionSuccessful = false
        errorMessage = ""
        callbackNewContentStartIndex = 0
        Task {
            await reset()
            await transcribe()
        }
    }
    
//    @MainActor func resetTranscript() {
//        Task {
//            await reset()
//        }
//    }
    
//    @MainActor func stopTranscribing() {
//        Task {
//            await reset()
//        }
//    }
    
    @MainActor func finishTranscribing() async {
        // Wait for speechRecognitionResult to be set
        await finish() // Now finish transcribing
        
        while !transcriptionFinished {
            try? await Task.sleep(nanoseconds: 100_000_000) // Sleep for 100ms # TODO: this might not be necessary now with the new callback function feature, however we also need to update that callback to also support errors for failure case
            // this is incredibly hacky...
        }
    }
    
    /**
     Begin transcribing audio.
     
     Creates a `SFSpeechRecognitionTask` that transcribes speech to text until you call `stopTranscribing()`.
     The resulting transcription is continuously written to the published `transcript` property.
     */
    private func transcribe() {
        guard let recognizer, recognizer.isAvailable else {
            self.transcribe(RecognizerError.recognizerIsUnavailable)
            return
        }
        do {
            let (audioEngine, request) = try prepareEngine()
            self.startTranscriptionTimestamp = Date()
            self.audioEngine = audioEngine
            self.request = request
            self.task = recognizer.recognitionTask(with: request, resultHandler: { [weak self] result, error in
                self?.recognitionHandler(audioEngine: audioEngine, result: result, error: error)
            })
        } catch {
            self.reset()
            self.transcribe(error)
        }
    }
    
    /// Reset the speech recognizer.
    private func reset() {
        task?.cancel()
        audioEngine?.stop()
        request?.endAudio()
        audioEngine = nil
        request = nil
        task = nil
        
        let audioSession = AVAudioSession.sharedInstance()
        try? audioSession.setActive(false, options: .notifyOthersOnDeactivation)
        
        
        recognizer = SFSpeechRecognizer()
        guard recognizer != nil else {
            transcribe(RecognizerError.nilRecognizer)
            return
        }
        
        Task {
            do {
                guard await SFSpeechRecognizer.hasAuthorizationToRecognize() else {
                    throw RecognizerError.notAuthorizedToRecognize
                }
                guard await AVAudioSession.sharedInstance().hasPermissionToRecord() else {
                    throw RecognizerError.notPermittedToRecord
                }
            } catch {
                transcribe(error)
            }
        }
    }
    
    private func resetForExternalAudio() {
        task?.cancel()
        request?.endAudio()
        request = nil
        task = nil

        recognizer = SFSpeechRecognizer()
        guard recognizer != nil else {
            transcribe(RecognizerError.nilRecognizer)
            return
        }

        Task {
            do {
                guard await SFSpeechRecognizer.hasAuthorizationToRecognize() else {
                    throw RecognizerError.notAuthorizedToRecognize
                }
            } catch {
                transcribe(error)
            }
        }
    }

    private func transcribeWithExternalAudio() {
        guard let recognizer, recognizer.isAvailable else {
            self.transcribe(RecognizerError.recognizerIsUnavailable)
            return
        }
        self.startTranscriptionTimestamp = Date()
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = shouldReportPartialResults
        self.request = request
        self.task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            self?.recognitionHandlerExternal(result: result, error: error)
        }
    }

    nonisolated private func recognitionHandlerExternal(result: SFSpeechRecognitionResult?, error: Error?) {
        if let error {
            transcribe(error)
            return
        }
        if let result {
            transcribe(result)
        }
    }

    private func finish() async {
        task?.finish()
        audioEngine?.stop()
        request?.endAudio()
        audioEngine = nil
        request = nil
        task = nil
    }
    
    private func prepareEngine() throws -> (AVAudioEngine, SFSpeechAudioBufferRecognitionRequest) {
        let audioEngine = AVAudioEngine()
        
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = shouldReportPartialResults
        // I found that setting to false results in having the correct timestmps on the segments, whereas setting this to true does not report the correct timestamps, but does let you get live results.
        
        let audioSession = AVAudioSession.sharedInstance()
        try audioSession.setCategory(.record, mode: .measurement, options: .duckOthers)
        try audioSession.setActive(true, options: .notifyOthersOnDeactivation)
        let inputNode = audioEngine.inputNode
        
        let recordingFormat = inputNode.outputFormat(forBus: 0)
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { (buffer: AVAudioPCMBuffer, when: AVAudioTime) in
            request.append(buffer)
        }
        audioEngine.prepare()
        try audioEngine.start()
        
        return (audioEngine, request)
    }
    
    nonisolated private func recognitionHandler(audioEngine: AVAudioEngine, result: SFSpeechRecognitionResult?, error: Error?) {
        let receivedFinalResult = result?.isFinal ?? false
        let receivedError = error != nil
        
        if receivedFinalResult || receivedError {
            audioEngine.stop()
            audioEngine.inputNode.removeTap(onBus: 0)
        }
        
        if receivedError {
            transcribe(error!)
            return
        }
        
        // FIX: Call transcribe for ALL results (both partial and final)
        if let result = result {
            transcribe(result)
        }
    }
    
    
    nonisolated private func transcribe(_ speechRecognitionResult: SFSpeechRecognitionResult?) {
        guard let speechRecognitionResult = speechRecognitionResult else {
            return
        }
        
        Task { @MainActor in
            self.speechRecognitionResult = speechRecognitionResult
            
            // Call callback for both partial and final results
            if let callback = await callback {
                let segmentCount = speechRecognitionResult.bestTranscription.segments.count
                
                if callbackNewContentStartIndex < segmentCount {
                    callback(speechRecognitionResult, callbackNewContentStartIndex)
                    callbackNewContentStartIndex = segmentCount
                }
            }
            
            // Only mark as finished for final results
            if speechRecognitionResult.isFinal {
                self.transcriptionSuccessful = true
                self.transcriptionFinished = true
            }
        }
    }
    
    nonisolated private func transcribe(_ error: Error) {
        var errorMessage = ""
        if let error = error as? RecognizerError {
            errorMessage += error.message
        } else {
            errorMessage += error.localizedDescription
        }
        Task { @MainActor [errorMessage] in
            self.errorMessage = errorMessage
            self.transcriptionSuccessful = false
            self.transcriptionFinished = true
        }
    }
}

extension SFSpeechRecognizer {
    static func hasAuthorizationToRecognize() async -> Bool {
        await withCheckedContinuation { continuation in
            requestAuthorization { status in
                continuation.resume(returning: status == .authorized)
            }
        }
    }
}

extension AVAudioSession {
    func hasPermissionToRecord() async -> Bool {
        await withCheckedContinuation { continuation in
            requestRecordPermission { authorized in
                continuation.resume(returning: authorized)
            }
        }
    }
}
