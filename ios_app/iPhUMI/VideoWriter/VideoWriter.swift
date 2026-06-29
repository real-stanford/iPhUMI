//
//  VideoWriter.swift
//  iPhUMI
//
//  Created by Austin Patel on 12/19/24.
//  Copyright © 2024 Apple. All rights reserved.
//

import AVFoundation

class VideoWriter {
    private var assetWriter: AVAssetWriter!
    private var videoAssetWriterInput: AVAssetWriterInput!
    private var audioAssetWriterInput: AVAssetWriterInput?
    private var pixelBufferAdaptor: AVAssetWriterInputPixelBufferAdaptor!
    private var isWritingStarted = false
    
    init(outputURL: URL, width: Int, height: Int, includeAudio: Bool) throws {
        // Initialize AVAssetWriter
        assetWriter = try AVAssetWriter(outputURL: outputURL, fileType: .mov)
        
        // Define video settings
        let videoOutputSettings: [String: Any] = [
            AVVideoCodecKey: AVVideoCodecType.h264,
            AVVideoWidthKey: width,
            AVVideoHeightKey: height
        ]
        
        // Create AVAssetWriterInput for video
        videoAssetWriterInput = AVAssetWriterInput(mediaType: .video, outputSettings: videoOutputSettings)
        videoAssetWriterInput.expectsMediaDataInRealTime = true
        assetWriter.add(videoAssetWriterInput)
        
        // Create Pixel Buffer Adaptor for video
        pixelBufferAdaptor = AVAssetWriterInputPixelBufferAdaptor(
            assetWriterInput: videoAssetWriterInput,
            sourcePixelBufferAttributes: [
                kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB,
                kCVPixelBufferWidthKey as String: width,
                kCVPixelBufferHeightKey as String: height
            ]
        )
        
        // If audio is included, set up audio input
        if includeAudio {
            let audioOutputSettings: [String: Any] = [
                AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
                AVSampleRateKey: 48000,
                AVNumberOfChannelsKey: 2
            ]
            
            audioAssetWriterInput = AVAssetWriterInput(mediaType: .audio, outputSettings: audioOutputSettings)
            audioAssetWriterInput?.expectsMediaDataInRealTime = true
            if let audioInput = audioAssetWriterInput {
                assetWriter.add(audioInput)
            }
        }
    }
    
    func startWriting(at time: CMTime) {
        assetWriter.startWriting()
        assetWriter.startSession(atSourceTime: time)
        isWritingStarted = true
    }
    
    func appendVideo(pixelBuffer: CVPixelBuffer, at time: CMTime) {
        guard isWritingStarted, videoAssetWriterInput.isReadyForMoreMediaData else { return }
        pixelBufferAdaptor.append(pixelBuffer, withPresentationTime: time)
    }
    
    func appendAudio(sampleBuffer: CMSampleBuffer) {
        // Only append audio if audio input exists and writing has started
        let timestamp = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        if let audioInput = audioAssetWriterInput, isWritingStarted, audioInput.isReadyForMoreMediaData {
            audioInput.append(sampleBuffer)
        }
    }
    
    func finishWriting(completion: @escaping () -> Void) {
        videoAssetWriterInput.markAsFinished()
        audioAssetWriterInput?.markAsFinished()
        assetWriter.finishWriting {
            completion()
        }
    }
}
